from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any


def write_dashboard(
    path: Path,
    *,
    collected: dict[str, Any],
    anomaly_code: str,
) -> Path:
    """Write a zero-dependency operational dashboard suitable for the public lab."""

    path.parent.mkdir(parents=True, exist_ok=True)
    events = collected.get("event_journal", [])
    package_id = str(events[0].get("package_id", "UNKNOWN")) if events else "UNKNOWN"
    expected = collected.get("expected_container")
    observed = collected.get("final_container")
    rows = "".join(
        "<tr>"
        f"<td>{escape(str(item.get('received_sequence')))}</td>"
        f"<td>{escape(str(item.get('kind')))}</td>"
        f"<td>{escape(str(item.get('container_id')))}</td>"
        f"<td>{escape(str(item.get('business_sequence')))}</td>"
        "</tr>"
        for item in events
    )
    status = "ANOMALY" if expected != observed else "NORMAL"
    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Operational Intelligence Lab Dashboard</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 0; background: #f5f7fb; color: #172033; }}
main {{ max-width: 980px; margin: 40px auto; padding: 0 20px; }}
.grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }}
.card {{ background: white; border-radius: 12px; padding: 20px; box-shadow: 0 4px 16px rgba(0,0,0,.07); }}
.label {{ color: #657089; font-size: 13px; text-transform: uppercase; }}
.value {{ font-size: 24px; font-weight: 700; margin-top: 8px; }}
.bad {{ color: #b42318; }} .good {{ color: #137333; }}
table {{ width: 100%; border-collapse: collapse; background: white; margin-top: 20px; }}
th, td {{ padding: 12px; border-bottom: 1px solid #e7eaf0; text-align: left; }}
.banner {{ margin: 20px 0; padding: 16px 20px; background: #fff1f0; border: 1px solid #f2b8b5; border-radius: 10px; }}
</style>
</head>
<body><main>
<h1>Operations Dashboard</h1>
<div class="grid">
  <div class="card"><div class="label">Package</div><div class="value">{escape(package_id)}</div></div>
  <div class="card"><div class="label">Observed container</div><div class="value bad">{escape(str(observed or 'NONE'))}</div></div>
  <div class="card"><div class="label">Expected container</div><div class="value good">{escape(str(expected or 'NONE'))}</div></div>
</div>
<div class="banner"><strong>{escape(status)}:</strong> {escape(anomaly_code)}</div>
<table>
<thead><tr><th>Received</th><th>Event</th><th>Container</th><th>Business seq</th></tr></thead>
<tbody>{rows}</tbody>
</table>
</main></body></html>"""
    path.write_text(html, encoding="utf-8")
    return path
