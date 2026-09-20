from __future__ import annotations

import asyncio

import pytest

from engineering_control_plane.application.operational_intelligence.learning import (
    LearningApproval,
    VerifiedDiagnosisLearningInput,
    VerifiedDiagnosisLearningService,
)
from engineering_control_plane.application.operational_intelligence.service import (
    OperationalIntelligenceService,
)
from engineering_control_plane.application.strategy.promotion import (
    RecipePromotionPolicy,
    RecipePromotionService,
)
from engineering_control_plane.application.strategy.router import StrategyRouter
from engineering_control_plane.domain.common.ids import EvidenceId, ObservationId, WorkflowRunId
from engineering_control_plane.domain.knowledge.observations import EntityRef, Observation
from engineering_control_plane.domain.knowledge.promotion import PromotionResult, PromotionStatus
from engineering_control_plane.domain.strategy.models import (
    ExecutionStrategy,
    ReasoningTier,
    StrategyAssessment,
)
from engineering_control_plane.domain.task.models import TaskType
from engineering_control_plane.domain.workflow.models import WorkflowDefinition, WorkflowNode
from engineering_control_plane.domain.workspace.models import KnowledgeScope


GUARDS = (
    "event.kind == PACKAGE_REMOVED",
    "event.business_sequence < projection.last_business_sequence",
    "newer_package_assignment_already_applied == true",
    "projection_relationship != expected_relationship",
)


class RecordingWorkspaceTasks:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def run(self, **kwargs):
        self.calls.append(kwargs)
        return {"delegated": True}


class RecordingKnowledgePromotion:
    def __init__(self) -> None:
        self.recorded: list[Observation] = []

    def record_observation(self, observation: Observation) -> None:
        self.recorded.append(observation)

    def promote(self, observation: Observation, *, ownership=None) -> PromotionResult:
        return PromotionResult(
            observation_id=observation.id,
            status=PromotionStatus.PROMOTED,
            reason="test evidence accepted",
            knowledge_types=observation.knowledge_types,
            evidence_refs=observation.evidence_refs,
        )


class RecipeStore:
    def __init__(self) -> None:
        self.items = {}

    def save(self, recipe) -> None:
        self.items[recipe.recipe_id] = recipe

    def get(self, recipe_id: str):
        return self.items.get(recipe_id)

    def list_for_task_shape(self, task_shape: str):
        return tuple(
            item for item in self.items.values() if item.task_shape == task_shape
        )


def _anomaly(package: str, projected_container: str) -> Observation:
    return Observation(
        id=ObservationId.new(),
        subject=EntityRef(
            entity_type="PACKAGE",
            identity=package,
            attributes={"anomaly_code": "RELATIONSHIP_PROJECTION_MISMATCH"},
        ),
        predicate="MISMATCHES_EXPECTED_RELATIONSHIP",
        object=EntityRef(entity_type="CONTAINER", identity=projected_container),
        source_type="OPERATIONAL_DETECTOR",
        producer_capability="detector.relationship-consistency",
        knowledge_types=("RUNTIME_EVIDENCE",),
        evidence_refs=(EvidenceId(value=f"ev_{package.lower()}"),),
        confidence=1.0,
        run_id=WorkflowRunId.new(),
    )


def _approval(decision: str = "APPROVED") -> LearningApproval:
    return LearningApproval(
        approval_id="approval_test",
        evidence_package_ref="evidence_pkg_test",
        decision=decision,  # type: ignore[arg-type]
        scope="LEARN_DIAGNOSTIC_PATTERN",
        approved_by="human-reviewer",
        reason="verified in deterministic simulation",
    )


def _learning_input(
    definition: WorkflowDefinition,
    *,
    decision: str = "APPROVED",
) -> VerifiedDiagnosisLearningInput:
    return VerifiedDiagnosisLearningInput(
        anomaly_code="RELATIONSHIP_PROJECTION_MISMATCH",
        failure_mode="LATE_STALE_RELATIONSHIP_REMOVAL",
        task_shape="operational-diagnosis:relationship-projection-mismatch",
        generalized_conditions=GUARDS,
        definition=definition,
        diagnostic_run_id="run_diagnostic_1",
        evidence_refs=("ev_production", "ev_reproduction"),
        verification_evidence_ref="ev_verification",
        approval=_approval(decision),
        capability_versions={
            "simulation.event-replay": "1.0",
            "projection.inspect": "1.0",
        },
        knowledge_scope=KnowledgeScope(workspace_id="workspace-demo"),
        environment_fingerprint="env-demo-v1",
    )


