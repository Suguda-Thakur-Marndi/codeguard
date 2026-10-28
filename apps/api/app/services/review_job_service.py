"""Review job execution and Phase 2 code intelligence artifact generation service."""

import json
import os
from collections.abc import Callable
from datetime import UTC
from typing import Any

from code_intelligence.engine import CodeIntelligenceEngine
from code_intelligence.source.provider import (
    LocalDiskRepositorySourceProvider,
    MemoryRepositorySourceProvider,
    RepositorySourceProvider,
)
from sqlalchemy.orm import Session

from app.agents.llm.gemini import GeminiProvider
from app.agents.llm.mock import MockLLMProvider
from app.agents.llm.provider import LLMProvider
from app.agents.orchestrator.graph import ReviewWorkflowBuilder
from app.core.config import settings
from app.core.exceptions import EntityNotFoundError, GitHubAPIError
from app.core.logging import TimingLogger, logger, review_job_id_ctx
from app.db.repositories.pull_request_repo import PullRequestRepository
from app.db.repositories.repository_repo import RepositoryRepository
from app.db.repositories.review_artifact_repo import ReviewArtifactRepository
from app.db.repositories.review_finding_repo import ReviewFindingRepository
from app.db.repositories.review_job_repo import ReviewJobRepository
from app.github.client import GitHubClient
from app.models.review_artifact import ArtifactType
from app.models.review_job import ReviewJob, ReviewJobStatus
from app.services.code_intelligence_service import CodeIntelligenceService
from app.services.ephemeral_workspace import EphemeralWorkspace


