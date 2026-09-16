from __future__ import annotations

from typing import Any, ClassVar
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, field_validator, model_serializer, model_validator


class TypedId(BaseModel):
    model_config = ConfigDict(frozen=True)
    value: str
    prefix: ClassVar[str] = "id"

    @model_validator(mode="before")
    @classmethod
    def _accept_raw_string(cls, value: Any):
        if isinstance(value, str):
            return {"value": value}
        return value

    @field_validator("value")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("identifier value is required")
        return value

    @model_serializer
    def _serialize(self) -> str:
        return self.value

    @classmethod
    def new(cls):
        return cls(value=f"{cls.prefix}_{uuid4().hex}")

    def __str__(self) -> str:
        return self.value


class TenantId(TypedId): prefix = "tenant"
class WorkspaceId(TypedId): prefix = "workspace"
class TeamId(TypedId): prefix = "team"
class ProjectId(TypedId): prefix = "project"
class ObjectiveId(TypedId): prefix = "obj"
class WorkflowRunId(TypedId): prefix = "run"
class PlanId(TypedId): prefix = "plan"
class TaskId(TypedId): prefix = "task"
class EvidenceId(TypedId): prefix = "ev"
class ObservationId(TypedId): prefix = "obs"
