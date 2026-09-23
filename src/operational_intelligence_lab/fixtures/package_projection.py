from __future__ import annotations

from operational_intelligence_lab.models import (
    EventKind,
    IncidentTrace,
    PackageEvent,
    ProjectionTransition,
)
from operational_intelligence_lab.runtime.messaging import Message


class PackageProjection:
    """Synthetic application projection used by the public package/container fixture."""

    def __init__(self, *, expected_container: str, guard_stale_events: bool = False) -> None:
        self.expected_container = expected_container
        self.guard_stale_events = guard_stale_events
        self.current_container: str | None = None
        self.last_business_sequence = 0
        self._received_sequence = 0
        self._events: list[PackageEvent] = []
        self._transitions: list[ProjectionTransition] = []

    def consume(self, message: Message) -> None:
        self._received_sequence += 1
        event = PackageEvent(
            event_id=message.message_id,
            kind=EventKind(message.message_type),
            package_id=str(message.payload["package_id"]),
            container_id=str(message.payload["container_id"]),
            business_sequence=int(message.payload["business_sequence"]),
            received_sequence=self._received_sequence,
        )
        self._events.append(event)

        before = self.current_container
        stale = event.business_sequence < self.last_business_sequence
        if self.guard_stale_events and stale:
            self._transitions.append(
                ProjectionTransition(
                    event_id=event.event_id,
                    kind=event.kind.value,
                    before=before,
                    after=self.current_container,
                    business_sequence=event.business_sequence,
                    received_sequence=event.received_sequence,
                    accepted=False,
                    reason="stale business sequence rejected",
                )
            )
            return

        if event.kind is EventKind.PACKAGE_ASSIGNED:
            self.current_container = event.container_id
        else:
            self.current_container = None

        self.last_business_sequence = max(self.last_business_sequence, event.business_sequence)
        self._transitions.append(
            ProjectionTransition(
                event_id=event.event_id,
                kind=event.kind.value,
                before=before,
                after=self.current_container,
                business_sequence=event.business_sequence,
                received_sequence=event.received_sequence,
                accepted=True,
                reason="applied",
            )
        )

    def trace(self, *, runtime_signals: tuple[str, ...] = ()) -> IncidentTrace:
        if not self._events:
            raise RuntimeError("projection has not consumed any events")
        return IncidentTrace(
            package_id=self._events[0].package_id,
            expected_container=self.expected_container,
            final_container=self.current_container,
            events=tuple(self._events),
            transitions=tuple(self._transitions),
            runtime_signals=runtime_signals,
        )
