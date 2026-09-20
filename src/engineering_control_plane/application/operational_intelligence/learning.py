from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from engineering_control_plane.application.knowledge.promotion import KnowledgePromotionService
from engineering_control_plane.application.strategy.promotion import (
    RecipePromotionService,
    VerifiedWorkflowObservation,
)
from engineering_control_plane.domain.common.ids import EvidenceId, ObservationId, WorkflowRunId
from engineering_control_plane.domain.knowledge.observations import EntityRef, Observation
from engineering_control_plane.domain.knowledge.promotion import PromotionResult, PromotionStatus
from engineering_control_plane.domain.strategy.models import ProvenWorkflowRecipe
from engineering_control_plane.domain.tenancy.models import OwnershipScope
from engineering_control_plane.domain.workflow.models import WorkflowDefinition
from engineering_control_plane.domain.workspace.models import KnowledgeScope


class LearningApproval(BaseModel):
    """Durable human authority required before verified behavior becomes reusable."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    approval_id: str = Field(min_length=1)
    evidence_package_ref: str = Field(min_length=1)
    decision: Literal["APPROVED", "REJECTED"]
    scope: Literal["LEARN_DIAGNOSTIC_PATTERN"]
    approved_by: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class VerifiedDiagnosisLearningInput(BaseModel):
    """Generalized diagnosis supplied only after verification and human approval.

    Runtime instance identifiers deliberately have no field here. P1/C1/C2-like
    values stay in the Evidence Plane. Only the reusable anomaly/failure shape,
    generalized guards and approved workflow may enter canonical knowledge.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    anomaly_code: str = Field(min_length=1)
    failure_mode: str = Field(min_length=1)
    task_shape: str = Field(min_length=1)
    generalized_conditions: tuple[str, ...] = Field(min_length=1)
    definition: WorkflowDefinition
    diagnostic_run_id: str = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    verification_evidence_ref: str = Field(min_length=1)
    approval: LearningApproval
    capability_versions: dict[str, str] = Field(default_factory=dict)
    knowledge_scope: KnowledgeScope = Field(default_factory=KnowledgeScope)
    context_lens: str | None = None
    knowledge_revision: str | None = None
    environment_fingerprint: str | None = None

    @field_validator(
        "anomaly_code",
        "failure_mode",
        "task_shape",
        "diagnostic_run_id",
        "verification_evidence_ref",
    )
    @classmethod
    def _required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("verified diagnosis text fields cannot be blank")
        return normalized

    @field_validator("generalized_conditions", "evidence_refs")
    @classmethod
    def _bounded_nonempty_values(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(dict.fromkeys(item.strip() for item in value if item.strip()))
        if not normalized:
            raise ValueError("verified diagnosis tuple fields cannot be empty")
        if len(normalized) > 64:
            raise ValueError("verified diagnosis tuple exceeds 64 entries")
        return normalized


@dataclass(frozen=True)
class VerifiedDiagnosisLearningResult:
    observation: Observation
    knowledge: PromotionResult
    recipe: ProvenWorkflowRecipe


class VerifiedDiagnosisLearningService:
    """Close VERIFY -> APPROVE -> LEARN using knowledge and recipe promotion."""

    def __init__(
        self,
        *,
        knowledge: KnowledgePromotionService,
        recipes: RecipePromotionService,
    ) -> None:
        self._knowledge = knowledge
        self._recipes = recipes

    def record_verified(
        self,
        verified: VerifiedDiagnosisLearningInput,
        *,
        ownership: OwnershipScope | None = None,
    ) -> VerifiedDiagnosisLearningResult:
        if verified.approval.decision != "APPROVED":
            raise PermissionError("human approval is required before diagnostic knowledge promotion")

        evidence_refs = tuple(
            dict.fromkeys((*verified.evidence_refs, verified.verification_evidence_ref))
        )
        typed_evidence_refs = tuple(
            EvidenceId.model_validate(item) for item in evidence_refs
        )
        observation = Observation(
            id=ObservationId.new(),
            subject=EntityRef(
                entity_type="OPERATIONAL_ANOMALY_PATTERN",
                identity=verified.anomaly_code,
                attributes={
                    "task_shape": verified.task_shape,
                    "generalized_conditions": list(verified.generalized_conditions),
                    "verification": "DETERMINISTIC_SIMULATION",
                    "approval_id": verified.approval.approval_id,
                    "approved_by": verified.approval.approved_by,
                },
            ),
            predicate="ASSOCIATED_WITH",
            object=EntityRef(
                entity_type="VERIFIED_FAILURE_MODE",
                identity=verified.failure_mode,
                attributes={
                    "verification": "DETERMINISTIC_SIMULATION",
                },
            ),
            source_type="RUNTIME_VERIFICATION",
            producer_capability="operational-intelligence.learning",
            knowledge_types=(
                "OPERATIONAL_DIAGNOSTIC_PATTERN",
                "RELATED_INCIDENTS",
                "VERIFICATION_PATTERN",
            ),
            evidence_refs=typed_evidence_refs,
            confidence=1.0,
            run_id=WorkflowRunId.model_validate(verified.diagnostic_run_id),
            scope=verified.knowledge_scope,
        )

        self._knowledge.record_observation(observation)
        promotion = self._knowledge.promote(observation, ownership=ownership)
        if promotion.status is not PromotionStatus.PROMOTED:
            raise RuntimeError(
                "verified diagnosis was not accepted by Knowledge Promotion policy: "
                f"{promotion.reason}"
            )

        recipe = self._recipes.record_verified(
            VerifiedWorkflowObservation(
                task_shape=verified.task_shape,
                definition=verified.definition,
                run_id=verified.diagnostic_run_id,
                evidence_refs=evidence_refs,
                preconditions=verified.generalized_conditions,
                capability_versions=dict(verified.capability_versions),
                context_lens=verified.context_lens,
                knowledge_revision=verified.knowledge_revision,
                environment_fingerprint=verified.environment_fingerprint,
            )
        )
        return VerifiedDiagnosisLearningResult(
            observation=observation,
            knowledge=promotion,
            recipe=recipe,
        )
