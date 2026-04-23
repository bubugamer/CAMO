from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from camo.db.queries.characters import upsert_characters
from camo.db.queries.texts import list_text_segments_for_source
from camo.models.adapter import ModelAdapter
from camo.prompts import load_json_schema, render_prompt

SCHEMA_VERSION = "0.2"


@dataclass(frozen=True)
class CharacterMention:
    name: str
    aliases: list[str]
    titles: list[str]
    identities: list[dict[str, str]]
    description: str
    character_type: str
    segment_id: str
    position: int


async def run_character_index(
    *,
    session: AsyncSession,
    model_adapter: ModelAdapter,
    project_id: str,
    source_id: str,
    source_type: str,
    segment_limit: int | None = None,
    concurrency: int = 5,
) -> tuple[list, int]:
    mentions, total_segments = await extract_mentions(
        session=session,
        model_adapter=model_adapter,
        source_id=source_id,
        source_type=source_type,
        segment_limit=segment_limit,
        concurrency=concurrency,
    )
    clusters = initial_cluster_mentions(mentions)
    candidate_pairs = build_disambiguation_candidates(clusters)
    decisions = await disambiguate_cluster_pairs(candidate_pairs, model_adapter)
    clusters = apply_disambiguation_decisions(clusters, decisions)
    payloads = finalize_character_index_payloads(clusters, total_segments=total_segments)
    stored = await upsert_characters(session, project_id, payloads)
    return stored, total_segments


async def extract_mentions(
    *,
    session: AsyncSession,
    model_adapter: ModelAdapter,
    source_id: str,
    source_type: str,
    segment_limit: int | None = None,
    concurrency: int = 5,
) -> tuple[list[CharacterMention], int]:
    segments = await list_text_segments_for_source(session, source_id, limit=segment_limit)
    schema = load_json_schema("schemas/character_index.json")
    semaphore = asyncio.Semaphore(concurrency)

    async def extract_segment(segment) -> list[CharacterMention]:
        async with semaphore:
            prompt = render_prompt(
                "extraction/character_index.jinja2",
                source_type=source_type,
                segment_id=segment.segment_id,
                chapter=segment.chapter,
                round_num=segment.round,
                content=segment.content,
            )
            result = await model_adapter.complete(
                messages=[
                    {
                        "role": "system",
                        "content": "你是严格的人物实体识别器，只返回结构化结果。",
                    },
                    {"role": "user", "content": prompt},
                ],
                task="extraction",
                json_schema=schema,
            )
            structured = result.structured or {"schema_version": SCHEMA_VERSION, "characters": []}
            mentions: list[CharacterMention] = []
            for character in structured.get("characters", []):
                name = character.get("name", "").strip()
                if not name:
                    continue
                mentions.append(
                    CharacterMention(
                        name=name,
                        aliases=_clean_text_list(character.get("aliases", [])),
                        titles=_clean_text_list(character.get("titles", [])),
                        identities=_clean_identity_list(character.get("identities", [])),
                        description=str(character.get("description", "")).strip(),
                        character_type=_clean_character_type(
                            character.get("character_type"),
                            fallback=_default_character_type(source_type),
                        ),
                        segment_id=segment.segment_id,
                        position=segment.position,
                    )
                )
            return mentions

    mention_groups = await asyncio.gather(*(extract_segment(segment) for segment in segments))
    mentions = [mention for group in mention_groups for mention in group]
    return mentions, len(segments)


def initial_cluster_mentions(mentions: list[CharacterMention]) -> list[dict[str, Any]]:
    clusters: list[dict[str, Any]] = []
    for mention in mentions:
        normalized_name = _normalize_text(mention.name)
        normalized_aliases = {_normalize_text(alias) for alias in mention.aliases if alias}
        mention_names = {value for value in {normalized_name, *normalized_aliases} if value}

        matched_cluster = next(
            (
                cluster
                for cluster in clusters
                if _should_merge_mention_into_cluster(
                    cluster,
                    mention=mention,
                    normalized_name=normalized_name,
                    mention_names=mention_names,
                )
            ),
            None,
        )

        if matched_cluster is None:
            matched_cluster = _new_cluster(mention)
            clusters.append(matched_cluster)
            continue

        _append_mention_to_cluster(matched_cluster, mention)

    return clusters


