from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from camo.db.models import Character
from camo.models.adapter import ModelAdapter, ProviderConfigurationError
from camo.prompts import load_json_schema, render_prompt

logger = logging.getLogger(__name__)

DEFAULT_RULES = {
    ("meta", "break_character"): {"ai", "prompt", "system", "language model", "语言模型", "提示词"},
    ("meta", "meta_knowledge"): {"原作", "作者", "读者", "剧情需要", "设定", "剧本"},
    ("setting", "out_of_setting"): {"互联网", "手机", "wifi", "email", "程序员", "app"},
    ("plot", "future_spoiler"): set(),
}


async def run_consistency_check(
    *,
    model_adapter: ModelAdapter,
    character: Character,
    anchor_state: dict[str, Any],
    fixed_identity: dict[str, Any],
    current_stage: dict[str, Any],
    retrieval_summary: dict[str, Any],
    user_input: dict[str, Any],
    runtime_response: dict[str, Any],
    rules_root: Path,
) -> dict[str, Any]:
    reply_text = str(runtime_response.get("content", "")).strip()
    rule_issues, rule_trace = run_rule_engine(
        character=character,
        anchor_state=anchor_state,
        current_stage=current_stage,
        retrieval_summary=retrieval_summary,
        reply_text=reply_text,
        rules_root=rules_root,
    )
    judge_issues = await run_judge_check(
        model_adapter=model_adapter,
        anchor_state=anchor_state,
        fixed_identity=fixed_identity,
        current_stage=current_stage,
        retrieval_summary=retrieval_summary,
        user_input=user_input,
        runtime_response=runtime_response,
    )

    issues = [*rule_issues, *judge_issues]
    action = resolve_action(issues)
    return {
        "passed": not any(not _is_observational_issue(item) for item in issues),
        "action": action,
        "issues": issues,
        "rule_trace": rule_trace,
    }


