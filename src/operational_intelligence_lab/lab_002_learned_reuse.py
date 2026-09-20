from __future__ import annotations

from dataclasses import asdict
from typing import Any

from engineering_control_plane.application.operational_intelligence.learning import (
    LearningApproval,
    VerifiedDiagnosisLearningInput,
    VerifiedDiagnosisLearningService,
)
from engineering_control_plane.application.strategy.promotion import (
    RecipePromotionPolicy,
    RecipePromotionService,
)
from engineering_control_plane.application.strategy.router import StrategyRouter
from engineering_control_plane.domain.knowledge.observations import Observation
from engineering_control_plane.domain.knowledge.promotion import PromotionResult, PromotionStatus
from engineering_control_plane.domain.strategy.models import StrategyAssessment
from engineering_control_plane.domain.workflow.models import WorkflowDefinition, WorkflowNode
from engineering_control_plane.domain.workspace.models import KnowledgeScope
from operational_intelligence_lab.collectors import generalized_guard_conditions
from operational_intelligence_lab.lab_001_unknown_incident import (
    CAPABILITY_VERSIONS,
    ENVIRONMENT,
    FAILURE_MODE,
    TASK_SHAPE,
    run_lab_001,
)
from operational_intelligence_lab.models import InMemoryRecipeStore
from operational_intelligence_lab.simulation import (
    article2_events,
    replay,
    simulate_article2_incident,
)


class InMemoryKnowledgePromotion:
    def __init__(self) -> None:
        self.observations: list[Observation] = []

    def record_observation(self, observation: Observation) -> None:
        self.observations.append(observation)

    def promote(self, observation: Observation, *, ownership=None) -> PromotionResult:
        return PromotionResult(
            observation_id=observation.id,
            status=PromotionStatus.PROMOTED,
            reason="verified simulation and human approval accepted",
            knowledge_types=observation.knowledge_types,
            evidence_refs=observation.evidence_refs,
        )


def _scope() -> KnowledgeScope:
    return KnowledgeScope(
        enterprise_id="public-lab",
        workspace_id="operational-intelligence",
        system_id="package-container-demo",
    )


def _verified_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        id="stale-relationship-event-recovery",
        version="1.0",
        nodes=(
            WorkflowNode(
                id="inspect-current-sequence",
                capability="projection.inspect",
                operation="read-current-sequence",
            ),
            WorkflowNode(
                id="reject-stale-transition",
                capability="simulation.event-replay",
                operation="apply-stale-event-guard",
                depends_on=("inspect-current-sequence",),
            ),
            WorkflowNode(
                id="verify-projection",
                capability="projection.inspect",
                operation="verify-expected-relationship",
                depends_on=("reject-stale-transition",),
            ),
        ),
    )


async def run_lab_002() -> dict[str, Any]:
    discovery = await run_lab_001()

    recipes = InMemoryRecipeStore()
    knowledge = InMemoryKnowledgePromotion()
    learning = VerifiedDiagnosisLearningService(
        knowledge=knowledge,  # type: ignore[arg-type]
        recipes=RecipePromotionService(
            recipes,
            policy=RecipePromotionPolicy(
                evidence_supported_runs=1,
                runtime_verified_runs=1,
                proven_runs=1,
            ),
        ),
    )

    approval = LearningApproval(
        approval_id=discovery.approval.approval_id,
        evidence_package_ref=discovery.approval.evidence_package_ref,
        decision=discovery.approval.decision,  # type: ignore[arg-type]
        scope=discovery.approval.scope,  # type: ignore[arg-type]
        approved_by=discovery.approval.approved_by,
        reason=discovery.approval.reason,
    )

    learned = learning.record_verified(
        VerifiedDiagnosisLearningInput(
            anomaly_code=discovery.evidence_package.anomaly_code,
            failure_mode=FAILURE_MODE,
            task_shape=discovery.task_shape,
            generalized_conditions=discovery.generalized_conditions,
            definition=_verified_workflow(),
            diagnostic_run_id="run_ai_lab_001",
            evidence_refs=discovery.evidence_package.runtime_evidence_refs,
            verification_evidence_ref="ev_candidate_simulation",
            approval=approval,
            capability_versions=CAPABILITY_VERSIONS,
            knowledge_scope=_scope(),
            environment_fingerprint=ENVIRONMENT,
        )
    )

    # Same structural failure, different runtime identities.
    second_incident = simulate_article2_incident("P77", "C10", "C11")
    second_conditions = generalized_guard_conditions(second_incident)
    router = StrategyRouter(recipes)
    reuse_decision = router.select(
        StrategyAssessment(
            task_shape=TASK_SHAPE,
            knowledge_sufficient=True,
            context_sufficient=True,
            observed_conditions=second_conditions,
            available_capability_versions=CAPABILITY_VERSIONS,
            environment_fingerprint=ENVIRONMENT,
        )
    )

    if reuse_decision.reasoning_tier.value != "R0_NONE":
        raise RuntimeError("known verified pattern unexpectedly required model reasoning")

    # The public lab executes the deterministic behavior represented by the recipe.
    corrected = replay(
        article2_events("P77", "C10", "C11"),
        expected_container="C11",
        guarded=True,
    )
    if corrected.mismatch:
        raise RuntimeError("learned deterministic workflow did not correct the second incident")

    # Same anomaly code, but incomplete/different guards: must not reuse automatically.
    different_conditions = tuple(
        item
        for item in second_conditions
        if item != "newer_package_assignment_already_applied == true"
    )
    fallback_decision = router.select(
        StrategyAssessment(
            task_shape=TASK_SHAPE,
            knowledge_sufficient=True,
            context_sufficient=True,
            observed_conditions=different_conditions,
            available_capability_versions=CAPABILITY_VERSIONS,
            environment_fingerprint=ENVIRONMENT,
        )
    )
    if fallback_decision.reasoning_tier.value == "R0_NONE":
        raise RuntimeError("recipe was reused even though its semantic guards did not match")

    promoted_json = learned.observation.model_dump_json()
    if any(runtime_id in promoted_json for runtime_id in ("P1", "C1", "C2", "P77", "C10", "C11")):
        raise RuntimeError("runtime incident identities leaked into reusable knowledge")

    return {
        "lab": "AI Lab 002 - Learn and Reuse",
        "article_alignment": "Article 4",
        "source_evidence_package": discovery.evidence_package.evidence_package_id,
        "promotion": {
            "human_approved": True,
            "knowledge_status": learned.knowledge.status.value,
            "recipe_maturity": learned.recipe.maturity.value,
            "generalized_preconditions": list(learned.recipe.preconditions),
            "runtime_ids_promoted": False,
        },
        "known_occurrence": {
            "runtime": {
                "package": "P77",
                "original_container": "C10",
                "expected_container": "C11",
            },
            "strategy": reuse_decision.strategy.value,
            "reasoning_tier": reuse_decision.reasoning_tier.value,
            "llm_required": False,
            "reasoning_calls_total": discovery.reasoning_calls,
            "final_projection": corrected.final_container,
            "verified": not corrected.mismatch,
        },
        "guard_mismatch": {
            "strategy": fallback_decision.strategy.value,
            "reasoning_tier": fallback_decision.reasoning_tier.value,
            "llm_required": True,
            "reason": fallback_decision.reason,
        },
        "result": "KNOWN_PATTERN_REUSED_DETERMINISTICALLY",
    }
