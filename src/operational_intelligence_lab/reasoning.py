from __future__ import annotations

import asyncio
import json
import os
import tempfile
import urllib.error
import urllib.request
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

from operational_intelligence_lab.models import CandidateRemediation
from operational_intelligence_lab.simulation import STALE_GUARD_EXPRESSION


DEFAULT_OPENAI_MODEL = "gpt-5.6-luna"
SUPPORTED_REMEDIATION_ID = "STALE_RELATIONSHIP_EVENT_GUARD_V1"
UNSUPPORTED_REMEDIATION_ID = "UNSUPPORTED"
REASONING_PROVIDER_CHOICES = ("deterministic", "openai", "claude-cli", "codex-cli")


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


MODEL_NOTE = (
    "Model-produced candidate only. Controlled reproduction and deterministic "
    "verification remain authoritative for the lab result."
)


def _reasoning_schema() -> dict[str, Any]:
    return {
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
        "required": ["hypothesis", "evidence_refs", "confidence", "candidate_remediation"],
        "additionalProperties": False,
    }


def _reasoning_instructions() -> str:
    return (
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


def _validate_payload(
    payload: Any, evidence: dict[str, Any], *, label: str
) -> tuple[tuple[str, ...], CandidateRemediation]:
    schema_error = f"{label} reasoning response did not match the required schema"
    top_keys = {"hypothesis", "evidence_refs", "confidence", "candidate_remediation"}
    candidate_keys = {"remediation_id", "description", "guard"}
    if not isinstance(payload, dict) or set(payload) != top_keys:
        raise RuntimeError(schema_error)
    candidate_payload = payload["candidate_remediation"]
    confidence = payload["confidence"]
    if (
        not isinstance(payload["hypothesis"], str)
        or not payload["hypothesis"].strip()
        or not isinstance(payload["evidence_refs"], list)
        or not all(isinstance(ref, str) for ref in payload["evidence_refs"])
        or isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not 0 <= confidence <= 1
        or not isinstance(candidate_payload, dict)
        or set(candidate_payload) != candidate_keys
        or not all(isinstance(candidate_payload[key], str) for key in candidate_keys)
        or not candidate_payload["description"].strip()
    ):
        raise RuntimeError(schema_error)
    event_ids = {
        str(event.get("event_id"))
        for event in evidence.get("event_journal", [])
        if event.get("event_id")
    }
    returned_refs = tuple(str(item) for item in payload["evidence_refs"])
    unknown_refs = sorted(set(returned_refs) - event_ids)
    if unknown_refs:
        raise RuntimeError(
            f"{label} reasoning referenced evidence not present in the bounded context: "
            + ", ".join(unknown_refs)
        )
    remediation_id = str(candidate_payload["remediation_id"])
    guard = str(candidate_payload["guard"])
    if remediation_id == UNSUPPORTED_REMEDIATION_ID:
        raise RuntimeError(
            f"{label} reasoning did not find a supported remediation candidate: "
            + str(payload["hypothesis"])
        )
    if remediation_id != SUPPORTED_REMEDIATION_ID or guard != STALE_GUARD_EXPRESSION:
        raise RuntimeError(
            f"{label} reasoning candidate does not match the registered remediation contract"
        )
    return returned_refs, CandidateRemediation(
        remediation_id=remediation_id,
        description=str(candidate_payload["description"]),
        guard=guard,
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
        schema = _reasoning_schema()
        instructions = _reasoning_instructions()
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

        returned_refs, candidate = _validate_payload(payload, evidence, label="OpenAI")

        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "input_tokens", None) if usage is not None else None
        output_tokens = getattr(usage, "output_tokens", None) if usage is not None else None

        return ReasoningResult(
            hypothesis=str(payload["hypothesis"]),
            candidate_remediation=candidate,
            note=MODEL_NOTE,
            provider_name=self.provider_name,
            model_name=str(getattr(response, "model", None) or self.model_name),
            response_id=str(getattr(response, "id", "")) or None,
            evidence_refs=returned_refs,
            confidence=float(payload["confidence"]),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )


# Runner signature: (argv, stdin_text, timeout_seconds) -> (returncode, stdout, stderr)
CliRunner = Callable[[list[str], str, float], Awaitable[tuple[int, str, str]]]

DEFAULT_CLI_TIMEOUT_SECONDS = 300.0


async def _subprocess_runner(
    argv: list[str], stdin_text: str, timeout: float
) -> tuple[int, str, str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"CLI executable {argv[0]!r} was not found on PATH; install it and sign in first"
        ) from exc
    try:
        out, err = await asyncio.wait_for(
            proc.communicate(stdin_text.encode()), timeout=timeout
        )
    except asyncio.TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise RuntimeError(f"{argv[0]} timed out after {timeout:.0f}s") from exc
    return proc.returncode or 0, out.decode(errors="replace"), err.decode(errors="replace")


def _extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0] if "```" in text else text
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        first, last = text.find("{"), text.rfind("}")
        if first == -1 or last <= first:
            raise RuntimeError("CLI reasoning response was not valid JSON") from None
        try:
            value = json.loads(text[first : last + 1])
        except json.JSONDecodeError as exc:
            raise RuntimeError("CLI reasoning response was not valid JSON") from exc
    if not isinstance(value, dict):
        raise RuntimeError("CLI reasoning response was not a JSON object")
    return value


