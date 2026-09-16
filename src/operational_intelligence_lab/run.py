from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from typing import Any

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
from engineering_control_plane.domain.strategy.models import StrategyAssessment
from engineering_control_plane.domain.workflow.models import WorkflowDefinition, WorkflowNode
from engineering_control_plane.domain.workspace.models import KnowledgeScope
from engineering_control_plane.domain.workspace.runtime_config import WorkspaceRuntimeConfig

ANOMALY_CODE = "RELATIONSHIP_PROJECTION_MISMATCH"
FAILURE_MODE = "LATE_RELATIONSHIP_EVENT"
TASK_SHAPE = "operational-diagnosis:relationship-projection-mismatch"
CAPABILITY_VERSIONS = {"simulation.event-producer": "1.0"}
ENVIRONMENT = "public-lab-v1"


@dataclass(frozen=True)
class ReasoningResult:
    hypothesis: str
    note: str


class CredentialFreeReasoningSeam:
    def __init__(self) -> None:
        self.calls = 0

    async def run(self, **_: Any) -> ReasoningResult:
        self.calls += 1
        return ReasoningResult(
            hypothesis=(
                "The relationship-change event was received after the later arrival "
                "observation, temporarily leaving the projection stale."
            ),
            note="Hypothesis only; reproduction and verification are still required.",
        )


class RecipeStore:
    def __init__(self) -> None:
        self.items: dict[str, Any] = {}

    def save(self, recipe) -> None:
        self.items[recipe.recipe_id] = recipe

    def get(self, recipe_id: str):
        return self.items.get(recipe_id)

    def list_for_task_shape(self, task_shape: str):
        return tuple(item for item in self.items.values() if item.task_shape == task_shape)


class KnowledgePromotion:
    def __init__(self) -> None:
        self.observations: list[Observation] = []

    def record_observation(self, observation: Observation) -> None:
        self.observations.append(observation)

    def promote(self, observation: Observation, *, ownership=None) -> PromotionResult:
        return PromotionResult(
            observation_id=observation.id,
            status=PromotionStatus.PROMOTED,
            reason="deterministic reproduction evidence accepted",
            knowledge_types=observation.knowledge_types,
            evidence_refs=observation.evidence_refs,
        )


def _scope() -> KnowledgeScope:
    return KnowledgeScope(
        enterprise_id="public-lab",
        workspace_id="operational-intelligence",
        system_id="parcel-container-demo",
    )


def _workspace() -> WorkspaceRuntimeConfig:
    return WorkspaceRuntimeConfig(
        workspace_id="operational-intelligence",
        enterprise_id="public-lab",
        system_id="parcel-container-demo",
    )


def _simulate_live_incident(parcel: str, original: str, current: str) -> dict[str, Any]:
    projection = {parcel: original}
    business_order = [
        f"{parcel}_ASSIGNED_{original}",
        f"{parcel}_CHANGED_{original}_{current}",
        f"{current}_ARRIVED",
    ]
    received_order = [business_order[0], business_order[2], business_order[1]]

    observed_relationship = current
    projected_at_arrival = projection[parcel]
    mismatch = projected_at_arrival != observed_relationship
    projection[parcel] = current

    return {
        "business_order": business_order,
        "received_order": received_order,
        "projected_at_arrival": projected_at_arrival,
        "observed_at_arrival": observed_relationship,
        "mismatch": mismatch,
        "final_projection": projection[parcel],
    }


def _reproduce(parcel: str, original: str, current: str) -> dict[str, Any]:
    projection = {parcel: original}
    held_change = (parcel, current)
    observed_at_arrival = current
    mismatch_reproduced = projection[parcel] != observed_at_arrival
    projection[held_change[0]] = held_change[1]
    converged = projection[parcel] == observed_at_arrival
    return {
        "mismatch_reproduced": mismatch_reproduced,
        "converged_after_release": converged,
        "steps": (
            f"assign {parcel} -> {original}",
            f"hold {parcel} {original} -> {current}",
            f"emit {current} ARRIVED",
            "observe mismatch",
            "release relationship change",
            f"verify {parcel} -> {current}",
        ),
    }


def _anomaly(parcel: str, projected_container: str, evidence_id: str) -> Observation:
    return Observation(
        id=ObservationId.new(),
        subject=EntityRef(
            entity_type="PARCEL",
            identity=parcel,
            attributes={"anomaly_code": ANOMALY_CODE},
        ),
        predicate="MISMATCHES_OBSERVED_RELATIONSHIP",
        object=EntityRef(entity_type="CONTAINER", identity=projected_container),
        source_type="OPERATIONAL_DETECTOR",
        producer_capability="detector.relationship-consistency",
        knowledge_types=("RUNTIME_EVIDENCE",),
        evidence_refs=(EvidenceId(value=evidence_id),),
        confidence=1.0,
        run_id=WorkflowRunId.new(),
        scope=_scope(),
    )


def _definition() -> WorkflowDefinition:
    return WorkflowDefinition(
        id="operational-diagnostic-reproduction",
        version="1.0",
        nodes=(
            WorkflowNode(
                id="reproduce-late-relationship-event",
                capability="simulation.event-producer",
                operation="reproduce",
            ),
        ),
    )


