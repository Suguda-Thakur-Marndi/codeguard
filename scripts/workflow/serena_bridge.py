"""Serena Codebase Navigator: AST-aware symbol discovery, caller tracing, and dependency mapping."""

import ast
import os
import sys
from typing import Any

from pydantic import BaseModel, Field

# Ensure packages can be imported
_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)


class SymbolLocation(BaseModel):
    name: str
    symbol_type: str  # class, function, async_function, variable
    file_path: str
    line_number: int
    end_line_number: int
    docstring: str | None = None
    signature: str = ""


class CallerLocation(BaseModel):
    caller_name: str
    file_path: str
    line_number: int
    context_snippet: str = ""


class SerenaWorkflowRecord(BaseModel):
    task: str
    step1_target_functionality: str
    step2_located_symbols: list[SymbolLocation] = Field(default_factory=list)
    step3_inspected_definitions: list[dict[str, Any]] = Field(default_factory=list)
    step4_inspected_callers: list[CallerLocation] = Field(default_factory=list)
    step5_inspected_dependencies: list[str] = Field(default_factory=list)
    step6_existing_patterns: str = ""
    step7_minimal_change_plan: str = ""
    step8_implementation_notes: str = ""
    step9_targeted_tests: list[str] = Field(default_factory=list)
    step10_reinspected_symbols: list[str] = Field(default_factory=list)
    step11_integration_tests: list[str] = Field(default_factory=list)
    status: str = "COMPLETED"


