from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from operational_intelligence_lab.models import CandidateRemediation
from operational_intelligence_lab.simulation import STALE_GUARD_EXPRESSION


DEFAULT_OPENAI_MODEL = "gpt-5.6-luna"
SUPPORTED_REMEDIATION_ID = "STALE_RELATIONSHIP_EVENT_GUARD_V1"
UNSUPPORTED_REMEDIATION_ID = "UNSUPPORTED"


@dataclass(frozen=True)
class ReasoningResult:
    hypothesis: str
    candidate_remediation: CandidateRemediation
    note: str
    provider_name: str
    model_name: str | None = None
    response_id: str | None = None
    evidence_refs: tuple[str, ...] = ()
    confidence: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


class ReasoningProvider(Protocol):
    calls: int
    provider_name: str
    model_name: str | None

    async def run(self, **kwargs: Any) -> ReasoningResult: ...


def _bounded_context(kwargs: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    context = kwargs.get("context")
    if not isinstance(context, dict):
        raise ValueError("bounded incident context is required for reasoning")
    evidence = context.get("evidence")
    semantics = context.get("semantics")
    if not isinstance(evidence, dict) or not isinstance(semantics, dict):
        raise ValueError("reasoning context requires evidence and semantics")
    return context, evidence, semantics


def reasoning_result_as_dict(result: ReasoningResult) -> dict[str, Any]:
    return {
        "provider": result.provider_name,
        "model": result.model_name,
        "response_id": result.response_id,
        "hypothesis": result.hypothesis,
        "evidence_refs": list(result.evidence_refs),
        "confidence": result.confidence,
        "candidate_remediation": asdict(result.candidate_remediation),
        "note": result.note,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "authoritative": False,
    }


def compare_reasoning_results(
    selected: ReasoningResult,
    deterministic_reference: ReasoningResult,
) -> dict[str, Any]:
    return {
        "same_remediation_id": (
            selected.candidate_remediation.remediation_id
            == deterministic_reference.candidate_remediation.remediation_id
        ),
        "same_guard_contract": (
            selected.candidate_remediation.guard
            == deterministic_reference.candidate_remediation.guard
        ),
        "same_hypothesis_text": selected.hypothesis == deterministic_reference.hypothesis,
    }


class CredentialFreeReasoningSeam:
    provider_name = "deterministic"
    model_name = "deterministic-reference-v1"

    def __init__(self) -> None:
        self.calls = 0

    async def run(self, **kwargs: Any) -> ReasoningResult:
        self.calls += 1
        _context, evidence, semantics = _bounded_context(kwargs)
        events = evidence.get("event_journal", [])
        expected = semantics.get("expected_state", {}).get("assignedTo")
        observed = semantics.get("observed_state", {}).get("assignedTo")
        stale_removal = False
        newest_seen = 0
        refs: list[str] = []
        for event in events:
            business_sequence = int(event["business_sequence"])
            if event.get("kind") == "PACKAGE_REMOVED" and business_sequence < newest_seen:
                stale_removal = True
                if event.get("event_id"):
                    refs.append(str(event["event_id"]))
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
                remediation_id=SUPPORTED_REMEDIATION_ID,
                description=(
                    "Reject a relationship event whose business sequence is older "
                    "than the newest already-accepted transition for the entity."
                ),
                guard=STALE_GUARD_EXPRESSION,
            ),
            note=(
                "Deterministic reference only. Controlled reproduction and verification "
                "must establish whether the candidate is valid."
            ),
            provider_name=self.provider_name,
            model_name=self.model_name,
            evidence_refs=tuple(refs),
            confidence=1.0,
        )