def _assessment() -> StrategyAssessment:
    return StrategyAssessment(
        task_shape=TASK_SHAPE,
        knowledge_sufficient=True,
        context_sufficient=True,
        available_capability_versions=CAPABILITY_VERSIONS,
        environment_fingerprint=ENVIRONMENT,
    )


async def run_demo() -> dict[str, Any]:
    incident = _simulate_live_incident("P1", "C1", "C2")
    if not incident["mismatch"]:
        raise RuntimeError("lab incident did not produce the expected mismatch")

    recipes = RecipeStore()
    router = StrategyRouter(recipes)
    first_decision = router.select(_assessment())

    reasoning = CredentialFreeReasoningSeam()
    intelligence = OperationalIntelligenceService(reasoning)  # type: ignore[arg-type]
    investigation = await intelligence.investigate(
        anomaly=_anomaly("P1", "C1", "ev_production"),
        workspace=_workspace(),
        repository_ids=(),
        knowledge_scope=_scope(),
        provider_name="credential-free-public-lab",
    )

    reproduction = _reproduce("P1", "C1", "C2")
    verified = (
        reproduction["mismatch_reproduced"]
        and reproduction["converged_after_release"]
    )
    if not verified:
        raise RuntimeError("controlled reproduction did not verify the suspected failure mode")

    learning = VerifiedDiagnosisLearningService(
        knowledge=KnowledgePromotion(),  # type: ignore[arg-type]
        recipes=RecipePromotionService(
            recipes,
            policy=RecipePromotionPolicy(
                evidence_supported_runs=1,
                runtime_verified_runs=1,
                proven_runs=1,
            ),
        ),
    )
    learned = learning.record_verified(
        VerifiedDiagnosisLearningInput(
            anomaly_code=ANOMALY_CODE,
            failure_mode=FAILURE_MODE,
            task_shape=investigation.task_shape,
            generalized_conditions=(
                "relationship_change.event_time < arrival.event_time",
                "relationship_change.received_time > arrival.received_time",
                "projection_relationship != observed_relationship",
                "projection_converges_after_relationship_event == true",
            ),
            definition=_definition(),
            diagnostic_run_id="run_public_lab_1",
            evidence_refs=("ev_production", "ev_reproduction"),
            verification_evidence_ref="ev_verification",
            capability_versions=CAPABILITY_VERSIONS,
            knowledge_scope=_scope(),
            environment_fingerprint=ENVIRONMENT,
        )
    )

    second_incident = _simulate_live_incident("P77", "C10", "C11")
    second_shape = OperationalIntelligenceService.task_shape(ANOMALY_CODE)
    second_decision = router.select(
        _assessment().model_copy(update={"task_shape": second_shape})
    )

    if second_decision.reasoning_tier.value != "R0_NONE":
        raise RuntimeError("known verified pattern unexpectedly required reasoning")

    learned_json = learned.observation.model_dump_json()
    if any(runtime_id in learned_json for runtime_id in ("P1", "C1", "C2")):
        raise RuntimeError("runtime incident identities leaked into reusable knowledge")

    return {
        "scenario": "late relationship event creates a temporary stale projection",
        "live_incident": incident,
        "detected_anomaly": ANOMALY_CODE,
        "first_occurrence": {
            "strategy": first_decision.strategy.value,
            "reasoning_tier": first_decision.reasoning_tier.value,
            "hypothesis": investigation.execution.hypothesis,
            "reasoning_calls": reasoning.calls,
            "hypothesis_is_truth": False,
        },
        "reproduction": reproduction,
        "verification": {
            "result": "REPRODUCED_AND_VERIFIED",
            "failure_mode": FAILURE_MODE,
        },
        "learning": {
            "knowledge_status": learned.knowledge.status.value,
            "recipe_maturity": learned.recipe.maturity.value,
            "runtime_ids_promoted": False,
        },
        "next_occurrence": {
            "different_runtime_data": second_incident,
            "task_shape": second_shape,
            "strategy": second_decision.strategy.value,
            "reasoning_tier": second_decision.reasoning_tier.value,
            "llm_required": False,
            "reasoning_calls_total": reasoning.calls,
        },
    }


def _print_human(summary: dict[str, Any]) -> None:
    print("\nOperational Intelligence Learning Loop")
    print("=" * 39)
    print("1. OBSERVE   A late relationship event creates a temporary stale projection.")
    print(f"2. DETECT    {summary['detected_anomaly']}")
    print(
        "3. REASON    First occurrence -> "
        f"{summary['first_occurrence']['strategy']} / "
        f"{summary['first_occurrence']['reasoning_tier']}"
    )
    print(f"             Hypothesis: {summary['first_occurrence']['hypothesis']}")
    print("4. REPRODUCE Hold the relationship change, emit arrival, then release it.")
    print("5. VERIFY    The same mismatch is reproduced and final state converges.")
    print(
        "6. LEARN     Generalized diagnosis promoted; recipe -> "
        f"{summary['learning']['recipe_maturity']}"
    )
    print(
        "7. REUSE     Next occurrence -> "
        f"{summary['next_occurrence']['strategy']} / "
        f"{summary['next_occurrence']['reasoning_tier']}"
    )
    print(f"             LLM required = {summary['next_occurrence']['llm_required']}")
    print("\nUnknown -> reason -> reproduce -> verify -> learn -> deterministic reuse\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the operational intelligence learning-loop lab.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()
    summary = asyncio.run(run_demo())
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        _print_human(summary)


if __name__ == "__main__":
    main()
