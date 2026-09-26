from __future__ import annotations

import json
import os
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any

from operational_intelligence_lab.models import EvidencePackage, HumanApproval


def _source_revision() -> str:
    configured = (
        os.getenv("GIT_COMMIT")
        or os.getenv("GITHUB_SHA")
        or os.getenv("SOURCE_REVISION")
    )
    if configured:
        return configured
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
        revision = result.stdout.strip()
        return revision or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def persist_lab_001_evidence(
    run_dir: Path,
    *,
    collected: dict[str, Any],
    reasoning_context: dict[str, Any],
    reasoning_result: Any,
    evidence_package: EvidencePackage,
    approval: HumanApproval | None,
) -> dict[str, str]:
    """Persist the proof chain so Lab 1 evidence survives the model conversation."""

    run_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "incident": run_dir / "incident.json",
        "context": run_dir / "context.json",
        "reasoning": run_dir / "reasoning.json",
        "reproduction": run_dir / "reproduction.json",
        "verification": run_dir / "verification.json",
        "approval": run_dir / "approval.json",
        "manifest": run_dir / "manifest.json",
    }

    _write_json(paths["incident"], collected)
    _write_json(paths["context"], reasoning_context)
    _write_json(
        paths["reasoning"],
        {
            "hypothesis": reasoning_result.hypothesis,
            "candidate_remediation": asdict(reasoning_result.candidate_remediation),
            "note": reasoning_result.note,
            "authoritative": False,
        },
    )
    _write_json(paths["reproduction"], asdict(evidence_package.reproduction))
    _write_json(
        paths["verification"],
        {
            "passed": evidence_package.simulation.passed,
            "baseline_final": evidence_package.simulation.baseline_final,
            "remediation": asdict(evidence_package.simulation.remediation),
            "cases": [asdict(case) for case in evidence_package.simulation.cases],
        },
    )
    _write_json(paths["approval"], asdict(approval) if approval is not None else None)

    manifest = {
        "lab": "AI Lab 001 - Unknown Incident",
        "run_id": evidence_package.run_id,
        "evidence_package_id": evidence_package.evidence_package_id,
        "status": evidence_package.status,
        "source_revision": _source_revision(),
        "artifacts": {name: file.name for name, file in paths.items() if name != "manifest"},
    }
    _write_json(paths["manifest"], manifest)
    return {name: str(path) for name, path in paths.items()}


def approve_persisted_lab_001_run(
    run_id: str,
    *,
    approved_by: str,
    reason: str,
    output_root: Path | None = None,
    decision: str = "APPROVED",
) -> HumanApproval:
    """Record a real post-run human decision after the evidence can be inspected."""

    normalized = decision.strip().upper()
    if normalized not in {"APPROVED", "REJECTED"}:
        raise ValueError("decision must be APPROVED or REJECTED")
    if not approved_by.strip() or not reason.strip():
        raise ValueError("approved_by and reason are required")

    run_dir = (output_root or Path(".lab-state/lab001/runs")) / run_id
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Lab 1 evidence run not found: {run_id}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    package_id = str(manifest["evidence_package_id"])
    approval = HumanApproval(
        approval_id=f"approval_{run_id}",
        evidence_package_ref=package_id,
        decision=normalized,
        scope="LEARN_DIAGNOSTIC_PATTERN",
        approved_by=approved_by.strip(),
        reason=reason.strip(),
    )
    _write_json(run_dir / "approval.json", asdict(approval))
    manifest["status"] = (
        "APPROVED_FOR_LEARNING" if normalized == "APPROVED" else "REJECTED_FOR_LEARNING"
    )
    manifest["human_approval"] = asdict(approval)
    _write_json(manifest_path, manifest)
    return approval
