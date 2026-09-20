from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from operational_intelligence_lab.lab_001_unknown_incident import run_lab_001
from operational_intelligence_lab.lab_002_learned_reuse import run_lab_002


async def run_demo() -> dict[str, Any]:
    discovery = await run_lab_001()
    reuse = await run_lab_002(discovery)
    return {
        "lab_001": discovery.summary,
        "lab_002": reuse,
    }


def _print_lab_001(summary: dict[str, Any]) -> None:
    print("\nAI Lab 001 — Unknown Incident")
    print("=" * 33)
    print("1. SIMULATE  Article 2 late-removal failure -> P1 projection becomes NONE")
    print("2. COLLECT   event journal + projection transitions + runtime signals")
    print("3. KNOW      Package --assignedTo--> Container + one-active-container invariant")
    print(
        "4. REASON    "
        f"{summary['routing']['strategy']} / {summary['routing']['reasoning_tier']} "
        f"(calls={summary['reasoning']['calls']})"
    )
    print(f"             Hypothesis: {summary['reasoning']['hypothesis']}")
    print("5. SIMULATE  candidate remediation against multiple deterministic cases")
    print(f"6. VERIFY    all candidate cases passed = {summary['simulation']['passed']}")
    print(
        "7. APPROVE   "
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
    print(
        "5. GUARD     different preconditions -> "
        f"{summary['guard_mismatch']['strategy']} / "
        f"{summary['guard_mismatch']['reasoning_tier']}"
    )


async def _run_selected(lab: str) -> dict[str, Any]:
    if lab == "1":
        first = await run_lab_001()
        return {"lab_001": first.summary}
    if lab == "2":
        second = await run_lab_002()
        return {"lab_002": second}
    return await run_demo()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the public Operational Intelligence AI Labs."
    )
    parser.add_argument(
        "--lab",
        choices=("1", "2", "all"),
        default="all",
        help="Run AI Lab 001, AI Lab 002, or the complete learning loop.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    summary = asyncio.run(_run_selected(args.lab))
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
        return

    if "lab_001" in summary:
        _print_lab_001(summary["lab_001"])
    if "lab_002" in summary:
        _print_lab_002(summary["lab_002"])

    print(
        "\nUnknown -> bounded reasoning -> simulate -> verify -> human approve "
        "-> learn -> guarded deterministic reuse\n"
    )


if __name__ == "__main__":
    main()
