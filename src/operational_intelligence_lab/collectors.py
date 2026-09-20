from __future__ import annotations

from typing import Any

from operational_intelligence_lab.models import IncidentTrace


ANOMALY_CODE = "RELATIONSHIP_PROJECTION_MISMATCH"


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
