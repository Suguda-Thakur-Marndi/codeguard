"""Code Intelligence domain service coordinating repository indexing and context retrieval."""

import os
from datetime import UTC, datetime

from code_intelligence.context.ranker import ContextRanker
from code_intelligence.engine import CodeIntelligenceEngine
from code_intelligence.graph.builder import RepositoryGraphBuilder
from code_intelligence.models import (
    FileDependency as CIMFileDependency,
)
from code_intelligence.models import (
    RelevantContext,
    SymbolKind,
)
from code_intelligence.models import (
    Symbol as CIMSymbol,
)
from code_intelligence.models import (
    SymbolReference as CIMSymbolReference,
)
from code_intelligence.source.provider import (
    LocalDiskRepositorySourceProvider,
    MemoryRepositorySourceProvider,
    RepositorySourceProvider,
)
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import EntityNotFoundError
from app.core.logging import logger
from app.db.repositories.code_symbol_repo import CodeSymbolRepository
from app.db.repositories.file_dependency_repo import FileDependencyRepository
from app.db.repositories.repository_index_repo import RepositoryIndexRepository
from app.db.repositories.repository_repo import RepositoryRepository
from app.db.repositories.symbol_reference_repo import SymbolReferenceRepository
from app.models.code_symbol import CodeSymbol
from app.models.file_dependency import FileDependency
from app.models.repository_index import IndexStatus, RepositoryIndex


