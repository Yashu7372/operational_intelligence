from __future__ import annotations

from typing import Protocol

from engineering_control_plane.domain.strategy.models import ProvenWorkflowRecipe


class ProvenWorkflowStorePort(Protocol):
    def save(self, recipe: ProvenWorkflowRecipe) -> None: ...
    def get(self, recipe_id: str) -> ProvenWorkflowRecipe | None: ...
    def list_for_task_shape(self, task_shape: str) -> tuple[ProvenWorkflowRecipe, ...]: ...
