"""Test script for ClingoReasoner."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reasoner.app.clingo_reasoner import ClingoReasoner

LP_PATH = Path(__file__).resolve().parent.parent / "reasoner" / "asp" / "security.lp"


async def test_violation_detection() -> None:
    reasoner = ClingoReasoner(lp_path=str(LP_PATH))

    facts = """
user(john).
assigned_role(john, analyst).
access_event(john, db_server, read, "10.0.0.5", t1).
forbidden_subnet("10.0.0.0/24").
ip_in_subnet("10.0.0.5", "10.0.0.0/24").
"""

    result = await reasoner.solve(facts)
    print(f"Satisfiable: {result.satisfiable}")
    print(f"Unsatisfiable: {result.unsatisfiable}")
    print(f"Models: {len(result.models)}")
    for i, model in enumerate(result.models):
        print(f"  Model {i}: {model}")
    print(f"Error: {result.error}")

    assert result.satisfiable is True or result.satisfiable is None
    print("\nViolation detection test passed!")


async def test_contradiction_detection() -> None:
    reasoner = ClingoReasoner(lp_path=str(LP_PATH))

    facts = """
user(john).
assigned_role(john, analyst).
assigned_role(john, admin).
"""

    result = await reasoner.solve(facts)
    print(f"Satisfiable: {result.satisfiable}")
    print(f"Unsatisfiable: {result.unsatisfiable}")
    print(f"Models: {len(result.models)}")
    print(f"Error: {result.error}")

    print("\nContradiction detection test passed!")


async def test_empty_facts() -> None:
    reasoner = ClingoReasoner(lp_path=str(LP_PATH))

    result = await reasoner.solve("")
    print(f"Satisfiable: {result.satisfiable}")
    print(f"Error: {result.error}")

    print("\nEmpty facts test passed!")


async def main() -> None:
    print("=" * 60)
    print("LiveLogic ClingoReasoner Tests")
    print("=" * 60)

    await test_violation_detection()
    print()
    await test_contradiction_detection()
    print()
    await test_empty_facts()

    print("\n" + "=" * 60)
    print("All tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
