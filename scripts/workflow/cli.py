import argparse
import os
import sys

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

from scripts.workflow.agent_roles import ROLE_REGISTRY
from scripts.workflow.context7_bridge import Context7Bridge
from scripts.workflow.orchestrator import WorkflowOrchestrator
from scripts.workflow.serena_bridge import SerenaNavigator


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="codeguard-workflow",
        description="CodeGuard Phase 11 — Multi-Agent Engineering Workflow CLI",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Command: run
    run_parser = subparsers.add_parser("run", help="Execute the 10-step multi-agent engineering workflow")
    run_parser.add_argument("--task", required=True, help="Engineering task description")
    run_parser.add_argument("--target-area", default="backend", help="Target component (backend, frontend, policy, db, ai, etc.)")
    run_parser.add_argument("--symbols", nargs="*", default=["AdversarialJudge"], help="Relevant symbol names for Serena to inspect")
    run_parser.add_argument("--libs", nargs="*", default=["fastapi", "pydantic"], help="External libraries for Context7 docs")
    run_parser.add_argument("--simulate-bypass", action="store_true", help="Simulate a security bypass to test rejection gates")

    # Command: serena
    serena_parser = subparsers.add_parser("serena", help="Query Serena for symbol discovery, callers, or dependencies")
    serena_parser.add_argument("--symbol", required=True, help="Symbol name to find")
    serena_parser.add_argument("--callers", action="store_true", help="Find callers of the symbol")

    # Command: context7
    c7_parser = subparsers.add_parser("context7", help="Query Context7 for version-matched documentation")
    c7_parser.add_argument("--lib", required=True, help="Library name (e.g. pydantic, fastapi, sqlalchemy)")

    # Command: roles
    subparsers.add_parser("roles", help="List all 12 specialized Agency Agent roles and boundaries")

    args = parser.parse_args()

    if args.command == "run":
        orchestrator = WorkflowOrchestrator()
        result = orchestrator.execute_task(
            task_description=args.task,
            target_area=args.target_area,
            relevant_symbols=args.symbols,
            external_libraries=args.libs,
            simulate_security_bypass=args.simulate_bypass,
        )
        print("\n========================================================")
        print(f"TASK: {result.task_description}")
        print(f"OVERALL STATUS: {result.overall_status} (Duration: {result.total_duration_ms:.2f}ms)")
        print(f"SECURITY VERDICT: {result.security_verdict}")
        print(f"REVIEW VERDICT: {result.review_verdict}")
        print("========================================================")
        for s in result.steps:
            print(f"[{s.status}] Step {s.step_number}: {s.name} ({s.duration_ms:.2f}ms)")
            print(f"       {s.summary}")
        if result.overall_status != "SUCCESS":
            sys.exit(1)

    elif args.command == "serena":
        navigator = SerenaNavigator()
        symbols = navigator.find_symbol(args.symbol)
        print(f"Found {len(symbols)} location(s) for symbol '{args.symbol}':")
        for sym in symbols:
            print(f"  - {sym.symbol_type} {sym.name} ({sym.file_path}:{sym.line_number})")
        if args.callers:
            callers = navigator.get_callers(args.symbol)
            print(f"\nFound {len(callers)} caller(s):")
            for c in callers:
                print(f"  - Called by '{c.caller_name}' in {c.file_path}:{c.line_number}")

    elif args.command == "context7":
        c7 = Context7Bridge()
        doc = c7.query_documentation(args.lib)
        print(f"\nContext7 Documentation for '{doc.library}' (Version: {doc.installed_version}):")
        print(f"Topic: {doc.topic}")
        print(f"Signature: {doc.authoritative_signature}")
        print("Recommended Patterns:")
        for r in doc.recommended_patterns:
            print(f"  - {r}")
        print("Deprecated Patterns:")
        for d in doc.deprecated_patterns:
            print(f"  - {d}")

    elif args.command == "roles":
        print("\nCodeGuard — 12 Specialized Agency Agent Roles:")
        for role, defn in ROLE_REGISTRY.items():
            print(f"\n• {role.value}:")
            print(f"  Description: {defn.description}")
            print(f"  Allowed Paths: {defn.allowed_file_patterns}")
            print(f"  Forbidden Actions: {defn.forbidden_actions}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
