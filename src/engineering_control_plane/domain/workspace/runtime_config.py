from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class WorkspaceRuntimeConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    workspace_id: str
    enterprise_id: str
    system_id: str | None = None
