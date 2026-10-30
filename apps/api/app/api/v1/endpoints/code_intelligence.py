"""Code Intelligence REST API endpoints for repository AST, symbols, and context."""

import math

from code_intelligence.filter.file_filter import FileFilter
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user_or_bypass, verify_tenant_access
from app.db.repositories.repository_repo import RepositoryRepository
from app.db.session import get_db
from app.models.repository import Repository
from app.schemas.code_intelligence import (
    CodeSymbolRead,
    FileDependencyRead,
    IndexTriggerRequest,
    RelevantContextSchema,
    RepositoryIndexRead,
)
from app.schemas.common import PaginatedResponse
from app.services.code_intelligence_service import CodeIntelligenceService

router = APIRouter(prefix="/repositories", tags=["Code Intelligence"])


def _get_verified_repo(repository_id: str, db: Session, user: dict) -> Repository:
    """Retrieve repository and enforce tenant authorization."""
    repo = RepositoryRepository(db).get_by_id(repository_id)
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository with ID '{repository_id}' not found",
        )
    verify_tenant_access(user, repo.organization_id, db=db)
    return repo


@router.get("/{repository_id}/index", response_model=RepositoryIndexRead)
def get_repository_index_status(
    repository_id: str,
    commit_sha: str | None = Query(None, description="Target commit SHA"),
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user_or_bypass),
) -> RepositoryIndexRead:
    """Retrieve indexing status, metadata, and performance metrics for a repository."""
    _get_verified_repo(repository_id, db, _user)

    service = CodeIntelligenceService(db)
    idx = service.get_index_status(repository_id, commit_sha=commit_sha)
    if not idx:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Index for repository '{repository_id}' not found",
        )
    return RepositoryIndexRead.model_validate(idx)


@router.post("/{repository_id}/index", response_model=RepositoryIndexRead)
def trigger_repository_indexing(
    repository_id: str,
    body: IndexTriggerRequest = IndexTriggerRequest(),
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user_or_bypass),
) -> RepositoryIndexRead:
    """Trigger full or incremental repository indexing."""
    _get_verified_repo(repository_id, db, _user)

    service = CodeIntelligenceService(db)
    idx = service.trigger_indexing(
        repository_id=repository_id,
        commit_sha=body.commit_sha,
        force_reindex=body.force_reindex,
    )
    return RepositoryIndexRead.model_validate(idx)


@router.get("/{repository_id}/symbols", response_model=PaginatedResponse[CodeSymbolRead])
def list_repository_symbols(
    repository_id: str,
    commit_sha: str | None = Query(None, description="Commit SHA filter"),
    file_path: str | None = Query(None, description="File path filter"),
    kind: str | None = Query(None, description="Symbol kind filter (FUNCTION, METHOD, CLASS, etc.)"),
    name: str | None = Query(None, description="Name search substring"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Page size"),
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user_or_bypass),
) -> PaginatedResponse[CodeSymbolRead]:
    """List code symbols with pagination, kind filtering, and name search."""
    _get_verified_repo(repository_id, db, _user)
    service = CodeIntelligenceService(db)
    symbols, total = service.get_symbols(
        repository_id=repository_id,
        commit_sha=commit_sha,
        file_path=file_path,
        kind=kind,
        name_filter=name,
        page=page,
        page_size=page_size,
    )
    total_pages = math.ceil(total / page_size) if total > 0 else 1

    return PaginatedResponse[CodeSymbolRead](
        items=[CodeSymbolRead.model_validate(s) for s in symbols],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/{repository_id}/symbols/{symbol_id}", response_model=CodeSymbolRead)
def get_symbol_detail(
    repository_id: str,
    symbol_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user_or_bypass),
) -> CodeSymbolRead:
    """Retrieve details of a specific code symbol by ID."""
    _get_verified_repo(repository_id, db, _user)
    service = CodeIntelligenceService(db)
    symbol = service.get_symbol_by_id(symbol_id)
    if not symbol or symbol.repository_id != repository_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Symbol with ID '{symbol_id}' not found in repository",
        )
    return CodeSymbolRead.model_validate(symbol)


@router.get("/{repository_id}/files/{file_path:path}/symbols", response_model=list[CodeSymbolRead])
def get_file_symbols(
    repository_id: str,
    file_path: str,
    commit_sha: str | None = Query(None, description="Commit SHA filter"),
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user_or_bypass),
) -> list[CodeSymbolRead]:
    """Retrieve all symbols defined in a specific repository file."""
    _get_verified_repo(repository_id, db, _user)
    if not FileFilter.is_safe_path(file_path):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file path or path traversal detected: '{file_path}'",
        )
    service = CodeIntelligenceService(db)
    symbols = service.get_file_symbols(repository_id, file_path, commit_sha=commit_sha)
    return [CodeSymbolRead.model_validate(s) for s in symbols]


@router.get("/{repository_id}/files/{file_path:path}/dependencies", response_model=list[FileDependencyRead])
def get_file_dependencies(
    repository_id: str,
    file_path: str,
    commit_sha: str | None = Query(None, description="Commit SHA filter"),
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user_or_bypass),
) -> list[FileDependencyRead]:
    """Retrieve static file dependencies (imports) for a specific file."""
    _get_verified_repo(repository_id, db, _user)
    if not FileFilter.is_safe_path(file_path):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file path or path traversal detected: '{file_path}'",
        )
    service = CodeIntelligenceService(db)
    deps = service.get_file_dependencies(repository_id, file_path, commit_sha=commit_sha)
    return [FileDependencyRead.model_validate(d) for d in deps]


@router.get("/{repository_id}/context", response_model=RelevantContextSchema)
def get_code_context(
    repository_id: str,
    changed_file: str = Query(..., description="Path to changed file"),
    changed_symbol: str | None = Query(None, description="Target changed symbol name"),
    commit_sha: str | None = Query(None, description="Target commit SHA"),
    max_files: int = Query(15, ge=1, le=50, description="Max files allowed in budget"),
    max_symbols: int = Query(30, ge=1, le=100, description="Max symbols allowed in budget"),
    max_characters: int = Query(25000, ge=1000, le=100000, description="Max character budget"),
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user_or_bypass),
) -> RelevantContextSchema:
    """Retrieve semantically ranked context for a changed file and symbol."""
    _get_verified_repo(repository_id, db, _user)
    if not FileFilter.is_safe_path(changed_file):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid changed file path or path traversal detected: '{changed_file}'",
        )
    service = CodeIntelligenceService(db)
    context = service.get_context(
        repository_id=repository_id,
        changed_file=changed_file,
        changed_symbol=changed_symbol,
        commit_sha=commit_sha,
        max_files=max_files,
        max_symbols=max_symbols,
        max_characters=max_characters,
    )
    return RelevantContextSchema.model_validate(context.model_dump())
