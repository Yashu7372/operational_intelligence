"""Host-side bridge so a containerised lab can use the CLIs logged in on the host.

Run on the machine where `claude` / `codex` are installed and signed in:

    oi-cli-bridge --host 0.0.0.0 --port 8765

The container sets CLI_BRIDGE_URL and CLI_BRIDGE_TOKEN. The bridge never accepts
an argv from the caller: it only accepts a provider name, optional model, prompt
and schema, and builds the CLI invocation itself with tools disabled / read-only.
"""

from __future__ import annotations

import argparse
import asyncio
import hmac
import json
import os
import re
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from operational_intelligence_lab.reasoning import (
    ClaudeCliReasoningProvider,
    CodexCliReasoningProvider,
)

BRIDGE_PATH = "/v1/reason"
MAX_BODY_BYTES = 2_000_000
_MODEL_RE = re.compile(r"^[A-Za-z0-9._:\-\[\]]{1,100}$")
_PROVIDERS = {
    "claude-cli": ClaudeCliReasoningProvider,
    "codex-cli": CodexCliReasoningProvider,
}


def handle_request(body: dict[str, Any]) -> dict[str, Any]:
    provider_cls = _PROVIDERS.get(str(body.get("provider")))
    if provider_cls is None:
        raise ValueError("provider must be one of: " + ", ".join(sorted(_PROVIDERS)))
    prompt, schema, model = body.get("prompt"), body.get("schema"), body.get("model")
    if not isinstance(prompt, str) or not prompt or not isinstance(schema, dict):
        raise ValueError("prompt (string) and schema (object) are required")
    if model is not None and not (isinstance(model, str) and _MODEL_RE.match(model)):
        raise ValueError("invalid model name")
    provider = provider_cls(model_name=model)
    payload, meta = asyncio.run(provider._invoke(prompt, schema))
    return {"payload": payload, "meta": meta}


def make_handler(token: str) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _reply(self, status: int, body: dict[str, Any]) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:  # health check, no auth, no data
            if self.path == "/healthz":
                self._reply(200, {"status": "ok"})
            else:
                self._reply(404, {"error": "not found"})

        def do_POST(self) -> None:
            supplied = self.headers.get("Authorization", "")
            if not hmac.compare_digest(supplied, f"Bearer {token}"):
                self._reply(401, {"error": "unauthorized"})
                return
            if self.path != BRIDGE_PATH:
                self._reply(404, {"error": "not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_BODY_BYTES:
                    raise ValueError("invalid request size")
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError("body must be a JSON object")
                self._reply(200, handle_request(body))
            except (ValueError, json.JSONDecodeError) as exc:
                self._reply(400, {"error": str(exc)})
            except Exception as exc:  # CLI failure, timeout, bad CLI output
                self._reply(502, {"error": str(exc)[:1000]})

        def log_message(self, fmt: str, *args: Any) -> None:
            print(f"[bridge] {self.address_string()} {fmt % args}", flush=True)

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="Host bridge for claude / codex CLIs.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    token = os.getenv("CLI_BRIDGE_TOKEN")
    if not token:
        token = secrets.token_urlsafe(24)
        print(f"CLI_BRIDGE_TOKEN not set; generated one for this run:\n  {token}", flush=True)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(token))
    print(f"CLI bridge listening on http://{args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
