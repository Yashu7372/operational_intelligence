from __future__ import annotations

import asyncio

from operational_intelligence_lab.run import run_demo


def test_public_lab_closes_the_learning_loop_without_reusing_ai_for_known_pattern():
    result = asyncio.run(run_demo())

    assert result["live_incident"]["mismatch"] is True
    assert result["first_occurrence"]["strategy"] == "ADAPTIVE_REASONING"
    assert result["reproduction"]["mismatch_reproduced"] is True
    assert result["reproduction"]["converged_after_release"] is True
    assert result["verification"]["result"] == "REPRODUCED_AND_VERIFIED"
    assert result["learning"]["knowledge_status"] == "PROMOTED"
    assert result["learning"]["recipe_maturity"] == "PROVEN"
    assert result["learning"]["runtime_ids_promoted"] is False
    assert result["next_occurrence"]["strategy"] == "DETERMINISTIC_RECIPE"
    assert result["next_occurrence"]["reasoning_tier"] == "R0_NONE"
    assert result["next_occurrence"]["llm_required"] is False
    assert result["next_occurrence"]["reasoning_calls_total"] == 1
