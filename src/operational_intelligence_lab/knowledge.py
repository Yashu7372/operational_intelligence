from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from operational_intelligence_lab.models import IncidentTrace, PackageEvent


DEFAULT_DOMAIN_FILE = (
    Path(__file__).resolve().parents[2] / "config" / "domain" / "package-container.yaml"
)


def load_domain_knowledge(path: Path | None = None) -> dict[str, Any]:
    source = path or DEFAULT_DOMAIN_FILE
    raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("domain knowledge must be a mapping")

    entities = raw.get("entities", {})
    relationships = raw.get("relationships", {})
    invariants = raw.get("invariants", [])
    if "Package" not in entities or "Container" not in entities:
        raise ValueError("package-container domain requires Package and Container semantics")
    assigned_to = relationships.get("assignedTo", {})
    if assigned_to.get("source") != "Package" or assigned_to.get("target") != "Container":
        raise ValueError("assignedTo must map Package -> Container")
    invariant_ids = {item.get("id") for item in invariants if isinstance(item, dict)}
    if "one-active-container" not in invariant_ids:
        raise ValueError("one-active-container invariant is required")
    if "projection-matches-business-history" not in invariant_ids:
        raise ValueError("projection-matches-business-history invariant is required")
    return raw


def resolve_expected_assignment(
    knowledge: dict[str, Any],
    events: tuple[PackageEvent, ...],
) -> str | None:
    """Resolve business truth from semantic event effects, not delivery order."""

    if not events:
        return None

    effects = knowledge.get("events", {})
    current: str | None = None
    for event in sorted(events, key=lambda item: item.business_sequence):
        definition = effects.get(event.kind.value, {})
        effect = str(definition.get("effect", "")).strip()
        if effect == "establish assignment":
            current = event.container_id
        elif effect == "remove the referenced assignment":
            if current == event.container_id:
                current = None
        else:
            raise ValueError(f"unsupported semantic event effect for {event.kind.value}: {effect}")
    return current


def build_bounded_semantic_context(
    knowledge: dict[str, Any],
    incident: IncidentTrace,
) -> dict[str, Any]:
    relationship = knowledge["relationships"]["assignedTo"]
    invariant = next(
        item
        for item in knowledge["invariants"]
        if item["id"] == "projection-matches-business-history"
    )
    expected = resolve_expected_assignment(knowledge, incident.events)
    return {
        "entity": {
            "type": "Package",
            "identity": incident.package_id,
        },
        "relationship": {
            "name": "assignedTo",
            "source": relationship["source"],
            "target": relationship["target"],
            "meaning": relationship["meaning"],
        },
        "invariant": {
            "id": invariant["id"],
            "description": invariant["description"],
        },
        "expected_state": {
            "assignedTo": expected,
            "source": "business-sequence semantic replay",
        },
        "observed_state": {
            "assignedTo": incident.final_container,
            "source": "live projection",
        },
    }
