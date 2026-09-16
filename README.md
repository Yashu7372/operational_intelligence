# Operational Intelligence Learning Loop

A public, runnable reference lab for the idea:

```text
OBSERVE -> DETECT -> REASON -> REPRODUCE -> VERIFY -> LEARN -> REUSE
```

The core question is simple:

> Can AI help investigate an unknown operational incident once, then let the system diagnose the same verified pattern deterministically the next time?

This repository contains the public learning-loop slice extracted from a larger private Engineering Control Plane. The private platform is not required to run this lab.

## Scenario

Business/event-time order:

```text
1. P1 assigned -> C1
2. P1 changed C1 -> C2
3. C2 arrived
```

Observed delivery order:

```text
1. P1 assigned -> C1
2. C2 arrived
3. P1 changed C1 -> C2   (late)
```

During the delivery gap the projection says `P1 -> C1`, while independent operational evidence says `P1 -> C2`.

The deterministic detector produces:

```text
RELATIONSHIP_PROJECTION_MISMATCH
```

On the first occurrence there is no proven recipe, so the lab invokes a bounded reasoning seam to form a hypothesis. The hypothesis has no authority by itself. The lab then reproduces the suspected ordering condition, verifies the result deterministically, promotes only the generalized diagnosis, and records a reusable verified workflow recipe.

On the next occurrence the same stable task shape resolves through the proven recipe:

```text
DETERMINISTIC_RECIPE / R0_NONE
LLM required = false
```

## Repository layout

```text
config/
  knowledge-requirements.yaml

docs/
  OPERATIONAL_INTELLIGENCE_LEARNING_LOOP.md

src/engineering_control_plane/
  application/operational_intelligence/
    service.py
    learning.py
  application/strategy/
    promotion.py
    router.py
  domain/
    ...minimal public contracts used by the extracted slice

src/operational_intelligence_lab/
  run.py

tests/
  test_operational_intelligence_learning_loop.py
  test_runnable_lab.py

Dockerfile
compose.yaml
pyproject.toml
requirements.txt
```

The `engineering_control_plane` package in this public repo is deliberately a **minimal contract subset**, not the full private Control Plane. It exists only so the extracted operational-intelligence slice is independently runnable and testable.

## Run with Docker

```bash
docker compose up --build --abort-on-container-exit
```

No local Python installation or API key is required.

## Run locally

Requires Python 3.12+.

```bash
python -m venv .venv
```

macOS/Linux:

```bash
source .venv/bin/activate
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Install and run:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
operational-intelligence-lab
```

Machine-readable output:

```bash
operational-intelligence-lab --json
```

## Expected result

```text
1. OBSERVE   live event delivery creates a temporary relationship mismatch
2. DETECT    RELATIONSHIP_PROJECTION_MISMATCH
3. REASON    first occurrence -> ADAPTIVE_REASONING / R1_LIGHT
4. REPRODUCE hold relationship change -> emit arrival -> release delayed change
5. VERIFY    mismatch reproduced and final state converges
6. LEARN     generalized diagnosis + verified recipe promoted
7. REUSE     next occurrence -> DETERMINISTIC_RECIPE / R0_NONE

LLM required on known path = false
```

## Run tests

```bash
python -m pip install -e ".[dev]"
pytest -q
```

The tests verify that runtime identities such as `P1`, `C1`, and `C2` do not become reusable knowledge and that a proven compatible diagnosis routes to deterministic R0 execution.

## Reasoning boundary

The public lab intentionally uses a credential-free deterministic fixture at the bounded reasoning seam. This keeps Docker and CI reproducible. In a full platform that seam can be backed by an LLM provider, but model output remains a hypothesis until deterministic reproduction and verification succeed.

## License

MIT.
