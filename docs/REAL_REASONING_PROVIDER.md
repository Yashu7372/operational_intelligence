# Real reasoning provider for Lab 1

Lab 1 keeps the credential-free deterministic reasoning seam as its default, but it can also make one real OpenAI Responses API call against the exact same bounded incident context.

## Install

Python 3.12+:

    python -m pip install -e ".[dev,ai]"

Set OPENAI_API_KEY in your shell. Do not commit the key.

PowerShell:

    $env:OPENAI_API_KEY="your-key"

Bash/zsh:

    export OPENAI_API_KEY="your-key"

## Run with a real model

Low-cost default model:

    operational-intelligence-lab --lab 1 --reasoning-provider openai

Choose a model explicitly:

    operational-intelligence-lab --lab 1 --reasoning-provider openai --model gpt-5.6-sol

For the Article 3 evidence run, preserve the deterministic reference result beside the real model result:

    operational-intelligence-lab --lab 1 --reasoning-provider openai --model gpt-5.6-sol --compare-with-deterministic

The run still stops at READY_FOR_HUMAN_REVIEW.

Inspect:

    .lab-state/lab001/runs/<run-id>/

reasoning.json records the selected provider, model, response ID, token counts, structured model result, candidate remediation, and, when comparison mode is enabled, the deterministic reference and comparison.

The model is never execution authority. The candidate must still map to a registered remediation contract, reproduce the incident in the controlled simulator, and pass deterministic verification.

After inspecting the evidence:

    operational-intelligence-lab --approve-run <run-id> --approved-by "your-name" --approval-reason "reviewed real model reasoning, reproduction and deterministic verification"

Only explicit review moves the persisted run to APPROVED_FOR_LEARNING.
