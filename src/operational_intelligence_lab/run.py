from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from operational_intelligence_lab.lab_001_unknown_incident import run_lab_001
from operational_intelligence_lab.lab_002_learned_reuse import run_lab_002
from operational_intelligence_lab.evidence import approve_persisted_lab_001_run
from operational_intelligence_lab.models import HumanReviewDecision


def _review(
    *,
    approve_learning: bool,
    approved_by: str | None,
    approval_reason: str | None,
) -> HumanReviewDecision | None:
    if not approve_learning:
        return None
    if not approved_by or not approved_by.strip():
        raise ValueError("--approved-by is required with --approve-learning")
    return HumanReviewDecision(
        decision="APPROVED",
        approved_by=approved_by.strip(),
        reason=(approval_reason or "reviewed deterministic Lab 1 evidence").strip(),
    )


async def run_demo(review: HumanReviewDecision) -> dict[str, Any]:
    discovery = await run_lab_001(review=review)
    reuse = await run_lab_002(discovery)
    return {
        "lab_001": discovery.summary,
        "lab_002": reuse,
    }


def _print_lab_001(summary: dict[str, Any]) -> None:
    print("\nAI Lab 001 — Unknown Incident")
    print("=" * 33)
    print(f"RUN          {summary['run_id']}")
    print("1. OBSERVE   live collector watches event + projection transitions")
    print(
        "2. DETECT    "
        f"{summary['live_detection']['anomaly']['code']} -> "
        f"observed={summary['baseline_final_projection']}"
    )
    print("3. KNOW      Package --assignedTo--> Container + projection consistency")
    print(
        "4. REASON    "
        f"{summary['routing']['strategy']} / {summary['routing']['reasoning_tier']} "
        f"(calls={summary['reasoning']['calls']})"
    )
    print(f"             Hypothesis: {summary['reasoning']['hypothesis']}")
    print(
        "5. REPRODUCE "
        f"delivery order = {summary['reproduction']['delivery_order']} -> "
        f"mismatch = {summary['reproduction']['mismatch_reproduced']}"
    )
    print("6. VERIFY    candidate remediation against four deterministic cases")
    print(f"             all candidate cases passed = {summary['simulation']['passed']}")
    print(f"7. EVIDENCE  {summary['evidence']['manifest']}")
    print(f"8. DASHBOARD {summary['dashboard']}")
    if summary["human_approval"] is None:
        print("9. APPROVE   pending explicit human review")
    else:
        print(
            "9. APPROVE   "
            f"{summary['human_approval']['decision']} -> {summary['result']}"
        )


def _print_lab_002(summary: dict[str, Any]) -> None:
    print("\nAI Lab 002 — Learn and Reuse")
    print("=" * 31)
    print(
        "1. LEARN     human-approved generalized pattern -> "
        f"{summary['promotion']['recipe_maturity']}"
    )
    print(
        "2. REUSE     new runtime identities -> "
        f"{summary['known_occurrence']['strategy']} / "
        f"{summary['known_occurrence']['reasoning_tier']}"
    )
    print(
        "3. NO LLM    "
        f"required = {summary['known_occurrence']['llm_required']} "
        f"(total reasoning calls={summary['known_occurrence']['reasoning_calls_total']})"
    )
    print(
        "4. VERIFY    corrected projection -> "
        f"{summary['known_occurrence']['final_projection']}"
    )


async def _run_selected(
    lab: str,
    *,
    review: HumanReviewDecision | None,
) -> dict[str, Any]:
    if lab == "1":
        first = await run_lab_001(review=review)
        return {"lab_001": first.summary}
    if review is None:
        raise ValueError("Lab 2/all requires explicit Lab 1 approval via --approve-learning")
    if lab == "2":
        first = await run_lab_001(review=review)
        second = await run_lab_002(first)
        return {"lab_002": second}
    return await run_demo(review)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the public Operational Intelligence AI Labs."
    )
    parser.add_argument(
        "--lab",
        choices=("1", "2", "all"),
        default="1",
        help="Run AI Lab 001, AI Lab 002, or the complete learning loop.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument(
        "--approve-learning",
        action="store_true",
        help="Demo path for Lab 2/all: explicitly approve a fresh Lab 1 result.",
    )
    parser.add_argument(
        "--approve-run",
        metavar="RUN_ID",
        help="Approve an already-persisted Lab 1 run after reviewing its evidence.",
    )
    parser.add_argument("--approved-by", help="Human reviewer identity for approval evidence.")
    parser.add_argument("--approval-reason", help="Reason recorded with human approval.")
    args = parser.parse_args()

    if args.approve_run:
        if args.approve_learning:
            parser.error("--approve-run cannot be combined with --approve-learning")
        if not args.approved_by or not args.approved_by.strip():
            parser.error("--approved-by is required with --approve-run")
        if not args.approval_reason or not args.approval_reason.strip():
            parser.error("--approval-reason is required with --approve-run")
        try:
            approval = approve_persisted_lab_001_run(
                args.approve_run,
                approved_by=args.approved_by,
                reason=args.approval_reason,
            )
        except (ValueError, FileNotFoundError) as exc:
            parser.error(str(exc))
        payload = {
            "run_id": args.approve_run,
            "decision": approval.decision,
            "approved_by": approval.approved_by,
            "evidence_package_ref": approval.evidence_package_ref,
            "status": "APPROVED_FOR_LEARNING",
        }
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(f"Approved Lab 1 run {args.approve_run} for learning.")
        return

    if args.lab == "1" and args.approve_learning:
        parser.error(
            "Lab 1 approval is post-run. Run Lab 1 first, inspect its evidence, "
            "then use --approve-run <run-id>."
        )

    try:
        review = _review(
            approve_learning=args.approve_learning,
            approved_by=args.approved_by,
            approval_reason=args.approval_reason,
        )
        summary = asyncio.run(_run_selected(args.lab, review=review))
    except ValueError as exc:
        parser.error(str(exc))

    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
        return

    if "lab_001" in summary:
        _print_lab_001(summary["lab_001"])
    if "lab_002" in summary:
        _print_lab_002(summary["lab_002"])


if __name__ == "__main__":
    main()
