from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from engineering_control_plane.application.operational_intelligence.service import (
    OperationalIntelligenceService,
)
from engineering_control_plane.application.strategy.router import StrategyRouter
from engineering_control_plane.domain.common.ids import EvidenceId, ObservationId, WorkflowRunId
from engineering_control_plane.domain.knowledge.observations import EntityRef, Observation
from engineering_control_plane.domain.strategy.models import StrategyAssessment
from engineering_control_plane.domain.workspace.models import KnowledgeScope
from engineering_control_plane.domain.workspace.runtime_config import WorkspaceRuntimeConfig
from operational_intelligence_lab.collectors import (
    ANOMALY_CODE,
    collect_evidence,
    detect_relationship_mismatch,
    generalized_guard_conditions,
)
from operational_intelligence_lab.knowledge import (
    build_bounded_semantic_context,
    load_domain_knowledge,
)
from operational_intelligence_lab.models import (
    CandidateRemediation,
    EvidencePackage,
    HumanApproval,
    InMemoryRecipeStore,
)
from operational_intelligence_lab.simulation import (
    STALE_EVENT_GUARDS,
    reproduce_late_stale_removal,
    simulate_lab_001_incident,
    verify_candidate,
)


FAILURE_MODE = "LATE_STALE_RELATIONSHIP_REMOVAL"
TASK_SHAPE = OperationalIntelligenceService.task_shape(ANOMALY_CODE)
CAPABILITY_VERSIONS = {
    "simulation.event-replay": "1.0",
    "projection.inspect": "1.0",
}
ENVIRONMENT = "public-ai-lab-v1"


@dataclass(frozen=True)
class ReasoningResult:
    hypothesis: str
    candidate_remediation: CandidateRemediation
    note: str


class CredentialFreeReasoningSeam:
    """Reproducible stand-in for the one bounded LLM call used by the lab."""

    def __init__(self) -> None:
        self.calls = 0

    async def run(self, **_: Any) -> ReasoningResult:
        self.calls += 1
        return ReasoningResult(
            hypothesis=(
                "An older PACKAGE_REMOVED transition arrived after a newer package "
                "assignment and cleared the newer relationship."
            ),
            candidate_remediation=CandidateRemediation(
                remediation_id="STALE_RELATIONSHIP_EVENT_GUARD_V1",
                description=(
                    "Reject a relationship event whose business sequence is older "
                    "than the newest already-accepted transition for the entity."
                ),
                guard="event.business_sequence < projection.last_business_sequence",
            ),
            note=(
                "Hypothesis only. The OS must reproduce the failure and prove the "
                "candidate remediation before it can be approved for learning."
            ),
        )


@dataclass(frozen=True)
class Lab001Outcome:
    summary: dict[str, Any]
    evidence_package: EvidencePackage
    approval: HumanApproval
    generalized_conditions: tuple[str, ...]
    task_shape: str
    reasoning_calls: int


def _scope() -> KnowledgeScope:
    return KnowledgeScope(
        enterprise_id="public-lab",
        workspace_id="operational-intelligence",
        system_id="package-container-demo",
    )


def _workspace() -> WorkspaceRuntimeConfig:
    return WorkspaceRuntimeConfig(
        workspace_id="operational-intelligence",
        enterprise_id="public-lab",
        system_id="package-container-demo",
    )


def _anomaly(package_id: str, projected_container: str | None) -> Observation:
    return Observation(
        id=ObservationId.new(),
        subject=EntityRef(
            entity_type="PACKAGE",
            identity=package_id,
            attributes={"anomaly_code": ANOMALY_CODE},
        ),
        predicate="MISMATCHES_EXPECTED_RELATIONSHIP",
        object=EntityRef(
            entity_type="CONTAINER",
            identity=projected_container or "NONE",
        ),
        source_type="OPERATIONAL_DETECTOR",
        producer_capability="detector.relationship-consistency",
        knowledge_types=("RUNTIME_EVIDENCE",),
        evidence_refs=(
            EvidenceId(value="ev_event_journal"),
            EvidenceId(value="ev_projection_transitions"),
            EvidenceId(value="ev_runtime_signals"),
        ),
        confidence=1.0,
        run_id=WorkflowRunId.new(),
        scope=_scope(),
    )


