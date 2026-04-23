from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from camo.db.models import Character
from camo.db.queries.texts import list_project_segment_records


def list_character_anchors(character: Character) -> list[dict[str, Any]]:
    snapshots = character.character_facet.get("temporal_snapshots", []) if character.character_facet else []
    return [deepcopy(item) for item in snapshots if isinstance(item, dict)]


async def resolve_default_anchor(
    session: AsyncSession,
    *,
    project_id: str,
    character: Character,
) -> tuple[dict[str, Any], dict[str, Any]]:
    snapshots = list_character_anchors(character)
    default_snapshot_id = (
        character.character_facet.get("extraction_meta", {}).get("default_snapshot_id")
        if character.character_facet
        else None
    )
    if default_snapshot_id:
        for snapshot in snapshots:
            if snapshot.get("snapshot_id") == default_snapshot_id:
                cutoff = int(snapshot.get("activation_range", {}).get("end_timeline_pos", 1))
                return (
                    _build_anchor_state_from_snapshot(snapshot, cutoff),
                    {"mode": "default_snapshot", "snapshot_id": default_snapshot_id},
                )

    if snapshots:
        snapshot = sorted(
            snapshots,
            key=lambda item: item.get("activation_range", {}).get("end_timeline_pos", 0),
        )[-1]
        cutoff = int(snapshot.get("activation_range", {}).get("end_timeline_pos", 1))
        return (
            _build_anchor_state_from_snapshot(snapshot, cutoff),
            {"mode": "latest_snapshot", "snapshot_id": snapshot.get("snapshot_id")},
        )

    records = await list_project_segment_records(session, project_id)
    max_timeline = max((_segment_timeline_pos(item.segment) for item in records), default=1)
    return (
        {
            "anchor_mode": "source_progress",
            "source_type": "timeline_pos",
            "cutoff_value": max_timeline,
            "resolved_timeline_pos": max_timeline,
            "snapshot_id": None,
            "display_label": f"Timeline {max_timeline}",
            "summary": "仅使用全局画像，无阶段快照命中。",
        },
        {"mode": "timeline_fallback", "resolved_timeline_pos": max_timeline},
    )


