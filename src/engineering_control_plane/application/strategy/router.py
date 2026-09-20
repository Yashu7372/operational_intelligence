from __future__ import annotations

from engineering_control_plane.domain.strategy.models import (
    ExecutionStrategy,
    RecipeMaturity,
    ReasoningTier,
    StrategyAssessment,
    StrategyDecision,
)
from engineering_control_plane.ports.proven_workflow_store import ProvenWorkflowStorePort


class StrategyRouter:
    """Choose the lightest sufficient path using deterministic assessment data."""

    def __init__(self, recipes: ProvenWorkflowStorePort) -> None:
        self._recipes = recipes

    def select(self, assessment: StrategyAssessment) -> StrategyDecision:
        if not assessment.knowledge_sufficient:
            return StrategyDecision(
                strategy=ExecutionStrategy.ADAPTIVE_REASONING,
                reasoning_tier=ReasoningTier.STANDARD,
                reason="required knowledge is not yet sufficient",
            )
        if not assessment.context_sufficient:
            return StrategyDecision(
                strategy=ExecutionStrategy.ADAPTIVE_REASONING,
                reasoning_tier=ReasoningTier.LIGHT,
                reason="bounded execution context is not yet sufficient",
            )

        candidates = tuple(
            recipe
            for recipe in self._recipes.list_for_task_shape(assessment.task_shape)
            if recipe.maturity is RecipeMaturity.PROVEN
            and self._preconditions_compatible(
                recipe.preconditions,
                assessment.observed_conditions,
            )
            and self._capabilities_compatible(
                recipe.capability_versions,
                assessment.available_capability_versions,
            )
            and self._environment_compatible(
                recipe.environment_fingerprint,
                assessment.environment_fingerprint,
            )
        )
        if candidates:
            selected = sorted(
                candidates,
                key=lambda item: (-len(item.source_run_ids), item.recipe_id),
            )[0]
            return StrategyDecision(
                strategy=ExecutionStrategy.DETERMINISTIC_RECIPE,
                reasoning_tier=ReasoningTier.NONE,
                recipe_id=selected.recipe_id,
                reason="proven workflow recipe with matching guards and runtime compatibility",
            )

        return StrategyDecision(
            strategy=ExecutionStrategy.ADAPTIVE_REASONING,
            reasoning_tier=ReasoningTier.LIGHT,
            reason=(
                "knowledge/context are sufficient but no proven recipe matches "
                "the observed guards and runtime compatibility"
            ),
        )

    @staticmethod
    def _preconditions_compatible(
        required: tuple[str, ...],
        observed: tuple[str, ...],
    ) -> bool:
        return set(required).issubset(set(observed))

    @staticmethod
    def _capabilities_compatible(required: dict[str, str], available: dict[str, str]) -> bool:
        return all(available.get(name) == version for name, version in required.items())

    @staticmethod
    def _environment_compatible(required: str | None, actual: str | None) -> bool:
        return required is None or required == actual
