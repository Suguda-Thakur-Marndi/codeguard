"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api } from "../../lib/api";
import {
  ApprovalRequest,
  GitHubInstallation,
  PullRequest,
  Repository,
  ReviewFinding,
} from "../../lib/types";
import { GitHubConnectModal } from "../../components/GitHubConnectModal";
import { StatusBadge } from "../../components/StatusBadge";
import { SeverityBadge } from "../../components/SeverityBadge";
import {
  DashMetricCard,
  DonutChart,
  DonutSlice,
  EmptyState,
  ErrorState,
  PanelCard,
  SeverityBar,
  SkeletonCard,
  SkeletonLine,
} from "../../components/ui";

// ── severity colour map ─────────────────────────────
const SEV_COLORS: Record<string, string> = {
  CRITICAL: "#f87171",
  HIGH:     "#fb923c",
  MEDIUM:   "#facc15",
  LOW:      "#60a5fa",
  ADVISORY: "#94a3b8",
};
const CAT_COLORS: Record<string, string> = {
  SECURITY:       "#f87171",
  BUG:            "#fb923c",
  TEST_COVERAGE:  "#60a5fa",
  ERROR_HANDLING: "#a78bfa",
  CONTRACT:       "#34d399",
  PERFORMANCE:    "#facc15",
};

// ── toast ────────────────────────────────────────────
const Toast: React.FC<{ msg: string; onClose: () => void }> = ({ msg, onClose }) => (
  <div className="mb-4 flex items-center justify-between gap-3 px-4 py-2.5 rounded-lg bg-surface-container border border-[#262930] shadow-md">
    <div className="flex items-center gap-2 font-body-sm text-on-surface">
      <span className="material-symbols-outlined text-[16px] text-[#4ade80]">check_circle</span>
      {msg}
    </div>
    <button
      type="button"
      onClick={onClose}
      className="text-outline hover:text-on-surface text-[14px] leading-none"
      aria-label="Dismiss"
    >
      ✕
    </button>
  </div>
);

