from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class Message:
    message_id: str
    message_type: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class TransportRecord:
    action: str
    message_id: str


class ControlledMessageTransport:
    """Tiny protocol-neutral transport for deterministic hold/release experiments."""

    def __init__(self) -> None:
        self._subscribers: list[Callable[[Message], None]] = []
        self._held_ids: set[str] = set()
        self._held_messages: dict[str, Message] = {}
        self._records: list[TransportRecord] = []
        self._delivery_order: list[str] = []

    def subscribe(self, consumer: Callable[[Message], None]) -> None:
        self._subscribers.append(consumer)

    def hold(self, message_id: str) -> None:
        if message_id in self._held_messages:
            raise ValueError(f"message already held: {message_id}")
        self._held_ids.add(message_id)
        self._records.append(TransportRecord(action="HOLD", message_id=message_id))

    def publish(self, message: Message) -> None:
        self._records.append(TransportRecord(action="PUBLISH", message_id=message.message_id))
        if message.message_id in self._held_ids:
            if message.message_id in self._held_messages:
                raise ValueError(f"held message already published: {message.message_id}")
            self._held_messages[message.message_id] = message
            self._records.append(TransportRecord(action="QUEUED_HELD", message_id=message.message_id))
            return
        self._deliver(message)

    def release(self, message_id: str) -> None:
        try:
            message = self._held_messages.pop(message_id)
        except KeyError as exc:
            raise KeyError(f"no held message available for release: {message_id}") from exc
        self._held_ids.discard(message_id)
        self._records.append(TransportRecord(action="RELEASE", message_id=message_id))
        self._deliver(message)

    def _deliver(self, message: Message) -> None:
        self._delivery_order.append(message.message_id)
        self._records.append(TransportRecord(action="DELIVER", message_id=message.message_id))
        for consumer in tuple(self._subscribers):
            consumer(message)

    @property
    def held_message_ids(self) -> tuple[str, ...]:
        return tuple(self._held_messages)

    @property
    def delivery_order(self) -> tuple[str, ...]:
        return tuple(self._delivery_order)

    @property
    def records(self) -> tuple[TransportRecord, ...]:
        return tuple(self._records)
