from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from engineering_control_plane.domain.common.ids import ObjectiveId, TaskId
from engineering_control_plane.domain.tenancy.models import OwnershipScope


class TaskType(StrEnum):
    BOOTSTRAP_SYSTEM = "BOOTSTRAP_SYSTEM"
    UNDERSTAND_SYSTEM = "UNDERSTAND_SYSTEM"
    IMPLEMENT_FEATURE = "IMPLEMENT_FEATURE"
    FIX_DEFECT = "FIX_DEFECT"
    VALIDATE_FEATURE = "VALIDATE_FEATURE"
    PERFORMANCE_DIAGNOSIS = "PERFORMANCE_DIAGNOSIS"
    OPERATIONAL_DIAGNOSIS = "OPERATIONAL_DIAGNOSIS"
    ARCHITECTURE_REVIEW = "ARCHITECTURE_REVIEW"
    SECURITY_REVIEW = "SECURITY_REVIEW"
    ENTERPRISE_READINESS = "ENTERPRISE_READINESS"


class TaskState(StrEnum):
    CREATED = "CREATED"
    READY = "READY"
    IN_PROGRESS = "IN_PROGRESS"
    NEEDS_CONTEXT = "NEEDS_CONTEXT"
    NEEDS_CAPABILITY = "NEEDS_CAPABILITY"
    NEEDS_APPROVAL = "NEEDS_APPROVAL"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"


class AcceptanceCriterion(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    verifier: str
    specification: dict[str, Any] = Field(default_factory=dict)
    mandatory: bool = True


class SemanticTask(BaseModel):
    id: TaskId
    objective_id: ObjectiveId
    task_type: TaskType
    description: str
    expected_outcome: str
    state: TaskState = TaskState.CREATED
    concepts: tuple[str, ...] = ()
    scope: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    acceptance_criteria: tuple[AcceptanceCriterion, ...] = ()
    # Legacy/unowned tasks remain readable for migration compatibility. Every
    # new governed tenant task should carry a resolved ownership scope.
    ownership: OwnershipScope | None = None
