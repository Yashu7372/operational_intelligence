from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from engineering_control_plane.domain.common.ids import EvidenceId, ObservationId, WorkflowRunId
from engineering_control_plane.domain.workspace.models import KnowledgeScope


class EntityRef(BaseModel):
    model_config = {"frozen": True}
    entity_type: str
    identity: str
    attributes: dict[str, Any] = Field(default_factory=dict)


class Observation(BaseModel):
    id: ObservationId
    subject: EntityRef
    predicate: str
    object: EntityRef
    source_type: str
    producer_capability: str
    knowledge_types: tuple[str, ...] = ()
    evidence_refs: tuple[EvidenceId, ...] = ()
    confidence: float = Field(ge=0.0, le=1.0)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    run_id: WorkflowRunId
    scope: KnowledgeScope = Field(default_factory=KnowledgeScope)
