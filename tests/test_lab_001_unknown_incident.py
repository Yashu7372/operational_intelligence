from __future__ import annotations

import asyncio

from operational_intelligence_lab.lab_001_unknown_incident import run_lab_001


def test_lab_001_proves_unknown_incident_before_learning():
    outcome = asyncio.run(run_lab_001())
    result = outcome.summary

    assert result["business_truth"] == "P1 -> C2"
    assert result["baseline_final_projection"] is None
    assert result["mismatch"] is True
    assert result["knowledge"]["relationship"]["name"] == "assignedTo"
    assert result["knowledge"]["invariant"]["id"] == "one-active-container"
    assert result["reasoning"]["calls"] == 1
    assert result["reasoning"]["authoritative"] is False
    assert result["simulation"]["passed"] is True
    assert len(result["simulation"]["cases"]) == 4
    assert all(case["passed"] for case in result["simulation"]["cases"])
    assert result["human_approval"]["scope"] == "LEARN_DIAGNOSTIC_PATTERN"
    assert result["result"] == "APPROVED_FOR_LEARNING"
