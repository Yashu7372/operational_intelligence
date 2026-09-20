from __future__ import annotations

from dataclasses import replace

from operational_intelligence_lab.models import (
    CandidateRemediation,
    EventKind,
    IncidentTrace,
    PackageEvent,
    ProjectionTransition,
    SimulationCaseResult,
    SimulationReport,
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
    # Business truth: assign C1 -> remove C1 -> assign C2.
    # Delivery: assign C1 -> assign C2 -> old removal C1 arrives late.
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
            # Deliberately naive baseline: an old removal clears the package even
            # after a newer assignment has already been accepted.
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


def simulate_article2_incident(
    package_id: str,
    original_container: str,
    current_container: str,
) -> IncidentTrace:
    return replay(
        article2_events(package_id, original_container, current_container),
        expected_container=current_container,
        guarded=False,
        runtime_signals=("consumer-restarted-before-late-removal",),
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