class ReviewJobService:
    """Core domain service orchestrating review job execution, code intelligence extraction, and Phase 3 multi-agent review."""

    def __init__(
        self,
        db: Session,
        github_client: GitHubClient | None = None,
        source_provider: RepositorySourceProvider | None = None,
        llm_provider: LLMProvider | None = None,
    ):
        self.db = db
        self.github = github_client or GitHubClient()
        self.source_provider = source_provider
        self.llm_provider = llm_provider or self._resolve_default_llm_provider()
        self.job_repo = ReviewJobRepository(db)
        self.pr_repo = PullRequestRepository(db)
        self.repo_repo = RepositoryRepository(db)
        self.artifact_repo = ReviewArtifactRepository(db)
        self.finding_repo = ReviewFindingRepository(db)
        self.ci_service = CodeIntelligenceService(db)
        self.engine = CodeIntelligenceEngine()

    def _resolve_default_llm_provider(self) -> LLMProvider:
        """Resolve LLM provider from settings; fallback to MockLLMProvider only in non-production dev/test environments."""
        if settings.APP_ENV == "production":
            if not settings.GEMINI_API_KEY:
                raise ValueError("GEMINI_API_KEY must be configured in production environment.")
            if settings.LLM_PROVIDER == "mock":
                raise ValueError("LLM_PROVIDER cannot be 'mock' in production environment.")
            return GeminiProvider()

        if settings.LLM_PROVIDER == "mock" or not settings.GEMINI_API_KEY:
            return MockLLMProvider()
        return GeminiProvider()

    async def _acquire_source_provider(
        self,
        repo: Any,
        head_sha: str,
        installation_id: int,
        raw_diff: str,
    ) -> tuple[RepositorySourceProvider, Callable[[], None] | None]:
        """
        Acquire repository source code at exact head commit for AST analysis and code intelligence.

        Guarantees:
        - Real GitHub pull requests fetch repository source from GitHub App into an ephemeral workspace.
        - Ephemeral workspace is cleaned up on both success and failure.
        - Never falls back silently to fixtures for real repositories.
        - Keeps local fixtures strictly for explicit test and dev scenarios (e.g. repo name is python_repo).
        """
        # 1. Explicitly injected provider (e.g., unit test mock or pre-configured provider)
        if self.source_provider:
            return self.source_provider, None

        # 2. Explicit local fixture scenario (ONLY in non-production, and ONLY if repo is explicitly a fixture)
        if settings.APP_ENV in ("development", "test"):
            is_fixture_repo = (
                repo.owner == "fixtures"
                or repo.name in ("python_repo", "javascript_repo", "typescript_repo")
            )
            if is_fixture_repo:
                fixture_candidate = os.path.abspath(os.path.join(os.getcwd(), "fixtures", repo.name))
                if os.path.isdir(fixture_candidate):
                    logger.info(f"Using explicit local test fixture repository for {repo.full_name}: {fixture_candidate}")
                    return LocalDiskRepositorySourceProvider(fixture_candidate), None

        # 3. Real repository source retrieval from GitHub into ephemeral workspace
        workspace = EphemeralWorkspace(prefix=f"codeguard_{repo.name}_")
        try:
            logger.info(f"Acquiring repository source archive from GitHub for {repo.full_name}@{head_sha}")
            tarball_bytes = await self.github.download_repository_archive(
                owner=repo.owner,
                repo=repo.name,
                ref=head_sha,
                installation_id=installation_id,
            )
            extracted_dir = workspace.extract_tarball(tarball_bytes)
            provider = LocalDiskRepositorySourceProvider(extracted_dir)
            logger.info(f"Successfully extracted {repo.full_name}@{head_sha} into ephemeral workspace {extracted_dir}")
            return provider, workspace.cleanup

        except Exception as exc:
            workspace.cleanup()
            logger.error(
                f"Failed to acquire repository source archive for {repo.full_name} at commit {head_sha}: {exc}"
            )
            # Never proceed with missing or inaccessible repository source
            raise GitHubAPIError(
                f"Failed to acquire repository source archive for {repo.full_name} at commit {head_sha}: {exc}",
                status_code=502,
            ) from exc

    async def execute_job(self, job_id: str) -> ReviewJob:
        """
        Execute Phase 2 review job pipeline:
        1. Guard idempotency & state transition
        2. Fetch PR metadata & raw unified diff from GitHub
        3. Acquire repository source code for head commit
        4. Parse PR diff into structured DiffFiles and hunks
        5. Build deterministic CHANGED_LINE_INDEX (LEFT vs RIGHT)
        6. Parse changed files with Tree-sitter & extract AST chunks
        7. Extract symbols, imports, and references
        8. Index/update repository graph
        9. Build semantically ranked CONTEXT_MAP for changed entities
        10. Store all 7 Phase 2 review artifacts in PostgreSQL
        11. Mark job COMPLETED
        """
        review_job_id_ctx.set(job_id)
        job = self.job_repo.get_by_id(job_id)
        if not job:
            raise EntityNotFoundError("ReviewJob", job_id)

        # Idempotency guard
        if job.status == ReviewJobStatus.COMPLETED:
            logger.info(f"Review job {job_id} is already COMPLETED. Skipping duplicate execution.")
            return job

        if job.status == ReviewJobStatus.RUNNING:
            logger.warning(f"Review job {job_id} is currently RUNNING by another worker.")
            return job

        running_job = self.job_repo.mark_running(job_id)
        if not running_job:
            raise EntityNotFoundError("ReviewJob", job_id)
        job = running_job
        logger.info(
            f"Starting review job {job_id}",
            extra={"event": "review_job_started", "extra_fields": {"job_id": job_id}},
        )

        cleanup_source: Callable[[], None] | None = None
        try:
            with TimingLogger("review_job_execution", {"job_id": job_id}):
                pr = self.pr_repo.get_by_id(job.pull_request_id)
                if not pr:
                    raise EntityNotFoundError("PullRequest", job.pull_request_id)

                repo = self.repo_repo.get_by_id(pr.repository_id)
                if not repo:
                    raise EntityNotFoundError("Repository", pr.repository_id)

                installation_id = repo.organization.github_installation_id if repo.organization else 1

                # 1. Fetch Pull Request metadata
                logger.info(f"Fetching PR metadata from GitHub for {repo.full_name}#{pr.number}")
                pr_meta = await self.github.get_pull_request(
                    owner=repo.owner,
                    repo=repo.name,
                    pull_number=pr.number,
                    installation_id=installation_id,
                )

                # 2. Fetch Pull Request raw unified diff
                logger.info(f"Fetching PR unified diff from GitHub for {repo.full_name}#{pr.number}")
                raw_diff = await self.github.get_pull_request_diff(
                    owner=repo.owner,
                    repo=repo.name,
                    pull_number=pr.number,
                    installation_id=installation_id,
                )

                # 3. Store PR_METADATA artifact
                metadata_dict: dict[str, Any] = {
                    "github_pr_id": pr_meta.get("id"),
                    "number": pr_meta.get("number"),
                    "title": pr_meta.get("title"),
                    "state": pr_meta.get("state"),
                    "draft": pr_meta.get("draft", False),
                    "author": pr_meta.get("user", {}).get("login"),
                    "base_sha": pr_meta.get("base", {}).get("sha"),
                    "head_sha": pr_meta.get("head", {}).get("sha"),
                    "additions": pr_meta.get("additions", 0),
                    "deletions": pr_meta.get("deletions", 0),
                    "changed_files": pr_meta.get("changed_files", 0),
                    "merged": pr_meta.get("merged", False),
                }
                self.artifact_repo.upsert_artifact(
                    review_job_id=job.id,
                    artifact_type=ArtifactType.PR_METADATA,
                    content=f"Pull Request #{pr.number}: {pr.title}\nAuthor: {pr.author_login}\nBase: {pr.base_sha} -> Head: {pr.head_sha}",
                    metadata_json=metadata_dict,
                )

                # 4. Store raw DIFF artifact
                diff_stats = {
                    "byte_size": len(raw_diff.encode("utf-8")),
                    "line_count": len(raw_diff.splitlines()),
                    "base_sha": pr.base_sha,
                    "head_sha": pr.head_sha,
                }
                self.artifact_repo.upsert_artifact(
                    review_job_id=job.id,
                    artifact_type=ArtifactType.DIFF,
                    content=raw_diff,
                    metadata_json=diff_stats,
                )

                # 5. Acquire repository source provider for head commit
                source_provider, cleanup_source = await self._acquire_source_provider(
                    repo=repo,
                    head_sha=pr.head_sha,
                    installation_id=installation_id,
                    raw_diff=raw_diff,
                )

                # Index repository if not indexed yet
                _repo_index = self.ci_service.trigger_indexing(
                    repository_id=repo.id,
                    commit_sha=pr.head_sha,
                    source_provider=source_provider,
                )

                # 6. Run Code Intelligence PR Analysis
                analysis = self.engine.analyze_pull_request(
                    raw_diff=raw_diff,
                    source_provider=source_provider,
                    head_sha=pr.head_sha,
                    repository_id=repo.id,
                )

                # 7. Persist PARSED_DIFF artifact
                parsed_diff_json = [df.model_dump() for df in analysis.diff_files]
                self.artifact_repo.upsert_artifact(
                    review_job_id=job.id,
                    artifact_type=ArtifactType.PARSED_DIFF,
                    content=json.dumps(parsed_diff_json, indent=2),
                    metadata_json={"file_count": len(analysis.diff_files)},
                )

                # 8. Persist CHANGED_LINE_INDEX artifact
                line_index_dict = analysis.line_index.to_dict() if analysis.line_index else {}
                self.artifact_repo.upsert_artifact(
                    review_job_id=job.id,
                    artifact_type=ArtifactType.CHANGED_LINE_INDEX,
                    content=json.dumps(line_index_dict, indent=2),
                    metadata_json={"files_indexed": len(line_index_dict)},
                )

                # 9. Persist AST_CHUNKS artifact
                ast_chunks_json = [chunk.model_dump() for chunk in analysis.ast_chunks]
                self.artifact_repo.upsert_artifact(
                    review_job_id=job.id,
                    artifact_type=ArtifactType.AST_CHUNKS,
                    content=json.dumps(ast_chunks_json, indent=2),
                    metadata_json={"chunk_count": len(analysis.ast_chunks)},
                )

                # 10. Persist SYMBOL_INDEX artifact
                db_symbols, _ = self.ci_service.get_symbols(repo.id, commit_sha=pr.head_sha, page=1, page_size=100)
                symbols_json = [
                    {
                        "id": s.id,
                        "name": s.name,
                        "kind": s.kind,
                        "file_path": s.file_path,
                        "signature": s.signature,
                        "start_line": s.start_line,
                        "end_line": s.end_line,
                    }
                    for s in db_symbols
                ]
                self.artifact_repo.upsert_artifact(
                    review_job_id=job.id,
                    artifact_type=ArtifactType.SYMBOL_INDEX,
                    content=json.dumps(symbols_json, indent=2),
                    metadata_json={"symbol_count": len(symbols_json)},
                )

                # 11. Persist REFERENCE_INDEX artifact
                db_refs = self.ci_service.ref_repo.list_references(repo.id, commit_sha=pr.head_sha)
                refs_json = [
                    {
                        "id": r.id,
                        "source_symbol": r.source_symbol,
                        "target_symbol": r.target_symbol,
                        "source_file": r.source_file,
                        "target_file": r.target_file,
                        "reference_type": r.reference_type,
                        "resolved": r.resolved,
                    }
                    for r in db_refs
                ]
                self.artifact_repo.upsert_artifact(
                    review_job_id=job.id,
                    artifact_type=ArtifactType.REFERENCE_INDEX,
                    content=json.dumps(refs_json, indent=2),
                    metadata_json={"reference_count": len(refs_json)},
                )

                # 12. Persist CONTEXT_MAP artifact
                context_map_json = {
                    sym: ctx.model_dump() for sym, ctx in analysis.context_by_symbol.items()
                }
                self.artifact_repo.upsert_artifact(
                    review_job_id=job.id,
                    artifact_type=ArtifactType.CONTEXT_MAP,
                    content=json.dumps(context_map_json, indent=2),
                    metadata_json={"symbol_contexts_count": len(context_map_json)},
                )

                # 13. Persist PARSER_DIAGNOSTICS artifact
                diags_json = [d.model_dump() for d in analysis.diagnostics]
                self.artifact_repo.upsert_artifact(
                    review_job_id=job.id,
                    artifact_type=ArtifactType.PARSER_DIAGNOSTICS,
                    content=json.dumps(diags_json, indent=2),
                    metadata_json={"diagnostic_count": len(diags_json)},
                )

                # 14. Phase 3: Agentic AI Review Workflow (LangGraph)
                job.status = ReviewJobStatus.COMPREHENDING
                self.db.commit()

                # Build source code dict
                source_code_by_file: dict[str, str] = {}
                for df in analysis.diff_files:
                    raw_content = source_provider.get_file(df.file_path)
                    if not raw_content and hasattr(self.github, "get_file_content"):
                        try:
                            raw_content = await self.github.get_file_content(
                                owner=repo.owner,
                                repo=repo.name,
                                path=df.file_path,
                                ref=pr.head_sha,
                                installation_id=installation_id,
                            )
                            if raw_content and isinstance(source_provider, MemoryRepositorySourceProvider):
                                current_files = source_provider.get_files(pr.head_sha)
                                current_files[df.file_path] = raw_content if isinstance(raw_content, bytes) else str(raw_content).encode("utf-8")
                                source_provider.set_commit_files(pr.head_sha, current_files)
                        except Exception as fetch_err:
                            logger.debug(f"Could not fetch {df.file_path} from GitHub: {fetch_err}")

                    if isinstance(raw_content, bytes):
                        source_code_by_file[df.file_path] = raw_content.decode("utf-8", errors="replace")
                    elif isinstance(raw_content, str):
                        source_code_by_file[df.file_path] = raw_content
                    else:
                        source_code_by_file[df.file_path] = ""

                initial_state: dict[str, Any] = {
                    "review_job_id": job.id,
                    "repository_id": repo.id,
                    "pr_id": pr.id,
                    "base_sha": pr.base_sha,
                    "head_sha": pr.head_sha,
                    "pr_title": pr.title,
                    "pr_description": pr.description or "",
                    "changed_files": [df.file_path for df in analysis.diff_files],
                    "diff_hunks_by_file": {df.file_path: [h.model_dump() for h in df.hunks] for df in analysis.diff_files},
                    "changed_lines_by_file": line_index_dict,
                    "ast_chunks_by_file": {
                        df.file_path: [ch.model_dump() for ch in analysis.ast_chunks if ch.file_path == df.file_path]
                        for df in analysis.diff_files
                    },
                    "context_by_symbol": {sym: ctx.model_dump() for sym, ctx in analysis.context_by_symbol.items()},
                    "source_code_by_file": source_code_by_file,
                    "comprehension": None,
                    "selected_specialists": [],
                    "routing_reason": "",
                    "security_findings": [],
                    "bug_findings": [],
                    "test_findings": [],
                    "performance_findings": [],
                    "raw_candidate_findings": [],
                    "validated_findings": [],
                    "invalid_findings": [],
                    "agent_runs": [],
                    "agent_traces": [],
                    "errors": [],
                    "execution_status": "RUNNING",
                    "total_input_tokens": 0,
                    "total_output_tokens": 0,
                    "total_tokens": 0,
                    "estimated_cost": 0.0,
                }

                logger.info(f"Invoking LangGraph multi-agent review workflow for review job {job.id}")
                review_workflow = ReviewWorkflowBuilder(self.llm_provider).build()
                final_state = await review_workflow.ainvoke(initial_state)

                # Persist Agent Runs
                created_agent_runs: dict[str, str] = {}
                for r in final_state.get("agent_runs", []):
                    run_record = self.finding_repo.create_agent_run(
                        {
                            "review_job_id": job.id,
                            "agent_name": r.get("agent_name"),
                            "agent_version": r.get("agent_version", "1.0.0"),
                            "model_name": r.get("model_name", "unknown"),
                            "prompt_version": r.get("prompt_version", ""),
                            "status": r.get("status", "COMPLETED"),
                            "started_at": r.get("started_at"),
                            "completed_at": r.get("completed_at"),
                            "input_tokens": r.get("input_tokens", 0),
                            "output_tokens": r.get("output_tokens", 0),
                            "total_tokens": r.get("total_tokens", 0),
                            "estimated_cost": r.get("estimated_cost", 0.0),
                            "latency_ms": r.get("latency_ms", 0.0),
                            "retry_count": r.get("retry_count", 0),
                            "error_message": r.get("error_message"),
                        }
                    )
                    created_agent_runs[r.get("agent_name")] = run_record.id

                # Persist Agent Traces
                for t in final_state.get("agent_traces", []):
                    agent_name = t.get("agent_name")
                    self.finding_repo.create_agent_trace(
                        {
                            "review_job_id": job.id,
                            "agent_run_id": created_agent_runs.get(agent_name),
                            "node_name": t.get("node_name"),
                            "agent_name": agent_name,
                            "status": t.get("status"),
                            "start_time": t.get("start_time"),
                            "end_time": t.get("end_time"),
                            "duration_ms": t.get("duration_ms", 0.0),
                            "model_name": t.get("model_name"),
                            "input_tokens": t.get("input_tokens", 0),
                            "output_tokens": t.get("output_tokens", 0),
                            "total_tokens": t.get("total_tokens", 0),
                            "retry_count": t.get("retry_count", 0),
                            "error_message": t.get("error_message"),
                        }
                    )

                # 15. Phase 4: Adversarial Verification & Execution-Grounded Validation
                job.status = ReviewJobStatus.VALIDATING
                self.db.commit()

                from app.services.verification_service import VerificationService
                verif_service = VerificationService(self.db, self.llm_provider)

                candidate_findings = list(final_state.get("validated_findings", []))
                repo_target_dir = getattr(source_provider, "base_dir", None) if hasattr(source_provider, "base_dir") else None

                publishable_findings, rejected_findings = await verif_service.verify_review_job_findings(
                    review_job_id=job.id,
                    candidate_findings=candidate_findings,
                    changed_files=[df.file_path for df in analysis.diff_files],
                    valid_lines_by_file=line_index_dict,
                    diff_hunks_by_file={df.file_path: [h.model_dump() for h in df.hunks] for df in analysis.diff_files},
                    ast_chunks_by_file={
                        df.file_path: [ch.model_dump() for ch in analysis.ast_chunks if ch.file_path == df.file_path]
                        for df in analysis.diff_files
                    },
                    context_by_symbol={sym: ctx.model_dump() for sym, ctx in analysis.context_by_symbol.items()},
                    source_code_by_file=source_code_by_file,
                    repo_dir=repo_target_dir,
                )

                # Persist Findings (Publishable/Validated, Rejected, and Invalid)
                all_findings_to_store = []
                for f in publishable_findings:
                    all_findings_to_store.append(
                        {
                            "id": f.finding_id,
                            "review_job_id": job.id,
                            "agent_run_id": created_agent_runs.get(f.agent_name),
                            "file_path": f.file_path,
                            "line_number": f.line_number,
                            "side": f.side,
                            "start_line": f.start_line,
                            "start_side": f.start_side,
                            "category": f.category.value if hasattr(f.category, "value") else str(f.category),
                            "severity": f.severity.value if hasattr(f.severity, "value") else str(f.severity),
                            "original_severity": f.original_severity,
                            "final_severity": f.final_severity,
                            "title": f.title,
                            "description": f.description,
                            "impact": f.impact,
                            "recommendation": f.recommendation,
                            "confidence": f.confidence,
                            "specialist_confidence": f.specialist_confidence,
                            "judge_confidence": f.judge_confidence,
                            "final_confidence": f.final_confidence,
                            "evidence": [ev.model_dump() for ev in f.evidence],
                            "affected_symbol": f.affected_symbol,
                            "related_files": f.related_files,
                            "related_symbols": f.related_symbols,
                            "agent_name": f.agent_name,
                            "source_agents": f.source_agents or [f.agent_name],
                            "duplicate_of": f.duplicate_of,
                            "root_cause_id": f.root_cause_id,
                            "finding_group_id": f.finding_group_id,
                            "status": f.status.value if hasattr(f.status, "value") else str(f.status),
                            "validation_notes": f.validation_notes,
                        }
                    )
                for f in rejected_findings:
                    all_findings_to_store.append(
                        {
                            "id": f.finding_id,
                            "review_job_id": job.id,
                            "agent_run_id": created_agent_runs.get(f.agent_name),
                            "file_path": f.file_path,
                            "line_number": f.line_number,
                            "side": f.side,
                            "start_line": f.start_line,
                            "start_side": f.start_side,
                            "category": f.category.value if hasattr(f.category, "value") else str(f.category),
                            "severity": f.severity.value if hasattr(f.severity, "value") else str(f.severity),
                            "original_severity": f.original_severity,
                            "final_severity": f.final_severity,
                            "title": f.title,
                            "description": f.description,
                            "impact": f.impact,
                            "recommendation": f.recommendation,
                            "confidence": f.confidence,
                            "specialist_confidence": f.specialist_confidence,
                            "judge_confidence": f.judge_confidence,
                            "final_confidence": f.final_confidence,
                            "evidence": [ev.model_dump() for ev in f.evidence],
                            "affected_symbol": f.affected_symbol,
                            "related_files": f.related_files,
                            "related_symbols": f.related_symbols,
                            "agent_name": f.agent_name,
                            "source_agents": f.source_agents or [f.agent_name],
                            "duplicate_of": f.duplicate_of,
                            "root_cause_id": f.root_cause_id,
                            "finding_group_id": f.finding_group_id,
                            "status": "REJECTED",
                            "validation_notes": f.validation_notes,
                        }
                    )
                for f in final_state.get("invalid_findings", []):
                    all_findings_to_store.append(
                        {
                            "id": f.finding_id,
                            "review_job_id": job.id,
                            "agent_run_id": created_agent_runs.get(f.agent_name),
                            "file_path": f.file_path,
                            "line_number": f.line_number,
                            "side": f.side,
                            "start_line": f.start_line,
                            "start_side": f.start_side,
                            "category": f.category.value if hasattr(f.category, "value") else str(f.category),
                            "severity": f.severity.value if hasattr(f.severity, "value") else str(f.severity),
                            "original_severity": f.severity.value if hasattr(f.severity, "value") else str(f.severity),
                            "final_severity": f.severity.value if hasattr(f.severity, "value") else str(f.severity),
                            "title": f.title,
                            "description": f.description,
                            "impact": f.impact,
                            "recommendation": f.recommendation,
                            "confidence": f.confidence,
                            "specialist_confidence": f.confidence,
                            "judge_confidence": 0.0,
                            "final_confidence": 0.0,
                            "evidence": [ev.model_dump() for ev in f.evidence],
                            "affected_symbol": f.affected_symbol,
                            "related_files": f.related_files,
                            "related_symbols": f.related_symbols,
                            "agent_name": f.agent_name,
                            "source_agents": [f.agent_name] if f.agent_name else [],
                            "duplicate_of": None,
                            "root_cause_id": None,
                            "finding_group_id": None,
                            "status": "REJECTED",
                            "validation_notes": f.validation_notes or "Rejected at Gate 1: Diff Boundary Failure",
                        }
                    )

                if all_findings_to_store:
                    for item in all_findings_to_store:
                        self.finding_repo.upsert_finding(item)

                # Final review job update
                job.total_tokens = final_state.get("total_tokens", 0)
                job.estimated_cost = final_state.get("estimated_cost", 0.0)
                job.agents_executed = final_state.get("selected_specialists", [])

                execution_status = final_state.get("execution_status", "COMPLETED")
                if execution_status == "PARTIAL":
                    job.status = ReviewJobStatus.PARTIAL
                else:
                    job.status = ReviewJobStatus.COMPLETED

                from datetime import datetime
                job.completed_at = datetime.now(UTC)
                self.db.commit()
                self.db.refresh(job)

                logger.info(
                    f"Review job {job.id} {job.status.value} with {len(final_state.get('validated_findings', []))} valid findings.",
                    extra={"event": "review_job_completed", "extra_fields": {"job_id": job.id}},
                )

                # 16. Policy Governance & Publication Preparation
                try:
                    from app.models.github_publication import PublicationStatus
                    from app.services.publication_service import PublicationService
                    pub_service = PublicationService(self.db)
                    pub_record, _approval_req = pub_service.prepare_publication(
                        review_job_id=job.id,
                        action="COMMENT",
                        requested_by="codeguard-agent",
                    )
                    # If publication does not require human approval and is PENDING, dispatch publication task
                    if pub_record and pub_record.status == PublicationStatus.PENDING:
                        try:
                            from app.workers.tasks import publish_review_task
                            publish_review_task.delay(pub_record.id)
                        except Exception as pub_err:
                            logger.warning(
                                f"Notice: Publication task dispatch deferred for review job {job.id}: {pub_err}"
                            )
                except Exception as pub_prep_err:
                    logger.warning(
                        f"Notice: Publication preparation deferred for review job {job.id}: {pub_prep_err}"
                    )

                return job

        except Exception as exc:
            error_msg = f"{exc.__class__.__name__}: {str(exc)}"
            logger.error(
                f"Review job {job_id} failed: {error_msg}",
                extra={"event": "review_job_failed", "extra_fields": {"error": error_msg}},
                exc_info=True,
            )
            failed_job = self.job_repo.mark_failed(job.id, error_msg)
            if isinstance(exc, GitHubAPIError) and exc.retryable:
                raise
            return failed_job if failed_job is not None else job
        finally:
            if cleanup_source:
                try:
                    cleanup_source()
                except Exception as clean_err:
                    logger.warning(
                        f"Failed to cleanup ephemeral workspace for {job_id}: {clean_err}"
                    )

    async def rerun_job(self, job_id: str) -> ReviewJob:
        """Reset and re-execute a review job without deleting historical artifacts."""
        job = self.job_repo.get_by_id(job_id)
        if not job:
            raise EntityNotFoundError("ReviewJob", job_id)
        job.status = ReviewJobStatus.PENDING
        job.error_message = None
        self.db.commit()
        return await self.execute_job(job_id)

