from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from engineering_control_plane.domain.workflow.models import WorkflowDefinition


class ReasoningTier(StrEnum):
    NONE = "R0_NONE"
    LIGHT = "R1_LIGHT"
    STANDARD = "R2_STANDARD"
    DEEP = "R3_DEEP"
    SPECIALIZED = "R4_SPECIALIZED"


class ExecutionStrategy(StrEnum):
    DETERMINISTIC_RECIPE = "DETERMINISTIC_RECIPE"
    ADAPTIVE_REASONING = "ADAPTIVE_REASONING"


class RecipeMaturity(StrEnum):
    CANDIDATE = "CANDIDATE"
    EVIDENCE_SUPPORTED = "EVIDENCE_SUPPORTED"
    RUNTIME_VERIFIED = "RUNTIME_VERIFIED"
    PROVEN = "PROVEN"
    STALE = "STALE"


class ProvenWorkflowRecipe(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    recipe_id: str = Field(min_length=1)
    task_shape: str = Field(min_length=1)
    maturity: RecipeMaturity
    definition: WorkflowDefinition
    preconditions: tuple[str, ...] = ()
    capability_versions: dict[str, str] = Field(default_factory=dict)
    source_run_ids: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    context_lens: str | None = None
    knowledge_revision: str | None = None
    environment_fingerprint: str | None = None
    supersedes: str | None = None


class StrategyAssessment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    task_shape: str = Field(min_length=1)
    knowledge_sufficient: bool
    context_sufficient: bool
    observed_conditions: tuple[str, ...] = ()
    available_capability_versions: dict[str, str] = Field(default_factory=dict)
    environment_fingerprint: str | None = None


class StrategyDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy: ExecutionStrategy
    reasoning_tier: ReasoningTier
    recipe_id: str | None = None
    reason: str
