from __future__ import annotations

from typing import Protocol

from engineering_control_plane.domain.knowledge.observations import Observation
from engineering_control_plane.domain.knowledge.promotion import PromotionResult
from engineering_control_plane.domain.tenancy.models import OwnershipScope


class KnowledgePromotionService(Protocol):
    """Public contract used by the extracted learning coordinator."""

    def record_observation(self, observation: Observation) -> None: ...

    def promote(
        self,
        observation: Observation,
        *,
        ownership: OwnershipScope | None = None,
    ) -> PromotionResult: ...
