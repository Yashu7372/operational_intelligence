from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from engineering_control_plane.domain.common.ids import PlanId


class WorkflowNode(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    capability: str
    operation: str
    input: dict[str, Any] = Field(default_factory=dict)
    depends_on: tuple[str, ...] = ()


class WorkflowDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    version: str = "1.0"
    nodes: tuple[WorkflowNode, ...]

    def validate_dag(self) -> None:
        by_id = {node.id: node for node in self.nodes}
        if len(by_id) != len(self.nodes):
            raise ValueError("workflow node ids must be unique")
        for node in self.nodes:
            for dependency in node.depends_on:
                if dependency not in by_id:
                    raise ValueError(f"unknown dependency: {dependency}")
                if dependency == node.id:
                    raise ValueError("workflow node cannot depend on itself")

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in visited:
                return
            if node_id in visiting:
                raise ValueError("workflow contains a dependency cycle")
            visiting.add(node_id)
            for dependency in by_id[node_id].depends_on:
                visit(dependency)
            visiting.remove(node_id)
            visited.add(node_id)

        for node_id in by_id:
            visit(node_id)

    def plan_id(self) -> PlanId:
        payload = self.model_dump(mode="json")
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return PlanId(value=f"plan_{digest[:32]}")
