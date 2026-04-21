from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class IdentityTag(BaseModel):
    type: str
    value: str


class HealthResponse(BaseModel):
    status: str
    app_name: str
    environment: str
    routing_tasks: list[str]


class ModelCheckRequest(BaseModel):
    prompt: str
    task: str = "runtime"


class ModelCheckResponse(BaseModel):
    task: str
    model: str
    content: str
    structured: dict[str, Any] | None
    usage: dict[str, int]
    latency_ms: int


class ProjectCreateRequest(BaseModel):
    tenant_id: str = "default"
    name: str
    description: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project_id: str
    tenant_id: str
    name: str
    description: str | None
    config: dict[str, Any]
    status: str
    created_at: datetime
    updated_at: datetime


class TextImportRequest(BaseModel):
    filename: str | None = None
    content: str
    source_type: Literal["novel", "chat", "plain"] | None = None
    encoding: str | None = None


class TextImportResponse(BaseModel):
    source_id: str
    project_id: str
    source_type: str
    filename: str | None
    file_path: str
    char_count: int
    segment_count: int
    metadata: dict[str, Any]


class TextSourceResponse(BaseModel):
    source_id: str
    project_id: str
    filename: str | None
    source_type: str
    file_path: str | None
    char_count: int | None
    metadata: dict[str, Any]
    created_at: datetime


class TextSegmentResponse(BaseModel):
    segment_id: str
    source_id: str
    position: int
    chapter: str | None
    round: int | None
    content: str
    raw_offset: int
    char_count: int
    metadata: dict[str, Any]
    created_at: datetime


class EntityIndexRunRequest(BaseModel):
    segment_limit: int | None = None


class CharacterIndexResponse(BaseModel):
    character_id: str
    project_id: str
    schema_version: str
    name: str
    description: str
    character_type: str
    aliases: list[str]
    titles: list[str]
    identities: list[IdentityTag]
    first_appearance: str | None
    confidence: float
    source_segments: list[str]
    status: str
    created_at: datetime
    updated_at: datetime


class CharacterDetailResponse(CharacterIndexResponse):
    core: dict[str, Any] | None = None
    facet: dict[str, Any] | None = None


class EntityIndexRunResponse(BaseModel):
    project_id: str
    source_id: str
    processed_segments: int
    character_count: int
    characters: list[CharacterIndexResponse]


class CharacterPortraitRequest(BaseModel):
    name: str
    aliases: list[str] = Field(default_factory=list)
    max_segments: int = Field(default=12, ge=1, le=24)


class EventRecordResponse(BaseModel):
    event_id: str
    schema_version: str
    title: str
    description: str | None = None
    timeline_pos: int | None = None
    participant_character_ids: list[str] = Field(default_factory=list)
    location: str | None = None
    emotion_valence: str | None = None
    source_segments: list[str] = Field(default_factory=list)
    created_at: datetime


class MemoryRecordResponse(BaseModel):
    memory_id: str
    character_id: str
    project_id: str
    schema_version: str
    memory_type: str
    salience: float
    recency: float
    content: str
    source_event_id: str | None = None
    related_character_ids: list[str] = Field(default_factory=list)
    emotion_valence: str | None = None
    source_segments: list[str] = Field(default_factory=list)
    created_at: datetime


class CharacterPortraitResponse(BaseModel):
    project_id: str
    source_id: str
    character_id: str
    name: str
    aliases: list[str]
    processed_segments: int
    matched_segment_ids: list[str]
    core: dict[str, Any]
    facet: dict[str, Any]
    events: list[EventRecordResponse]
    memories: list[MemoryRecordResponse]


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class CharacterChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = Field(default_factory=list)


class CharacterChatResponse(BaseModel):
    character_id: str
    reply: str
    tone: str
    style_tags: list[str] = Field(default_factory=list)
    speaker: str | None = None
    reasoning_summary: str | None = None
    consistency_check: dict[str, Any] | None = None
    memory_count: int
