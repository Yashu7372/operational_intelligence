from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field

from engineering_control_plane.domain.strategy.models import ProvenWorkflowRecipe, RecipeMaturity
from engineering_control_plane.domain.workflow.models import WorkflowDefinition
from engineering_control_plane.ports.proven_workflow_store import ProvenWorkflowStorePort


class RecipePromotionPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_supported_runs: int = Field(default=1, ge=1)
    runtime_verified_runs: int = Field(default=2, ge=1)
    proven_runs: int = Field(default=3, ge=1)


class VerifiedWorkflowObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    task_shape: str = Field(min_length=1)
    definition: WorkflowDefinition
    run_id: str = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    capability_versions: dict[str, str] = Field(default_factory=dict)
    context_lens: str | None = None
    knowledge_revision: str | None = None
    environment_fingerprint: str | None = None


class RecipePromotionService:
    """Promote only deterministically verified workflow observations."""

    def __init__(
        self,
        store: ProvenWorkflowStorePort,
        *,
        policy: RecipePromotionPolicy | None = None,
    ) -> None:
        self._store = store
        self._policy = policy or RecipePromotionPolicy()
        if not (
            self._policy.evidence_supported_runs
            <= self._policy.runtime_verified_runs
            <= self._policy.proven_runs
        ):
            raise ValueError("recipe promotion thresholds must be monotonic")

    def record_verified(self, observation: VerifiedWorkflowObservation) -> ProvenWorkflowRecipe:
        recipe_id = self._recipe_id(observation)
        current = self._store.get(recipe_id)
        run_ids = tuple(
            dict.fromkeys([*(current.source_run_ids if current else ()), observation.run_id])
        )
        evidence_refs = tuple(
            dict.fromkeys([*(current.evidence_refs if current else ()), *observation.evidence_refs])
        )
        recipe = ProvenWorkflowRecipe(
            recipe_id=recipe_id,
            task_shape=observation.task_shape,
            maturity=self._maturity(len(run_ids)),
            definition=observation.definition,
            capability_versions=dict(observation.capability_versions),
            source_run_ids=run_ids,
            evidence_refs=evidence_refs,
            context_lens=observation.context_lens,
            knowledge_revision=observation.knowledge_revision,
            environment_fingerprint=observation.environment_fingerprint,
            supersedes=current.supersedes if current else None,
        )
        self._store.save(recipe)
        return recipe

    def _maturity(self, successful_runs: int) -> RecipeMaturity:
        if successful_runs >= self._policy.proven_runs:
            return RecipeMaturity.PROVEN
        if successful_runs >= self._policy.runtime_verified_runs:
            return RecipeMaturity.RUNTIME_VERIFIED
        if successful_runs >= self._policy.evidence_supported_runs:
            return RecipeMaturity.EVIDENCE_SUPPORTED
        return RecipeMaturity.CANDIDATE

    @staticmethod
    def _recipe_id(observation: VerifiedWorkflowObservation) -> str:
        payload = {
            "task_shape": observation.task_shape,
            "plan_id": str(observation.definition.plan_id()),
            "capability_versions": dict(sorted(observation.capability_versions.items())),
            "environment_fingerprint": observation.environment_fingerprint,
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return f"workflow_recipe_{digest[:32]}"
