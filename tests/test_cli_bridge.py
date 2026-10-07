from __future__ import annotations

import asyncio
import json
import stat
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from operational_intelligence_lab.cli_bridge import make_handler
from operational_intelligence_lab.reasoning import ClaudeCliReasoningProvider
from test_reasoning_providers import _context, _payload

TOKEN = "test-token"


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    fake = tmp_path / "fake-claude"
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "sys.stdin.read()\n"
        f"print(json.dumps({{'structured_output': {json.dumps(_payload())}, 'session_id': 'bridge-1'}}))\n"
    )
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("CLAUDE_CLI", str(fake))
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(TOKEN))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_provider_reaches_host_cli_through_bridge(bridge):
    provider = ClaudeCliReasoningProvider(bridge_url=bridge, bridge_token=TOKEN)
    result = asyncio.run(provider.run(context=_context()))
    assert result.provider_name == "claude-cli"
    assert result.response_id == "bridge-1"
    assert result.evidence_refs == ("assign-c2", "remove-c1")


def test_bridge_rejects_bad_token_and_arbitrary_provider(bridge):
    bad = ClaudeCliReasoningProvider(bridge_url=bridge, bridge_token="wrong")
    with pytest.raises(RuntimeError, match="401"):
        asyncio.run(bad.run(context=_context()))

    request = urllib.request.Request(
        bridge + "/v1/reason",
        data=json.dumps({"provider": "bash", "prompt": "x", "schema": {}}).encode(),
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
    )
    with pytest.raises(urllib.error.HTTPError) as err:
        urllib.request.urlopen(request)
    assert err.value.code == 400


def test_unreachable_bridge_gives_actionable_error():
    provider = ClaudeCliReasoningProvider(bridge_url="http://127.0.0.1:9", bridge_token="t")
    with pytest.raises(RuntimeError, match="oi-cli-bridge"):
        asyncio.run(provider.run(context=_context()))
