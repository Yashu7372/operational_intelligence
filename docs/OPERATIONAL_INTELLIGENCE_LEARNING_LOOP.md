# Operational Intelligence Learning Loop

Status: implementation slice on top of the frozen Control Plane architecture.

This document does **not** introduce a second runtime, knowledge system, simulator, or agent authority. It connects already-implemented Control Plane seams into one operational diagnosis loop.

## Product boundaries

### Application Workspace

A separate small production-like application is the system being observed. It owns its application code, database, UI, producer, and natural operational event flow. A late/out-of-order event in the first incident is application/runtime behaviour, **not** an OS simulation.

### Engineering Control Plane

The Control Plane owns governed observation-to-diagnosis execution. Existing components remain authoritative:

- collectors produce `Observation`, `EvidenceRecord`, and diagnostics;
- evidence remains in the Evidence Plane;
- `WorkspaceGovernedTaskExecutionService` binds the application workspace;
- `StrategyRouter` chooses deterministic recipe reuse or adaptive reasoning;
- `ExecutionRecipe` / `WorkflowDefinition` remain the OS execution contract;
- `GraphRuntimePort` keeps LangGraph replaceable;
- simulation remains a capability behind the capability/runtime boundary;
- model output remains a claim until deterministic verification;
- `KnowledgePromotionService` owns canonical knowledge promotion;
- `RecipePromotionService` owns evidence-backed workflow maturity.

### Knowledge Spine

The Knowledge Spine owns reusable semantics and evidence-backed learned diagnostic knowledge. It does not store live parcel/container ids, timestamps, current projection state, or other runtime incident instances.

### LLM

An LLM is used only when deterministic knowledge/recipes are insufficient. It may reason over bounded evidence and Knowledge Spine context and propose a diagnosis/reproduction plan. It does not decide anomaly truth, execute capabilities directly, verify success, or promote knowledge.

## Closed loop

```text
Application Workspace
        |
        | production-like events
        v
Collectors / Observations / Evidence
        |
        v
Deterministic anomaly detector
        |
        v
OperationalIntelligenceService
        |
        v
WorkspaceGovernedTaskExecutionService
        |
        v
StrategyRouter
   |                 |
   | known/proven    | unknown
   v                 v
R0 deterministic   bounded adaptive reasoning
recipe             (LLM may participate)
   |                 |
   +--------+--------+
            v
     governed diagnostic
     reproduction/simulation
            |
            v
     deterministic VERIFY
            |
            v
VerifiedDiagnosisLearningService
      |                    |
      v                    v
KnowledgePromotion   RecipePromotion
      |                    |
      +---------+----------+
                v
               LEARN
```

## First occurrence

A detector emits an evidence-backed anomaly observation such as `RELATIONSHIP_PROJECTION_MISMATCH`. `OperationalIntelligenceService` derives a stable task shape from the anomaly type, not from runtime identities such as P1/C1/C2, and delegates to the existing workspace-governed task path.

When no proven compatible diagnostic recipe exists, the current Strategy Router uses adaptive reasoning. The LLM may form a hypothesis such as `LATE_RELATIONSHIP_EVENT`, but that remains a claim. The OS must reproduce the suspected event ordering through existing simulation capabilities and create deterministic verification evidence before learning is allowed.

## VERIFY -> LEARN

`VerifiedDiagnosisLearningService` accepts only a generalized diagnosis after deterministic reproduction/verification. Runtime instance values are intentionally absent from its input contract. It records a generalized Observation through `KnowledgePromotionService` and records the verified diagnostic DAG through `RecipePromotionService`.

Example learned shape:

```text
OPERATIONAL_ANOMALY_PATTERN
  RELATIONSHIP_PROJECTION_MISMATCH
        ASSOCIATED_WITH
VERIFIED_FAILURE_MODE
  LATE_RELATIONSHIP_EVENT

conditions:
- relationship_change.event_time < arrival.event_time
- relationship_change.received_time > arrival.received_time
- projection_relationship != observed_relationship
- projection_converges_after_relationship_event == true
```

Concrete runtime values remain referenced only by Evidence ids.

## Later occurrence

For the same stable task shape, the existing promotion policy decides when the diagnostic workflow is mature enough to become `PROVEN`. Once it is proven and its capability/environment compatibility still matches, `StrategyRouter` selects:

```text
ExecutionStrategy.DETERMINISTIC_RECIPE
ReasoningTier.R0_NONE
```

No model invocation is required for that diagnosis path. The OS can execute the already-verified recipe, confirm the required evidence conditions, and notify the human with the known diagnosis and provenance.

The default production policy deliberately requires multiple verified runs before a recipe becomes `PROVEN`. A local portfolio/demo profile may use a stricter controlled-reproduction assumption and lower the injected `RecipePromotionPolicy` threshold without changing the router or execution architecture.

## Repository split

This branch modifies only `engineering-control-plane` integration seams. The intended ecosystem remains:

```text
operational-intelligence-workspace
  small production-like application being observed

engineering-control-plane
  observe -> diagnose -> reproduce -> verify -> learn

knowledge-spine
  semantic context + promoted verified patterns/history

architecture-vault
  external knowledge acquisition; outside this runtime loop

portfolio
  public-safe explanation and evidence projection
```

The dummy application must remain outside generic OS domain code. Parcel/container names may appear in a demo workspace or evidence fixture, never as Control Plane execution rules.