class _CliReasoningProvider:
    """Shared plumbing for agent CLIs used as reasoning providers.

    The CLI is invoked non-interactively, read-only, with the same bounded
    context, schema and validation as the OpenAI provider. It has no authority.
    """

    provider_name = "cli"
    label = "CLI"

    def __init__(
        self,
        *,
        model_name: str | None = None,
        runner: CliRunner | None = None,
        executable: str | None = None,
        timeout: float = DEFAULT_CLI_TIMEOUT_SECONDS,
        bridge_url: str | None = None,
        bridge_token: str | None = None,
    ) -> None:
        self.model_name = model_name
        self._bridge_url = bridge_url or os.getenv("CLI_BRIDGE_URL") or None
        self._bridge_token = bridge_token or os.getenv("CLI_BRIDGE_TOKEN") or None
        self._runner = runner or _subprocess_runner
        self._executable = executable
        self._timeout = timeout
        self.calls = 0

    def _prompt(self, context: dict[str, Any], schema: dict[str, Any]) -> str:
        return (
            _reasoning_instructions()
            + "\n\nRespond with ONLY a single JSON object matching this JSON Schema, "
            "no prose and no code fences:\n"
            + json.dumps(schema, sort_keys=True)
            + "\n\nIncident context:\n"
            + json.dumps(context, indent=2, sort_keys=True, default=str)
        )

    async def _invoke(self, prompt: str, schema: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        """Return (payload, metadata) where metadata may hold model/response_id/tokens."""
        raise NotImplementedError

    def _invoke_via_bridge(
        self, prompt: str, schema: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Delegate to the host-side bridge (see cli_bridge.py), e.g. from Docker."""
        if not self._bridge_token:
            raise RuntimeError("CLI_BRIDGE_TOKEN is required when CLI_BRIDGE_URL is set")
        request = urllib.request.Request(
            self._bridge_url.rstrip("/") + "/v1/reason",
            data=json.dumps(
                {
                    "provider": self.provider_name,
                    "model": self.model_name,
                    "prompt": prompt,
                    "schema": schema,
                }
            ).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._bridge_token}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout + 30) as response:
                body = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:500]
            raise RuntimeError(f"CLI bridge returned {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(
                f"could not reach CLI bridge at {self._bridge_url}: {exc}. "
                "Is `oi-cli-bridge` running on the host?"
            ) from exc
        payload, meta = body.get("payload"), body.get("meta") or {}
        if not isinstance(payload, dict) or not isinstance(meta, dict):
            raise RuntimeError("CLI bridge returned a malformed response")
        return payload, meta

    async def run(self, **kwargs: Any) -> ReasoningResult:
        context, evidence, _semantics = _bounded_context(kwargs)
        self.calls += 1
        schema = _reasoning_schema()
        prompt = self._prompt(context, schema)
        if self._bridge_url:
            payload, meta = await asyncio.to_thread(self._invoke_via_bridge, prompt, schema)
        else:
            payload, meta = await self._invoke(prompt, schema)
        refs, candidate = _validate_payload(payload, evidence, label=self.label)
        try:
            confidence = float(payload["confidence"])
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"{self.label} reasoning confidence was not a number") from exc
        return ReasoningResult(
            hypothesis=str(payload["hypothesis"]),
            candidate_remediation=candidate,
            note=MODEL_NOTE,
            provider_name=self.provider_name,
            model_name=meta.get("model") or self.model_name,
            response_id=meta.get("response_id"),
            evidence_refs=refs,
            confidence=confidence,
            input_tokens=meta.get("input_tokens"),
            output_tokens=meta.get("output_tokens"),
        )


class ClaudeCliReasoningProvider(_CliReasoningProvider):
    """Uses the Claude Code CLI (`claude -p`), authenticated by its own login."""

    provider_name = "claude-cli"
    label = "Claude CLI"

    async def _invoke(self, prompt, schema):
        argv = [
            self._executable or os.getenv("CLAUDE_CLI") or "claude",
            "-p",
            "--output-format", "json",
            "--json-schema", json.dumps(schema),
            "--tools", "",
        ]
        if self.model_name:
            argv += ["--model", self.model_name]
        code, out, err = await self._runner(argv, prompt, self._timeout)
        if code != 0:
            raise RuntimeError(f"claude CLI exited with {code}: {err.strip()[:500]}")
        envelope = _extract_json_object(out)
        if envelope.get("is_error"):
            raise RuntimeError(f"claude CLI reported an error: {str(envelope.get('result'))[:500]}")
        structured = envelope.get("structured_output")
        payload = structured if isinstance(structured, dict) else _extract_json_object(
            str(envelope.get("result") or "")
        )
        usage = envelope.get("usage") or {}
        return payload, {
            "response_id": envelope.get("session_id"),
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
        }


class CodexCliReasoningProvider(_CliReasoningProvider):
    """Uses the OpenAI Codex CLI (`codex exec`), authenticated by its own login."""

    provider_name = "codex-cli"
    label = "Codex CLI"

    async def _invoke(self, prompt, schema):
        with tempfile.TemporaryDirectory(prefix="oi-codex-") as tmp:
            schema_path = Path(tmp) / "schema.json"
            out_path = Path(tmp) / "last-message.txt"
            schema_path.write_text(json.dumps(schema))
            argv = [
                self._executable or os.getenv("CODEX_CLI") or "codex",
                "exec",
                "--sandbox", "read-only",
                "--skip-git-repo-check",
                "--ephemeral",
                "--output-schema", str(schema_path),
                "--output-last-message", str(out_path),
            ]
            if self.model_name:
                argv += ["--model", self.model_name]
            argv.append("-")  # read prompt from stdin
            code, _out, err = await self._runner(argv, prompt, self._timeout)
            if code != 0:
                raise RuntimeError(f"codex CLI exited with {code}: {err.strip()[:500]}")
            if not out_path.exists():
                raise RuntimeError("codex CLI did not write a final message")
            return _extract_json_object(out_path.read_text()), {}


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
    if normalized in {"claude-cli", "claude"}:
        return ClaudeCliReasoningProvider(model_name=model_name)
    if normalized in {"codex-cli", "codex"}:
        return CodexCliReasoningProvider(model_name=model_name)
    raise ValueError(
        "unsupported reasoning provider; expected one of: "
        + ", ".join(REASONING_PROVIDER_CHOICES)
    )
