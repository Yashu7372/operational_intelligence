from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from operational_intelligence_lab.evidence import approve_persisted_lab_001_run
from operational_intelligence_lab.lab_001_unknown_incident import run_lab_001
from operational_intelligence_lab.models import CandidateRemediation, HumanReviewDecision
from operational_intelligence_lab.simulation import verify_candidate


def test_lab_001_proves_unknown_incident_before_learning(tmp_path: Path):
    outcome = asyncio.run(run_lab_001(output_root=tmp_path))
    result = outcome.summary

    assert result["business_truth"] == "P1 -> C2"
    assert result["baseline_final_projection"] is None
    assert result["mismatch"] is True
    assert result["live_detection"]["detected_before_manual_review"] is True
    assert result["live_detection"]["anomaly"]["triggering_event_id"] == "remove-c1"
    assert result["collectors"]["expected_container"] == "C2"
    assert result["collectors"]["final_container"] is None
    assert result["knowledge"]["relationship"]["name"] == "assignedTo"
    assert result["knowledge"]["invariant"]["id"] == "projection-matches-business-history"
    assert result["reasoning"]["calls"] == 1
    assert result["reasoning"]["context_event_count"] == 3
    assert result["reasoning"]["authoritative"] is False
    assert result["reproduction"]["held_message_id"] == "remove-c1"
    assert result["reproduction"]["candidate_remediation_id"] == "STALE_RELATIONSHIP_EVENT_GUARD_V1"
    assert result["reproduction"]["delivery_order"] == (
        "assign-c1",
        "assign-c2",
        "remove-c1",
    )
    assert result["reproduction"]["before_release_container"] == "C2"
    assert result["reproduction"]["after_release_container"] is None
    assert result["reproduction"]["mismatch_reproduced"] is True
    assert any(
        item["action"] == "RELEASE" and item["message_id"] == "remove-c1"
        for item in result["reproduction"]["transport_timeline"]
    )
    assert result["simulation"]["passed"] is True
    assert result["simulation"]["candidate_remediation_id"] == "STALE_RELATIONSHIP_EVENT_GUARD_V1"
    assert len(result["simulation"]["cases"]) == 4
    assert all(case["passed"] for case in result["simulation"]["cases"])
    assert result["human_approval"] is None
    assert result["result"] == "READY_FOR_HUMAN_REVIEW"
    assert Path(result["dashboard"]).exists()
    assert Path(result["evidence"]["manifest"]).exists()


def test_lab_001_requires_explicit_review_to_approve_learning(tmp_path: Path):
    review = HumanReviewDecision(
        decision="APPROVED",
        approved_by="test-reviewer",
        reason="verified the evidence package",
    )

    outcome = asyncio.run(run_lab_001(review=review, output_root=tmp_path))

    assert outcome.approval is not None
    assert outcome.approval.approved_by == "test-reviewer"
    assert outcome.summary["human_approval"]["decision"] == "APPROVED"
    assert outcome.summary["result"] == "APPROVED_FOR_LEARNING"
    assert outcome.evidence_package.status == "APPROVED_FOR_LEARNING"


def test_unknown_candidate_cannot_silently_use_stale_event_guard():
    candidate = CandidateRemediation(
        remediation_id="SOME_OTHER_FIX",
        description="not registered",
        guard="true",
    )

    with pytest.raises(ValueError, match="unsupported candidate remediation"):
        verify_candidate(candidate)


def test_persisted_lab_001_run_is_approved_only_after_review(tmp_path: Path):
    outcome = asyncio.run(run_lab_001(output_root=tmp_path))
    run_id = outcome.summary["run_id"]

    approval = approve_persisted_lab_001_run(
        run_id,
        approved_by="test-reviewer",
        reason="reviewed dashboard, reproduction, and verification evidence",
        output_root=tmp_path,
    )

    assert approval.decision == "APPROVED"
    manifest = json.loads(
        (tmp_path / run_id / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["status"] == "APPROVED_FOR_LEARNING"
    assert manifest["human_approval"]["approved_by"] == "test-reviewer"


def test_candidate_guard_contract_must_match_registered_behavior():
    candidate = CandidateRemediation(
        remediation_id="STALE_RELATIONSHIP_EVENT_GUARD_V1",
        description="claims a different behavior",
        guard="always_true",
    )

    with pytest.raises(ValueError, match="guard contract"):
        verify_candidate(candidate)
