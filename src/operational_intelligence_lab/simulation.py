from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yaml

from operational_intelligence_lab.fixtures.package_projection import PackageProjection
from operational_intelligence_lab.models import (
    CandidateRemediation,
    EventKind,
    IncidentTrace,
    PackageEvent,
    ProjectionTransition,
    ReproductionReport,
    SimulationCaseResult,
    SimulationReport,
)
from operational_intelligence_lab.runtime.messaging import ControlledMessageTransport, Message


DEFAULT_SCENARIO_FILE = (
    Path(__file__).resolve().parents[2] / "config" / "scenarios" / "late-stale-removal.yaml"
)

STALE_EVENT_GUARDS = (
    "event.kind == PACKAGE_REMOVED",
    "event.business_sequence < projection.last_business_sequence",
    "newer_package_assignment_already_applied == true",
    "projection_relationship != expected_relationship",
)


def article2_events(
    package_id: str,
    original_container: str,
    current_container: str,
) -> tuple[PackageEvent, ...]:
    # Deterministic regression fixtures. The controlled reproduction below uses
    # message.hold/release rather than encoding the late arrival directly.
    return (
        PackageEvent(
            event_id=f"{package_id}-assign-{original_container}",
            kind=EventKind.PACKAGE_ASSIGNED,
            package_id=package_id,
            container_id=original_container,
            business_sequence=1,
            received_sequence=1,
        ),
        PackageEvent(
            event_id=f"{package_id}-remove-{original_container}",
            kind=EventKind.PACKAGE_REMOVED,
            package_id=package_id,
            container_id=original_container,
            business_sequence=2,
            received_sequence=3,
        ),
        PackageEvent(
            event_id=f"{package_id}-assign-{current_container}",
            kind=EventKind.PACKAGE_ASSIGNED,
            package_id=package_id,
            container_id=current_container,
            business_sequence=3,
            received_sequence=2,
        ),
    )


def replay(
    events: tuple[PackageEvent, ...],
    *,
    expected_container: str,
    guarded: bool,
    runtime_signals: tuple[str, ...] = (),
) -> IncidentTrace:
    ordered = tuple(sorted(events, key=lambda item: item.received_sequence))
    current: str | None = None
    last_business_sequence = 0
    transitions: list[ProjectionTransition] = []

    for event in ordered:
        before = current
        stale = event.business_sequence < last_business_sequence
        if guarded and stale:
            transitions.append(
                ProjectionTransition(
                    event_id=event.event_id,
                    kind=event.kind.value,
                    before=before,
                    after=current,
                    business_sequence=event.business_sequence,
                    received_sequence=event.received_sequence,
                    accepted=False,
                    reason="stale business sequence rejected",
                )
            )
            continue

        if event.kind is EventKind.PACKAGE_ASSIGNED:
            current = event.container_id
        else:
            current = None

        last_business_sequence = max(last_business_sequence, event.business_sequence)
        transitions.append(
            ProjectionTransition(
                event_id=event.event_id,
                kind=event.kind.value,
                before=before,
                after=current,
                business_sequence=event.business_sequence,
                received_sequence=event.received_sequence,
                accepted=True,
                reason="applied",
            )
        )

    return IncidentTrace(
        package_id=ordered[0].package_id,
        expected_container=expected_container,
        final_container=current,
        events=ordered,
        transitions=tuple(transitions),
        runtime_signals=runtime_signals,
    )


def _load_scenario(path: Path | None = None) -> dict[str, Any]:
    source = path or DEFAULT_SCENARIO_FILE
    raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("simulation scenario must be a mapping")
    if not isinstance(raw.get("messages"), dict) or not isinstance(raw.get("steps"), list):
        raise ValueError("simulation scenario requires messages and steps")
    return raw


def _scenario_message(message_id: str, definition: dict[str, Any]) -> Message:
    message_type = str(definition.get("type", "")).strip()
    payload = definition.get("payload")
    if not message_type or not isinstance(payload, dict):
        raise ValueError(f"invalid message fixture: {message_id}")
    return Message(message_id=message_id, message_type=message_type, payload=dict(payload))


@dataclass(frozen=True)
class _ControlledScenarioExecution:
    trace: IncidentTrace
    scenario_id: str
    expected_container: str
    released_message_id: str
    delivery_order: tuple[str, ...]
    held_before_release: tuple[str, ...]
    snapshots: dict[str, str | None]