class CodeIntelligenceService:
    """Service managing repository AST indexing, dependency graphs, and context ranking."""

    def __init__(self, db: Session, engine: CodeIntelligenceEngine | None = None):
        self.db = db
        self.engine = engine or CodeIntelligenceEngine()
        self.repo_repo = RepositoryRepository(db)
        self.index_repo = RepositoryIndexRepository(db)
        self.symbol_repo = CodeSymbolRepository(db)
        self.ref_repo = SymbolReferenceRepository(db)
        self.dep_repo = FileDependencyRepository(db)

    def get_default_commit(self, repository_id: str) -> str:
        """Resolve a fallback commit SHA for repository if not specified."""
        idx = self.index_repo.get_latest_for_repo(repository_id)
        if idx:
            return idx.commit_sha
        repo = self.repo_repo.get_by_id(repository_id)
        if repo and repo.pull_requests:
            return repo.pull_requests[0].head_sha
        return "main"

    def get_index_status(
        self, repository_id: str, commit_sha: str | None = None
    ) -> RepositoryIndex | None:
        """Fetch index record for repository at commit_sha or latest."""
        if commit_sha:
            return self.index_repo.get_by_repo_and_commit(repository_id, commit_sha)
        return self.index_repo.get_latest_for_repo(repository_id)

    def trigger_indexing(
        self,
        repository_id: str,
        commit_sha: str | None = None,
        force_reindex: bool = False,
        source_provider: RepositorySourceProvider | None = None,
    ) -> RepositoryIndex:
        """
        Execute indexing on repository source code at commit_sha.
        Persists symbols, dependencies, and references into PostgreSQL.
        """
        repo = self.repo_repo.get_by_id(repository_id)
        if not repo:
            raise EntityNotFoundError("Repository", repository_id)

        target_sha = commit_sha or self.get_default_commit(repository_id)

        # Idempotency / Cache check
        existing_idx = self.index_repo.get_by_repo_and_commit(repository_id, target_sha)
        if existing_idx and existing_idx.status == IndexStatus.READY and not force_reindex:
            logger.info(
                f"Repository {repository_id} at {target_sha} is already indexed and READY. Returning cached index.",
                extra={"event": "code_index_cached", "extra_fields": {"repo": repo.full_name, "commit": target_sha}},
            )
            return existing_idx

        # Mark as INDEXING
        idx = self.index_repo.upsert_index(
            repository_id=repository_id,
            commit_sha=target_sha,
            status=IndexStatus.INDEXING,
            metadata_json={"started_at": datetime.now(UTC).isoformat()},
        )

        logger.info(
            f"Starting code indexing for {repo.full_name} at commit {target_sha}",
            extra={"event": "code_index_started", "extra_fields": {"repo": repo.full_name, "commit": target_sha}},
        )

        try:
            # Determine provider if not explicitly passed
            provider = source_provider
            if not provider:
                is_fixture = (
                    settings.APP_ENV in ("development", "test")
                    and (repo.owner == "fixtures" or repo.name in ("python_repo", "javascript_repo", "typescript_repo"))
                )
                fixture_path = os.path.abspath(os.path.join(os.getcwd(), "fixtures", repo.name))
                if is_fixture and os.path.isdir(fixture_path):
                    provider = LocalDiskRepositorySourceProvider(fixture_path)
                else:
                    provider = MemoryRepositorySourceProvider()

            # Run engine indexing
            res = self.engine.index_repository(repository_id, target_sha, provider)

            # Purge any prior data for this commit
            self.symbol_repo.delete_all_for_commit(repository_id, target_sha)
            self.ref_repo.delete_all_for_commit(repository_id, target_sha)
            self.dep_repo.delete_all_for_commit(repository_id, target_sha)

            # Bulk persist symbols
            symbol_records = [
                {
                    "repository_id": repository_id,
                    "commit_sha": target_sha,
                    "file_path": s.file_path,
                    "name": s.name,
                    "kind": s.kind.value,
                    "language": s.language,
                    "start_line": s.start_line,
                    "end_line": s.end_line,
                    "start_byte": s.start_byte,
                    "end_byte": s.end_byte,
                    "signature": s.signature,
                    "return_type": s.return_type,
                    "parameters": s.parameters,
                    "parent_symbol": s.parent_symbol,
                    "source_code": s.source_code,
                    "metadata_json": s.metadata,
                }
                for s in res.symbols
            ]
            self.symbol_repo.bulk_create(symbol_records)

            # Bulk persist references
            ref_records = [
                {
                    "repository_id": repository_id,
                    "commit_sha": target_sha,
                    "source_symbol": r.source_symbol,
                    "target_symbol": r.target_symbol,
                    "source_file": r.source_file,
                    "target_file": r.target_file,
                    "line_number": r.line_number,
                    "reference_type": r.reference_type.value,
                    "resolved": r.resolved,
                    "metadata_json": r.metadata,
                }
                for r in res.references
            ]
            self.ref_repo.bulk_create(ref_records)

            # Bulk persist file dependencies
            dep_records = [
                {
                    "repository_id": repository_id,
                    "commit_sha": target_sha,
                    "source_file": d.source_file,
                    "target_file": d.target_file,
                    "dependency_type": d.dependency_type,
                    "imported_symbols": d.imported_symbols,
                    "line_number": d.line_number,
                    "metadata_json": d.metadata,
                }
                for d in res.dependencies
            ]
            self.dep_repo.bulk_create(dep_records)

            # Update index state to READY
            status_enum = IndexStatus[res.status] if res.status in IndexStatus.__members__ else IndexStatus.READY
            idx = self.index_repo.upsert_index(
                repository_id=repository_id,
                commit_sha=target_sha,
                status=status_enum,
                last_indexed_commit=target_sha,
                files_processed=res.files_processed,
                files_failed=res.files_failed,
                error_count=res.error_count,
                metadata_json={
                    "metrics": res.metrics,
                    "diagnostics": [d.model_dump() for d in res.diagnostics[:50]],
                    "symbols_count": len(res.symbols),
                    "references_count": len(res.references),
                    "dependencies_count": len(res.dependencies),
                },
            )

            logger.info(
                f"Repository indexing completed for {repo.full_name} at {target_sha}: {res.files_processed} files processed.",
                extra={"event": "code_index_completed", "extra_fields": {"repo": repo.full_name, "commit": target_sha}},
            )
            return idx

        except Exception as exc:
            logger.error(f"Repository indexing failed for {repository_id}: {exc}", exc_info=True)
            return self.index_repo.upsert_index(
                repository_id=repository_id,
                commit_sha=target_sha,
                status=IndexStatus.FAILED,
                error_count=1,
                metadata_json={"error": str(exc)},
            )

    def get_symbols(
        self,
        repository_id: str,
        commit_sha: str | None = None,
        file_path: str | None = None,
        kind: str | None = None,
        name_filter: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[CodeSymbol], int]:
        sha = commit_sha or self.get_default_commit(repository_id)
        return self.symbol_repo.list_symbols(
            repository_id=repository_id,
            commit_sha=sha,
            file_path=file_path,
            kind=kind,
            name_filter=name_filter,
            page=page,
            page_size=page_size,
        )

    def get_symbol_by_id(self, symbol_id: str) -> CodeSymbol | None:
        return self.symbol_repo.get_by_id(symbol_id)

    def get_file_symbols(
        self, repository_id: str, file_path: str, commit_sha: str | None = None
    ) -> list[CodeSymbol]:
        sha = commit_sha or self.get_default_commit(repository_id)
        return self.symbol_repo.get_by_file_path(repository_id, sha, file_path)

    def get_file_dependencies(
        self, repository_id: str, file_path: str, commit_sha: str | None = None
    ) -> list[FileDependency]:
        sha = commit_sha or self.get_default_commit(repository_id)
        return self.dep_repo.get_dependencies_for_file(repository_id, sha, file_path)

    def get_context(
        self,
        repository_id: str,
        changed_file: str,
        changed_symbol: str | None = None,
        commit_sha: str | None = None,
        max_files: int = 15,
        max_symbols: int = 30,
        max_characters: int = 25000,
    ) -> RelevantContext:
        """Retrieve semantically ranked context for a file and symbol."""
        sha = commit_sha or self.get_default_commit(repository_id)

        # Retrieve symbols and dependencies from DB
        db_symbols, _ = self.symbol_repo.list_symbols(repository_id, commit_sha=sha, page=1, page_size=200)
        db_refs = self.ref_repo.list_references(repository_id, commit_sha=sha)
        db_deps = self.dep_repo.get_dependencies_for_file(repository_id, sha, changed_file)

        # Convert ORM to Code Intelligence models
        ci_symbols = [
            CIMSymbol(
                symbol_id=s.id,
                name=s.name,
                kind=SymbolKind(s.kind) if s.kind in SymbolKind.__members__ else SymbolKind.FUNCTION,
                file_path=s.file_path,
                start_line=s.start_line,
                end_line=s.end_line,
                start_byte=s.start_byte,
                end_byte=s.end_byte,
                signature=s.signature,
                return_type=s.return_type,
                parent_symbol=s.parent_symbol,
                language=s.language,
                source_code=s.source_code,
            )
            for s in db_symbols
        ]

        ci_refs = [
            CIMSymbolReference(
                source_symbol=r.source_symbol,
                target_symbol=r.target_symbol,
                source_file=r.source_file,
                target_file=r.target_file,
                line_number=r.line_number,
                reference_type=r.reference_type,  # type: ignore
                resolved=r.resolved,
            )
            for r in db_refs
        ]

        ci_deps = [
            CIMFileDependency(
                source_file=d.source_file,
                target_file=d.target_file,
                dependency_type=d.dependency_type,
                imported_symbols=d.imported_symbols,
                line_number=d.line_number,
            )
            for d in db_deps
        ]

        # Build in-memory graph
        graph = RepositoryGraphBuilder.build_graph(
            repository_id=repository_id,
            commit_sha=sha,
            symbols=ci_symbols,
            references=ci_refs,
            dependencies=ci_deps,
        )

        ranker = ContextRanker()
        return ranker.build_relevant_context(
            repository_id=repository_id,
            commit_sha=sha,
            changed_file=changed_file,
            changed_symbol=changed_symbol,
            graph=graph,
            symbols=ci_symbols,
            max_files=max_files,
            max_symbols=max_symbols,
            max_characters=max_characters,
        )
