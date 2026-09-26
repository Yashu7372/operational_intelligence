from __future__ import annotations

import asyncio

from operational_intelligence_lab.lab_001_unknown_incident import run_lab_001
from operational_intelligence_lab.lab_002_learned_reuse import run_lab_002
from operational_intelligence_lab.models import HumanReviewDecision


def test_lab_002_reuses_only_exact_guarded_pattern_without_llm():
    discovery = asyncio.run(
        run_lab_001(
            review=HumanReviewDecision(
                decision="APPROVED",
                approved_by="test-reviewer",
                reason="reviewed Lab 1 evidence",
            )
        )
    )
    result = asyncio.run(run_lab_002(discovery))

    assert result["promotion"]["human_approved"] is True
    assert result["promotion"]["recipe_maturity"] == "PROVEN"
    assert len(result["promotion"]["generalized_preconditions"]) == 4

    known = result["known_occurrence"]
    assert known["runtime"]["package"] == "P77"
    assert known["strategy"] == "DETERMINISTIC_RECIPE"
    assert known["reasoning_tier"] == "R0_NONE"
    assert known["llm_required"] is False
    assert known["reasoning_calls_total"] == 1
    assert known["final_projection"] == "C11"
    assert known["verified"] is True

    different = result["guard_mismatch"]
    assert different["strategy"] == "ADAPTIVE_REASONING"
    assert different["reasoning_tier"] == "R1_LIGHT"
    assert different["llm_required"] is True
