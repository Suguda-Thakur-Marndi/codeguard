"""Context7 Documentation Assistant: Version-safe documentation retrieval and precedence hierarchy enforcement."""

import json
import os
import re
import sys
from typing import Any

from pydantic import BaseModel, Field

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)


class DocReference(BaseModel):
    library: str
    installed_version: str
    topic: str
    authoritative_signature: str
    deprecated_patterns: list[str] = Field(default_factory=list)
    recommended_patterns: list[str] = Field(default_factory=list)
    hierarchy_note: str = "Project Architecture and Security Policy supersede external library documentation."


class CompatibilityReport(BaseModel):
    library: str
    installed_version: str
    is_compatible: bool
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class ConflictReport(BaseModel):
    library: str
    conflicts_with_project: bool
    conflict_reasons: list[str] = Field(default_factory=list)
    recommended_resolution: str


# Knowledge base of verified official documentation for CodeGuard's installed library versions
VERIFIED_DOC_DATABASE: dict[str, dict[str, Any]] = {
    "fastapi": {
        "installed_range": ">=0.111.0",
        "topic": "Router, Dependency Injection, Exception Handlers",
        "signature": "APIRouter(), Depends(dependency), HTTPException(status_code, detail)",
        "deprecated": [
            "@app.on_event('startup')",  # Deprecated in modern FastAPI; lifespan context manager preferred
        ],
        "recommended": [
            "Use lifespan context manager for application startup/shutdown",
            "Use annotated dependencies: Annotated[Service, Depends(get_service)]",
            "Keep API routes thin and delegate to domain services",
        ],
    },
    "pydantic": {
        "installed_range": ">=2.7.0",
        "topic": "Pydantic V2 Models, Field Validators, Serialization",
        "signature": "BaseModel, field_validator, model_validator(mode='after'), ConfigDict",
        "deprecated": [
            "@validator",  # V1 deprecated
            "@root_validator",  # V1 deprecated
            "class Config:",  # V1 deprecated; use model_config = ConfigDict(...)
            ".dict()",  # V1 deprecated; use .model_dump()
            ".json()",  # V1 deprecated; use .model_dump_json()
        ],
        "recommended": [
            "Use model_config = ConfigDict(from_attributes=True, extra='forbid')",
            "Use @field_validator for single-field logic",
            "Use @model_validator(mode='after') for cross-field consistency",
        ],
    },
    "sqlalchemy": {
        "installed_range": ">=2.0.30",
        "topic": "SQLAlchemy 2.0 Unified Query Execution and Declarative Models",
        "signature": "select(Model).where(...), db.execute(stmt), db.scalars(stmt)",
        "deprecated": [
            "session.query(Model)",  # Legacy 1.x query API
            "Column(Integer, primary_key=True)",  # Legacy column syntax; use mapped_column
        ],
        "recommended": [
            "Always use select(Model).where(...) with session.scalars() or session.execute()",
            "Use mapped_column() and Mapped[T] for typed models",
            "Always use transactional context or explicit commit/rollback",
        ],
    },
    "langgraph": {
        "installed_range": ">=0.2.0",
        "topic": "StateGraph, Node Functions, Edge Routing",
        "signature": "StateGraph(StateType), builder.add_node(name, func), builder.add_edge(src, dst)",
        "deprecated": [
            "Imperative run loops outside compiled graph",
        ],
        "recommended": [
            "Define explicit typed State TypedDict with reducers",
            "Ensure nodes are pure or handle external side-effects deterministically",
            "Compile workflow with builder.compile()",
        ],
    },
    "google-genai": {
        "installed_range": ">=0.1.0",
        "topic": "Google GenAI SDK Client, Content Generation",
        "signature": "genai.Client(api_key=...), client.models.generate_content(...)",
        "deprecated": [
            "google.generativeai legacy package import",
        ],
        "recommended": [
            "Use official google-genai Client abstraction",
            "Redact sensitive tokens before logging prompts",
            "Treat model generation as untrusted input requiring judge validation",
        ],
    },
    "tree-sitter": {
        "installed_range": ">=0.24.0",
        "topic": "Tree-sitter Language Parsers, AST Traversal",
        "signature": "Parser(Language), tree = parser.parse(bytes)",
        "deprecated": [
            "Old language build binding scripts from tree_sitter 0.20",
        ],
        "recommended": [
            "Use official precompiled tree-sitter-python, tree-sitter-javascript packages",
            "Check for node.has_error or node.is_missing for robust syntax handling",
        ],
    },
    "next": {
        "installed_range": "^15.2.0",
        "topic": "Next.js App Router, React 19 Server/Client Components",
        "signature": "NextResponse.json(...), 'use client', 'use server'",
        "deprecated": [
            "pages/ router for new features",
            "Direct DOM manipulation bypassing React state",
        ],
        "recommended": [
            "Preserve existing UI component hierarchy in apps/web/components",
            "Do NOT introduce new styling frameworks or redesign layouts",
            "Use Tailwind classes consistent with existing design tokens",
        ],
    },
}


