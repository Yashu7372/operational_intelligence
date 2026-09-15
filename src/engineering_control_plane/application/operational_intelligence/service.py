from __future__ import annotations

import re
from dataclasses import dataclass

from engineering_control_plane.application.workspace.task_execution import (
    WorkspaceGovernedTaskExecutionService,
    WorkspaceGovernedTaskResult,
)
from engineering_control_plane.domain.knowledge.observations import Observation
from engineering_control_plane.domain.task.models import TaskType
from engineering_control_plane.domain.tenancy.models import OwnershipScope
from engineering_control_plane.domain.workspace.models import KnowledgeScope
from engineering_control_plane.domain.workspace.runtime_config import WorkspaceRuntimeConfig


_TOKEN = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class OperationalDiagnosisResult:
    """Observed anomaly plus the existing governed task result chosen by the OS."""

    anomaly: Observation
    anomaly_code: str
    task_shape: str
    execution: WorkspaceGovernedTaskResult


class OperationalIntelligenceService:
    """Bridge deterministic anomaly observations into the existing OS task path.

    Collectors/detectors own factual observations and evidence. This service does
    not decide whether an anomaly exists and does not invoke an LLM directly. It
    turns an already-detected anomaly into a stable task shape and delegates to
    WorkspaceGovernedTaskExecutionService. The existing StrategyRouter then
    chooses a proven deterministic recipe (R0) or bounded adaptive reasoning.
    """

    def __init__(self, workspace_tasks: WorkspaceGovernedTaskExecutionService) -> None:
        self._workspace_tasks = workspace_tasks

    async def investigate(
        self,
        *,
        anomaly: Observation,
        workspace: WorkspaceRuntimeConfig,
        repository_ids: tuple[str, ...],
        knowledge_scope: KnowledgeScope,
        provider_name: str,
        anomaly_code: str | None = None,
        concepts: tuple[str, ...] = (),
        token_budget: int | None = None,
        cost_budget: float | None = None,
        ownership: OwnershipScope | None = None,
    ) -> OperationalDiagnosisResult:
        if not anomaly.evidence_refs:
            raise ValueError(
                "operational diagnosis requires detector/collector evidence before OS reasoning"
            )

        code = self._anomaly_code(anomaly, anomaly_code)
        task_shape = self.task_shape(code)
        evidence_refs = tuple(str(item) for item in anomaly.evidence_refs)
        normalized_concepts = tuple(
            dict.fromkeys(
                (
                    code,
                    anomaly.subject.entity_type,
                    anomaly.predicate,
                    anomaly.object.entity_type,
                    *concepts,
                )
            )
        )
        description = (
            f"Investigate observed operational anomaly {code}. "
            f"Observed relation: {anomaly.subject.entity_type} "
            f"{anomaly.subject.identity} {anomaly.predicate} "
            f"{anomaly.object.entity_type} {anomaly.object.identity}. "
            f"Evidence refs: {', '.join(evidence_refs)}. "
            "Use bounded workspace evidence and Knowledge Spine context. "
            "Any model-produced cause is a claim until reproduced and "
            "deterministically verified by governed capabilities."
        )
        expected_outcome = (
            "Evidence-backed operational diagnosis with deterministic verification; "
            "reuse a proven diagnostic recipe without model reasoning when one is compatible."
        )

        execution = await self._workspace_tasks.run(
            workspace=workspace,
            repository_ids=repository_ids,
            knowledge_scope=knowledge_scope,
            provider_name=provider_name,
            description=description,
            expected_outcome=expected_outcome,
            concepts=normalized_concepts,
            task_type=TaskType.OPERATIONAL_DIAGNOSIS,
            task_shape=task_shape,
            token_budget=token_budget,
            cost_budget=cost_budget,
            ownership=ownership,
        )
        return OperationalDiagnosisResult(
            anomaly=anomaly,
            anomaly_code=code,
            task_shape=task_shape,
            execution=execution,
        )

    @staticmethod
    def task_shape(anomaly_code: str) -> str:
        normalized = _TOKEN.sub("-", anomaly_code.strip().lower()).strip("-")
        if not normalized:
            raise ValueError("anomaly code must contain a stable token")
        return f"operational-diagnosis:{normalized}"

    @staticmethod
    def _anomaly_code(anomaly: Observation, supplied: str | None) -> str:
        candidates = (
            supplied,
            anomaly.subject.attributes.get("anomaly_code"),
            anomaly.object.attributes.get("anomaly_code"),
            anomaly.predicate,
        )
        for candidate in candidates:
            if candidate is None:
                continue
            value = str(candidate).strip()
            if value:
                return value.upper()
        raise ValueError("anomaly observation does not contain a stable anomaly code")