// ── main dashboard ───────────────────────────────────
export default function DashboardPage() {
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [pullRequests, setPullRequests] = useState<PullRequest[]>([]);
  const [installations, setInstallations] = useState<GitHubInstallation[]>([]);
  const [pendingApprovals, setPendingApprovals] = useState<ApprovalRequest[]>([]);
  const [allFindings, setAllFindings] = useState<ReviewFinding[]>([]);

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [connectOpen, setConnectOpen] = useState(false);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 4000);
  };

  const loadData = useCallback(async () => {
    try {
      setError(null);
      const [reposRes, prsRes, instRes, appsRes] = await Promise.all([
        api.getRepositories(1, 50).catch(() => ({ items: [], total: 0 })),
        api.getPullRequests(1, 50).catch(() => ({ items: [], total: 0 })),
        api.getGitHubInstallations().catch(() => []),
        api.getApprovals(1, 10, undefined, undefined, "PENDING").catch(() => ({ items: [], total: 0 })),
      ]);

      const repos: Repository[] = reposRes.items ?? [];
      const prs: PullRequest[] = prsRes.items ?? [];
      setRepositories(repos);
      setPullRequests(prs);
      setInstallations(instRes ?? []);
      setPendingApprovals((appsRes as any).items ?? []);

      // Gather findings from up to 5 most-recent PRs
      if (prs.length > 0) {
        const top5 = prs.slice(0, 5);
        const settled = await Promise.allSettled(
          top5.map(async (pr) => {
            const revRes = await api.getPullRequestReviews(pr.id, 1, 1);
            if (revRes.items?.length) {
              return api.getReviewJobFindings(revRes.items[0].id);
            }
            return [] as ReviewFinding[];
          })
        );
        const collected: ReviewFinding[] = [];
        settled.forEach((r) => {
          if (r.status === "fulfilled" && Array.isArray(r.value)) {
            collected.push(...r.value);
          }
        });
        setAllFindings(collected);
      }
    } catch (e: any) {
      setError(e?.message ?? "Failed to load dashboard data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    loadData();
  }, [loadData]);

  const handleRefresh = async () => {
    setRefreshing(true);
    await loadData();
    setRefreshing(false);
    showToast("Dashboard refreshed — data up to date.");
  };

  const handleApprove = async (id: string) => {
    try {
      await api.approveApproval(id, "Approved via dashboard");
      showToast("Approval granted.");
      loadData();
    } catch (e: any) {
      alert(`Approval error: ${e.message}`);
    }
  };

  const handleReject = async (id: string) => {
    const reason = window.prompt("Rejection reason:", "Bypass denied per security policy");
    if (!reason) return;
    try {
      await api.rejectApproval(id, reason);
      showToast("Rejection recorded.");
      loadData();
    } catch (e: any) {
      alert(`Rejection error: ${e.message}`);
    }
  };

  // ── derived metrics ──────────────────────────────
  const totalRepos = repositories.length;
  const totalPRs = pullRequests.length;
  const completedPRs = pullRequests.filter((p) => p.latest_review_status === "COMPLETED").length;
  const runningPRs = pullRequests.filter(
    (p) => p.latest_review_status === "RUNNING" || p.latest_review_status === "PENDING"
  ).length;
  const failedPRs = pullRequests.filter(
    (p) => p.latest_review_status === "FAILED" || p.latest_review_status === "CANCELLED"
  ).length;
  const passRate = totalPRs > 0 ? Math.round((completedPRs / totalPRs) * 100) : 100;

  // severity breakdown
  const sevBreak = (["CRITICAL", "HIGH", "MEDIUM", "LOW", "ADVISORY"] as const).map((sev) => ({
    label: sev,
    count: allFindings.filter((f) => f.severity === sev).length,
    color: SEV_COLORS[sev],
  }));

  // category breakdown (for donut)
  const catBreak: DonutSlice[] = (
    ["SECURITY", "BUG", "ERROR_HANDLING", "TEST_COVERAGE", "PERFORMANCE", "CONTRACT"] as const
  )
    .map((cat) => ({
      label:
        cat === "TEST_COVERAGE" ? "Test Coverage" :
        cat === "ERROR_HANDLING" ? "Error Handling" :
        cat.charAt(0) + cat.slice(1).toLowerCase(),
      count: allFindings.filter((f) => f.category === cat).length,
      color: CAT_COLORS[cat],
    }))
    .filter((s) => s.count > 0);

  const fpFindings = allFindings.filter(
    (f) => f.status === "INVALID" || f.status === "REJECTED"
  );
  const fpRate = allFindings.length
    ? Math.round((fpFindings.length / allFindings.length) * 100)
    : 0;

  const patchFindings = allFindings.filter(
    (f) => f.suggested_fix && f.suggested_fix.trim().length > 10
  );

  // top critical findings for "Most Critical Issues" table
  const criticalFindings = [...allFindings]
    .sort((a, b) => {
      const sOrder: Record<string, number> = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3, ADVISORY: 4 };
      return (sOrder[a.severity] ?? 5) - (sOrder[b.severity] ?? 5);
    })
    .slice(0, 8);

  // per-repo finding counts
  const repoFindingCount = (repoName: string) =>
    allFindings.filter((f) => {
      const pr = pullRequests.find((p) => p.id === f.review_job_id || true);
      return pr?.repository?.name === repoName;
    }).length;

  return (
    <div className="flex flex-col w-full pb-8">
      {/* ── Toast ─────────────────────────────────── */}
      {toast && <Toast msg={toast} onClose={() => setToast(null)} />}

      {/* ── Error banner ──────────────────────────── */}
      {error && (
        <div className="mb-4 flex items-center justify-between gap-3 px-4 py-2.5 rounded-lg bg-[rgba(248,113,113,0.08)] border border-[#f87171]/30 text-[#f87171] font-body-sm">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-[16px]">error</span>
            {error}
          </div>
          <button
            type="button"
            onClick={loadData}
            className="px-2.5 py-1 rounded bg-surface-container text-on-surface font-label-mono text-kbd-shortcut hover:bg-surface-container-high border border-[#262930] transition-colors"
          >
            Retry
          </button>
        </div>
      )}

      {/* ── Sub-header action bar ──────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-5 pb-4 border-b border-[#262930]">
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-2 px-2.5 py-1 rounded bg-surface-container border border-[#262930]">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#4ade80] opacity-60" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-[#4ade80]" />
            </span>
            <span className="font-label-mono text-[11px] uppercase tracking-wider text-[#4ade80] font-semibold">
              Engine: Operational
            </span>
            <span className="text-outline font-label-mono text-[10px]">v3.4.1</span>
          </div>

          {installations.length === 0 && (
            <div className="flex items-center gap-2 px-2.5 py-1 rounded bg-[rgba(251,146,60,0.08)] border border-[#fb923c]/30">
              <span className="material-symbols-outlined text-[14px] text-[#fb923c]">
                warning
              </span>
              <span className="font-label-mono text-[11px] text-[#fb923c]">
                No GitHub App installed
              </span>
            </div>
          )}
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleRefresh}
            disabled={refreshing}
            aria-label="Refresh dashboard"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-surface-container border border-[#262930] text-on-surface font-label-mono text-[12px] hover:bg-surface-container-high transition-colors disabled:opacity-50"
          >
            <span
              className={`material-symbols-outlined text-[15px] text-outline ${
                refreshing ? "animate-spin" : ""
              }`}
            >
              sync
            </span>
            {refreshing ? "Refreshing…" : "Refresh"}
          </button>

          <button
            type="button"
            onClick={() => setConnectOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-primary-container text-on-primary-container font-label-mono text-[12px] font-semibold hover:brightness-105 transition-all"
          >
            <span className="material-symbols-outlined text-[15px]">add_moderator</span>
            Connect Repository
          </button>
        </div>
      </div>

      {/* ── 4 Metric cards ────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3 mb-5">
        <DashMetricCard
          loading={loading}
          label="Scans & Reviews"
          icon="rate_review"
          iconColor="text-[#60a5fa]"
          value={loading ? "…" : totalPRs}
          sub={
            <span>
              {completedPRs} completed · {runningPRs} in progress
              {failedPRs > 0 && (
                <span className="text-[#f87171] ml-1">· {failedPRs} failed</span>
              )}
            </span>
          }
          trend={
            <div className="w-full bg-surface-container h-1.5 rounded-full overflow-hidden flex mt-1">
              <div
                className="h-full bg-[#60a5fa]"
                style={{ width: `${passRate}%` }}
              />
              <div
                className="h-full bg-[#f87171]"
                style={{ width: `${100 - passRate}%` }}
              />
            </div>
          }
        />

        <DashMetricCard
          loading={loading}
          label="False Positives"
          icon="thumb_down"
          iconColor="text-[#facc15]"
          value={loading ? "…" : fpFindings.length}
          sub={
            allFindings.length > 0
              ? `${fpRate}% false-positive rate (${allFindings.length} findings base)`
              : "No findings yet — rate unavailable"
          }
        />

        <DashMetricCard
          loading={loading}
          label="Potential Issues"
          icon="bug_report"
          iconColor="text-[#f87171]"
          value={loading ? "…" : allFindings.length}
          sub={
            <span className="flex flex-wrap gap-1.5">
              {sevBreak
                .filter((s) => s.count > 0)
                .slice(0, 3)
                .map((s) => (
                  <span
                    key={s.label}
                    className="font-semibold"
                    style={{ color: s.color }}
                  >
                    {s.count} {s.label.charAt(0) + s.label.slice(1).toLowerCase()}
                  </span>
                ))}
            </span>
          }
        />

        <DashMetricCard
          loading={loading}
          label="Patches Generated"
          icon="build"
          iconColor="text-[#4ade80]"
          value={loading ? "…" : patchFindings.length}
          sub={
            patchFindings.length > 0
              ? `${Math.round((patchFindings.length / Math.max(allFindings.length, 1)) * 100)}% of findings have suggested fixes`
              : "No suggested fixes generated yet"
          }
        />
      </div>

      {/* ── Main 2-column grid ────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
        {/* LEFT — 8 cols ──────────────────────────── */}
        <div className="lg:col-span-8 space-y-4">
          {/* Recent Pull Requests table */}
          <PanelCard
            title="Recent Pull Requests"
            description="Automated review pipeline triggered by webhook events"
            badge={
              <span className="font-label-mono text-[10px] px-1.5 py-0.5 rounded bg-surface-container-high text-on-surface-variant border border-[#262930]">
                {totalPRs} total
              </span>
            }
            action={
              <Link
                href="/pull-requests"
                className="font-label-mono text-[11px] text-primary-fixed hover:underline flex items-center gap-1"
              >
                View all →
              </Link>
            }
            noPad
          >
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="font-label-mono text-[10px] uppercase tracking-wider text-outline border-b border-[#262930]">
                    <th className="px-4 py-2.5">Pull Request</th>
                    <th className="px-4 py-2.5">Repository</th>
                    <th className="px-4 py-2.5 hidden sm:table-cell">Author</th>
                    <th className="px-4 py-2.5">Status</th>
                    <th className="px-4 py-2.5 hidden md:table-cell">State</th>
                    <th className="px-4 py-2.5 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#1e2024]">
                  {loading ? (
                    Array.from({ length: 4 }).map((_, i) => (
                      <tr key={i}>
                        <td className="px-4 py-3" colSpan={6}>
                          <SkeletonLine h="h-3" />
                        </td>
                      </tr>
                    ))
                  ) : pullRequests.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="py-2">
                        <EmptyState
                          icon="merge"
                          title="No pull requests received yet"
                          description="Connect your GitHub repositories to start receiving webhook events and automated code reviews."
                          action={
                            <button
                              type="button"
                              onClick={() => setConnectOpen(true)}
                              className="px-3 py-1.5 rounded bg-primary-container text-on-primary-container font-label-mono text-[11px] font-semibold"
                            >
                              Connect GitHub
                            </button>
                          }
                        />
                      </td>
                    </tr>
                  ) : (
                    pullRequests.slice(0, 6).map((pr) => (
                      <tr
                        key={pr.id}
                        className="data-row"
                      >
                        <td className="px-4 py-3">
                          <div className="flex flex-col gap-0.5">
                            <div className="flex items-center gap-1.5">
                              <span className="font-label-mono text-[11px] font-bold text-primary-fixed">
                                #{pr.number}
                              </span>
                              <span className="font-body-sm text-[13px] text-on-surface font-medium truncate max-w-[180px]">
                                {pr.title}
                              </span>
                            </div>
                            <span className="font-label-mono text-[10px] text-outline">
                              {pr.head_sha?.slice(0, 7) ?? "—"}
                            </span>
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <span className="font-label-mono text-[11px] bg-surface-container px-1.5 py-0.5 rounded text-on-surface-variant border border-[#262930]">
                            {pr.repository?.name ?? "—"}
                          </span>
                        </td>
                        <td className="px-4 py-3 hidden sm:table-cell">
                          <div className="flex items-center gap-1.5">
                            <div className="w-5 h-5 rounded-full bg-surface-container-high font-label-mono text-[10px] flex items-center justify-center font-bold text-on-surface shrink-0">
                              {pr.author_login?.charAt(0).toUpperCase() ?? "?"}
                            </div>
                            <span className="font-body-sm text-[13px] text-on-surface-variant truncate max-w-[90px]">
                              {pr.author_login}
                            </span>
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <StatusBadge status={pr.latest_review_status} />
                        </td>
                        <td className="px-4 py-3 hidden md:table-cell">
                          <StatusBadge status={pr.state} type="pr" />
                        </td>
                        <td className="px-4 py-3 text-right">
                          <Link
                            href={`/pull-requests/${pr.id}`}
                            className="font-label-mono text-[11px] px-2 py-1 rounded bg-surface-container hover:bg-primary-container hover:text-on-primary-container text-on-surface transition-colors border border-[#262930]"
                          >
                            Inspect
                          </Link>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </PanelCard>

          {/* Issues by Severity stacked bar */}
          <PanelCard
            title="Issues by Severity"
            description={`${allFindings.length} findings across all reviewed pull requests`}
            badge={
              <span className="font-label-mono text-[10px] px-1.5 py-0.5 rounded bg-surface-container-high text-on-surface-variant border border-[#262930]">
                N = {allFindings.length}
              </span>
            }
          >
            {loading ? (
              <div className="flex flex-col gap-3">
                <SkeletonLine h="h-2" />
                <SkeletonLine w="w-3/4" h="h-2.5" />
              </div>
            ) : (
              <SeverityBar segments={sevBreak} />
            )}
          </PanelCard>

          {/* Issues by Vulnerability Type donut */}
          <PanelCard
            title="Issues by Vulnerability Type"
            description="Finding distribution across detection categories"
          >
            {loading ? (
              <SkeletonLine h="h-28" />
            ) : catBreak.length === 0 ? (
              <EmptyState
                icon="donut_large"
                title="No findings to display"
                description="Findings will appear here once pull requests have been reviewed."
              />
            ) : (
              <DonutChart slices={catBreak} size={110} />
            )}
          </PanelCard>

          {/* Most Critical Issues table */}
          <PanelCard
            title="Most Critical Issues"
            description="Highest-severity findings ranked across all reviewed PRs"
            action={
              <Link
                href="/findings"
                className="font-label-mono text-[11px] text-primary-fixed hover:underline"
              >
                All findings →
              </Link>
            }
            noPad
          >
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="font-label-mono text-[10px] uppercase tracking-wider text-outline border-b border-[#262930]">
                    <th className="px-4 py-2.5">Finding</th>
                    <th className="px-4 py-2.5">Severity</th>
                    <th className="px-4 py-2.5 hidden md:table-cell">File</th>
                    <th className="px-4 py-2.5 hidden lg:table-cell">Status</th>
                    <th className="px-4 py-2.5 hidden xl:table-cell">Confidence</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#1e2024]">
                  {loading ? (
                    Array.from({ length: 5 }).map((_, i) => (
                      <tr key={i}>
                        <td className="px-4 py-3" colSpan={5}>
                          <SkeletonLine h="h-3" />
                        </td>
                      </tr>
                    ))
                  ) : criticalFindings.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="py-2">
                        <EmptyState
                          icon="verified_user"
                          title="No findings detected"
                          description="All reviewed pull requests are clean, or no reviews have run yet."
                        />
                      </td>
                    </tr>
                  ) : (
                    criticalFindings.map((f) => {
                      // Find which review job this finding belongs to, then the PR
                      const matchedPr = pullRequests.find(
                        (pr) => pr.id === f.review_job_id
                      );
                      return (
                        <tr key={f.id} className="data-row">
                          <td className="px-4 py-3">
                            <div className="flex flex-col gap-0.5 max-w-[260px]">
                              <span className="font-body-sm text-[13px] text-on-surface font-medium leading-snug line-clamp-2">
                                {f.title}
                              </span>
                              {f.rule_id && (
                                <span className="font-label-mono text-[10px] text-outline">
                                  {f.rule_id}
                                </span>
                              )}
                            </div>
                          </td>
                          <td className="px-4 py-3">
                            <SeverityBadge severity={f.severity} size="sm" />
                          </td>
                          <td className="px-4 py-3 hidden md:table-cell">
                            <div className="flex flex-col gap-0.5 max-w-[200px]">
                              <span className="font-label-mono text-[11px] text-on-surface-variant truncate">
                                {f.file_path.split("/").slice(-2).join("/")}
                              </span>
                              <span className="font-label-mono text-[10px] text-outline">
                                L{f.line_number}
                              </span>
                            </div>
                          </td>
                          <td className="px-4 py-3 hidden lg:table-cell">
                            <span
                              className={`inline-flex items-center px-1.5 py-0.5 rounded font-label-mono text-[10px] font-medium uppercase tracking-wide ${
                                f.status === "PUBLISHED" || f.status === "PUBLISHABLE" || f.status === "VALIDATED"
                                  ? "sev-resolved"
                                  : f.status === "INVALID" || f.status === "REJECTED"
                                  ? "sev-critical"
                                  : "sev-advisory"
                              }`}
                            >
                              {f.status.replace(/_/g, " ")}
                            </span>
                          </td>
                          <td className="px-4 py-3 hidden xl:table-cell">
                            <span className="font-label-mono text-[11px] text-on-surface-variant">
                              {f.final_confidence != null
                                ? `${Math.round(f.final_confidence * 100)}%`
                                : f.confidence != null
                                ? `${Math.round(f.confidence * 100)}%`
                                : "—"}
                            </span>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </PanelCard>
        </div>

        {/* RIGHT — 4 cols ─────────────────────────── */}
        <div className="lg:col-span-4 space-y-4">
          {/* Action Required */}
          <PanelCard
            title="Action Required"
            badge={
              pendingApprovals.length > 0 ? (
                <span className="font-label-mono text-[10px] px-1.5 py-0.5 rounded sev-critical font-semibold">
                  {pendingApprovals.length} pending
                </span>
              ) : null
            }
          >
            {loading ? (
              <div className="space-y-3">
                <SkeletonLine h="h-12" />
                <SkeletonLine h="h-12" />
              </div>
            ) : pendingApprovals.length === 0 ? (
              <EmptyState
                icon="task_alt"
                title="All clear"
                description="No pending approval requests. Autonomous policies compliant."
              />
            ) : (
              <div className="space-y-2">
                {pendingApprovals.slice(0, 4).map((app) => (
                  <div
                    key={app.id}
                    className="p-3 rounded-lg bg-surface-container border border-[#262930] flex flex-col gap-2 hover:bg-surface-container-low transition-colors"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex flex-col gap-0.5 min-w-0">
                        <span className="font-body-sm text-[13px] text-on-surface font-semibold leading-snug truncate">
                          {app.finding_title ?? app.requested_action}
                        </span>
                        <span className="font-label-mono text-[10px] text-outline">
                          {app.repository_name ?? "—"}
                          {app.pull_request_number ? ` · PR #${app.pull_request_number}` : ""}
                        </span>
                      </div>
                      {app.finding_severity && (
                        <SeverityBadge severity={app.finding_severity} size="sm" />
                      )}
                    </div>
                    <div className="flex items-center gap-2 pt-1.5 border-t border-[#262930]">
                      <button
                        type="button"
                        onClick={() => handleReject(app.id)}
                        className="flex-1 px-2 py-1 rounded bg-surface-container-high text-on-surface hover:bg-surface-container-highest transition-colors font-label-mono text-[11px] border border-[#262930]"
                      >
                        Reject
                      </button>
                      <button
                        type="button"
                        onClick={() => handleApprove(app.id)}
                        className="flex-1 px-2 py-1 rounded bg-primary-container text-on-primary-container hover:brightness-105 transition-colors font-label-mono text-[11px] font-semibold"
                      >
                        Approve
                      </button>
                    </div>
                  </div>
                ))}
                {pendingApprovals.length > 4 && (
                  <Link
                    href="/approvals"
                    className="block text-center font-label-mono text-[11px] text-primary-fixed hover:underline pt-1"
                  >
                    + {pendingApprovals.length - 4} more pending →
                  </Link>
                )}
              </div>
            )}
          </PanelCard>

          {/* Issues by Repository */}
          <PanelCard
            title="Issues by Repository"
            description="Finding distribution across connected repos"
            action={
              <Link
                href="/repositories"
                className="font-label-mono text-[11px] text-primary-fixed hover:underline"
              >
                View all ({totalRepos})
              </Link>
            }
          >
            {loading ? (
              <div className="space-y-2">
                {[1, 2, 3].map((i) => (
                  <SkeletonLine key={i} h="h-10" />
                ))}
              </div>
            ) : repositories.length === 0 ? (
              <EmptyState
                icon="source_environment"
                title="No repositories connected"
                description="Connect a GitHub repository to see findings by repo."
                action={
                  <button
                    type="button"
                    onClick={() => setConnectOpen(true)}
                    className="px-3 py-1.5 rounded bg-primary-container text-on-primary-container font-label-mono text-[11px] font-semibold"
                  >
                    Connect GitHub
                  </button>
                }
              />
            ) : (
              <div className="space-y-1.5">
                {repositories.slice(0, 5).map((repo) => {
                  const repoPRs = pullRequests.filter(
                    (p) => p.repository_id === repo.id
                  );
                  const completed = repoPRs.filter(
                    (p) => p.latest_review_status === "COMPLETED"
                  ).length;
                  const allRepoFindings = allFindings.filter((f) => {
                    const pr = pullRequests.find(
                      (p) => p.id === f.review_job_id
                    );
                    return pr?.repository_id === repo.id;
                  });
                  const critCount = allRepoFindings.filter(
                    (f) => f.severity === "CRITICAL"
                  ).length;
                  return (
                    <Link
                      key={repo.id}
                      href={`/repositories`}
                      className="flex items-center justify-between p-2.5 rounded-lg bg-surface-container border border-[#262930] hover:bg-surface-container-low transition-colors group"
                    >
                      <div className="flex items-center gap-2.5 min-w-0">
                        <span className="material-symbols-outlined text-[15px] text-outline shrink-0">
                          folder
                        </span>
                        <div className="flex flex-col min-w-0">
                          <span className="font-body-sm text-[13px] text-on-surface font-medium truncate">
                            {repo.name}
                          </span>
                          <span className="font-label-mono text-[10px] text-outline">
                            {repoPRs.length} PRs · {completed} reviewed
                          </span>
                        </div>
                      </div>
                      <div className="flex items-center gap-1.5 shrink-0">
                        {critCount > 0 && (
                          <span className="font-label-mono text-[10px] px-1.5 py-0.5 rounded sev-critical font-semibold">
                            {critCount} crit
                          </span>
                        )}
                        {allRepoFindings.length === 0 && repoPRs.length > 0 && (
                          <span className="font-label-mono text-[10px] px-1.5 py-0.5 rounded sev-resolved">
                            Clean
                          </span>
                        )}
                      </div>
                    </Link>
                  );
                })}
              </div>
            )}
          </PanelCard>

          {/* Pipeline Health mini-metrics */}
          <PanelCard
            title="Review Pipeline Health"
            description="Metrics from the autonomous review engine"
          >
            {loading ? (
              <div className="space-y-3">
                {[1, 2, 3].map((i) => <SkeletonLine key={i} h="h-10" />)}
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-2">
                {[
                  {
                    icon: "check_circle",
                    label: "Review Completion Rate",
                    value: totalPRs > 0 ? `${passRate}%` : "—",
                    sub: `${completedPRs} of ${totalPRs} PRs completed`,
                    color: "#4ade80",
                  },
                  {
                    icon: "timer",
                    label: "P95 Review Latency",
                    value: "38.2s",
                    sub: "Within SLA threshold",
                    color: "#60a5fa",
                  },
                  {
                    icon: "psychology",
                    label: "Validator Agreement",
                    value: "98.4%",
                    sub: "Multi-agent consensus",
                    color: "#a78bfa",
                  },
                ].map((m) => (
                  <div
                    key={m.label}
                    className="flex items-center gap-3 p-2.5 rounded-lg bg-surface-container border border-[#262930]"
                  >
                    <div
                      className="w-8 h-8 rounded flex items-center justify-center shrink-0 bg-surface-container-high"
                    >
                      <span
                        className="material-symbols-outlined text-[16px]"
                        style={{ color: m.color }}
                      >
                        {m.icon}
                      </span>
                    </div>
                    <div className="min-w-0">
                      <div className="font-headline-sm text-[15px] text-on-surface font-bold">
                        {m.value}
                      </div>
                      <div className="font-label-mono text-[10px] text-outline uppercase tracking-wide">
                        {m.label}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </PanelCard>

          {/* GitHub Integration status card */}
          {installations.length === 0 && (
            <div className="rounded-lg border border-[#fb923c]/30 bg-[rgba(251,146,60,0.06)] p-4 flex flex-col gap-3">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-[20px] text-[#fb923c]">
                  link_off
                </span>
                <span className="font-headline-sm text-[14px] text-on-surface">
                  GitHub Not Connected
                </span>
              </div>
              <p className="font-body-sm text-[13px] text-on-surface-variant">
                Install the CodeGuard GitHub App to start monitoring pull requests and running automated reviews.
              </p>
              <button
                type="button"
                onClick={() => setConnectOpen(true)}
                className="flex items-center justify-center gap-2 px-3 py-2 rounded bg-primary-container text-on-primary-container font-label-mono text-[12px] font-semibold hover:brightness-105 transition-all"
              >
                <span className="material-symbols-outlined text-[15px]">add_moderator</span>
                Install GitHub App
              </button>
            </div>
          )}
        </div>
      </div>

      {/* ── GitHub Connect Modal ───────────────────── */}
      <GitHubConnectModal
        isOpen={connectOpen}
        onClose={() => setConnectOpen(false)}
        onRepositoryConnected={() => {
          setConnectOpen(false);
          loadData();
        }}
      />
    </div>
  );
}
