from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yaml

from operational_intelligence_lab.collectors import LiveOperationalCollector
from operational_intelligence_lab.fixtures.package_projection import PackageProjection
from operational_intelligence_lab.knowledge import load_domain_knowledge, resolve_expected_assignment
from operational_intelligence_lab.models import (
    CandidateRemediation,
    EventKind,
    IncidentTrace,
    LiveAnomaly,
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

STALE_GUARD_EXPRESSION = "event.business_sequence < projection.last_business_sequence"

STALE_EVENT_GUARDS = (
    "event.kind == PACKAGE_REMOVED",
    STALE_GUARD_EXPRESSION,
    "newer_package_assignment_already_applied == true",
    "projection_relationship != expected_relationship",
)

EventGuard = Callable[[PackageEvent, int], bool]


def stale_relationship_event_guard(event: PackageEvent, last_business_sequence: int) -> bool:
    return (
        event.kind is EventKind.PACKAGE_REMOVED
        and event.business_sequence < last_business_sequence
    )


REMEDIATION_GUARDS: dict[str, EventGuard] = {
    "STALE_RELATIONSHIP_EVENT_GUARD_V1": stale_relationship_event_guard,
}

REMEDIATION_SCENARIOS: dict[str, Path] = {
    "STALE_RELATIONSHIP_EVENT_GUARD_V1": DEFAULT_SCENARIO_FILE,
}


def resolve_remediation_guard(remediation: CandidateRemediation) -> EventGuard:
    if remediation.guard != STALE_GUARD_EXPRESSION:
        raise ValueError(
            "candidate remediation guard contract does not match the registered implementation"
        )
    try:
        return REMEDIATION_GUARDS[remediation.remediation_id]
    except KeyError as exc:
        raise ValueError(
            f"unsupported candidate remediation: {remediation.remediation_id}"
        ) from exc


def article2_events(
    package_id: str,
    original_container: str,
    current_container: str,
) -> tuple[PackageEvent, ...]:
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
    expected_container: str | None,
    guarded: bool = False,
    guard: EventGuard | None = None,
    runtime_signals: tuple[str, ...] = (),
) -> IncidentTrace:
    ordered = tuple(sorted(events, key=lambda item: item.received_sequence))
    current: str | None = None
    last_business_sequence = 0
    transitions: list[ProjectionTransition] = []
    active_guard = guard or (stale_relationship_event_guard if guarded else None)

    for event in ordered:
        before = current
        if active_guard is not None and active_guard(event, last_business_sequence):
            transitions.append(
                ProjectionTransition(
                    event_id=event.event_id,
                    kind=event.kind.value,
                    before=before,
                    after=current,
                    business_sequence=event.business_sequence,
                    received_sequence=event.received_sequence,
                    accepted=False,
                    reason="candidate remediation rejected stale transition",
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
class ControlledScenarioExecution:
    trace: IncidentTrace
    collected: dict[str, Any]
    anomalies: tuple[LiveAnomaly, ...]
    scenario_id: str
    released_message_id: str
    delivery_order: tuple[str, ...]
    held_before_release: tuple[str, ...]
    snapshots: dict[str, str | None]
    transport_timeline: tuple[dict[str, str], ...]


def _execute_controlled_scenario(path: Path | None = None) -> ControlledScenarioExecution:
    scenario = _load_scenario(path)
    messages = {
        message_id: _scenario_message(message_id, definition)
        for message_id, definition in scenario["messages"].items()
    }

    knowledge = load_domain_knowledge()
    resolver = lambda events: resolve_expected_assignment(knowledge, events)
    collector = LiveOperationalCollector(resolver)
    collector.observe_runtime_signal("controlled-message-transport")

    transport = ControlledMessageTransport()
    projection = PackageProjection()
    projection.subscribe(collector.observe_transition)
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

    trace = collector.trace()
    declared_expected = scenario.get("expected_container")
    if declared_expected is not None and str(declared_expected) != str(trace.expected_container):
        raise ValueError(
            "scenario expected_container disagrees with semantic business-sequence resolution"
        )

    return ControlledScenarioExecution(
        trace=trace,
        collected=collector.evidence(),
        anomalies=collector.anomalies,
        scenario_id=str(scenario["scenario"]),
        released_message_id=released_message_id,
        delivery_order=transport.delivery_order,
        held_before_release=held_before_release,
        snapshots=snapshots,
        transport_timeline=tuple(
            {"action": item.action, "message_id": item.message_id}
            for item in transport.records
        ),
    )


def execute_lab_001_incident(path: Path | None = None) -> ControlledScenarioExecution:
    """Run the production-like Lab 1 scenario with live collection enabled."""

    return _execute_controlled_scenario(path)


def simulate_lab_001_incident(path: Path | None = None) -> IncidentTrace:
    """Compatibility wrapper returning only the final trace."""

    return execute_lab_001_incident(path).trace


def reproduce_late_stale_removal(
    remediation: CandidateRemediation,
) -> ReproductionReport:
    """Re-run the suspected mechanism and bind the run to the proposed candidate."""

    scenario_path = REMEDIATION_SCENARIOS.get(remediation.remediation_id)
    if scenario_path is None:
        raise ValueError(
            f"no controlled reproduction registered for {remediation.remediation_id}"
        )
    execution = _execute_controlled_scenario(scenario_path)
    return ReproductionReport(
        scenario_id=execution.scenario_id,
        candidate_remediation_id=remediation.remediation_id,
        expected_container=execution.trace.expected_container,
        held_message_id=execution.released_message_id,
        delivery_order=execution.delivery_order,
        before_release_container=execution.snapshots["before-release"],
        after_release_container=execution.snapshots["after-release"],
        held_before_release=execution.held_before_release,
        transport_timeline=execution.transport_timeline,
        mismatch_reproduced=(
            execution.snapshots["after-release"] != execution.trace.expected_container
        ),
    )


def simulate_article2_incident(
    package_id: str,
    original_container: str,
    current_container: str,
) -> IncidentTrace:
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
    guard = resolve_remediation_guard(remediation)
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
        trace = replay(
            scenario_events,
            expected_container=expected,
            guard=guard,
        )
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
