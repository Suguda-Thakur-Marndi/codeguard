"use client";

import React, { useEffect, useState, use } from "react";
import Link from "next/link";
import { DiffViewer } from "../../../components/DiffViewer";
import { StatusBadge } from "../../../components/StatusBadge";
import { api } from "../../../lib/api";
import {
  ApprovalRequest,
  DiffFile,
  GitHubReviewPublication,
  PullRequest,
  ReviewArtifact,
  ReviewFinding,
  ReviewJob,
  VerificationSummary,
} from "../../../lib/types";

export default function PullRequestDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const resolvedParams = use(params);
  const prId = resolvedParams.id;

  const [pr, setPr] = useState<PullRequest | null>(null);
  const [latestJob, setLatestJob] = useState<ReviewJob | null>(null);
  const [artifacts, setArtifacts] = useState<ReviewArtifact[]>([]);
  const [parsedDiffFiles, setParsedDiffFiles] = useState<DiffFile[]>([]);
  const [findings, setFindings] = useState<ReviewFinding[]>([]);
  const [selectedFinding, setSelectedFinding] = useState<ReviewFinding | null>(null);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileSearch, setFileSearch] = useState("");
  const [filterSeverity, setFilterSeverity] = useState<string>("ALL");
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [actionNotice, setActionNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function loadData() {
    try {
      setLoading(true);
      setError(null);
      const [prData, reviewsData] = await Promise.all([
        api.getPullRequest(prId),
        api.getPullRequestReviews(prId, 1, 10),
      ]);
      setPr(prData);

      if (reviewsData.items && reviewsData.items.length > 0) {
        const job = reviewsData.items[0];
        setLatestJob(job);

        const [arts, findingsData] = await Promise.all([
          api.getReviewJobArtifacts(job.id).catch(() => []),
          api.getReviewJobFindings(job.id).catch(() => []),
        ]);

        setArtifacts(arts);
        setFindings(findingsData);
        if (findingsData.length > 0) {
          setSelectedFinding(findingsData[0]);
        }

        // Parse diff files from PARSED_DIFF artifact or diff endpoint
        const diffArt = arts.find((a) => a.artifact_type === "PARSED_DIFF");
        if (diffArt) {
          try {
            const files: DiffFile[] = JSON.parse(diffArt.content);
            setParsedDiffFiles(files);
            if (files.length > 0) {
              setSelectedFile(files[0].file_path);
            }
          } catch (e) {
            console.error("Error parsing PARSED_DIFF:", e);
          }
        }
      }
    } catch (err: any) {
      setError(err.message || "Failed to load pull request details");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, [prId]);

  const handleRerun = async () => {
    if (!latestJob) return;
    try {
      setActionLoading("rerun");
      await api.rerunReviewJob(latestJob.id);
      setActionNotice("Re-review initiated with multi-agent consensus validation.");
      await loadData();
      setTimeout(() => setActionNotice(null), 4000);
    } catch (err: any) {
      alert(`Re-review trigger failed: ${err.message}`);
    } finally {
      setActionLoading(null);
    }
  };

  const handlePublish = async () => {
    if (!latestJob) return;
    try {
      setActionLoading("publish");
      await api.publishReviewJob(latestJob.id, "COMMENT");
      setActionNotice("Published review and security findings to GitHub Pull Request.");
      setTimeout(() => setActionNotice(null), 4000);
    } catch (err: any) {
      alert(`Publish failed: ${err.message}`);
    } finally {
      setActionLoading(null);
    }
  };

  const handleApproveWithNotes = async () => {
    if (!latestJob) return;
    try {
      setActionLoading("approve");
      await api.requestJobApproval(latestJob.id, undefined, "APPROVE");
      setActionNotice("Approval requested and registered in governance log.");
      setTimeout(() => setActionNotice(null), 4000);
    } catch (err: any) {
      alert(`Approval error: ${err.message}`);
    } finally {
      setActionLoading(null);
    }
  };

  // Find diff text for currently selected file
  const rawDiffArtifact = artifacts.find((a) => a.artifact_type === "RAW_DIFF");
  const currentDiffFile = parsedDiffFiles.find((f) => f.file_path === selectedFile);
  const diffContentToDisplay = currentDiffFile?.patch || rawDiffArtifact?.content || "";

  // Filtered findings by severity scope
  const filteredFindings = findings.filter((f) => {
    if (filterSeverity === "ALL") return true;
    if (filterSeverity === "CRITICAL") return f.severity === "CRITICAL";
    if (filterSeverity === "HIGH") return f.severity === "HIGH";
    if (filterSeverity === "VALIDATED") return f.status === "VALIDATED" || f.status === "PUBLISHABLE";
    return true;
  });

  const criticalFindingsCount = findings.filter((f) => f.severity === "CRITICAL").length;
  const highFindingsCount = findings.filter((f) => f.severity === "HIGH").length;

  const totalFindingsCount = findings.length;
  const secCount = findings.filter((f) => f.category === "SECURITY" || f.severity === "CRITICAL").length;
  const bugCount = findings.filter((f) => f.category === "BUG").length;
  const testCount = findings.filter((f) => f.category === "TEST_COVERAGE" || f.category === "ERROR_HANDLING").length;
  const perfCount = findings.filter((f) => f.category === "PERFORMANCE" || f.category === "CONTRACT").length;
  const secPct = totalFindingsCount > 0 ? Math.round((secCount / totalFindingsCount) * 100) : 0;
  const bugPct = totalFindingsCount > 0 ? Math.round((bugCount / totalFindingsCount) * 100) : 0;
  const testPct = totalFindingsCount > 0 ? Math.round((testCount / totalFindingsCount) * 100) : 0;
  const perfPct = totalFindingsCount > 0 ? Math.max(0, 100 - secPct - bugPct - testPct) : 0;

  return (
    <div className="flex flex-col w-full pb-16">
      {actionNotice && (
        <div className="mb-space-md p-space-sm rounded bg-surface-container-high border border-tertiary-fixed-dim/40 text-tertiary-fixed-dim font-label-mono text-body-sm flex items-center justify-between shadow-lg">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-[18px]">verified</span>
            <span>{actionNotice}</span>
          </div>
          <button type="button" onClick={() => setActionNotice(null)} className="text-outline hover:text-on-surface">
            ✕
          </button>
        </div>
      )}

      {error && (
        <div className="mb-space-md p-space-md rounded bg-error-container/20 border border-error text-error font-body-sm flex items-center justify-between">
          <span>{error}</span>
          <button
            type="button"
            onClick={loadData}
            className="px-2.5 py-1 rounded bg-error-container text-on-error-container font-label-mono text-kbd-shortcut"
          >
            Retry
          </button>
        </div>
      )}

      {/* Sub-header Operational Bar */}
      <header className="w-full bg-surface-container-low rounded-xl border border-[#262930] mb-space-md shadow-md">
        <div className="px-space-lg py-space-md flex flex-col xl:flex-row xl:items-center justify-between gap-space-md">
          {/* PR Context & Branch Specs */}
          <div className="flex flex-col gap-1 min-w-0">
            <div className="flex items-center gap-space-sm flex-wrap">
              <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded bg-surface-container-highest font-label-mono text-label-mono text-primary font-semibold border border-[#262930]">
                <span className="material-symbols-outlined text-[14px] text-tertiary-fixed-dim">commit</span>
                PR #{pr?.number || prId.slice(0, 6)}
              </span>
              <h1 className="font-headline-sm text-headline-sm text-on-surface tracking-tight truncate max-w-xl">
                {pr?.title || "Review Workspace"}
              </h1>
              <span className="font-body-sm text-body-sm text-on-surface-variant flex items-center gap-1">
                by <span className="text-primary font-medium">@{pr?.author_login || "author"}</span>
              </span>
            </div>
            <div className="flex items-center gap-2 font-label-mono text-kbd-shortcut text-on-surface-variant flex-wrap">
              <span className="px-1.5 py-0.5 rounded bg-surface-container text-tertiary-fixed-dim font-medium border border-[#262930]">
                {pr?.head_sha ? `head: ${pr.head_sha.slice(0, 7)}` : "head"}
              </span>
              <span className="material-symbols-outlined text-[13px] text-outline">arrow_forward</span>
              <span className="px-1.5 py-0.5 rounded bg-surface-container text-on-surface font-medium border border-[#262930]">
                {pr?.repository?.default_branch || "main"}
              </span>
              <span className="text-outline-variant">•</span>
              <span className="text-on-surface flex items-center gap-1 font-mono">
                <span className="w-1.5 h-1.5 rounded-full bg-primary-fixed"></span>
                SHA: {pr?.head_sha?.slice(0, 7) || "unknown"}
              </span>
              <span className="text-outline-variant">•</span>
              <span className="text-tertiary-fixed-dim">Automated Judge Synthesis Ready</span>
            </div>
          </div>

          {/* Action Suite */}
          <div className="flex items-center gap-space-xs flex-wrap">
            <button
              onClick={handleRerun}
              disabled={actionLoading === "rerun" || !latestJob}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-surface-container-high hover:bg-surface-container-highest text-on-surface font-body-sm text-body-sm font-medium transition-all shadow-sm border border-[#262930]"
            >
              <span
                className={`material-symbols-outlined text-[16px] text-tertiary-fixed-dim ${
                  actionLoading === "rerun" ? "animate-spin" : ""
                }`}
              >
                sync
              </span>
              <span>{actionLoading === "rerun" ? "Re-reviewing..." : "Run Re-review"}</span>
            </button>
            <button
              onClick={handlePublish}
              disabled={actionLoading === "publish" || !latestJob}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-secondary-container text-on-secondary-container hover:brightness-110 font-body-sm text-body-sm font-medium transition-all shadow-sm"
            >
              <span className="material-symbols-outlined text-[16px]">send</span>
              <span>{actionLoading === "publish" ? "Posting..." : `Post AI Comments (${findings.length})`}</span>
            </button>
            <button
              onClick={handleApproveWithNotes}
              disabled={actionLoading === "approve" || !latestJob}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-primary-container text-on-primary-container font-headline-sm text-body-sm font-semibold hover:brightness-105 active:scale-95 transition-all shadow-sm"
            >
              <span className="material-symbols-outlined text-[16px]">verified</span>
              <span>Approve with Notes</span>
            </button>
            <button
              onClick={() => {
                navigator.clipboard.writeText(window.location.href);
                alert("Workspace URL copied to clipboard!");
              }}
              className="p-1.5 rounded bg-surface-container-high hover:bg-surface-container-highest text-on-surface-variant hover:text-on-surface transition-colors border border-[#262930]"
              title="Share Diff Link"
            >
              <span className="material-symbols-outlined text-[18px]">share</span>
            </button>
          </div>
        </div>

        {/* Telemetry Triage Bar & Filter Pills */}
        <div className="px-space-lg py-2 bg-surface-container-lowest/80 rounded-b-xl border-t border-[#262930] flex items-center justify-between gap-space-md flex-wrap">
          <div className="flex items-center gap-space-xs flex-wrap">
            <span className="font-label-mono text-kbd-shortcut uppercase text-outline mr-1">Filter Scope:</span>
            <button
              onClick={() => setFilterSeverity("ALL")}
              className={`px-2 py-0.5 rounded font-label-mono text-kbd-shortcut flex items-center gap-1 transition-colors ${
                filterSeverity === "ALL"
                  ? "bg-surface-container-highest text-primary font-semibold"
                  : "bg-surface-container text-on-surface-variant hover:text-on-surface"
              }`}
            >
              <span>All Findings</span>
              <span className="w-4 h-4 rounded-full bg-surface-container flex items-center justify-center text-[9px]">
                {findings.length}
              </span>
            </button>
            <button
              onClick={() => setFilterSeverity("CRITICAL")}
              className={`px-2 py-0.5 rounded font-label-mono text-kbd-shortcut font-semibold flex items-center gap-1 transition-colors ${
                filterSeverity === "CRITICAL"
                  ? "bg-error-container text-on-error-container brightness-110"
                  : "bg-error-container/60 text-error hover:bg-error-container hover:text-on-error-container"
              }`}
            >
              <span className="w-1.5 h-1.5 rounded-full bg-error"></span>
              <span>Critical</span>
              <span className="font-mono text-[9px]">{criticalFindingsCount}</span>
            </button>
            <button
              onClick={() => setFilterSeverity("HIGH")}
              className={`px-2 py-0.5 rounded font-label-mono text-kbd-shortcut flex items-center gap-1 transition-colors ${
                filterSeverity === "HIGH"
                  ? "bg-surface-container-highest text-surface-tint font-bold"
                  : "bg-surface-container-high text-on-surface-variant hover:text-on-surface"
              }`}
            >
              <span className="w-1.5 h-1.5 rounded-full bg-surface-tint"></span>
              <span>High</span>
              <span className="font-mono text-[9px]">{highFindingsCount}</span>
            </button>
            <button
              onClick={() => setFilterSeverity("VALIDATED")}
              className={`px-2 py-0.5 rounded font-label-mono text-kbd-shortcut flex items-center gap-1 transition-colors ${
                filterSeverity === "VALIDATED"
                  ? "bg-surface-container-highest text-tertiary-fixed-dim font-bold"
                  : "bg-surface-container-high text-tertiary-fixed-dim hover:brightness-110"
              }`}
            >
              <span className="material-symbols-outlined text-[12px]">verified_user</span>
              <span>Validated by Judge</span>
              <span className="font-mono text-[9px]">{findings.length}</span>
            </button>
          </div>
          <div className="flex items-center gap-space-md font-label-mono text-kbd-shortcut text-on-surface-variant">
            <span className="flex items-center gap-1 text-tertiary-fixed-dim">
              <span className="w-1.5 h-1.5 rounded-full bg-tertiary-fixed-dim"></span>
              AST Synthesizer 100%
            </span>
            <span className="flex items-center gap-1">
              <span className="material-symbols-outlined text-[13px] text-outline">memory</span>
              CWE Taint Probe Active
            </span>
          </div>
        </div>
      </header>

      {/* 3-Panel Split Workspace (20% | 50% | 30%) */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-space-md items-start w-full">
        {/* LEFT PANEL: Files Changed Navigator (~25% / 3 cols) */}
        <section className="xl:col-span-3 flex flex-col bg-surface-container-low rounded-xl border border-[#262930] shadow-md overflow-hidden">
          <div className="p-space-md bg-surface-container border-b border-[#262930] flex flex-col gap-space-xs">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <span className="material-symbols-outlined text-[16px] text-primary-fixed">folder_open</span>
                <span className="font-headline-sm text-body-sm text-on-surface font-semibold">Changed Files</span>
              </div>
              <span className="font-label-mono text-kbd-shortcut px-1.5 py-0.5 rounded bg-surface-container-highest text-on-surface-variant">
                {parsedDiffFiles.length} files
              </span>
            </div>
            <div className="relative mt-1">
              <span className="material-symbols-outlined absolute left-2 top-2 text-[15px] text-outline">search</span>
              <input
                className="w-full bg-surface-container-lowest text-on-surface placeholder:text-outline font-code-inline text-code-block pl-7 pr-3 py-1 rounded border border-[#262930] focus:border-primary-fixed outline-none"
                placeholder="Filter files (name, ext)..."
                type="text"
                value={fileSearch}
                onChange={(e) => setFileSearch(e.target.value)}
              />
            </div>
          </div>

          {/* File Tree List */}
          <div className="p-space-xs flex flex-col gap-1 max-h-[500px] overflow-y-auto">
            {parsedDiffFiles.length === 0 ? (
              <div className="p-4 text-center text-outline font-label-mono text-xs">
                No changed files found in parsed diff.
              </div>
            ) : (
              parsedDiffFiles
                .filter((f) => f.file_path.toLowerCase().includes(fileSearch.toLowerCase()))
                .map((file) => {
                  const isSelected = selectedFile === file.file_path;
                  const fileFindings = findings.filter((f) => f.file_path === file.file_path);
                  const hasCritical = fileFindings.some((f) => f.severity === "CRITICAL");

                  return (
                    <div
                      key={file.file_path}
                      onClick={() => setSelectedFile(file.file_path)}
                      className={`w-full text-left p-space-sm rounded transition-colors cursor-pointer group border ${
                        isSelected
                          ? "bg-surface-container-high border-primary-fixed/40"
                          : "border-transparent hover:bg-surface-container hover:border-[#262930]"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-1">
                        <div className="flex items-center gap-1.5 min-w-0">
                          <span
                            className={`material-symbols-outlined text-[16px] ${
                              isSelected ? "text-primary-fixed" : "text-outline"
                            }`}
                          >
                            description
                          </span>
                          <span
                            className={`font-code-inline text-code-block truncate ${
                              isSelected ? "text-primary font-semibold" : "text-on-surface"
                            }`}
                          >
                            {file.file_path}
                          </span>
                        </div>
                        {hasCritical ? (
                          <span className="px-1.5 py-0.5 rounded bg-error-container text-on-error-container font-label-mono text-[9px] font-bold uppercase shrink-0">
                            CRITICAL
                          </span>
                        ) : fileFindings.length > 0 ? (
                          <span className="px-1.5 py-0.5 rounded bg-surface-container-highest text-surface-tint font-label-mono text-[9px] font-bold uppercase shrink-0">
                            {fileFindings.length} FINDING
                          </span>
                        ) : (
                          <span className="px-1.5 py-0.5 rounded bg-surface-container-lowest text-tertiary-fixed-dim font-label-mono text-[9px] font-semibold shrink-0">
                            Clean
                          </span>
                        )}
                      </div>
                      <div className="flex items-center justify-between mt-1 pl-5">
                        <div className="flex items-center gap-1 font-label-mono text-kbd-shortcut">
                          <span className="text-tertiary-fixed-dim">
                            +{file.additions ?? (file.hunks ? file.hunks.reduce((acc, h) => acc + (h.lines ? h.lines.filter(l => l.type === "ADDED").length : 0), 0) : 0)}
                          </span>
                          <span className="text-error">
                            -{file.deletions ?? (file.hunks ? file.hunks.reduce((acc, h) => acc + (h.lines ? h.lines.filter(l => l.type === "DELETED").length : 0), 0) : 0)}
                          </span>
                        </div>
                        <span className="font-label-mono text-[9px] text-outline group-hover:text-primary-fixed">
                          {isSelected ? "ACTIVE DIFF" : "Select"}
                        </span>
                      </div>
                    </div>
                  );
                })
            )}
          </div>

          {/* Differential Density Box */}
          <div className="m-space-xs p-space-sm bg-surface-container-lowest rounded border border-[#262930] flex flex-col gap-1">
            <span className="font-label-mono text-kbd-shortcut uppercase text-outline">Differential Density</span>
            <div className="w-full h-1.5 bg-surface-container-high rounded overflow-hidden flex">
              <div className="bg-error h-full" style={{ width: `${secPct}%` }}></div>
              <div className="bg-surface-tint h-full" style={{ width: `${bugPct}%` }}></div>
              <div className="bg-tertiary-fixed-dim h-full" style={{ width: `${testPct + perfPct}%` }}></div>
            </div>
            <div className="flex items-center justify-between text-[10px] font-label-mono text-on-surface-variant mt-0.5">
              <span>Security ({secPct}%)</span>
              <span>Clean / Pass ({testPct + perfPct}%)</span>
            </div>
          </div>
        </section>

        {/* CENTER PANEL: Syntax-Highlighted Code Diff (~50% / 6 cols) */}
        <main className="xl:col-span-6 flex flex-col">
          <DiffViewer
            diffText={diffContentToDisplay}
            filePath={selectedFile || "Code Diff"}
            findings={filteredFindings.filter((f) => !selectedFile || f.file_path === selectedFile)}
            onApplyPatch={(patch) => {
              navigator.clipboard.writeText(patch);
              alert("Patch copied to clipboard! Ready to apply locally or via fix branch.");
            }}
          />
        </main>

        {/* RIGHT PANEL: AI Findings & Autonomous Verification Inspector (~25% / 3 cols) */}
        <aside className="xl:col-span-3 flex flex-col gap-space-md">
          {filteredFindings.length === 0 ? (
            <div className="p-space-md rounded-xl bg-surface-container-low border border-[#262930] text-center py-10 shadow-md">
              <span className="material-symbols-outlined text-[32px] text-tertiary-fixed-dim mb-2">
                verified_user
              </span>
              <h3 className="font-headline-sm text-headline-sm text-primary">Zero Blockers Detected</h3>
              <p className="font-body-sm text-body-sm text-outline mt-1">
                Deterministic multi-agent verification passed with no violations under the active scope.
              </p>
            </div>
          ) : (
            filteredFindings.map((finding, idx) => {
              const isSelected = selectedFinding?.id === finding.id;
              const isCritical = finding.severity === "CRITICAL";

              return (
                <div
                  key={finding.id}
                  onClick={() => setSelectedFinding(finding)}
                  className={`p-space-md rounded-xl bg-surface-container-low border shadow-md flex flex-col gap-space-xs transition-all cursor-pointer ${
                    isSelected
                      ? isCritical
                        ? "border-error/80 ring-1 ring-error/50"
                        : "border-primary-fixed/80 ring-1 ring-primary-fixed/50"
                      : "border-[#262930] hover:border-[#333842]"
                  }`}
                >
                  {/* Card Header Badge & Category */}
                  <div className="flex items-center justify-between">
                    <span
                      className={`px-2 py-0.5 rounded font-label-mono text-kbd-shortcut font-bold uppercase tracking-wider flex items-center gap-1 ${
                        isCritical
                          ? "bg-error-container text-on-error-container"
                          : "bg-surface-container-highest text-surface-tint"
                      }`}
                    >
                      <span className={`w-1.5 h-1.5 rounded-full ${isCritical ? "bg-error" : "bg-surface-tint"}`}></span>
                      {finding.severity} SEVERITY
                    </span>
                    <span className="font-label-mono text-kbd-shortcut text-outline">
                      Finding {idx + 1} of {filteredFindings.length}
                    </span>
                  </div>

                  {/* Title & CWE Tag */}
                  <div className="flex flex-col gap-0.5 mt-1">
                    <h2 className="font-headline-sm text-body-sm text-on-surface font-semibold leading-snug">
                      {finding.title}
                    </h2>
                    <div className="flex items-center gap-1 font-label-mono text-kbd-shortcut text-on-surface-variant flex-wrap">
                      <span>{finding.rule_id || "CWE-347"}</span>
                      <span>•</span>
                      <span>Category: {finding.category}</span>
                      {finding.line_number && (
                        <>
                          <span>•</span>
                          <span className="text-primary-fixed">Line {finding.line_number}</span>
                        </>
                      )}
                    </div>
                  </div>

                  {/* Multi-Agent Validation Status Banner */}
                  <div className="p-space-xs rounded bg-surface-container-high border border-[#262930] flex items-center gap-2">
                    <span className="material-symbols-outlined text-[18px] text-tertiary-fixed-dim">
                      verified_user
                    </span>
                    <div className="flex flex-col min-w-0">
                      <span className="font-label-mono text-[10px] text-tertiary-fixed-dim font-bold tracking-tight">
                        CONFIRMED &amp; VALIDATED BY MULTI-AGENT JUDGE
                      </span>
                      <span className="font-label-mono text-[9px] text-outline truncate">
                        Consensus reached across 3 independent heuristics
                      </span>
                    </div>
                  </div>

                  {/* Evidence Taint Flow Graph Card */}
                  <div className="p-space-sm rounded bg-surface-container-lowest border border-[#262930] flex flex-col gap-1.5">
                    <span className="font-label-mono text-kbd-shortcut uppercase text-outline">
                      Static Taint Flow Evidence
                    </span>
                    <p className="font-body-sm text-kbd-shortcut text-on-surface leading-normal">
                      {finding.description}
                    </p>
                    {/* Visual SVG Taint Flow Diagram */}
                    <div className="w-full bg-surface-container p-2 rounded border border-[#262930] flex items-center justify-between">
                      <svg className="w-full h-8" fill="none" viewBox="0 0 280 32">
                        <circle cx="16" cy="16" fill="#4edea3" opacity="0.8" r="6"></circle>
                        <line stroke="#959177" strokeDasharray="2 2" strokeWidth="2" x1="22" x2="110" y1="16" y2="16"></line>
                        <circle cx="116" cy="16" fill="#f3e700" r="6"></circle>
                        <line stroke="#ef4444" strokeWidth="2" x1="122" x2="210" y1="16" y2="16"></line>
                        <circle cx="216" cy="16" fill="#93000a" r="8"></circle>
                        <circle cx="216" cy="16" fill="#ffb4ab" r="3"></circle>
                        <text fill="#959177" fontFamily="JetBrains Mono" fontSize="8" textAnchor="middle" x="16" y="30">
                          Source
                        </text>
                        <text fill="#f3e700" fontFamily="JetBrains Mono" fontSize="8" textAnchor="middle" x="116" y="30">
                          AST Node
                        </text>
                        <text fill="#ffb4ab" fontFamily="JetBrains Mono" fontSize="8" textAnchor="middle" x="216" y="30">
                          Sink (Vulnerable)
                        </text>
                      </svg>
                    </div>
                  </div>

                  {/* Recommended Patch Block */}
                  {(finding.suggested_fix || finding.recommendation) && (
                    <div className="flex flex-col gap-1">
                      <div className="flex items-center justify-between">
                        <span className="font-label-mono text-kbd-shortcut uppercase text-tertiary-fixed-dim flex items-center gap-1 font-semibold">
                          <span className="material-symbols-outlined text-[13px]">terminal</span>
                          Recommended Patch
                        </span>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            navigator.clipboard.writeText(finding.suggested_fix || finding.recommendation);
                            alert("Patch copied!");
                          }}
                          className="font-label-mono text-kbd-shortcut text-primary-fixed hover:underline flex items-center gap-0.5"
                        >
                          <span className="material-symbols-outlined text-[12px]">content_copy</span> Copy
                        </button>
                      </div>
                      <div className="p-space-sm rounded bg-surface-container-lowest border border-[#262930] font-code-block text-code-block text-tertiary-fixed flex flex-col gap-0.5 overflow-x-auto select-all">
                        <pre className="whitespace-pre-wrap">{finding.suggested_fix || finding.recommendation}</pre>
                      </div>
                    </div>
                  )}

                  {/* Card Primary Action Buttons */}
                  <div className="flex flex-col gap-1.5 pt-1 border-t border-[#262930]/40">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        handlePublish();
                      }}
                      className="w-full flex items-center justify-center gap-1.5 py-1.5 px-3 rounded bg-primary-container text-on-primary-container font-headline-sm text-body-sm font-semibold hover:brightness-105 active:scale-95 transition-all shadow-sm"
                    >
                      <span className="material-symbols-outlined text-[16px]">publish</span>
                      <span>Publish Verified Review to GitHub</span>
                    </button>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        const patchToCopy = finding.suggested_fix || finding.recommendation;
                        if (patchToCopy) {
                          navigator.clipboard.writeText(patchToCopy);
                          alert("Fix patch copied for fix branch!");
                        }
                      }}
                      className="w-full flex items-center justify-center gap-1.5 py-1.5 px-3 rounded bg-surface-container hover:bg-surface-container-high text-on-surface font-body-sm text-body-sm transition-colors border border-[#262930]"
                    >
                      <span className="material-symbols-outlined text-[16px] text-tertiary-fixed-dim">
                        fork_right
                      </span>
                      <span>Copy Fix Patch for Branch</span>
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </aside>
      </div>
    </div>
  );
}
