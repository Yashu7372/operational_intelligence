from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from engineering_control_plane.application.operational_intelligence.service import (
    OperationalIntelligenceService,
)
from engineering_control_plane.application.strategy.router import StrategyRouter
from engineering_control_plane.domain.common.ids import EvidenceId, ObservationId, WorkflowRunId
from engineering_control_plane.domain.knowledge.observations import EntityRef, Observation
from engineering_control_plane.domain.strategy.models import StrategyAssessment
from engineering_control_plane.domain.workspace.models import KnowledgeScope
from engineering_control_plane.domain.workspace.runtime_config import WorkspaceRuntimeConfig
from operational_intelligence_lab.collectors import ANOMALY_CODE, generalized_guard_conditions
from operational_intelligence_lab.dashboard import write_dashboard
from operational_intelligence_lab.evidence import persist_lab_001_evidence
from operational_intelligence_lab.knowledge import (
    build_bounded_semantic_context,
    load_domain_knowledge,
)
from operational_intelligence_lab.models import (
    CandidateRemediation,
    EvidencePackage,
    HumanApproval,
    HumanReviewDecision,
    InMemoryRecipeStore,
)
from operational_intelligence_lab.simulation import (
    STALE_EVENT_GUARDS,
    STALE_GUARD_EXPRESSION,
    execute_lab_001_incident,
    reproduce_late_stale_removal,
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
    """Deterministic public stand-in for one bounded model reasoning call.

    It consumes the same materialized context a real model provider would receive.
    If the evidence does not support the stale-removal hypothesis, the seam refuses
    to manufacture the expected answer.
    """

    def __init__(self) -> None:
        self.calls = 0

    async def run(self, **kwargs: Any) -> ReasoningResult:
        self.calls += 1
        context = kwargs.get("context")
        if not isinstance(context, dict):
            raise ValueError("bounded incident context is required for reasoning")

        evidence = context.get("evidence")
        semantics = context.get("semantics")
        if not isinstance(evidence, dict) or not isinstance(semantics, dict):
            raise ValueError("reasoning context requires evidence and semantics")

        events = evidence.get("event_journal", [])
        expected = semantics.get("expected_state", {}).get("assignedTo")
        observed = semantics.get("observed_state", {}).get("assignedTo")
        stale_removal = False
        newest_seen = 0
        for event in events:
            business_sequence = int(event["business_sequence"])
            if (
                event.get("kind") == "PACKAGE_REMOVED"
                and business_sequence < newest_seen
            ):
                stale_removal = True
            newest_seen = max(newest_seen, business_sequence)

        if not stale_removal or expected == observed:
            raise RuntimeError(
                "bounded evidence does not support the stale relationship event hypothesis"
            )

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
                guard=STALE_GUARD_EXPRESSION,
            ),
            note=(
                "Hypothesis only. Controlled reproduction and deterministic verification "
                "must establish whether the candidate is valid."
            ),
        )


@dataclass(frozen=True)
class Lab001Outcome:
    summary: dict[str, Any]
    evidence_package: EvidencePackage
    approval: HumanApproval | None
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


def _approval_from_review(
    review: HumanReviewDecision | None,
    evidence_package_id: str,
) -> HumanApproval | None:
    if review is None:
        return None
    decision = review.decision.strip().upper()
    if decision not in {"APPROVED", "REJECTED"}:
        raise ValueError("human review decision must be APPROVED or REJECTED")
    if not review.approved_by.strip() or not review.reason.strip():
        raise ValueError("human review requires approved_by and reason")
    return HumanApproval(
        approval_id=f"approval_{uuid4().hex[:12]}",
        evidence_package_ref=evidence_package_id,
        decision=decision,
        scope="LEARN_DIAGNOSTIC_PATTERN",
        approved_by=review.approved_by.strip(),
        reason=review.reason.strip(),
    )


