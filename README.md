# Operational Intelligence AI Labs

A public, runnable reference for one core Engineering OS idea:

> Use model reasoning to investigate an unknown operational problem, prove the proposal with deterministic simulation and evidence, require human approval before learning, then reuse the verified workflow without another model call when the same guarded pattern appears again.

The repository now contains two connected labs aligned to the article series.

## Article 2 scenario

Business truth:

```text
1. Package P1 assigned -> C1
2. Package P1 removed from C1
3. Package P1 assigned -> C2
```

Observed processing order:

```text
1. ASSIGN P1 -> C1
2. ASSIGN P1 -> C2
3. REMOVE P1 -> C1   (old event arrives late)
```

The deliberately naive projection clears the package on the late removal and finishes at:

```text
P1 -> NONE
```

while the correct operational state is:

```text
P1 -> C2
```

## AI Lab 001 — Unknown Incident

Aligned to Article 3.

```text
SIMULATE FAILURE
      ->
COLLECT event + projection + runtime evidence
      ->
KNOW Package --assignedTo--> Container
      ->
DETECT invariant violation
      ->
BUILD bounded context
      ->
ONE bounded reasoning call
      ->
candidate diagnosis + remediation
      ->
SIMULATE candidate
      ->
VERIFY multiple deterministic cases
      ->
EVIDENCE PACKAGE
      ->
HUMAN APPROVAL
```

The model proposal is never treated as truth. The lab ends at:

```text
APPROVED_FOR_LEARNING
```

## AI Lab 002 — Learn and Reuse

Aligned to Article 4.

The approved Lab 001 result is split across the right responsibilities:

```text
Knowledge Spine
  WHAT the generalized failure pattern means

Workflow / Recipe Registry
  HOW the verified recovery is executed

Evidence Plane
  WHY the system is allowed to trust it
```

A later incident using different runtime identities is matched against the learned guards. When the guards, capability versions and environment are compatible, the router selects:

```text
DETERMINISTIC_RECIPE / R0_NONE
LLM required = false
```

The lab also tests the safety case: the same anomaly code with different/incomplete guards must fall back to adaptive reasoning.

## Small semantic layer

The public domain pack lives at:

```text
config/domain/package-container.yaml
```

It defines only the semantics needed by the lab:

```text
Package
Container
Package --assignedTo--> Container
Invariant: one active container assignment
PACKAGE_ASSIGNED
PACKAGE_REMOVED
```

Package/container knowledge remains outside the generic Engineering Control Plane contracts.

## Repository layout

```text
config/
  knowledge-requirements.yaml
  domain/
    package-container.yaml

docs/
  OPERATIONAL_INTELLIGENCE_LEARNING_LOOP.md
  AI_LABS_ROADMAP.md

src/engineering_control_plane/
  application/
  domain/
  ports/

src/operational_intelligence_lab/
  collectors.py
  knowledge.py
  models.py
  simulation.py
  lab_001_unknown_incident.py
  lab_002_learned_reuse.py
  run.py

tests/
  test_operational_intelligence_learning_loop.py
  test_runnable_lab.py
  test_lab_001_unknown_incident.py
  test_lab_002_learned_reuse.py
```

The `engineering_control_plane` package is a deliberately small public contract subset. It is not the complete private Engineering OS.

## Run

Docker:

```bash
docker compose up --build --abort-on-container-exit
```

Local Python 3.12+:

```bash
python -m pip install -e ".[dev]"
operational-intelligence-lab
```

Run one lab:

```bash
operational-intelligence-lab --lab 1
operational-intelligence-lab --lab 2
```

Machine-readable output:

```bash
operational-intelligence-lab --json
```

Tests:

```bash
pytest -q
```

## Architectural boundaries

- collectors establish observations and evidence;
- the semantic/domain pack explains what Package, Container and `assignedTo` mean;
- the LLM is a bounded reasoning resource, not execution authority;
- simulation and deterministic verification establish whether the proposal works;
- human approval is required before verified behavior is promoted;
- reusable knowledge contains generalized conditions, not P1/C1/C2 runtime identities;
- deterministic reuse requires matching learned guards, capabilities and environment;
- a guard mismatch returns to adaptive reasoning.

See `docs/AI_LABS_ROADMAP.md` for the article/lab sequence and future outline.

## License

MIT.