def test_observed_anomaly_delegates_to_stable_workspace_governed_task_shape():
    workspace_tasks = RecordingWorkspaceTasks()
    service = OperationalIntelligenceService(workspace_tasks)  # type: ignore[arg-type]

    first = asyncio.run(
        service.investigate(
            anomaly=_anomaly("P1", "C1"),
            workspace=object(),  # type: ignore[arg-type]
            repository_ids=("application",),
            knowledge_scope=KnowledgeScope(workspace_id="workspace-demo"),
            provider_name="reasoning-provider",
        )
    )
    second = asyncio.run(
        service.investigate(
            anomaly=_anomaly("P77", "C10"),
            workspace=object(),  # type: ignore[arg-type]
            repository_ids=("application",),
            knowledge_scope=KnowledgeScope(workspace_id="workspace-demo"),
            provider_name="reasoning-provider",
        )
    )

    assert first.task_shape == second.task_shape
    assert first.task_shape == "operational-diagnosis:relationship-projection-mismatch"
    assert workspace_tasks.calls[0]["task_type"] is TaskType.OPERATIONAL_DIAGNOSIS
    assert workspace_tasks.calls[0]["task_shape"] == first.task_shape
    assert "P1" in workspace_tasks.calls[0]["description"]
    assert "ev_p1" in workspace_tasks.calls[0]["description"]


def test_verified_learning_requires_human_approval_and_guard_match_for_r0_reuse():
    knowledge = RecordingKnowledgePromotion()
    recipe_store = RecipeStore()
    recipes = RecipePromotionService(
        recipe_store,
        policy=RecipePromotionPolicy(
            evidence_supported_runs=1,
            runtime_verified_runs=1,
            proven_runs=1,
        ),
    )
    learning = VerifiedDiagnosisLearningService(
        knowledge=knowledge,  # type: ignore[arg-type]
        recipes=recipes,
    )
    definition = WorkflowDefinition(
        id="stale-relationship-event-recovery",
        version="1.0",
        nodes=(
            WorkflowNode(
                id="replay-with-guard",
                capability="simulation.event-replay",
                operation="apply-stale-event-guard",
            ),
        ),
    )

    learned = learning.record_verified(_learning_input(definition))

    serialized = learned.observation.model_dump_json()
    assert "P1" not in serialized
    assert "C1" not in serialized
    assert "C2" not in serialized
    assert "LATE_STALE_RELATIONSHIP_REMOVAL" in serialized
    assert learned.knowledge.status is PromotionStatus.PROMOTED
    assert learned.recipe.maturity.value == "PROVEN"
    assert learned.recipe.preconditions == GUARDS

    matching = StrategyRouter(recipe_store).select(
        StrategyAssessment(
            task_shape=learned.recipe.task_shape,
            knowledge_sufficient=True,
            context_sufficient=True,
            observed_conditions=GUARDS,
            available_capability_versions={
                "simulation.event-replay": "1.0",
                "projection.inspect": "1.0",
            },
            environment_fingerprint="env-demo-v1",
        )
    )
    assert matching.strategy is ExecutionStrategy.DETERMINISTIC_RECIPE
    assert matching.reasoning_tier is ReasoningTier.NONE

    guard_mismatch = StrategyRouter(recipe_store).select(
        StrategyAssessment(
            task_shape=learned.recipe.task_shape,
            knowledge_sufficient=True,
            context_sufficient=True,
            observed_conditions=GUARDS[:-1],
            available_capability_versions={
                "simulation.event-replay": "1.0",
                "projection.inspect": "1.0",
            },
            environment_fingerprint="env-demo-v1",
        )
    )
    assert guard_mismatch.strategy is ExecutionStrategy.ADAPTIVE_REASONING
    assert guard_mismatch.reasoning_tier is ReasoningTier.LIGHT


def test_rejected_human_approval_cannot_promote_learning():
    learning = VerifiedDiagnosisLearningService(
        knowledge=RecordingKnowledgePromotion(),  # type: ignore[arg-type]
        recipes=RecipePromotionService(
            RecipeStore(),
            policy=RecipePromotionPolicy(
                evidence_supported_runs=1,
                runtime_verified_runs=1,
                proven_runs=1,
            ),
        ),
    )
    definition = WorkflowDefinition(
        id="stale-relationship-event-recovery",
        nodes=(
            WorkflowNode(
                id="verify",
                capability="projection.inspect",
                operation="verify",
            ),
        ),
    )

    with pytest.raises(PermissionError):
        learning.record_verified(_learning_input(definition, decision="REJECTED"))