async def resolve_anchor(
    session: AsyncSession,
    *,
    project_id: str,
    character: Character,
    anchor_input: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not anchor_input:
        return await resolve_default_anchor(session, project_id=project_id, character=character)

    anchor_mode = str(anchor_input.get("anchor_mode", "source_progress")).strip() or "source_progress"
    if anchor_mode == "snapshot":
        snapshot_id = str(anchor_input.get("snapshot_id", "")).strip()
        snapshot = _load_snapshot_by_id(character, snapshot_id)
        if snapshot is None:
            return await resolve_default_anchor(session, project_id=project_id, character=character)
        cutoff = int(snapshot.get("activation_range", {}).get("end_timeline_pos", 1))
        return (
            _build_anchor_state_from_snapshot(snapshot, cutoff),
            {"mode": "snapshot", "snapshot_id": snapshot_id},
        )

    source_type = str(anchor_input.get("source_type", "timeline_pos")).strip() or "timeline_pos"
    cutoff_value = anchor_input.get("cutoff_value")
    resolved_timeline_pos, trace = await map_source_progress_to_timeline_pos(
        session,
        project_id=project_id,
        source_type=source_type,
        cutoff_value=cutoff_value,
    )
    snapshot = find_best_snapshot(character, resolved_timeline_pos)
    display_label = snapshot.get("display_hint", {}).get("primary") if snapshot else None
    summary = snapshot.get("stage_summary") if snapshot else None
    return (
        {
            "anchor_mode": "source_progress",
            "source_type": source_type,
            "cutoff_value": cutoff_value,
            "resolved_timeline_pos": resolved_timeline_pos,
            "snapshot_id": snapshot.get("snapshot_id") if snapshot else None,
            "display_label": display_label or f"{source_type}:{cutoff_value}",
            "summary": summary or "未命中阶段快照，退回全局画像。",
        },
        {
            "mode": "source_progress",
            "source_type": source_type,
            "cutoff_value": cutoff_value,
            "resolved_timeline_pos": resolved_timeline_pos,
            "snapshot_id": snapshot.get("snapshot_id") if snapshot else None,
            "mapping_trace": trace,
        },
    )


def find_best_snapshot(character: Character, cutoff_timeline_pos: int) -> dict[str, Any] | None:
    snapshots = list_character_anchors(character)
    containing = [
        item
        for item in snapshots
        if _range_start(item) <= cutoff_timeline_pos <= _range_end(item)
    ]
    if containing:
        return sorted(containing, key=_range_start)[-1]

    prior = [item for item in snapshots if _range_end(item) <= cutoff_timeline_pos]
    if prior:
        return sorted(prior, key=_range_end)[-1]
    return None


def load_active_snapshot(character: Character, cutoff_timeline_pos: int) -> dict[str, Any] | None:
    snapshot = find_best_snapshot(character, cutoff_timeline_pos)
    return deepcopy(snapshot) if snapshot is not None else None


async def map_source_progress_to_timeline_pos(
    session: AsyncSession,
    *,
    project_id: str,
    source_type: str,
    cutoff_value: Any,
) -> tuple[int, dict[str, Any]]:
    records = await list_project_segment_records(session, project_id)
    if not records:
        return 1, {"records": 0, "source_type": source_type}

    if source_type == "timeline_pos":
        resolved = _coerce_positive_int(cutoff_value, default=_segment_timeline_pos(records[-1].segment))
        return resolved, {"records": len(records), "source_type": source_type, "matched": resolved}

    matched_positions: list[int] = []
    for record in records:
        metadata = record.segment.segment_metadata or {}
        progress = metadata.get("source_progress", {}) or {}
        timeline_pos = _segment_timeline_pos(record.segment)
        if _matches_source_progress(progress, source_type=source_type, cutoff_value=cutoff_value):
            matched_positions.append(timeline_pos)

    if matched_positions:
        resolved = max(matched_positions)
    else:
        resolved = _segment_timeline_pos(records[0].segment)
    return (
        resolved,
        {
            "records": len(records),
            "source_type": source_type,
            "cutoff_value": cutoff_value,
            "matched_positions": matched_positions[-5:],
        },
    )


def _matches_source_progress(progress: dict[str, Any], *, source_type: str, cutoff_value: Any) -> bool:
    if source_type == "chapter":
        expected = _coerce_positive_int(cutoff_value, default=0)
        return _coerce_positive_int(progress.get("chapter_index"), default=0) <= expected
    if source_type == "page":
        expected = _coerce_positive_int(cutoff_value, default=0)
        return _coerce_positive_int(progress.get("page_end"), default=0) <= expected
    if source_type == "message_index":
        expected = _coerce_positive_int(cutoff_value, default=0)
        return _coerce_positive_int(progress.get("message_index_end"), default=0) <= expected
    if source_type == "timestamp":
        raw = str(progress.get("timestamp_end") or progress.get("timestamp_start") or "").strip()
        if not raw:
            return False
        try:
            progress_ts = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            cutoff_ts = datetime.fromisoformat(str(cutoff_value).replace("Z", "+00:00"))
        except ValueError:
            return False
        return progress_ts <= cutoff_ts
    return False


def _build_anchor_state_from_snapshot(snapshot: dict[str, Any], cutoff: int) -> dict[str, Any]:
    display_hint = snapshot.get("display_hint", {}) if isinstance(snapshot.get("display_hint"), dict) else {}
    return {
        "anchor_mode": "snapshot",
        "source_type": None,
        "cutoff_value": snapshot.get("snapshot_id"),
        "resolved_timeline_pos": cutoff,
        "snapshot_id": snapshot.get("snapshot_id"),
        "display_label": str(display_hint.get("primary", "")).strip() or str(snapshot.get("period_label", "")).strip(),
        "summary": str(snapshot.get("stage_summary", "")).strip() or str(snapshot.get("notes", "")).strip(),
    }


def _load_snapshot_by_id(character: Character, snapshot_id: str) -> dict[str, Any] | None:
    for snapshot in list_character_anchors(character):
        if snapshot.get("snapshot_id") == snapshot_id:
            return deepcopy(snapshot)
    return None


def _range_start(snapshot: dict[str, Any]) -> int:
    return _coerce_positive_int(snapshot.get("activation_range", {}).get("start_timeline_pos"), default=1)


def _range_end(snapshot: dict[str, Any]) -> int:
    return _coerce_positive_int(snapshot.get("activation_range", {}).get("end_timeline_pos"), default=_range_start(snapshot))


def _segment_timeline_pos(segment) -> int:
    metadata = getattr(segment, "segment_metadata", {}) or {}
    return _coerce_positive_int(metadata.get("timeline_pos"), default=segment.position)


def _coerce_positive_int(value: Any, *, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, number)
