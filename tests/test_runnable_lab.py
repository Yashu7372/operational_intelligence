from __future__ import annotations

import asyncio

from operational_intelligence_lab.run import run_demo


def test_public_labs_close_the_adaptive_learning_loop():
    result = asyncio.run(run_demo())

    first = result["lab_001"]
    assert first["mismatch"] is True
    assert first["baseline_final_projection"] is None
    assert first["routing"]["strategy"] == "ADAPTIVE_REASONING"
    assert first["reasoning"]["calls"] == 1
    assert first["reasoning"]["authoritative"] is False
    assert first["reproduction"]["mismatch_reproduced"] is True
    assert first["simulation"]["passed"] is True
    assert first["human_approval"]["decision"] == "APPROVED"
    assert first["result"] == "APPROVED_FOR_LEARNING"

    second = result["lab_002"]
    assert second["promotion"]["knowledge_status"] == "PROMOTED"
    assert second["promotion"]["recipe_maturity"] == "PROVEN"
    assert second["promotion"]["runtime_ids_promoted"] is False
    assert second["known_occurrence"]["strategy"] == "DETERMINISTIC_RECIPE"
    assert second["known_occurrence"]["reasoning_tier"] == "R0_NONE"
    assert second["known_occurrence"]["llm_required"] is False
    assert second["known_occurrence"]["reasoning_calls_total"] == 1
    assert second["known_occurrence"]["final_projection"] == "C11"
    assert second["known_occurrence"]["verified"] is True
    assert second["guard_mismatch"]["strategy"] == "ADAPTIVE_REASONING"
    assert second["guard_mismatch"]["llm_required"] is True
