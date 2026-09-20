from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from operational_intelligence_lab.models import IncidentTrace


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
    if not any(item.get("id") == "one-active-container" for item in invariants):
        raise ValueError("one-active-container invariant is required")
    return raw


def build_bounded_semantic_context(
    knowledge: dict[str, Any],
    incident: IncidentTrace,
) -> dict[str, Any]:
    relationship = knowledge["relationships"]["assignedTo"]
    invariant = next(
        item for item in knowledge["invariants"] if item["id"] == "one-active-container"
    )
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
            "assignedTo": incident.expected_container,
        },
        "observed_state": {
            "assignedTo": incident.final_container,
        },
    }
