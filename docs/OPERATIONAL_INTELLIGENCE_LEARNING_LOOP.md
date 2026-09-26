# Operational Intelligence Learning Loop

Status: implementation slice aligned with the frozen Engineering OS direction.

This repository demonstrates a small public version of the closed loop without introducing a second OS, knowledge system or agent authority.

## Core rule

```text
Model reasoning proposes.
Simulation reproduces.
Deterministic verification proves.
Human governance authorizes learning.
Knowledge + workflow registries enable safe reuse.
```

## Product boundaries

### Application / simulation workspace

The package/container scenario is synthetic business behavior. Domain names and event rules remain outside the generic OS contracts.

### Collectors / Evidence Plane

Collectors subscribe while the synthetic application runs and gather the smallest useful incident story:

- event journal;
- projection transitions;
- runtime signals;
- expected versus observed relationship.

Runtime identities remain evidence. They are not promoted as reusable knowledge.

### Knowledge Spine

The tiny domain pack describes:

```text
Package
Container
Package --assignedTo--> Container
one-active-container invariant
projection-matches-business-history invariant
```

The Knowledge Spine also receives only generalized, human-approved diagnostic patterns after verification.

### Model runtime

A model is used only for an unknown case when no proven compatible recipe exists. Its output is a candidate diagnosis/remediation, not truth and not authority.

### Workflow / strategy runtime

`StrategyRouter` selects the lightest sufficient path:

```text
PROVEN recipe
+ matching generalized guards
+ matching capability versions
+ compatible environment
    -> DETERMINISTIC_RECIPE / R0_NONE

otherwise
    -> ADAPTIVE_REASONING
```

## AI Lab 001 — first occurrence

The Article 2 business order is:

```text
ASSIGN P1 -> C1
REMOVE P1 -> C1
ASSIGN P1 -> C2
```

The failure delivery order is:

```text
ASSIGN P1 -> C1
ASSIGN P1 -> C2
REMOVE P1 -> C1   (late)
```

The baseline implementation intentionally applies the old removal after the newer assignment and finishes with `P1 -> NONE`.

The loop is:

```text
production-like scenario
  ->
live collection
  ->
semantic expected-state resolution
  ->
deterministic mismatch detection
  ->
bounded reasoning
  ->
candidate STALE_RELATIONSHIP_EVENT_GUARD_V1
  ->
simulate multiple cases
  ->
verify all required cases
  ->
evidence package
  ->
human approval
```

The candidate rejects a relationship event when its business sequence is older than the newest accepted transition.

Required public verification cases include:

- Article 2 late removal;
- normal event order;
- duplicate newer assignment;
- retry of the late removal.

Lab 001 first ends at `READY_FOR_HUMAN_REVIEW`. An explicit human review is required to transition the evidence package to `APPROVED_FOR_LEARNING`. The run also persists a dashboard and evidence manifest under `.lab-state/lab001/runs/<run-id>/`.

## VERIFY -> APPROVE -> LEARN

`VerifiedDiagnosisLearningService` now requires a `LearningApproval` before promotion.

The generalized knowledge shape is:

```text
OPERATIONAL_ANOMALY_PATTERN
  RELATIONSHIP_PROJECTION_MISMATCH
        ASSOCIATED_WITH
VERIFIED_FAILURE_MODE
  LATE_STALE_RELATIONSHIP_REMOVAL
```

Generalized preconditions are stored separately from runtime evidence:

```text
event.kind == PACKAGE_REMOVED
event.business_sequence < projection.last_business_sequence
newer_package_assignment_already_applied == true
projection_relationship != expected_relationship
```

The workflow recipe stores the deterministic execution shape. The evidence plane retains the incident-specific reason the pattern was trusted.

## AI Lab 002 — later occurrence

A second incident uses different runtime data:

```text
P77
C10
C11
```

The same structural failure produces the same generalized guards.

The router can therefore choose:

```text
ExecutionStrategy.DETERMINISTIC_RECIPE
ReasoningTier.R0_NONE
```

No second model call is required. The deterministic workflow applies the approved stale-event guard and verifies the final projection.

## Safety fallback

An anomaly name by itself is not enough for reuse.

If `RELATIONSHIP_PROJECTION_MISMATCH` occurs but the learned guards do not all match, the recipe is not selected:

```text
same anomaly code
+ different/incomplete preconditions
    -> ADAPTIVE_REASONING
```

This is the key difference between adaptive learning and blind memorization.

## Public/private split

```text
AI Labs
  synthetic proof and evidence

Engineering OS
  generalized runtime, policy, workflow, knowledge and capability architecture

Project Control
  real personal product/domain integration

Employer systems
  never copied into this public repository
```

The roadmap in `AI_LABS_ROADMAP.md` is the durable outline for the article/lab progression.