async def run_lab_001() -> Lab001Outcome:
    # 1. Create the Article 2 failure through generic message hold/release behavior.
    incident = simulate_lab_001_incident()
    anomaly_code = detect_relationship_mismatch(incident)
    if anomaly_code != ANOMALY_CODE:
        raise RuntimeError("Article 2 simulation did not produce the expected mismatch")

    # 2. Collect a bounded evidence story around the affected entity.
    collected = collect_evidence(incident)

    # 3. Ground the entity relationship in a tiny domain pack.
    knowledge = load_domain_knowledge()
    semantic_context = build_bounded_semantic_context(knowledge, incident)

    # 4. No proven recipe exists, so the router selects adaptive reasoning.
    recipe_store = InMemoryRecipeStore()
    router = StrategyRouter(recipe_store)
    observed_conditions = generalized_guard_conditions(incident)
    first_decision = router.select(
        StrategyAssessment(
            task_shape=TASK_SHAPE,
            knowledge_sufficient=True,
            context_sufficient=True,
            observed_conditions=observed_conditions,
            available_capability_versions=CAPABILITY_VERSIONS,
            environment_fingerprint=ENVIRONMENT,
        )
    )

    # 5. One bounded reasoning call proposes a diagnosis and remediation.
    reasoning = CredentialFreeReasoningSeam()
    intelligence = OperationalIntelligenceService(reasoning)  # type: ignore[arg-type]
    investigation = await intelligence.investigate(
        anomaly=_anomaly(incident.package_id, incident.final_container),
        workspace=_workspace(),
        repository_ids=(),
        knowledge_scope=_scope(),
        provider_name="credential-free-public-lab",
        concepts=("Package", "Container", "assignedTo", "one-active-container"),
    )
    reasoning_result = investigation.execution

    # 6. Re-run the suspected mechanism through generic message hold/release.
    reproduction = reproduce_late_stale_removal()
    if not reproduction.mismatch_reproduced:
        raise RuntimeError("controlled reproduction did not recreate the observed mismatch")

    # 7. Verify the proposed remediation across several deterministic cases.
    simulation = verify_candidate(reasoning_result.candidate_remediation)
    if not simulation.passed:
        raise RuntimeError("candidate remediation failed deterministic simulation")

    # 8. Evidence is packaged before any learning authority is granted.
    evidence_package = EvidencePackage(
        evidence_package_id="evidence_pkg_lab001",
        anomaly_code=ANOMALY_CODE,
        runtime_evidence_refs=(
            "ev_event_journal",
            "ev_projection_transitions",
            "ev_runtime_signals",
            "ev_controlled_reproduction",
            "ev_candidate_simulation",
        ),
        semantic_context=semantic_context,
        diagnosis=reasoning_result.hypothesis,
        remediation=reasoning_result.candidate_remediation,
        reproduction=reproduction,
        simulation=simulation,
    )

    # 9. Public lab fixture for the human governance boundary.
    approval = HumanApproval(
        approval_id="approval_lab001",
        evidence_package_ref=evidence_package.evidence_package_id,
        decision="APPROVED",
        scope="LEARN_DIAGNOSTIC_PATTERN",
        approved_by="human-reviewer",
        reason=(
            "suspected failure mechanism was reproduced and the candidate remediation "
            "passed the required deterministic simulations"
        ),
    )

    summary = {
        "lab": "AI Lab 001 - Unknown Incident",
        "article_alignment": "Article 3",
        "scenario": (
            "old PACKAGE_REMOVED arrives after a newer PACKAGE_ASSIGNED and "
            "clears the correct projection"
        ),
        "business_truth": "P1 -> C2",
        "baseline_final_projection": incident.final_container,
        "mismatch": incident.mismatch,
        "collectors": collected,
        "knowledge": semantic_context,
        "routing": {
            "strategy": first_decision.strategy.value,
            "reasoning_tier": first_decision.reasoning_tier.value,
        },
        "reasoning": {
            "calls": reasoning.calls,
            "hypothesis": reasoning_result.hypothesis,
            "candidate_remediation": asdict(reasoning_result.candidate_remediation),
            "authoritative": False,
        },
        "reproduction": asdict(reproduction),
        "simulation": {
            "passed": simulation.passed,
            "baseline_final": simulation.baseline_final,
            "cases": [asdict(case) for case in simulation.cases],
        },
        "evidence": {
            "package_id": evidence_package.evidence_package_id,
            "status": evidence_package.status,
        },
        "human_approval": asdict(approval),
        "result": "APPROVED_FOR_LEARNING",
    }

    if tuple(STALE_EVENT_GUARDS) != observed_conditions:
        raise RuntimeError("detected incident guards drifted from the canonical lab guards")

    return Lab001Outcome(
        summary=summary,
        evidence_package=evidence_package,
        approval=approval,
        generalized_conditions=observed_conditions,
        task_shape=investigation.task_shape,
        reasoning_calls=reasoning.calls,
    )