def build_disambiguation_candidates(clusters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for left_index, left in enumerate(clusters):
        for right_index in range(left_index + 1, len(clusters)):
            right = clusters[right_index]
            if not _should_consider_disambiguation(left, right):
                continue
            candidates.append(
                {
                    "left_index": left_index,
                    "right_index": right_index,
                    "left": _cluster_summary(left),
                    "right": _cluster_summary(right),
                }
            )
    return candidates


async def disambiguate_cluster_pairs(
    candidate_pairs: list[dict[str, Any]],
    model_adapter: ModelAdapter,
) -> list[dict[str, Any]]:
    if not candidate_pairs:
        return []

    schema = load_json_schema("schemas/character_disambiguation.json")
    decisions: list[dict[str, Any]] = []
    for candidate in candidate_pairs:
        prompt = render_prompt(
            "extraction/character_disambiguation.jinja2",
            left_cluster=candidate["left"],
            right_cluster=candidate["right"],
        )
        result = await model_adapter.complete(
            messages=[
                {
                    "role": "system",
                    "content": "你是严格的人物别名消歧器，只能根据提供的两组证据判断是否是同一角色。",
                },
                {"role": "user", "content": prompt},
            ],
            task="aggregation",
            json_schema=schema,
        )
        structured = result.structured or {}
        decisions.append(
            {
                "left_index": candidate["left_index"],
                "right_index": candidate["right_index"],
                "same_character": bool(structured.get("same_character", False)),
                "confidence": max(0.0, min(1.0, float(structured.get("confidence", 0.0) or 0.0))),
                "reason": str(structured.get("reason", "")).strip(),
            }
        )
    return decisions


def apply_disambiguation_decisions(
    clusters: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    parents = list(range(len(clusters)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left_index: int, right_index: int) -> None:
        left_root = find(left_index)
        right_root = find(right_index)
        if left_root == right_root:
            return
        parents[right_root] = left_root

    for decision in decisions:
        if decision["same_character"] and decision["confidence"] >= 0.6:
            union(decision["left_index"], decision["right_index"])

    merged: dict[int, dict[str, Any]] = {}
    for index, cluster in enumerate(clusters):
        root = find(index)
        if root not in merged:
            merged[root] = _clone_cluster(cluster)
            continue
        merged[root] = _merge_clusters(merged[root], cluster)

    return list(merged.values())


def finalize_character_index_payloads(
    clusters: list[dict[str, Any]],
    *,
    total_segments: int,
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for cluster in clusters:
        canonical_name = sorted(cluster["names"], key=lambda item: (len(item), item))[0]
        first_position, first_segment_id = min(cluster["positions"], key=lambda item: item[0])
        unique_segment_count = len(cluster["source_segments"])
        confidence = round(unique_segment_count / total_segments, 3) if total_segments else 0.0
        description = cluster["descriptions"][0] if cluster["descriptions"] else ""
        aliases = sorted(alias for alias in cluster["aliases"] if alias != canonical_name)
        payloads.append(
            {
                "character_id": f"char_{uuid4().hex[:12]}",
                "_sort_position": first_position,
                "character_index": {
                    "schema_version": SCHEMA_VERSION,
                    "character_type": cluster["character_type"],
                    "name": canonical_name,
                    "description": description,
                    "aliases": aliases,
                    "titles": sorted(cluster["titles"]),
                    "identities": sorted(
                        cluster["identities"].values(),
                        key=lambda item: (item["type"], item["value"]),
                    ),
                    "first_appearance": first_segment_id,
                    "confidence": confidence,
                    "source_segments": sorted(cluster["source_segments"]),
                },
            }
        )

    payloads.sort(key=lambda item: item["_sort_position"])
    for payload in payloads:
        payload.pop("_sort_position", None)
    return payloads


def _aggregate_mentions(
    *,
    mentions: list[CharacterMention],
    total_segments: int,
) -> list[dict[str, Any]]:
    return finalize_character_index_payloads(initial_cluster_mentions(mentions), total_segments=total_segments)


def _new_cluster(mention: CharacterMention) -> dict[str, Any]:
    cluster = {
        "normalized_names": set(),
        "primary_names": set(),
        "names": set(),
        "aliases": set(),
        "titles": set(),
        "identities": {},
        "descriptions": [],
        "character_type": mention.character_type or "unidentified_person",
        "source_segments": set(),
        "positions": [],
    }
    _append_mention_to_cluster(cluster, mention)
    return cluster


def _append_mention_to_cluster(cluster: dict[str, Any], mention: CharacterMention) -> None:
    mention_names = {mention.name, *mention.aliases}
    cluster["normalized_names"].update(_normalize_text(value) for value in mention_names if value)
    cluster["primary_names"].add(_normalize_text(mention.name))
    cluster["names"].add(mention.name)
    cluster["aliases"].update(alias for alias in mention.aliases if alias and alias != mention.name)
    cluster["titles"].update(title for title in mention.titles if title)
    for identity in mention.identities:
        identity_type = identity.get("type", "").strip()
        identity_value = identity.get("value", "").strip()
        if identity_type and identity_value:
            cluster["identities"][(identity_type, identity_value)] = {
                "type": identity_type,
                "value": identity_value,
            }
    if mention.description:
        cluster["descriptions"].append(mention.description)
    cluster["source_segments"].add(mention.segment_id)
    cluster["positions"].append((mention.position, mention.segment_id))


def _should_merge_mention_into_cluster(
    cluster: dict[str, Any],
    *,
    mention: CharacterMention,
    normalized_name: str,
    mention_names: set[str],
) -> bool:
    cluster_names = cluster["normalized_names"]
    shared_names = mention_names & cluster_names
    alias_cross_reference = _is_alias_cross_reference(cluster, mention)
    shared_titles = {
        _normalize_text(title)
        for title in mention.titles
        if title and _normalize_text(title) in {_normalize_text(item) for item in cluster["titles"]}
    }
    shared_identities = {
        (identity.get("type", "").strip(), identity.get("value", "").strip())
        for identity in mention.identities
        if identity.get("type") and identity.get("value")
    } & set(cluster["identities"])

    if not shared_names and not alias_cross_reference:
        return False

    # Only sharing the bare canonical name is too weak and can collapse same-name different people.
    if shared_names == {normalized_name} and normalized_name in cluster["primary_names"]:
        return bool(shared_titles or shared_identities or alias_cross_reference)

    return bool(shared_names or alias_cross_reference)


def _is_alias_cross_reference(cluster: dict[str, Any], mention: CharacterMention) -> bool:
    normalized_aliases = {_normalize_text(alias) for alias in mention.aliases if alias}
    normalized_cluster_aliases = {_normalize_text(alias) for alias in cluster["aliases"]}
    normalized_mention_name = _normalize_text(mention.name)
    return bool(
        normalized_aliases & cluster["normalized_names"]
        or normalized_cluster_aliases & {normalized_mention_name}
    )


def _should_consider_disambiguation(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_names = left["normalized_names"]
    right_names = right["normalized_names"]
    if left_names & right_names:
        return True

    left_titles = {_normalize_text(item) for item in left["titles"]}
    right_titles = {_normalize_text(item) for item in right["titles"]}
    if left_titles & right_titles:
        return True

    left_identities = {value[1].lower() for value in left["identities"]}
    right_identities = {value[1].lower() for value in right["identities"]}
    if left_identities & right_identities:
        return True

    left_first = min(position for position, _ in left["positions"])
    right_first = min(position for position, _ in right["positions"])
    return abs(left_first - right_first) <= 1


def _cluster_summary(cluster: dict[str, Any]) -> dict[str, Any]:
    first_position, first_segment_id = min(cluster["positions"], key=lambda item: item[0])
    return {
        "names": sorted(cluster["names"]),
        "aliases": sorted(cluster["aliases"]),
        "titles": sorted(cluster["titles"]),
        "identities": sorted(
            cluster["identities"].values(),
            key=lambda item: (item["type"], item["value"]),
        ),
        "descriptions": cluster["descriptions"][:4],
        "source_segments": sorted(cluster["source_segments"]),
        "first_position": first_position,
        "first_segment_id": first_segment_id,
        "character_type": cluster["character_type"],
    }


def _clone_cluster(cluster: dict[str, Any]) -> dict[str, Any]:
    return {
        "normalized_names": set(cluster["normalized_names"]),
        "primary_names": set(cluster["primary_names"]),
        "names": set(cluster["names"]),
        "aliases": set(cluster["aliases"]),
        "titles": set(cluster["titles"]),
        "identities": dict(cluster["identities"]),
        "descriptions": list(cluster["descriptions"]),
        "character_type": cluster["character_type"],
        "source_segments": set(cluster["source_segments"]),
        "positions": list(cluster["positions"]),
    }


def _merge_clusters(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    merged = _clone_cluster(left)
    merged["normalized_names"].update(right["normalized_names"])
    merged["primary_names"].update(right["primary_names"])
    merged["names"].update(right["names"])
    merged["aliases"].update(right["aliases"])
    merged["titles"].update(right["titles"])
    merged["identities"].update(right["identities"])
    merged["descriptions"].extend(right["descriptions"])
    merged["source_segments"].update(right["source_segments"])
    merged["positions"].extend(right["positions"])
    return merged


def _normalize_text(value: str) -> str:
    return value.strip().lower()


def _clean_text_list(values: list[Any]) -> list[str]:
    cleaned = []
    for value in values:
        text = str(value).strip()
        if text:
            cleaned.append(text)
    return cleaned


def _clean_identity_list(values: Any) -> list[dict[str, str]]:
    if not isinstance(values, list):
        return []
    cleaned: list[dict[str, str]] = []
    for value in values:
        if not isinstance(value, dict):
            continue
        identity_type = str(value.get("type", "")).strip()
        identity_value = str(value.get("value", "")).strip()
        if identity_type and identity_value:
            cleaned.append({"type": identity_type, "value": identity_value})
    return cleaned


def _default_character_type(source_type: str) -> str:
    if source_type == "novel":
        return "fictional_person"
    if source_type == "chat":
        return "real_person"
    return "unidentified_person"


def _clean_character_type(value: Any, *, fallback: str) -> str:
    text = str(value).strip()
    return text or fallback
