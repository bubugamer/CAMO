from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


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
    source_type: Literal["novel", "chat", "script", "interview", "plain"] | None = None
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


class CharacterIndexRunRequest(BaseModel):
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
    character_core: dict[str, Any] | None = None
    character_facet: dict[str, Any] | None = None


class CharacterIndexRunResponse(BaseModel):
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


class RelationshipRecordResponse(BaseModel):
    relationship_id: str
    project_id: str
    schema_version: str
    source_character_id: str
    target_character_id: str
    relation_category: str
    relation_subtype: str
    public_state: dict[str, Any]
    hidden_state: dict[str, Any] | None = None
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    source_segments: list[str] = Field(default_factory=list)
    confidence: float | None = None
    created_at: datetime
    updated_at: datetime


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
    character_core: dict[str, Any]
    character_facet: dict[str, Any]
    relationships: list[RelationshipRecordResponse] = Field(default_factory=list)
    events: list[EventRecordResponse]
    memories: list[MemoryRecordResponse]


class AnchorInput(BaseModel):
    anchor_mode: Literal["source_progress", "snapshot"]
    source_type: Literal["chapter", "page", "timestamp", "message_index", "timeline_pos"] | None = None
    cutoff_value: str | int | None = None
    snapshot_id: str | None = None


class AnchorStateResponse(BaseModel):
    anchor_mode: str
    source_type: str | None = None
    cutoff_value: str | int | None = None
    resolved_timeline_pos: int
    snapshot_id: str | None = None
    display_label: str
    summary: str


class AnchorSnapshotResponse(BaseModel):
    snapshot_id: str
    period_label: str
    activation_range: dict[str, int]
    display_hint: dict[str, str]
    stage_summary: str
    known_facts: list[str] = Field(default_factory=list)
    unknown_facts: list[str] = Field(default_factory=list)
    profile_overrides: dict[str, Any] = Field(default_factory=dict)
    notes: str


class ModelingJobCreateRequest(BaseModel):
    source_ids: list[str] = Field(default_factory=list)
    segment_limit: int | None = Field(default=None, ge=1)
    max_segments_per_chapter: int = Field(
        default=10,
        ge=1,
        le=32,
        validation_alias=AliasChoices("max_segments_per_chapter", "max_segments_per_character"),
        serialization_alias="max_segments_per_chapter",
    )


class ModelingJobCreateResponse(BaseModel):
    job_id: str
    project_id: str
    status: str


class ModelingJobStatusResponse(BaseModel):
    job_id: str
    project_id: str
    status: str
    progress: float = 0.0
    message: str = ""
    stage: str | None = None
    stage_message: str | None = None
    processed_sources: int = 0
    processed_characters: int = 0
    character_count: int = 0
    current_source_id: str | None = None
    current_character_id: str | None = None
    current_chapter: str | None = None
    error: str | None = None


class SceneRuleSet(BaseModel):
    turn_based: bool = False
    visibility: Literal["full", "role_based", "hidden_state"] = "full"


class RuntimeScene(BaseModel):
    scene_id: str | None = None
    scene_type: Literal["single_chat", "group_chat", "simulation", "review"] = "single_chat"
    description: str | None = None
    rules: SceneRuleSet = Field(default_factory=SceneRuleSet)
    anchor: AnchorInput


class RuntimeSessionCreateRequest(BaseModel):
    project_id: str
    participants: list[str] = Field(default_factory=list)
    speaker_target: str
    scene: RuntimeScene


class RuntimeSessionResponse(BaseModel):
    session_id: str
    project_id: str
    participants: list[str] = Field(default_factory=list)
    speaker_target: str
    scene: dict[str, Any]
    anchor: AnchorStateResponse
    created_at: datetime


class RuntimeUserInput(BaseModel):
    speaker: str = "user"
    content: str


class RuntimeOptions(BaseModel):
    include_reasoning_summary: bool = True
    debug: bool = False


class RuntimeHistoryItem(BaseModel):
    speaker: str
    content: str


class RuntimeTurnRequest(BaseModel):
    participants: list[str] = Field(default_factory=list)
    speaker_target: str | None = None
    user_input: RuntimeUserInput
    recent_history: list[RuntimeHistoryItem] = Field(default_factory=list)
    runtime_options: RuntimeOptions = Field(default_factory=RuntimeOptions)


class ConsistencyIssueResponse(BaseModel):
    dimension: str
    severity: Literal["low", "medium", "high"]
    description: str
    suggestion: str
    evidence_rule_id: str | None = None


class ConsistencyCheckResponse(BaseModel):
    passed: bool
    action: Literal["accept", "warn", "regenerate", "block"]
    issues: list[ConsistencyIssueResponse] = Field(default_factory=list)


class RuntimeTurnResponse(BaseModel):
    session_id: str
    anchor_state: AnchorStateResponse
    response: dict[str, Any]
    reasoning_summary: str | None = None
    triggered_memories: list[dict[str, Any]] = Field(default_factory=list)
    applied_rules: list[dict[str, Any]] = Field(default_factory=list)
    consistency_check: ConsistencyCheckResponse
    anchor_trace: dict[str, Any] | None = None
    context_window: dict[str, Any] | None = None
    retrieval_trace: dict[str, Any] | None = None
    rule_trace: dict[str, Any] | None = None


class RuntimeSwitchAnchorRequest(BaseModel):
    scene: RuntimeScene
    participants: list[str] = Field(default_factory=list)
    speaker_target: str | None = None


class ConsistencyCheckRequest(BaseModel):
    project_id: str
    character_id: str
    anchor: AnchorInput
    response_text: str
    user_input: str | None = None
    participants: list[str] = Field(default_factory=list)


class ReviewSubmitRequest(BaseModel):
    reviewer: str | None = None
    status: str
    note: str | None = None
    character_patch: dict[str, Any] = Field(default_factory=dict)


class ReviewResponse(BaseModel):
    review_id: str
    target_type: str
    target_id: str
    diff: dict[str, Any] | None = None
    reviewer: str | None = None
    status: str
    note: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime


class FeedbackCreateRequest(BaseModel):
    source: str
    target_type: str
    target_id: str
    rating: str | None = None
    reason: str | None = None
    linked_assets: list[str] = Field(default_factory=list)
    suggested_action: str | None = None


class FeedbackResponse(BaseModel):
    feedback_id: str
    source: str
    target_type: str
    target_id: str
    rating: str | None = None
    reason: str | None = None
    linked_assets: list[str] = Field(default_factory=list)
    suggested_action: str | None = None
    created_at: datetime


class CharacterPatchRequest(BaseModel):
    reviewer: str | None = None
    note: str | None = None
    status: str | None = None
    character_index_patch: dict[str, Any] = Field(default_factory=dict)
    character_core_patch: dict[str, Any] = Field(default_factory=dict)
    character_facet_patch: dict[str, Any] = Field(default_factory=dict)


class CharacterVersionResponse(BaseModel):
    version_id: str
    character_id: str
    version_num: int
    snapshot: dict[str, Any]
    diff: dict[str, Any] | None = None
    created_by: str | None = None
    note: str | None = None
    created_at: datetime


class CharacterRollbackRequest(BaseModel):
    version_id: str
    reviewer: str | None = None
    note: str | None = None


class EventCreateRequest(BaseModel):
    title: str
    description: str | None = None
    timeline_pos: int | None = None
    participant_character_ids: list[str] = Field(default_factory=list)
    location: str | None = None
    emotion_valence: str | None = None
    source_segments: list[str] = Field(default_factory=list)


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
