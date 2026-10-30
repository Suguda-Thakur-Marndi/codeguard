"use client";

import React, { useEffect, useState } from "react";
import { api } from "../../lib/api";
import {
  CodeSymbol,
  FileDependency,
  RelevantContext,
  Repository,
  RepositoryIndex,
} from "../../lib/types";

export default function DebugPage() {
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [selectedRepoId, setSelectedRepoId] = useState<string>("");
  const [repoIndex, setRepoIndex] = useState<RepositoryIndex | null>(null);
  const [symbols, setSymbols] = useState<CodeSymbol[]>([]);
  const [fileDependencies, setFileDependencies] = useState<FileDependency[]>([]);
  const [targetFilePath, setTargetFilePath] = useState<string>("");
  const [targetSymbolName, setTargetSymbolName] = useState<string>("");
  const [contextResult, setContextResult] = useState<RelevantContext | null>(null);
  const [reviewJobIdInput, setReviewJobIdInput] = useState<string>("");
  const [debugJobData, setDebugJobData] = useState<any>(null);

  const [activeTab, setActiveTab] = useState<
    "index" | "symbols" | "dependencies" | "context" | "review_job"
  >("index");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadRepos() {
      try {
        const res = await api.getRepositories(1, 100);
        setRepositories(res.items);
        if (res.items.length > 0) {
          setSelectedRepoId(res.items[0].id);
        }
      } catch (err: any) {
        setError(err.message || "Failed to load repositories");
      }
    }
    loadRepos();
  }, []);

  useEffect(() => {
    if (!selectedRepoId) return;
    loadRepoIndex();
    loadSymbols();
  }, [selectedRepoId]);

  async function loadRepoIndex() {
    try {
      const idx = await api.getRepositoryIndex(selectedRepoId);
      setRepoIndex(idx);
    } catch {
      setRepoIndex(null);
    }
  }

  async function loadSymbols() {
    try {
      const res = await api.getRepositorySymbols(selectedRepoId, 1, 100);
      setSymbols(res.items);
    } catch {
      setSymbols([]);
    }
  }

  async function handleLoadDependencies() {
    if (!selectedRepoId || !targetFilePath) return;
    try {
      setLoading(true);
      const deps = await api.getFileDependencies(selectedRepoId, targetFilePath);
      setFileDependencies(deps);
    } catch (err: any) {
      alert(`Error loading dependencies: ${err.message}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleQueryContext() {
    if (!selectedRepoId || !targetFilePath) return;
    try {
      setLoading(true);
      const ctx = await api.getRepositoryContext(
        selectedRepoId,
        targetFilePath,
        undefined,
        targetSymbolName || undefined
      );
      setContextResult(ctx);
    } catch (err: any) {
      alert(`Error querying context: ${err.message}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleInspectReviewJob() {
    if (!reviewJobIdInput.trim()) return;
    try {
      setLoading(true);
      const [diffData, chunksData, linesData] = await Promise.all([
        api.getReviewJobDiff(reviewJobIdInput).catch(() => null),
        api.getReviewJobChunks(reviewJobIdInput).catch(() => null),
        api.getReviewJobChangedLines(reviewJobIdInput).catch(() => null),
      ]);
      setDebugJobData({
        diff: diffData,
        chunks: chunksData,
        changedLines: linesData,
      });
    } catch (err: any) {
      alert(`Error inspecting review job: ${err.message}`);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      {/* Developer Tooling Warning Banner */}
      <div className="p-4 rounded-lg bg-amber-950/40 border border-amber-800/80 text-amber-200 flex items-start justify-between">
        <div>
          <div className="flex items-center space-x-2">
            <span className="px-2 py-0.5 rounded bg-amber-900 text-amber-100 text-[10px] font-bold uppercase tracking-wider">
              Internal Dev Tool
            </span>
            <h2 className="text-sm font-bold">CodeGuard — Code Intelligence Debug Platform</h2>
          </div>
          <p className="text-xs text-amber-300/80 mt-1">
            This console exposes deterministic AST analysis, symbol graphs, and context ranking for platform verification.
          </p>
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-lg bg-rose-950/60 border border-rose-800 text-rose-300 text-sm">
          {error}
        </div>
      )}

      {/* Target Repository Selector */}
      <div className="bg-surface-container-lowest border border-[#262930] rounded-lg p-5 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <label className="text-xs font-semibold text-outline uppercase tracking-wider block mb-1">
            Target Repository
          </label>
          <select
            value={selectedRepoId}
            onChange={(e) => setSelectedRepoId(e.target.value)}
            className="bg-surface-container-low border border-[#262930] text-on-surface text-sm rounded-lg px-3 py-2 min-w-[280px] focus:outline-none focus:border-primary-fixed font-mono"
          >
            {repositories.map((repo) => (
              <option key={repo.id} value={repo.id}>
                {repo.full_name} ({repo.default_branch})
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center space-x-3">
          <button
            onClick={() => {
              loadRepoIndex();
              loadSymbols();
            }}
            className="px-3 py-2 text-xs font-semibold rounded bg-surface-container-high hover:bg-surface-container-highest text-on-surface border border-[#333842] transition"
          >
            Refresh Data
          </button>
        </div>
      </div>

      {/* Debug Tabs */}
      <div className="bg-surface-container-lowest border border-[#262930] rounded-lg overflow-hidden shadow-sm">
        <div className="px-6 py-3 border-b border-[#262930] flex space-x-6 overflow-x-auto">
          {[
            { id: "index", label: "Repository Index State" },
            { id: "symbols", label: `Code Symbols (${symbols.length})` },
            { id: "dependencies", label: "File Dependencies" },
            { id: "context", label: "Context Ranking Engine" },
            { id: "review_job", label: "Review Job Inspector" },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`text-xs font-semibold uppercase tracking-wider pb-2 -mb-3 transition-colors border-b-2 whitespace-nowrap ${
                activeTab === tab.id
                  ? "border-primary-fixed text-primary-fixed font-bold"
                  : "border-transparent text-outline hover:text-on-surface"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="p-6">
          {/* 1. Repository Index State */}
          {activeTab === "index" && (
            <div className="space-y-4">
              <h3 className="text-sm font-semibold text-primary">Repository Index Telemetry</h3>
              {repoIndex ? (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 font-mono text-xs">
                  <div className="bg-surface-container-low p-4 rounded-lg border border-[#262930] space-y-1">
                    <span className="text-outline block text-[11px]">Index Status</span>
                    <span className="text-primary-fixed font-bold text-sm">{repoIndex.status}</span>
                  </div>
                  <div className="bg-surface-container-low p-4 rounded-lg border border-[#262930] space-y-1">
                    <span className="text-outline block text-[11px]">Indexed Commit SHA</span>
                    <span className="text-on-surface font-bold text-sm select-all">{repoIndex.commit_sha}</span>
                  </div>
                  <div className="bg-surface-container-low p-4 rounded-lg border border-[#262930] space-y-1">
                    <span className="text-outline block text-[11px]">Files Processed / Failed</span>
                    <span className="text-on-surface font-bold text-sm">
                      <span className="text-tertiary-fixed-dim">{repoIndex.files_processed}</span> /{" "}
                      <span className="text-error">{repoIndex.files_failed}</span>
                    </span>
                  </div>
                  <div className="bg-surface-container-low p-4 rounded-lg border border-[#262930] space-y-1 md:col-span-3">
                    <span className="text-outline block text-[11px]">Raw Telemetry Dump</span>
                    <pre className="text-on-surface-variant text-[11px] overflow-x-auto mt-2">
                      {JSON.stringify(repoIndex, null, 2)}
                    </pre>
                  </div>
                </div>
              ) : (
                <div className="p-12 text-center text-outline font-label-mono text-xs">
                  No index record found for repository {selectedRepoId}.
                </div>
              )}
            </div>
          )}

          {/* 2. Code Symbols */}
          {activeTab === "symbols" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-primary">Extracted Code Symbols</h3>
                <span className="text-xs font-mono text-outline">Showing up to 100 entries</span>
              </div>
              {symbols.length === 0 ? (
                <div className="p-12 text-center text-outline font-label-mono text-xs">
                  No symbols found. Ensure repository has been indexed.
                </div>
              ) : (
                <div className="overflow-x-auto border border-[#262930] rounded-lg">
                  <table className="w-full text-left text-xs font-mono text-on-surface">
                    <thead className="bg-surface-container-low text-outline uppercase text-[10px] border-b border-[#262930]">
                      <tr>
                        <th className="p-3">Symbol Name</th>
                        <th className="p-3">Kind</th>
                        <th className="p-3">File Path</th>
                        <th className="p-3">Range</th>
                        <th className="p-3">Signature</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#262930]/60">
                      {symbols.map((sym) => (
                        <tr key={sym.id} className="hover:bg-surface-container/50">
                          <td className="p-3 font-semibold text-tertiary-fixed-dim">{sym.name}</td>
                          <td className="p-3">
                            <span className="px-1.5 py-0.5 rounded bg-surface-container-high text-on-surface uppercase text-[10px] border border-[#262930]">
                              {sym.kind}
                            </span>
                          </td>
                          <td className="p-3 text-outline">{sym.file_path}</td>
                          <td className="p-3 text-outline">
                            L{sym.start_line}–L{sym.end_line}
                          </td>
                          <td className="p-3 text-on-surface-variant truncate max-w-xs">
                            {sym.signature || "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* 3. File Dependencies */}
          {activeTab === "dependencies" && (
            <div className="space-y-4">
              <div className="flex items-center space-x-3">
                <input
                  type="text"
                  placeholder="Enter file path (e.g. services/payment_service.py)"
                  value={targetFilePath}
                  onChange={(e) => setTargetFilePath(e.target.value)}
                  className="bg-surface-container-low border border-[#262930] text-on-surface text-xs font-mono rounded-lg px-3 py-2 w-80 focus:outline-none focus:border-primary-fixed"
                />
                <button
                  onClick={handleLoadDependencies}
                  disabled={loading || !targetFilePath}
                  className="px-3 py-2 text-xs font-semibold rounded bg-primary-container text-on-primary-container hover:brightness-105 disabled:opacity-50 transition"
                >
                  Query Dependencies
                </button>
              </div>

              {fileDependencies.length > 0 ? (
                <div className="overflow-x-auto border border-[#262930] rounded-lg">
                  <table className="w-full text-left text-xs font-mono text-on-surface">
                    <thead className="bg-surface-container-low text-outline uppercase text-[10px] border-b border-[#262930]">
                      <tr>
                        <th className="p-3">Source File</th>
                        <th className="p-3">Dependency Type</th>
                        <th className="p-3">Target File / Module</th>
                        <th className="p-3">External</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#262930]/60">
                      {fileDependencies.map((dep, idx) => (
                        <tr key={idx} className="hover:bg-surface-container/50">
                          <td className="p-3 text-outline">{dep.source_file}</td>
                          <td className="p-3">
                            <span className="px-1.5 py-0.5 rounded bg-secondary-container/40 text-secondary border border-secondary/30 uppercase text-[10px]">
                              {dep.dependency_type}
                            </span>
                          </td>
                          <td className="p-3 font-semibold text-primary">{dep.target_file}</td>
                          <td className="p-3 text-outline">
                            {dep.is_external ? "true" : "false"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="p-8 text-center text-outline font-label-mono text-xs bg-surface-container-low rounded-lg border border-[#262930]">
                  Enter a file path and query to inspect its static import relationships.
                </div>
              )}
            </div>
          )}

          {/* 4. Context Ranking Engine */}
          {activeTab === "context" && (
            <div className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <input
                  type="text"
                  placeholder="Changed file path (e.g. services/payment_service.py)"
                  value={targetFilePath}
                  onChange={(e) => setTargetFilePath(e.target.value)}
                  className="bg-surface-container-low border border-[#262930] text-on-surface text-xs font-mono rounded-lg px-3 py-2 focus:outline-none focus:border-primary-fixed"
                />
                <input
                  type="text"
                  placeholder="Changed symbol (optional, e.g. PaymentService.refund)"
                  value={targetSymbolName}
                  onChange={(e) => setTargetSymbolName(e.target.value)}
                  className="bg-surface-container-low border border-[#262930] text-on-surface text-xs font-mono rounded-lg px-3 py-2 focus:outline-none focus:border-primary-fixed"
                />
                <button
                  onClick={handleQueryContext}
                  disabled={loading || !targetFilePath}
                  className="px-4 py-2 text-xs font-semibold rounded bg-primary-container text-on-primary-container hover:brightness-105 disabled:opacity-50 transition"
                >
                  Simulate Context Ranking
                </button>
              </div>

              {contextResult ? (
                <div className="bg-surface-container-low p-5 rounded-lg border border-[#262930] font-mono text-xs space-y-4">
                  <div className="flex items-center justify-between border-b border-[#262930] pb-3">
                    <span className="font-bold text-primary">
                      Context Budget: {contextResult.total_characters} characters total
                    </span>
                    <span className="text-outline">
                      Changed Symbol: {contextResult.changed_symbol || "File Level"}
                    </span>
                  </div>

                  <div>
                    <h4 className="text-outline uppercase text-[10px] font-semibold tracking-wider mb-2">
                      Ranked Context Items (Deterministic Priority)
                    </h4>
                    <div className="divide-y divide-[#262930] border border-[#262930] rounded-lg overflow-hidden">
                      {contextResult.ranked_items.map((item, idx) => (
                        <div key={idx} className="p-3 bg-surface-container-lowest/60 flex items-center justify-between">
                          <div>
                            <span className="text-tertiary-fixed-dim font-semibold">{item.name}</span>
                            <span className="text-outline ml-2">({item.file_path})</span>
                            <div className="text-[11px] text-outline mt-0.5">
                              Reasons: {item.reasons.join(", ")}
                            </div>
                          </div>
                          <span className="px-2 py-0.5 rounded bg-secondary-container/40 text-secondary font-bold border border-secondary/30">
                            {(item.relevance_score * 100).toFixed(0)}%
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="p-8 text-center text-outline font-label-mono text-xs bg-surface-container-low rounded-lg border border-[#262930]">
                  Provide changed file and trigger ranking simulation.
                </div>
              )}
            </div>
          )}

          {/* 5. Review Job Inspector */}
          {activeTab === "review_job" && (
            <div className="space-y-4">
              <div className="flex items-center space-x-3">
                <input
                  type="text"
                  placeholder="Enter Review Job ID (UUID)"
                  value={reviewJobIdInput}
                  onChange={(e) => setReviewJobIdInput(e.target.value)}
                  className="bg-surface-container-low border border-[#262930] text-on-surface text-xs font-mono rounded-lg px-3 py-2 w-96 focus:outline-none focus:border-primary-fixed"
                />
                <button
                  onClick={handleInspectReviewJob}
                  disabled={loading || !reviewJobIdInput}
                  className="px-4 py-2 text-xs font-semibold rounded bg-primary-container text-on-primary-container hover:brightness-105 disabled:opacity-50 transition"
                >
                  Inspect Artifacts
                </button>
              </div>

              {debugJobData ? (
                <div className="bg-surface-container-low p-4 rounded-lg border border-[#262930] font-mono text-xs space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    <div className="p-3 rounded bg-surface-container-lowest border border-[#262930]">
                      <span className="text-outline text-[10px] block">Diff Files Parsed</span>
                      <span className="text-primary font-bold text-sm">
                        {debugJobData.diff ? debugJobData.diff.length : "N/A"}
                      </span>
                    </div>
                    <div className="p-3 rounded bg-surface-container-lowest border border-[#262930]">
                      <span className="text-outline text-[10px] block">AST Chunks Extracted</span>
                      <span className="text-primary font-bold text-sm">
                        {debugJobData.chunks ? debugJobData.chunks.length : "N/A"}
                      </span>
                    </div>
                    <div className="p-3 rounded bg-surface-container-lowest border border-[#262930]">
                      <span className="text-outline text-[10px] block">Changed Line Index</span>
                      <span className="text-primary font-bold text-sm">
                        {debugJobData.changedLines ? "Indexed" : "N/A"}
                      </span>
                    </div>
                  </div>

                  <div>
                    <span className="text-outline text-[10px] block mb-1">
                      Raw Changed-Line Mapping JSON
                    </span>
                    <pre className="p-3 bg-surface-container-lowest rounded border border-[#262930] max-h-64 overflow-y-auto text-on-surface-variant text-[11px]">
                      {JSON.stringify(debugJobData, null, 2)}
                    </pre>
                  </div>
                </div>
              ) : (
                <div className="p-8 text-center text-outline font-label-mono text-xs bg-surface-container-low rounded-lg border border-[#262930]">
                  Enter a review job ID to inspect parsed diff, AST chunks, and line mappings.
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
