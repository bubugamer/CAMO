from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from camo.db.models import LLMCallLog
from camo.models.adapter import LLMCallLogEntry


async def persist_llm_log_entry(session: AsyncSession, entry: LLMCallLogEntry) -> None:
    session.add(
        LLMCallLog(
            task=entry.task,
            provider=entry.provider,
            model=entry.model,
            input_tokens=entry.input_tokens,
            output_tokens=entry.output_tokens,
            latency_ms=entry.latency_ms,
            status=entry.status,
            error_message=entry.error_message,
        )
    )
    await session.commit()
