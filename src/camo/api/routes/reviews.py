from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from camo.api.deps import get_db_session
from camo.api.rate_limit import read_rate_limit, write_rate_limit
from camo.core.patching import build_structured_diff, deep_merge
from camo.core.schemas import ReviewResponse, ReviewSubmitRequest
from camo.db.queries.characters import get_character_by_id, save_character_assets
from camo.db.queries.reviews import get_review, list_reviews, save_review
from camo.db.queries.versions import create_character_version
from camo.tasks.modeling import build_character_snapshot

router = APIRouter(tags=["reviews"])


@router.get("/reviews", response_model=list[ReviewResponse], dependencies=[read_rate_limit])
async def list_reviews_endpoint(
    status_filter: str | None = None,
    session: AsyncSession = Depends(get_db_session),
) -> list[ReviewResponse]:
    reviews = await list_reviews(session, status=status_filter)
    return [_to_review_response(item) for item in reviews]


@router.post("/reviews/{review_id}", response_model=ReviewResponse, dependencies=[write_rate_limit])
async def submit_review_endpoint(
    review_id: str,
    payload: ReviewSubmitRequest,
    session: AsyncSession = Depends(get_db_session),
) -> ReviewResponse:
    review = await get_review(session, review_id=review_id)
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found")

    diff = review.diff
    if review.target_type == "character_asset":
        character = await get_character_by_id(session, review.target_id)
        if character is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character not found")
        before = build_character_snapshot(character)
        index_patch = payload.character_patch.get("character_index_patch", {})
        core_patch = payload.character_patch.get("character_core_patch", {})
        facet_patch = payload.character_patch.get("character_facet_patch", {})
        status_patch = payload.character_patch.get("status")
        await save_character_assets(
            session,
            character,
            character_index=deep_merge(character.character_index, index_patch) if index_patch else character.character_index,
            character_core=deep_merge(character.character_core or {}, core_patch) if core_patch else character.character_core,
            character_facet=deep_merge(character.character_facet or {}, facet_patch) if facet_patch else character.character_facet,
            status=status_patch or ("published" if payload.status == "approved" else character.status),
        )
        after = build_character_snapshot(character)
        diff = build_structured_diff(before, after)
        await create_character_version(
            session,
            character_id=character.character_id,
            snapshot=after,
            diff=diff,
            created_by=payload.reviewer,
            note=payload.note or "Review update",
        )

    updated = await save_review(
        session,
        review,
        diff=diff,
        reviewer=payload.reviewer,
        status=payload.status,
        note=payload.note,
        reviewed_at=datetime.now(timezone.utc),
    )
    return _to_review_response(updated)


def _to_review_response(review) -> ReviewResponse:
    return ReviewResponse(
        review_id=review.review_id,
        target_type=review.target_type,
        target_id=review.target_id,
        diff=review.diff,
        reviewer=review.reviewer,
        status=review.status,
        note=review.note,
        reviewed_at=review.reviewed_at,
        created_at=review.created_at,
    )
