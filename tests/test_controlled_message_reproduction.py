from __future__ import annotations

from operational_intelligence_lab.runtime.messaging import ControlledMessageTransport, Message
from operational_intelligence_lab.simulation import reproduce_late_stale_removal


def test_generic_transport_holds_and_releases_without_domain_logic():
    delivered: list[str] = []
    transport = ControlledMessageTransport()
    transport.subscribe(lambda message: delivered.append(message.message_id))

    held = Message(message_id="m2", message_type="ANY_EVENT", payload={"value": 2})
    transport.hold(held.message_id)
    transport.publish(Message(message_id="m1", message_type="ANY_EVENT", payload={"value": 1}))
    transport.publish(held)
    transport.publish(Message(message_id="m3", message_type="ANY_EVENT", payload={"value": 3}))

    assert delivered == ["m1", "m3"]
    assert transport.held_message_ids == ("m2",)

    transport.release("m2")

    assert delivered == ["m1", "m3", "m2"]
    assert transport.held_message_ids == ()


def test_lab_scenario_reproduces_late_removal_through_hold_release():
    result = reproduce_late_stale_removal()

    assert result.held_message_id == "remove-c1"
    assert result.held_before_release == ("remove-c1",)
    assert result.delivery_order == ("assign-c1", "assign-c2", "remove-c1")
    assert result.before_release_container == "C2"
    assert result.after_release_container is None
    assert result.mismatch_reproduced is True
