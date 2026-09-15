from __future__ import annotations

import asyncio

from engineering_control_plane.application.operational_intelligence.learning import (
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


def _anomaly(parcel: str, projected_container: str) -> Observation:
    return Observation(
        id=ObservationId.new(),
        subject=EntityRef(
            entity_type="PARCEL",
            identity=parcel,
            attributes={"anomaly_code": "RELATIONSHIP_PROJECTION_MISMATCH"},
        ),
        predicate="MISMATCHES_OBSERVED_RELATIONSHIP",
        object=EntityRef(entity_type="CONTAINER", identity=projected_container),
        source_type="OPERATIONAL_DETECTOR",
        producer_capability="detector.relationship-consistency",
        knowledge_types=("RUNTIME_EVIDENCE",),
        evidence_refs=(EvidenceId(value=f"ev_{parcel.lower()}"),),
        confidence=1.0,
        run_id=WorkflowRunId.new(),
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


def test_verified_learning_promotes_generalized_knowledge_and_enables_r0_recipe_reuse():
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
        id="operational-diagnostic-reproduction",
        version="1.0",
        nodes=(
            WorkflowNode(
                id="reproduce-event-order",
                capability="simulation.event-producer",
                operation="start",
            ),
        ),
    )
    task_shape = "operational-diagnosis:relationship-projection-mismatch"

    learned = learning.record_verified(
        VerifiedDiagnosisLearningInput(
            anomaly_code="RELATIONSHIP_PROJECTION_MISMATCH",
            failure_mode="LATE_RELATIONSHIP_EVENT",
            task_shape=task_shape,
            generalized_conditions=(
                "relationship_change.event_time < arrival.event_time",
                "relationship_change.received_time > arrival.received_time",
                "projection_relationship != observed_relationship",
                "projection_converges_after_relationship_event == true",
            ),
            definition=definition,
            diagnostic_run_id="run_diagnostic_1",
            evidence_refs=("ev_production", "ev_reproduction"),
            verification_evidence_ref="ev_verification",
            capability_versions={"simulation.event-producer": "1.0"},
            knowledge_scope=KnowledgeScope(workspace_id="workspace-demo"),
            environment_fingerprint="env-demo-v1",
        )
    )

    serialized = learned.observation.model_dump_json()
    assert "P1" not in serialized
    assert "C1" not in serialized
    assert "C2" not in serialized
    assert "LATE_RELATIONSHIP_EVENT" in serialized
    assert learned.knowledge.status is PromotionStatus.PROMOTED
    assert learned.recipe.maturity.value == "PROVEN"

    decision = StrategyRouter(recipe_store).select(
        StrategyAssessment(
            task_shape=task_shape,
            knowledge_sufficient=True,
            context_sufficient=True,
            available_capability_versions={"simulation.event-producer": "1.0"},
            environment_fingerprint="env-demo-v1",
        )
    )

    assert decision.strategy is ExecutionStrategy.DETERMINISTIC_RECIPE
    assert decision.reasoning_tier is ReasoningTier.NONE
    assert decision.recipe_id == learned.recipe.recipe_id