async def run_lab_001(
    *,
    review: HumanReviewDecision | None = None,
    output_root: Path | None = None,
) -> Lab001Outcome:
    run_id = f"lab001_{uuid4().hex[:12]}"
    run_dir = (output_root or Path(".lab-state/lab001/runs")) / run_id

    # 1. Run the production-like scenario. The collector is subscribed while it runs.
    observed_run = execute_lab_001_incident()
    incident = observed_run.trace
    if not observed_run.anomalies or observed_run.anomalies[-1].code != ANOMALY_CODE:
        raise RuntimeError("live collector did not detect the expected relationship mismatch")
    collected = observed_run.collected

    # 2. Add the smallest stable semantic meaning required for this incident.
    knowledge = load_domain_knowledge()
    semantic_context = build_bounded_semantic_context(knowledge, incident)
    reasoning_context = {
        "anomaly": {
            "code": ANOMALY_CODE,
            "package_id": incident.package_id,
            "triggering_event_id": observed_run.anomalies[-1].triggering_event_id,
        },
        "evidence": collected,
        "semantics": semantic_context,
    }

    # 3. No proven recipe exists, so the router selects adaptive reasoning.
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

    # 4. One bounded reasoning call proposes a diagnosis and remediation.
    reasoning = CredentialFreeReasoningSeam()
    intelligence = OperationalIntelligenceService(reasoning)  # type: ignore[arg-type]
    investigation = await intelligence.investigate(
        anomaly=_anomaly(incident.package_id, incident.final_container),
        workspace=_workspace(),
        repository_ids=(),
        knowledge_scope=_scope(),
        provider_name="credential-free-public-lab",
        concepts=(
            "Package",
            "Container",
            "assignedTo",
            "projection-matches-business-history",
        ),
        context=reasoning_context,
    )
    reasoning_result = investigation.execution

    # 5. Bind the proposed candidate to a controlled reproduction capability.
    reproduction = reproduce_late_stale_removal(reasoning_result.candidate_remediation)
    if not reproduction.mismatch_reproduced:
        raise RuntimeError("controlled reproduction did not recreate the observed mismatch")

    # 6. Resolve and execute the proposed remediation across deterministic cases.
    simulation = verify_candidate(reasoning_result.candidate_remediation)
    if not simulation.passed:
        raise RuntimeError("candidate remediation failed deterministic simulation")

    evidence_package_id = f"evidence_pkg_{run_id}"
    approval = _approval_from_review(review, evidence_package_id)
    if approval is None:
        result = "READY_FOR_HUMAN_REVIEW"
    elif approval.decision == "APPROVED":
        result = "APPROVED_FOR_LEARNING"
    else:
        result = "REJECTED_FOR_LEARNING"

    # 7. Evidence is packaged before any reusable learning authority is granted.
    evidence_package = EvidencePackage(
        evidence_package_id=evidence_package_id,
        run_id=run_id,
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
        status=result,
    )

    dashboard_path = write_dashboard(
        run_dir / "dashboard.html",
        collected=collected,
        anomaly_code=ANOMALY_CODE,
    )
    evidence_paths = persist_lab_001_evidence(
        run_dir,
        collected=collected,
        reasoning_context=reasoning_context,
        reasoning_result=reasoning_result,
        evidence_package=evidence_package,
        approval=approval,
    )

    summary = {
        "lab": "AI Lab 001 - Unknown Incident",
        "article_alignment": "Article 3",
        "run_id": run_id,
        "scenario": (
            "old PACKAGE_REMOVED arrives after a newer PACKAGE_ASSIGNED and "
            "clears the correct projection"
        ),
        "business_truth": f"P1 -> {incident.expected_container}",
        "baseline_final_projection": incident.final_container,
        "mismatch": incident.mismatch,
        "collectors": collected,
        "live_detection": {
            "detected_before_manual_review": True,
            "anomaly": asdict(observed_run.anomalies[-1]),
        },
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
            "context_event_count": len(collected["event_journal"]),
        },
        "reproduction": asdict(reproduction),
        "simulation": {
            "passed": simulation.passed,
            "baseline_final": simulation.baseline_final,
            "candidate_remediation_id": simulation.remediation.remediation_id,
            "cases": [asdict(case) for case in simulation.cases],
        },
        "evidence": {
            "package_id": evidence_package.evidence_package_id,
            "status": evidence_package.status,
            "manifest": evidence_paths["manifest"],
        },
        "dashboard": str(dashboard_path),
        "human_approval": asdict(approval) if approval is not None else None,
        "result": result,
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
