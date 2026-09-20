# AI Labs Roadmap

Status: ACCEPTED  
Date: 2026-09-20

## Purpose

This repository is the public experimental proof layer for the Engineering OS ideas. The labs should not reproduce the private platform or any employer system. They should use small synthetic domains to prove one architectural claim at a time.

The publishing loop is:

```text
Problem / article
      ->
Small runnable lab
      ->
Deterministic evidence
      ->
Reusable architecture lesson
      ->
Engineering OS
      ->
Real product integration
```

## Article 2 foundation

Article 2, **From Events to Operational Intelligence**, introduces:

- event delivery is not the same as correct business state;
- entity-centred operational evidence;
- event, projection and runtime collectors;
- bounded investigation context;
- a small introduction to the Engineering OS planes.

The package/container scenario is the canonical public example.

Business order:

```text
1. Package P1 assigned -> C1
2. Package P1 removed from C1
3. Package P1 assigned -> C2
```

Failure delivery order:

```text
1. ASSIGN P1 -> C1
2. ASSIGN P1 -> C2
3. REMOVE P1 -> C1   (old event arrives late)
```

A naive projection can finish at `P1 -> NONE` even though the correct state is `P1 -> C2`.

## Article 3 / AI Lab 001 — Unknown Incident

Goal: prove that the OS can investigate a previously unknown operational failure without trusting model output.

Flow:

```text
simulate real failure
      ->
collect event + projection + runtime evidence
      ->
apply small Package/Container semantic model
      ->
detect invariant violation
      ->
build bounded context
      ->
one reasoning call
      ->
candidate diagnosis + candidate remediation
      ->
simulate candidate remediation
      ->
deterministically verify multiple scenarios
      ->
package evidence
      ->
human approval
```

The LLM is a reasoning resource only. Its proposal has no execution or learning authority.

Expected end state:

```text
APPROVED_FOR_LEARNING
```

Lab 001 does not claim that the learned workflow should already execute automatically.

## Article 4 / AI Lab 002 — Learn and Reuse

Goal: prove that an approved and verified solution can become reusable operational knowledge and a deterministic workflow.

Promotion split:

```text
Knowledge Spine
  stores WHAT the generalized failure pattern means

Workflow / Recipe Registry
  stores HOW the approved resolution is executed

Evidence Plane
  stores WHY the system is allowed to trust it
```

Second occurrence:

```text
new Package / Containers
      ->
collect evidence
      ->
detect same anomaly
      ->
match semantic guards
      ->
select PROVEN recipe
      ->
R0_NONE
      ->
no LLM call
      ->
execute deterministic workflow
      ->
verify
      ->
record evidence
```

A similar anomaly with different guards must not reuse the recipe. It returns to adaptive reasoning.

## Canonical adaptive rule

```text
IF
  learned pattern is PROVEN
  AND semantic guard conditions match
  AND required capability versions match
  AND environment compatibility matches
THEN
  use deterministic recipe
ELSE
  use bounded adaptive reasoning
```

This prevents "memory" from becoming blind automation.

## Future lab backlog

These are architectural directions, not frozen article titles:

1. Bounded Context / Knowledge Lens
2. Governed Capability Execution
3. Durable Workflow Composition
4. Enterprise Capability Provider
5. Cross-system Semantic Resolution
6. Model Replacement / Routing
7. Project Control as a real product integration

## Relationship to other repositories

```text
Articles
  explain the problem and result

AI Labs
  prove individual architectural claims

Engineering OS
  generalizes proven patterns into the reusable platform

Project Control
  applies the platform to a real business product
```

The OS kernel must remain domain-neutral. Package/container, construction, aviation, ERP, Jira, Oracle and similar concepts belong in domain packs, collectors or enterprise providers at the edges.