def _execute_controlled_scenario(path: Path | None = None) -> _ControlledScenarioExecution:
    scenario = _load_scenario(path)
    expected_container = str(scenario["expected_container"])
    messages = {
        message_id: _scenario_message(message_id, definition)
        for message_id, definition in scenario["messages"].items()
    }

    transport = ControlledMessageTransport()
    projection = PackageProjection(expected_container=expected_container)
    transport.subscribe(projection.consume)

    snapshots: dict[str, str | None] = {}
    held_before_release: tuple[str, ...] = ()
    released_message_id: str | None = None

    for step in scenario["steps"]:
        if not isinstance(step, dict):
            raise ValueError("scenario step must be a mapping")
        action = str(step.get("action", "")).strip()
        if action == "message.publish":
            transport.publish(messages[str(step["message"])])
        elif action == "message.hold":
            transport.hold(str(step["message"]))
        elif action == "message.release":
            released_message_id = str(step["message"])
            held_before_release = transport.held_message_ids
            transport.release(released_message_id)
        elif action == "state.inspect":
            snapshots[str(step["name"])] = projection.current_container
        else:
            raise ValueError(f"unsupported scenario action: {action}")

    if released_message_id is None:
        raise ValueError("scenario must release a held message")
    if "before-release" not in snapshots or "after-release" not in snapshots:
        raise ValueError("scenario must inspect state before and after release")

    return _ControlledScenarioExecution(
        trace=projection.trace(runtime_signals=("controlled-message-hold-release",)),
        scenario_id=str(scenario["scenario"]),
        expected_container=expected_container,
        released_message_id=released_message_id,
        delivery_order=transport.delivery_order,
        held_before_release=held_before_release,
        snapshots=snapshots,
    )


def simulate_lab_001_incident(path: Path | None = None) -> IncidentTrace:
    """Create the public Lab 1 incident through generic transport behavior."""

    return _execute_controlled_scenario(path).trace


def reproduce_late_stale_removal(path: Path | None = None) -> ReproductionReport:
    """Re-run the suspected failure through generic message hold/release mechanics."""

    execution = _execute_controlled_scenario(path)
    return ReproductionReport(
        scenario_id=execution.scenario_id,
        expected_container=execution.expected_container,
        held_message_id=execution.released_message_id,
        delivery_order=execution.delivery_order,
        before_release_container=execution.snapshots["before-release"],
        after_release_container=execution.snapshots["after-release"],
        held_before_release=execution.held_before_release,
        mismatch_reproduced=(
            execution.snapshots["after-release"] != execution.expected_container
        ),
    )


def simulate_article2_incident(
    package_id: str,
    original_container: str,
    current_container: str,
) -> IncidentTrace:
    # Lab 2 still uses arbitrary runtime identities for the learned-reuse case.
    return replay(
        article2_events(package_id, original_container, current_container),
        expected_container=current_container,
        guarded=False,
        runtime_signals=("late-removal-observed",),
    )


def verify_candidate(
    remediation: CandidateRemediation,
    *,
    package_id: str = "P1",
    original_container: str = "C1",
    current_container: str = "C2",
) -> SimulationReport:
    events = article2_events(package_id, original_container, current_container)
    baseline = replay(events, expected_container=current_container, guarded=False)

    normal_order = tuple(
        replace(event, received_sequence=event.business_sequence) for event in events
    )
    duplicate_assignment = (
        *events,
        replace(
            events[2],
            event_id=f"{events[2].event_id}-retry",
            received_sequence=3,
        ),
    )
    retry_late_removal = (
        *events,
        replace(
            events[1],
            event_id=f"{events[1].event_id}-retry",
            received_sequence=4,
        ),
    )

    scenarios = (
        ("article2-late-removal", events, current_container),
        ("normal-order", normal_order, current_container),
        ("duplicate-newer-assignment", duplicate_assignment, current_container),
        ("retry-late-removal", retry_late_removal, current_container),
    )

    results: list[SimulationCaseResult] = []
    for name, scenario_events, expected in scenarios:
        trace = replay(scenario_events, expected_container=expected, guarded=True)
        rejected = tuple(
            item.event_id for item in trace.transitions if not item.accepted
        )
        results.append(
            SimulationCaseResult(
                name=name,
                final_container=trace.final_container,
                expected_container=expected,
                passed=trace.final_container == expected,
                rejected_events=rejected,
            )
        )

    return SimulationReport(
        remediation=remediation,
        baseline_final=baseline.final_container,
        cases=tuple(results),
    )