class Context7Bridge:
    """Provides version-safe documentation and guards project architecture precedence."""

    def __init__(self, workspace_root: str | None = None) -> None:
        self.workspace_root = workspace_root or _root
        self.installed_versions = self._inspect_manifest_versions()

    def _inspect_manifest_versions(self) -> dict[str, str]:
        """Read pyproject.toml and package.json to discover installed version specifications."""
        versions: dict[str, str] = {}

        # 1. API pyproject.toml
        api_pyproject = os.path.join(self.workspace_root, "apps", "api", "pyproject.toml")
        if os.path.exists(api_pyproject):
            try:
                with open(api_pyproject, encoding="utf-8") as f:
                    content = f.read()
                for line in content.splitlines():
                    match = re.search(r'"([a-zA-Z0-9_\-]+)(?:\[[^\]]+\])?([><=~^0-9\.]+)"', line)
                    if match:
                        versions[match.group(1).lower()] = match.group(2)
            except (OSError, UnicodeDecodeError) as exc:
                self._manifest_errors = getattr(self, "_manifest_errors", []) + [str(exc)]

        # 2. Web package.json
        web_pkg = os.path.join(self.workspace_root, "apps", "web", "package.json")
        if os.path.exists(web_pkg):
            try:
                with open(web_pkg, encoding="utf-8") as f:
                    data = json.load(f)
                for dep, ver in data.get("dependencies", {}).items():
                    versions[dep.lower()] = ver
                for dep, ver in data.get("devDependencies", {}).items():
                    versions[dep.lower()] = ver
            except (OSError, json.JSONDecodeError) as exc:
                self._manifest_errors = getattr(self, "_manifest_errors", []) + [str(exc)]

        return versions

    def get_installed_version(self, package_name: str) -> str:
        """Get the version constraint for a package from repository manifests."""
        pkg_lower = package_name.lower()
        if pkg_lower in self.installed_versions:
            return self.installed_versions[pkg_lower]
        # Fallback to known registry
        if pkg_lower in VERIFIED_DOC_DATABASE:
            return VERIFIED_DOC_DATABASE[pkg_lower]["installed_range"]
        return "unknown"

    def query_documentation(self, library: str, topic: str = "") -> DocReference:
        """Fetch version-safe documentation and best practices for the specified library."""
        lib_key = library.lower()
        installed_ver = self.get_installed_version(lib_key)
        doc_entry = VERIFIED_DOC_DATABASE.get(
            lib_key,
            {
                "topic": topic or "General API Reference",
                "signature": f"{library} Standard API",
                "deprecated": [],
                "recommended": ["Adhere to existing CodeGuard patterns"],
            },
        )

        return DocReference(
            library=library,
            installed_version=installed_ver,
            topic=doc_entry.get("topic", topic),
            authoritative_signature=doc_entry.get("signature", ""),
            deprecated_patterns=doc_entry.get("deprecated", []),
            recommended_patterns=doc_entry.get("recommended", []),
        )

    def validate_code_compatibility(self, library: str, code_snippet: str) -> CompatibilityReport:
        """Analyze code snippet for deprecated or incompatible library patterns."""
        lib_key = library.lower()
        installed_ver = self.get_installed_version(lib_key)
        doc_entry = VERIFIED_DOC_DATABASE.get(lib_key)
        warnings: list[str] = []
        errors: list[str] = []

        if doc_entry:
            for dep_pat in doc_entry.get("deprecated", []):
                # Simple check if deprecated identifier appears
                clean_term = re.sub(r"[^a-zA-Z0-9_.]", "", dep_pat)
                if clean_term and clean_term in code_snippet:
                    errors.append(f"Code uses deprecated pattern for {library} ({installed_ver}): '{dep_pat}'")

        return CompatibilityReport(
            library=library,
            installed_version=installed_ver,
            is_compatible=(len(errors) == 0),
            warnings=warnings,
            errors=errors,
        )

    def check_hierarchy_conflict(self, library: str, proposal: str) -> ConflictReport:
        """Enforce: PROJECT ARCHITECTURE > BUSINESS LOGIC > SECURITY POLICY > LIBRARY DOCS."""
        conflicts: list[str] = []
        lower_prop = proposal.lower()

        # Prohibited suggestions regardless of what library documentation might suggest
        if "disable" in lower_prop and ("auth" in lower_prop or "security" in lower_prop):
            conflicts.append("Documentation suggestion conflicts with Project Security Policy: Authentication cannot be disabled.")
        if "skip" in lower_prop and "approval" in lower_prop:
            conflicts.append("Documentation suggestion conflicts with Project Business Logic: Human approval is mandatory.")
        if "redesign" in lower_prop and "ui" in lower_prop:
            conflicts.append("Documentation suggestion conflicts with Project Invariant: UI/UX redesign is strictly prohibited.")
        if "drop table" in lower_prop or "delete from" in lower_prop:
            conflicts.append("Documentation suggestion conflicts with Database Safety: Destructive SQL requires Alembic migrations.")

        has_conflict = len(conflicts) > 0
        resolution = (
            "Reject external documentation suggestion. Maintain CodeGuard project architecture and security invariants."
            if has_conflict
            else "Compliant with project hierarchy."
        )

        return ConflictReport(
            library=library,
            conflicts_with_project=has_conflict,
            conflict_reasons=conflicts,
            recommended_resolution=resolution,
        )


if __name__ == "__main__":
    c7 = Context7Bridge()
    doc = c7.query_documentation("pydantic")
    print(f"Context7 Docs for {doc.library} (Installed: {doc.installed_version}):")
    print(f"  Signature: {doc.authoritative_signature}")
    print(f"  Deprecated: {doc.deprecated_patterns}")
    print(f"  Recommended: {doc.recommended_patterns}")