class OpenAIReasoningProvider:
    provider_name = "openai"

    def __init__(self, *, model_name: str | None = None, client: Any | None = None) -> None:
        self.model_name = model_name or os.getenv("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL
        self._client = client
        self.calls = 0

    def _client_or_create(self) -> Any:
        if self._client is not None:
            return self._client
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError(
                "OPENAI_API_KEY is required when --reasoning-provider openai is used"
            )
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise RuntimeError(
                'OpenAI provider requires the optional dependency. '
                'Install with: python -m pip install -e ".[ai]"'
            ) from exc
        self._client = AsyncOpenAI()
        return self._client

    async def run(self, **kwargs: Any) -> ReasoningResult:
        context, evidence, _semantics = _bounded_context(kwargs)
        self.calls += 1
        event_ids = {
            str(event.get("event_id"))
            for event in evidence.get("event_journal", [])
            if event.get("event_id")
        }
        schema = {
            "type": "object",
            "properties": {
                "hypothesis": {"type": "string", "minLength": 1},
                "evidence_refs": {"type": "array", "items": {"type": "string"}},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "candidate_remediation": {
                    "type": "object",
                    "properties": {
                        "remediation_id": {
                            "type": "string",
                            "enum": [SUPPORTED_REMEDIATION_ID, UNSUPPORTED_REMEDIATION_ID],
                        },
                        "description": {"type": "string", "minLength": 1},
                        "guard": {
                            "type": "string",
                            "enum": [STALE_GUARD_EXPRESSION, UNSUPPORTED_REMEDIATION_ID],
                        },
                    },
                    "required": ["remediation_id", "description", "guard"],
                    "additionalProperties": False,
                },
            },
            "required": [
                "hypothesis",
                "evidence_refs",
                "confidence",
                "candidate_remediation",
            ],
            "additionalProperties": False,
        }
        instructions = (
            "You are a bounded operational-incident reasoning provider. "
            "Use only the supplied incident context. Do not invent events, state, or evidence. "
            "evidence_refs must contain only event_id values present in evidence.event_journal. "
            "Produce a concise testable hypothesis, not hidden chain-of-thought. "
            "You have no execution authority. The remediation catalog contains one supported "
            f"candidate: {SUPPORTED_REMEDIATION_ID}, with guard contract "
            f"{STALE_GUARD_EXPRESSION!r}. Select it only when the evidence supports a stale "
            "relationship transition. Otherwise use remediation_id "
            f"{UNSUPPORTED_REMEDIATION_ID!r} and guard {UNSUPPORTED_REMEDIATION_ID!r}."
        )
        response = await self._client_or_create().responses.create(
            model=self.model_name,
            instructions=instructions,
            input=json.dumps(context, indent=2, sort_keys=True, default=str),
            text={
                "format": {
                    "type": "json_schema",
                    "name": "operational_incident_reasoning",
                    "strict": True,
                    "schema": schema,
                }
            },
        )
        output_text = getattr(response, "output_text", None)
        if not output_text:
            raise RuntimeError("OpenAI reasoning response did not contain structured output")
        try:
            payload = json.loads(output_text)
        except json.JSONDecodeError as exc:
            raise RuntimeError("OpenAI reasoning response was not valid JSON") from exc

        returned_refs = tuple(str(item) for item in payload["evidence_refs"])
        unknown_refs = sorted(set(returned_refs) - event_ids)
        if unknown_refs:
            raise RuntimeError(
                "OpenAI reasoning referenced evidence not present in the bounded context: "
                + ", ".join(unknown_refs)
            )

        candidate_payload = payload["candidate_remediation"]
        remediation_id = str(candidate_payload["remediation_id"])
        guard = str(candidate_payload["guard"])
        if remediation_id == UNSUPPORTED_REMEDIATION_ID:
            raise RuntimeError(
                "OpenAI reasoning did not find a supported remediation candidate: "
                + str(payload["hypothesis"])
            )
        if remediation_id != SUPPORTED_REMEDIATION_ID or guard != STALE_GUARD_EXPRESSION:
            raise RuntimeError(
                "OpenAI reasoning candidate does not match the registered remediation contract"
            )

        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "input_tokens", None) if usage is not None else None
        output_tokens = getattr(usage, "output_tokens", None) if usage is not None else None

        return ReasoningResult(
            hypothesis=str(payload["hypothesis"]),
            candidate_remediation=CandidateRemediation(
                remediation_id=remediation_id,
                description=str(candidate_payload["description"]),
                guard=guard,
            ),
            note=(
                "Model-produced candidate only. Controlled reproduction and deterministic "
                "verification remain authoritative for the lab result."
            ),
            provider_name=self.provider_name,
            model_name=str(getattr(response, "model", None) or self.model_name),
            response_id=str(getattr(response, "id", "")) or None,
            evidence_refs=returned_refs,
            confidence=float(payload["confidence"]),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )


def resolve_reasoning_provider(
    provider_name: str,
    *,
    model_name: str | None = None,
) -> ReasoningProvider:
    normalized = provider_name.strip().lower()
    if normalized in {"deterministic", "credential-free"}:
        return CredentialFreeReasoningSeam()
    if normalized == "openai":
        return OpenAIReasoningProvider(model_name=model_name)
    raise ValueError(
        "unsupported reasoning provider; expected one of: deterministic, openai"
    )