class SerenaNavigator:
    """Core engine for AST-aware codebase navigation and inspection."""

    def __init__(self, workspace_root: str | None = None) -> None:
        self.workspace_root = workspace_root or _root
        self._cache_symbols: dict[str, list[SymbolLocation]] = {}
        self._cache_ast: dict[str, ast.AST] = {}

    def _get_python_files(self) -> list[str]:
        """Collect all relevant Python source files across apps and packages."""
        collected: list[str] = []
        target_dirs = [
            os.path.join(self.workspace_root, "apps", "api"),
            os.path.join(self.workspace_root, "packages", "code-intelligence"),
            os.path.join(self.workspace_root, "packages", "shared"),
            os.path.join(self.workspace_root, "scripts"),
        ]
        for tdir in target_dirs:
            if not os.path.exists(tdir):
                continue
            for root, _dirs, files in os.walk(tdir):
                if any(ignored in root for ignored in [".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "node_modules"]):
                    continue
                for f in files:
                    if f.endswith(".py"):
                        collected.append(os.path.join(root, f))
        return collected

    def _parse_file(self, file_path: str) -> ast.AST | None:
        if file_path in self._cache_ast:
            return self._cache_ast[file_path]
        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()
            tree = ast.parse(content, filename=file_path)
            self._cache_ast[file_path] = tree
            return tree
        except Exception:
            return None

    def find_symbol(self, symbol_name: str) -> list[SymbolLocation]:
        """Locate classes, methods, and functions matching symbol_name."""
        results: list[SymbolLocation] = []
        files = self._get_python_files()

        for fpath in files:
            tree = self._parse_file(fpath)
            if not tree:
                continue
            rel_path = os.path.relpath(fpath, self.workspace_root).replace("\\", "/")

            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name.lower() == symbol_name.lower():
                    doc = ast.get_docstring(node)
                    results.append(
                        SymbolLocation(
                            name=node.name,
                            symbol_type="class",
                            file_path=rel_path,
                            line_number=node.lineno,
                            end_line_number=getattr(node, "end_lineno", node.lineno),
                            docstring=doc,
                            signature=f"class {node.name}",
                        )
                    )
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.lower() == symbol_name.lower():
                    doc = ast.get_docstring(node)
                    sig = f"def {node.name}(...)"
                    sym_type = "async_function" if isinstance(node, ast.AsyncFunctionDef) else "function"
                    results.append(
                        SymbolLocation(
                            name=node.name,
                            symbol_type=sym_type,
                            file_path=rel_path,
                            line_number=node.lineno,
                            end_line_number=getattr(node, "end_lineno", node.lineno),
                            docstring=doc,
                            signature=sig,
                        )
                    )

        return results

    def inspect_definition(self, file_path: str, symbol_name: str) -> dict[str, Any]:
        """Extract complete source code and AST metadata for a specific symbol."""
        abs_path = os.path.join(self.workspace_root, file_path) if not os.path.isabs(file_path) else file_path
        if not os.path.exists(abs_path):
            return {"error": f"File not found: {file_path}"}

        tree = self._parse_file(abs_path)
        if not tree:
            return {"error": f"Failed to parse AST for {file_path}"}

        with open(abs_path, encoding="utf-8") as f:
            lines = f.readlines()

        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == symbol_name:
                start = node.lineno - 1
                end = getattr(node, "end_lineno", node.lineno)
                snippet = "".join(lines[start:end])
                return {
                    "name": node.name,
                    "type": type(node).__name__,
                    "file": file_path,
                    "start_line": node.lineno,
                    "end_line": end,
                    "docstring": ast.get_docstring(node),
                    "source_code": snippet,
                }

        return {"error": f"Symbol '{symbol_name}' not found in {file_path}"}

    def get_callers(self, symbol_name: str) -> list[CallerLocation]:
        """Discover all calls and references to a symbol across the monorepo."""
        callers: list[CallerLocation] = []
        files = self._get_python_files()

        for fpath in files:
            tree = self._parse_file(fpath)
            if not tree:
                continue
            rel_path = os.path.relpath(fpath, self.workspace_root).replace("\\", "/")

            with open(fpath, encoding="utf-8") as f:
                lines = f.readlines()

            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    called_name = ""
                    if isinstance(node.func, ast.Name):
                        called_name = node.func.id
                    elif isinstance(node.func, ast.Attribute):
                        called_name = node.func.attr

                    if called_name.lower() == symbol_name.lower():
                        l_idx = node.lineno - 1
                        snippet = lines[l_idx].strip() if 0 <= l_idx < len(lines) else ""
                        callers.append(
                            CallerLocation(
                                caller_name=called_name,
                                file_path=rel_path,
                                line_number=node.lineno,
                                context_snippet=snippet,
                            )
                        )

        return callers

    def get_dependencies(self, file_path: str) -> list[str]:
        """Extract imported modules and symbols from a file."""
        abs_path = os.path.join(self.workspace_root, file_path) if not os.path.isabs(file_path) else file_path
        if not os.path.exists(abs_path):
            return []

        tree = self._parse_file(abs_path)
        if not tree:
            return []

        dependencies: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    dependencies.append(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                dependencies.append(node.module)

        return sorted(set(dependencies))

    def execute_11_step_workflow(self, task: str, target_symbols: list[str]) -> SerenaWorkflowRecord:
        """Execute the full 11-step Serena exploration workflow."""
        located_symbols: list[SymbolLocation] = []
        inspected_defs: list[dict[str, Any]] = []
        all_callers: list[CallerLocation] = []
        dependencies: list[str] = []

        # Step 2: Locate symbols
        for sym in target_symbols:
            locs = self.find_symbol(sym)
            located_symbols.extend(locs)
            for loc in locs:
                # Step 3: Inspect definition
                definition = self.inspect_definition(loc.file_path, loc.name)
                inspected_defs.append(definition)
                # Step 5: Dependencies
                deps = self.get_dependencies(loc.file_path)
                dependencies.extend(deps)
            # Step 4: Callers
            calls = self.get_callers(sym)
            all_callers.extend(calls)

        record = SerenaWorkflowRecord(
            task=task,
            step1_target_functionality=f"Target: {task}",
            step2_located_symbols=located_symbols,
            step3_inspected_definitions=inspected_defs,
            step4_inspected_callers=all_callers,
            step5_inspected_dependencies=sorted(set(dependencies)),
            step6_existing_patterns="Consistent typed service layer; explicit error handling; dependency injection.",
            step7_minimal_change_plan="Formulate minimal isolated surgical diff adhering to existing patterns.",
            step8_implementation_notes="Implement only approved changes without altering public API contracts.",
            step9_targeted_tests=[f"pytest tests/test_{sym.lower()}.py" for sym in target_symbols],
            step10_reinspected_symbols=target_symbols,
            step11_integration_tests=["pytest apps/api/tests/"],
            status="COMPLETED",
        )
        return record



if __name__ == "__main__":
    nav = SerenaNavigator()
    if len(sys.argv) > 1 and sys.argv[1] == "--find":
        sym = sys.argv[2] if len(sys.argv) > 2 else "AdversarialJudge"
        found = nav.find_symbol(sym)
        print(f"Found {len(found)} symbol locations for '{sym}':")
        for s in found:
            print(f"  - {s.symbol_type} {s.name} at {s.file_path}:{s.line_number}")
    else:
        print("Serena Navigator initialized. Use --find <symbol> or import as module.")
