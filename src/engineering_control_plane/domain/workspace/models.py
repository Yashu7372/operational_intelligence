from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator


class KnowledgeScope(BaseModel):
    model_config = ConfigDict(frozen=True)

    tenant_id: str | None = None
    enterprise_id: str = "default-enterprise"
    workspace_id: str = "default-workspace"
    team_id: str | None = None
    system_id: str | None = None
    project_id: str | None = None

    @field_validator("enterprise_id", "workspace_id")
    @classmethod
    def _required(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("scope identity is required")
        return normalized
