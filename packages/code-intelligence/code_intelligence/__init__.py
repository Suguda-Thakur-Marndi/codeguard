"""CodeGuard - Code Intelligence Package."""

from code_intelligence.ast.mapper import DiffLineMapping, DiffToASTMapper
from code_intelligence.context.ranker import ContextRanker
from code_intelligence.diff.line_index import ChangedLineIndex
from code_intelligence.diff.parser import UnifiedDiffParser
from code_intelligence.engine import (
    CodeIntelligenceEngine,
    IndexingResult,
    PRAnalysisResult,
)
from code_intelligence.filter.file_filter import FileFilter
from code_intelligence.graph.builder import RepositoryGraph, RepositoryGraphBuilder
from code_intelligence.languages.base import LanguageParser
from code_intelligence.languages.javascript import JavaScriptParser
from code_intelligence.languages.python import PythonParser
from code_intelligence.languages.registry import (
    LanguageParserRegistry,
    default_registry,
)
from code_intelligence.languages.typescript import TypeScriptParser
from code_intelligence.models import (
    ASTChunk,
    DiagnosticSeverity,
    DiagnosticStage,
    DiffFile,
    DiffHunk,
    DiffLine,
    DiffLineType,
    FileDependency,
    LineSide,
    ParserDiagnostic,
    RankedContextItem,
    ReferenceType,
    RelevantContext,
    Symbol,
    SymbolKind,
    SymbolReference,
)
from code_intelligence.references.resolver import ReferenceResolver
from code_intelligence.source.provider import (
    LocalDiskRepositorySourceProvider,
    MemoryRepositorySourceProvider,
    RepositorySourceProvider,
)

__all__ = [
    "ASTChunk",
    "ChangedLineIndex",
    "CodeIntelligenceEngine",
    "ContextRanker",
    "DiagnosticSeverity",
    "DiagnosticStage",
    "DiffFile",
    "DiffHunk",
    "DiffLine",
    "DiffLineMapping",
    "DiffLineType",
    "DiffToASTMapper",
    "FileDependency",
    "FileFilter",
    "IndexingResult",
    "JavaScriptParser",
    "LanguageParser",
    "LanguageParserRegistry",
    "LineSide",
    "LocalDiskRepositorySourceProvider",
    "MemoryRepositorySourceProvider",
    "PRAnalysisResult",
    "ParserDiagnostic",
    "PythonParser",
    "RankedContextItem",
    "ReferenceResolver",
    "ReferenceType",
    "RelevantContext",
    "RepositoryGraph",
    "RepositoryGraphBuilder",
    "RepositorySourceProvider",
    "Symbol",
    "SymbolKind",
    "SymbolReference",
    "TypeScriptParser",
    "UnifiedDiffParser",
    "default_registry",
]
