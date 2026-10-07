# Real reasoning provider for Lab 1

Lab 1 keeps the credential-free deterministic reasoning seam as its default, but it can also make one real model call against the exact same bounded incident context, through the OpenAI Responses API (API key) or a local Claude Code / Codex CLI (its own login, no API key).

## Install

Python 3.12+:

    python -m pip install -e ".[dev,ai]"

Set OPENAI_API_KEY in your shell. Do not commit the key.

PowerShell:

    $env:OPENAI_API_KEY="your-key"

Bash/zsh:

    export OPENAI_API_KEY="your-key"

## Use a local Claude Code or Codex CLI instead of an API key

Install and sign in to the CLI once (`claude` or `codex`); the adapter shells out to it non-interactively.

    operational-intelligence-lab --lab 1 --reasoning-provider claude-cli
    operational-intelligence-lab --lab 1 --reasoning-provider codex-cli --model <codex-model>

Same bounded context, same JSON schema, same validation as the OpenAI provider (evidence refs must exist in the journal, the candidate must match the registered remediation contract). Claude runs with tools disabled; Codex runs in a read-only sandbox. Override the executable with `CLAUDE_CLI` / `CODEX_CLI`. `--model` is optional; without it the CLI's configured model is used. `--compare-with-deterministic` works with these too.

## Run in Docker, using the CLI logged in on your laptop

A container cannot use your laptop's `claude`/`codex` binary or login (different OS; on macOS the login is in the Keychain). Instead, run a small bridge on the laptop and point the container at it. The bridge only accepts `claude-cli`/`codex-cli` requests with a bearer token and builds the CLI command itself (Claude with tools disabled, Codex read-only); callers cannot send arbitrary commands.

1. On the laptop (where `claude` works), install the package and start the bridge:

       python -m pip install -e .
       export CLI_BRIDGE_TOKEN="$(python -c 'import secrets;print(secrets.token_urlsafe(24))')"
       oi-cli-bridge --host 0.0.0.0 --port 8765

   Docker Desktop (Mac/Windows) also works with the default `--host 127.0.0.1`. On Linux the container reaches the host via the docker bridge, so use `--host 0.0.0.0` (and firewall the port from the network; the token is the only protection).

2. In another terminal, with the same token exported:

       docker compose --profile host-cli up --build lab-claude-cli

   This sets `CLI_BRIDGE_URL=http://host.docker.internal:8765`. The plain `operational-intelligence-lab` service is unchanged and still credential-free.

For `docker run` instead of compose: `-e CLI_BRIDGE_URL=http://host.docker.internal:8765 -e CLI_BRIDGE_TOKEN --add-host host.docker.internal:host-gateway ... --reasoning-provider claude-cli`. The same works for `codex-cli` if Codex is the one installed on the laptop. Quick check from the container side: `curl http://host.docker.internal:8765/healthz`.

## Run with a real model (OpenAI API)

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
