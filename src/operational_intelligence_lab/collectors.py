from __future__ import annotations

from collections.abc import Callable
from typing import Any

from operational_intelligence_lab.models import (
    IncidentTrace,
    LiveAnomaly,
    PackageEvent,
    ProjectionTransition,
)


ANOMALY_CODE = "RELATIONSHIP_PROJECTION_MISMATCH"
ExpectedRelationshipResolver = Callable[[tuple[PackageEvent, ...]], str | None]


class LiveOperationalCollector:
    """Observe the application while it runs and emit evidence-backed mismatches."""

    def __init__(self, expected_relationship: ExpectedRelationshipResolver) -> None:
        self._expected_relationship = expected_relationship
        self._events: list[PackageEvent] = []
        self._transitions: list[ProjectionTransition] = []
        self._runtime_signals: list[str] = []
        self._anomalies: list[LiveAnomaly] = []

    def observe_transition(
        self,
        event: PackageEvent,
        transition: ProjectionTransition,
        current_container: str | None,
    ) -> None:
        self._events.append(event)
        self._transitions.append(transition)

        expected = self._expected_relationship(tuple(self._events))
        if current_container != expected:
            self._anomalies.append(
                LiveAnomaly(
                    code=ANOMALY_CODE,
                    package_id=event.package_id,
                    expected_container=expected,
                    observed_container=current_container,
                    triggering_event_id=event.event_id,
                    received_sequence=event.received_sequence,
                )
            )

    def observe_runtime_signal(self, signal: str) -> None:
        if signal not in self._runtime_signals:
            self._runtime_signals.append(signal)

    @property
    def anomalies(self) -> tuple[LiveAnomaly, ...]:
        return tuple(self._anomalies)

    def trace(self) -> IncidentTrace:
        if not self._events:
            raise RuntimeError("collector has not observed any events")
        expected = self._expected_relationship(tuple(self._events))
        final = self._transitions[-1].after if self._transitions else None
        return IncidentTrace(
            package_id=self._events[0].package_id,
            expected_container=expected,
            final_container=final,
            events=tuple(self._events),
            transitions=tuple(self._transitions),
            runtime_signals=tuple(self._runtime_signals),
        )

    def evidence(self) -> dict[str, Any]:
        trace = self.trace()
        evidence = collect_evidence(trace)
        evidence["detected_anomalies"] = [
            {
                "code": item.code,
                "package_id": item.package_id,
                "expected_container": item.expected_container,
                "observed_container": item.observed_container,
                "triggering_event_id": item.triggering_event_id,
                "received_sequence": item.received_sequence,
            }
            for item in self._anomalies
        ]
        return evidence


def collect_evidence(trace: IncidentTrace) -> dict[str, Any]:
    return {
        "event_journal": [
            {
                "event_id": event.event_id,
                "kind": event.kind.value,
                "business_sequence": event.business_sequence,
                "received_sequence": event.received_sequence,
                "package_id": event.package_id,
                "container_id": event.container_id,
            }
            for event in trace.events
        ],
        "projection_transitions": [
            {
                "event_id": item.event_id,
                "kind": item.kind,
                "before": item.before,
                "after": item.after,
                "accepted": item.accepted,
                "reason": item.reason,
                "business_sequence": item.business_sequence,
                "received_sequence": item.received_sequence,
            }
            for item in trace.transitions
        ],
        "runtime_signals": list(trace.runtime_signals),
        "expected_container": trace.expected_container,
        "final_container": trace.final_container,
    }


def detect_relationship_mismatch(trace: IncidentTrace) -> str | None:
    if trace.mismatch:
        return ANOMALY_CODE
    return None


def generalized_guard_conditions(trace: IncidentTrace) -> tuple[str, ...]:
    late_removal = any(
        item.kind == "PACKAGE_REMOVED"
        and item.business_sequence < max(
            other.business_sequence
            for other in trace.transitions
            if other.received_sequence < item.received_sequence
        )
        for item in trace.transitions
        if item.received_sequence > 1
    )
    if not late_removal:
        return ()
    return (
        "event.kind == PACKAGE_REMOVED",
        "event.business_sequence < projection.last_business_sequence",
        "newer_package_assignment_already_applied == true",
        "projection_relationship != expected_relationship",
    )
