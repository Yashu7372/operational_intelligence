from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from engineering_control_plane.domain.common.ids import EvidenceId, ObservationId


class PromotionStatus(StrEnum):
    PROMOTED = "PROMOTED"
    HELD = "HELD"
    REJECTED = "REJECTED"


class PromotionResult(BaseModel):
    observation_id: ObservationId
    status: PromotionStatus
    reason: str
    knowledge_types: tuple[str, ...] = ()
    entity_ids: tuple[str, ...] = ()
    relation_key: str | None = None
    evidence_refs: tuple[EvidenceId, ...] = ()
    candidate: Any | None = None
