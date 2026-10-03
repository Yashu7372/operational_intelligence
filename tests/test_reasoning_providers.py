from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from operational_intelligence_lab.reasoning import (
    ClaudeCliReasoningProvider,
    CodexCliReasoningProvider,
    CredentialFreeReasoningSeam,
    OpenAIReasoningProvider,
    compare_reasoning_results,
    resolve_reasoning_provider,
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


def _payload(refs=("assign-c2", "remove-c1"), remediation="STALE_RELATIONSHIP_EVENT_GUARD_V1"):
    return {
        "hypothesis": "The removal for C1 is stale.",
        "evidence_refs": list(refs),
        "confidence": 0.8,
        "candidate_remediation": {
            "remediation_id": remediation,
            "description": "Reject stale relationship transitions.",
            "guard": STALE_GUARD_EXPRESSION if remediation != "UNSUPPORTED" else "UNSUPPORTED",
        },
    }


def test_claude_cli_provider_parses_structured_output():
    seen = {}

    async def runner(argv, stdin_text, timeout):
        seen.update(argv=argv, stdin=stdin_text)
        envelope = {
            "is_error": False,
            "structured_output": _payload(),
            "session_id": "sess-1",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        return 0, json.dumps(envelope), ""

    provider = ClaudeCliReasoningProvider(model_name="sonnet", runner=runner)
    result = asyncio.run(provider.run(context=_context()))

    assert result.provider_name == "claude-cli"
    assert result.response_id == "sess-1"
    assert result.input_tokens == 10
    assert result.candidate_remediation.guard == STALE_GUARD_EXPRESSION
    assert seen["argv"][:2] == ["claude", "-p"]
    assert "--model" in seen["argv"] and "sonnet" in seen["argv"]
    assert "remove-c1" in seen["stdin"]


def test_claude_cli_provider_falls_back_to_result_text():
    async def runner(argv, stdin_text, timeout):
        text = "```json\n" + json.dumps(_payload()) + "\n```"
        return 0, json.dumps({"result": text}), ""

    provider = ClaudeCliReasoningProvider(runner=runner)
    result = asyncio.run(provider.run(context=_context()))
    assert result.evidence_refs == ("assign-c2", "remove-c1")


def test_codex_cli_provider_reads_last_message_file():
    seen = {}

    async def runner(argv, stdin_text, timeout):
        seen["argv"] = argv
        Path(argv[argv.index("--output-last-message") + 1]).write_text(json.dumps(_payload()))
        return 0, "", ""

    provider = CodexCliReasoningProvider(runner=runner)
    result = asyncio.run(provider.run(context=_context()))

    assert result.provider_name == "codex-cli"
    assert result.model_name is None
    assert seen["argv"][:2] == ["codex", "exec"]
    assert "read-only" in seen["argv"]
    assert seen["argv"][-1] == "-"


def test_cli_provider_rejects_unknown_evidence_refs():
    async def runner(argv, stdin_text, timeout):
        return 0, json.dumps({"structured_output": _payload(refs=("made-up",))}), ""

    provider = ClaudeCliReasoningProvider(runner=runner)
    with pytest.raises(RuntimeError, match="not present in the bounded context"):
        asyncio.run(provider.run(context=_context()))


def test_cli_provider_rejects_unsupported_remediation_and_cli_failure():
    async def unsupported(argv, stdin_text, timeout):
        return 0, json.dumps({"structured_output": _payload(remediation="UNSUPPORTED")}), ""

    async def failing(argv, stdin_text, timeout):
        return 2, "", "not logged in"

    with pytest.raises(RuntimeError, match="supported remediation"):
        asyncio.run(ClaudeCliReasoningProvider(runner=unsupported).run(context=_context()))
    with pytest.raises(RuntimeError, match="not logged in"):
        asyncio.run(CodexCliReasoningProvider(runner=failing).run(context=_context()))


def test_resolver_knows_cli_providers():
    assert isinstance(resolve_reasoning_provider("claude-cli"), ClaudeCliReasoningProvider)
    assert isinstance(resolve_reasoning_provider("codex-cli"), CodexCliReasoningProvider)
