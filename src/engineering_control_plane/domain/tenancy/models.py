from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from engineering_control_plane.domain.common.ids import ProjectId, TeamId, TenantId, WorkspaceId


class OwnershipScope(BaseModel):
    model_config = ConfigDict(frozen=True)

    tenant_id: TenantId
    workspace_id: WorkspaceId
    team_id: TeamId
    project_id: ProjectId

    def canonical_key(self) -> str:
        return ":".join(
            (
                str(self.tenant_id),
                str(self.workspace_id),
                str(self.team_id),
                str(self.project_id),
            )
        )
