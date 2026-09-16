from __future__ import annotations

from typing import Any, Protocol

WorkspaceGovernedTaskResult = Any


class WorkspaceGovernedTaskExecutionService(Protocol):
    async def run(self, **kwargs: Any) -> WorkspaceGovernedTaskResult: ...