def run_rule_engine(
    *,
    character: Character,
    anchor_state: dict[str, Any],
    current_stage: dict[str, Any],
    retrieval_summary: dict[str, Any],
    reply_text: str,
    rules_root: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    lowered = reply_text.lower()
    issues: list[dict[str, Any]] = []
    trace: dict[str, Any] = {"matched": [], "checked": []}

    for namespace, tag in DEFAULT_RULES:
        terms = load_rule_terms(rules_root, namespace=namespace, tag=tag) | DEFAULT_RULES[(namespace, tag)]
        trace["checked"].append(f"{namespace}.{tag}")
        matched = sorted(term for term in terms if term and term.lower() in lowered)
        if not matched:
            continue
        trace["matched"].append({"rule": f"{namespace}.{tag}", "terms": matched})
        issues.append(
            {
                "dimension": _dimension_for_rule(namespace, tag),
                "severity": "high" if namespace in {"meta", "plot"} else "medium",
                "description": f"命中了规则 {namespace}.{tag}: {', '.join(matched[:5])}",
                "suggestion": "请保持角色口吻并收回越界表达。",
                "evidence_rule_id": f"{namespace}.{tag}",
            }
        )

    future_terms = _build_future_terms(anchor_state, current_stage, retrieval_summary)
    matched_future = sorted(term for term in future_terms if term and term.lower() in lowered)
    if matched_future:
        trace["matched"].append({"rule": "plot.future_spoiler", "terms": matched_future})
        issues.append(
            {
                "dimension": "timeline_consistency",
                "severity": "high",
                "description": f"回复疑似泄露锚点后的信息: {', '.join(matched_future[:5])}",
                "suggestion": "改为当前阶段可知的保守回答。",
                "evidence_rule_id": "plot.future_spoiler",
            }
        )

    forbidden = (
        character.character_core.get("constraint_profile", {}).get("forbidden_behaviors", [])
        if character.character_core
        else []
    )
    for item in forbidden:
        namespace = str(item.get("namespace", "")).strip()
        tag = str(item.get("tag", "")).strip()
        description = str(item.get("description", "")).strip()
        if not namespace or not tag:
            continue
        trace["checked"].append(f"{namespace}.{tag}")
        keywords = {
            piece.strip().lower()
            for piece in description.replace("，", ",").replace("。", ",").split(",")
            if piece.strip()
        }
        matched = sorted(term for term in keywords if term in lowered)
        if not matched:
            continue
        trace["matched"].append({"rule": f"{namespace}.{tag}", "terms": matched})
        issues.append(
            {
                "dimension": "constraint_consistency",
                "severity": "medium",
                "description": f"回复可能碰到自定义约束 {namespace}.{tag}",
                "suggestion": "改写为更克制、更符合边界的说法。",
                "evidence_rule_id": f"{namespace}.{tag}",
            }
        )

    return issues, trace


async def run_judge_check(
    *,
    model_adapter: ModelAdapter,
    anchor_state: dict[str, Any],
    fixed_identity: dict[str, Any],
    current_stage: dict[str, Any],
    retrieval_summary: dict[str, Any],
    user_input: dict[str, Any],
    runtime_response: dict[str, Any],
) -> list[dict[str, Any]]:
    schema = load_json_schema("schemas/consistency_result.json")
    prompt = render_prompt(
        "runtime/consistency_check.jinja2",
        anchor_state=anchor_state,
        fixed_identity_summary=fixed_identity,
        stage_summary=current_stage,
        retrieval_summary=retrieval_summary,
        user_input=user_input,
        runtime_response=runtime_response,
    )
    try:
        result = await model_adapter.complete(
            messages=[
                {"role": "system", "content": "你是角色一致性校验器。"},
                {"role": "user", "content": prompt},
            ],
            task="judge",
            json_schema=schema,
        )
    except ProviderConfigurationError as exc:
        logger.warning("Judge LLM unavailable because of provider configuration: %s", exc)
        return [_build_judge_unavailable_issue()]
    except Exception as exc:
        logger.exception("Judge LLM failed during consistency check")
        return [_build_judge_unavailable_issue(detail=str(exc))]

    structured = result.structured or {}
    issues = structured.get("issues", [])
    normalized: list[dict[str, Any]] = []
    for item in issues:
        if not isinstance(item, dict):
            continue
        severity = str(item.get("severity", "")).strip()
        if severity not in {"low", "medium", "high"}:
            severity = "medium"
        normalized.append(
            {
                "dimension": str(item.get("dimension", "")).strip() or "persona_consistency",
                "severity": severity,
                "description": str(item.get("description", "")).strip(),
                "suggestion": str(item.get("suggestion", "")).strip() or "请收敛到当前阶段可知范围内。",
                "evidence_rule_id": str(item.get("evidence_rule_id", "")).strip() or None,
            }
        )
    return [item for item in normalized if item["description"]]


def resolve_action(issues: list[dict[str, Any]]) -> str:
    if not issues:
        return "accept"
    if any(item.get("severity") == "high" for item in issues):
        return "regenerate"
    if any(item.get("severity") == "medium" for item in issues):
        return "warn"
    return "accept"


def load_rule_terms(rules_root: Path, *, namespace: str, tag: str) -> set[str]:
    path = rules_root / namespace / f"{tag}.txt"
    if not path.exists():
        return set()
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }


def _build_future_terms(
    anchor_state: dict[str, Any],
    current_stage: dict[str, Any],
    retrieval_summary: dict[str, Any],
) -> set[str]:
    future_terms = {
        str(item).strip().lower()
        for item in current_stage.get("unknown_facts", [])
        if str(item).strip()
    }
    cutoff = int(anchor_state.get("resolved_timeline_pos", 1))
    for event in retrieval_summary.get("future_events", []):
        if int(event.get("timeline_pos", 0) or 0) > cutoff:
            title = str(event.get("title", "")).strip().lower()
            if title:
                future_terms.add(title)
    return future_terms


def _dimension_for_rule(namespace: str, tag: str) -> str:
    if namespace == "plot":
        return "timeline_consistency"
    if namespace == "setting":
        return "knowledge_boundary"
    if namespace == "meta":
        return "constraint_consistency"
    return "constraint_consistency"


def _build_judge_unavailable_issue(*, detail: str | None = None) -> dict[str, Any]:
    description = "Judge LLM unavailable, skipped semantic consistency check"
    if detail:
        description = f"{description}: {detail}"
    return {
        "dimension": "judge_availability",
        "severity": "low",
        "description": description,
        "suggestion": "请结合规则引擎结果审阅本轮回复。",
        "evidence_rule_id": "system.judge_unavailable",
    }


def _is_observational_issue(item: dict[str, Any]) -> bool:
    return str(item.get("evidence_rule_id", "")).strip() == "system.judge_unavailable"
