from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class EventKind(StrEnum):
    PACKAGE_ASSIGNED = "PACKAGE_ASSIGNED"
    PACKAGE_REMOVED = "PACKAGE_REMOVED"


@dataclass(frozen=True)
class PackageEvent:
    event_id: str
    kind: EventKind
    package_id: str
    container_id: str
    business_sequence: int
    received_sequence: int


@dataclass(frozen=True)
class ProjectionTransition:
    event_id: str
    kind: str
    before: str | None
    after: str | None
    business_sequence: int
    received_sequence: int
    accepted: bool
    reason: str


@dataclass(frozen=True)
class IncidentTrace:
    package_id: str
    expected_container: str
    final_container: str | None
    events: tuple[PackageEvent, ...]
    transitions: tuple[ProjectionTransition, ...]
    runtime_signals: tuple[str, ...] = ()

    @property
    def mismatch(self) -> bool:
        return self.final_container != self.expected_container


@dataclass(frozen=True)
class CandidateRemediation:
    remediation_id: str
    description: str
    guard: str


@dataclass(frozen=True)
class SimulationCaseResult:
    name: str
    final_container: str | None
    expected_container: str | None
    passed: bool
    rejected_events: tuple[str, ...] = ()


@dataclass(frozen=True)
class SimulationReport:
    remediation: CandidateRemediation
    baseline_final: str | None
    cases: tuple[SimulationCaseResult, ...]

    @property
    def passed(self) -> bool:
        return bool(self.cases) and all(case.passed for case in self.cases)


@dataclass(frozen=True)
class EvidencePackage:
    evidence_package_id: str
    anomaly_code: str
    runtime_evidence_refs: tuple[str, ...]
    semantic_context: dict[str, Any]
    diagnosis: str
    remediation: CandidateRemediation
    simulation: SimulationReport
    status: str = "READY_FOR_HUMAN_REVIEW"


@dataclass(frozen=True)
class HumanApproval:
    approval_id: str
    evidence_package_ref: str
    decision: str
    scope: str
    approved_by: str
    reason: str


@dataclass
class InMemoryRecipeStore:
    items: dict[str, Any] = field(default_factory=dict)

    def save(self, recipe: Any) -> None:
        self.items[recipe.recipe_id] = recipe

    def get(self, recipe_id: str) -> Any:
        return self.items.get(recipe_id)

    def list_for_task_shape(self, task_shape: str) -> tuple[Any, ...]:
        return tuple(item for item in self.items.values() if item.task_shape == task_shape)
