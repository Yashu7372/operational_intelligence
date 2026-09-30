from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from operational_intelligence_lab.reasoning import (
    CredentialFreeReasoningSeam,
    OpenAIReasoningProvider,
    compare_reasoning_results,
)
from operational_intelligence_lab.simulation import STALE_GUARD_EXPRESSION


def _context() -> dict:
    return {
        "anomaly": {
            "code": "RELATIONSHIP_PROJECTION_MISMATCH",
            "package_id": "P1",
            "triggering_event_id": "remove-c1",
        },
        "evidence": {
            "event_journal": [
                {
                    "event_id": "assign-c1",
                    "kind": "PACKAGE_ASSIGNED",
                    "business_sequence": 1,
                },
                {
                    "event_id": "assign-c2",
                    "kind": "PACKAGE_ASSIGNED",
                    "business_sequence": 3,
                },
                {
                    "event_id": "remove-c1",
                    "kind": "PACKAGE_REMOVED",
                    "business_sequence": 2,
                },
            ]
        },
        "semantics": {
            "expected_state": {"assignedTo": "C2"},
            "observed_state": {"assignedTo": None},
        },
    }


class _FakeResponses:
    def __init__(self) -> None:
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        payload = {
            "hypothesis": (
                "The removal for C1 is stale because a newer assignment to C2 "
                "was already accepted."
            ),
            "evidence_refs": ["assign-c2", "remove-c1"],
            "confidence": 0.91,
            "candidate_remediation": {
                "remediation_id": "STALE_RELATIONSHIP_EVENT_GUARD_V1",
                "description": "Reject stale relationship transitions.",
                "guard": STALE_GUARD_EXPRESSION,
            },
        }
        return SimpleNamespace(
            output_text=json.dumps(payload),
            id="resp_test_123",
            model="gpt-test",
            usage=SimpleNamespace(input_tokens=120, output_tokens=60),
        )


class _FakeClient:
    def __init__(self) -> None:
        self.responses = _FakeResponses()


def test_openai_provider_uses_structured_output_and_returns_candidate():
    client = _FakeClient()
    provider = OpenAIReasoningProvider(model_name="gpt-test", client=client)

    result = asyncio.run(provider.run(context=_context()))

    assert result.provider_name == "openai"
    assert result.model_name == "gpt-test"
    assert result.response_id == "resp_test_123"
    assert result.evidence_refs == ("assign-c2", "remove-c1")
    assert result.confidence == 0.91
    assert result.candidate_remediation.remediation_id == "STALE_RELATIONSHIP_EVENT_GUARD_V1"
    assert result.candidate_remediation.guard == STALE_GUARD_EXPRESSION
    assert result.input_tokens == 120
    assert result.output_tokens == 60
    assert provider.calls == 1

    request = client.responses.kwargs
    assert request["model"] == "gpt-test"
    assert request["text"]["format"]["type"] == "json_schema"
    assert request["text"]["format"]["strict"] is True


def test_real_and_deterministic_results_can_be_compared():
    client = _FakeClient()
    openai_provider = OpenAIReasoningProvider(model_name="gpt-test", client=client)
    deterministic = CredentialFreeReasoningSeam()

    real_result = asyncio.run(openai_provider.run(context=_context()))
    deterministic_result = asyncio.run(deterministic.run(context=_context()))
    comparison = compare_reasoning_results(real_result, deterministic_result)

    assert comparison["same_remediation_id"] is True
    assert comparison["same_guard_contract"] is True
    assert comparison["same_hypothesis_text"] is False
