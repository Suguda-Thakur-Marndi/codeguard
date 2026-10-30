"use client";

import React, { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { GitHubConnectModal } from "../../components/GitHubConnectModal";
import { api } from "../../lib/api";
import { GitHubInstallation, Repository, RepositoryIndex } from "../../lib/types";

function RepositoriesContent() {
  const searchParams = useSearchParams();
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [indices, setIndices] = useState<Record<string, RepositoryIndex | null>>({});
  const [installations, setInstallations] = useState<GitHubInstallation[]>([]);
  const [loading, setLoading] = useState(true);
  const [indexingState, setIndexingState] = useState<Record<string, boolean>>({});
  const [disconnectingMap, setDisconnectingMap] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [searchFilter, setSearchFilter] = useState("");
  const [activeTab, setActiveTab] = useState<"installed" | "available" | "pending">("installed");
  const [selectedRepoIds, setSelectedRepoIds] = useState<Record<string, boolean>>({});
  const [autonomousToggles, setAutonomousToggles] = useState<Record<string, boolean>>({});

  // GitHub connection modal state
  const [isConnectModalOpen, setIsConnectModalOpen] = useState(false);
  const [modalInstallationId, setModalInstallationId] = useState<number | null>(null);

  useEffect(() => {
    loadData();

    // Check if redirected from GitHub App installation callback
    const instIdParam = searchParams.get("installation_id");
    if (instIdParam) {
      const instId = parseInt(instIdParam, 10);
      if (!isNaN(instId) && instId > 0) {
        setModalInstallationId(instId);
        setIsConnectModalOpen(true);
        setNotice("GitHub App installation detected. Select which repositories to monitor.");
      }
    }
  }, [searchParams]);

  async function loadData() {
    try {
      setLoading(true);
      setError(null);
      const [reposRes, instRes] = await Promise.all([
        api.getRepositories(1, 100).catch(() => ({ items: [], total: 0 })),
        api.getGitHubInstallations().catch(() => []),
      ]);

      const repos = reposRes.items || [];
      setRepositories(repos);
      setInstallations(instRes || []);

      // Default autonomous toggles to true for monitored repos
      const initialToggles: Record<string, boolean> = {};
      repos.forEach((r) => {
        initialToggles[r.id] = true;
      });
      setAutonomousToggles(initialToggles);

      // Fetch index status for all repositories in parallel
      const indexResults = await Promise.allSettled(
        repos.map(async (repo) => {
          try {
            const idx = await api.getRepositoryIndex(repo.id);
            return { repoId: repo.id, index: idx };
          } catch {
            return { repoId: repo.id, index: null };
          }
        })
      );

      const indexMap: Record<string, RepositoryIndex | null> = {};
      indexResults.forEach((result) => {
        if (result.status === "fulfilled" && result.value) {
          indexMap[result.value.repoId] = result.value.index;
        }
      });
      setIndices(indexMap);
    } catch (err: any) {
      setError(err.message || "Failed to load repositories");
    } finally {
      setLoading(false);
    }
  }

  async function handleTriggerIndex(repoId: string) {
    try {
      setIndexingState((prev) => ({ ...prev, [repoId]: true }));
      const newIdx = await api.triggerRepositoryIndex(repoId);
      setIndices((prev) => ({ ...prev, [repoId]: newIdx }));
      setNotice(`AST Indexing triggered successfully for repository.`);
      setTimeout(() => setNotice(null), 4000);
    } catch (err: any) {
      alert(`Indexing failed: ${err.message || "Unknown error"}`);
    } finally {
      setIndexingState((prev) => ({ ...prev, [repoId]: false }));
    }
  }

  async function handleDisconnect(repo: Repository) {
    const confirmed = window.confirm(
      `Disconnect repository '${repo.full_name}' from CodeGuard?\n\nThis will remove review history in CodeGuard while preserving your GitHub App installation on GitHub.`
    );
    if (!confirmed) return;

    try {
      setDisconnectingMap((prev) => ({ ...prev, [repo.id]: true }));
      await api.disconnectRepository(repo.id);
      setNotice(`Disconnected repository '${repo.full_name}'.`);
      await loadData();
      setTimeout(() => setNotice(null), 4000);
    } catch (err: any) {
      alert(`Failed to disconnect repository: ${err.message || "Unknown error"}`);
    } finally {
      setDisconnectingMap((prev) => ({ ...prev, [repo.id]: false }));
    }
  }

  const handleInstallApp = async () => {
    try {
      const { install_url } = await api.getGitHubInstallUrl();
      if (install_url) {
        window.location.href = install_url;
      }
    } catch (err: any) {
      alert(`Failed to retrieve GitHub install URL: ${err.message}`);
    }
  };

  const handleSelectAll = (checked: boolean) => {
    const newSelected: Record<string, boolean> = {};
    if (checked) {
      filteredRepos.forEach((r) => {
        newSelected[r.id] = true;
      });
    }
    setSelectedRepoIds(newSelected);
  };

  const handleToggleAutonomous = (repoId: string) => {
    setAutonomousToggles((prev) => ({
      ...prev,
      [repoId]: !prev[repoId],
    }));
  };

  const filteredRepos = repositories.filter((r) => {
    const matchSearch =
      r.name.toLowerCase().includes(searchFilter.toLowerCase()) ||
      r.full_name.toLowerCase().includes(searchFilter.toLowerCase());
    return matchSearch;
  });

  const allVisibleSelected =
    filteredRepos.length > 0 && filteredRepos.every((r) => selectedRepoIds[r.id]);

  return (
    <div className="flex flex-col w-full pb-space-xl">
      {notice && (
        <div className="mb-space-md p-space-sm rounded bg-surface-container-high border border-tertiary-fixed-dim/40 text-tertiary-fixed-dim font-label-mono text-body-sm flex items-center justify-between shadow-lg">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-[18px]">verified</span>
            <span>{notice}</span>
          </div>
          <button type="button" onClick={() => setNotice(null)} className="text-outline hover:text-on-surface">
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

      {/* Decorative ambient glow element behind top title */}
      <div className="relative w-full max-w-6xl mx-auto pt-space-xs">
        {/* Onboarding Header Banner */}
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-space-md pb-space-lg">
          <div className="space-y-space-xs max-w-2xl">
            <div className="flex items-center gap-space-xs">
              <span className="font-label-mono text-kbd-shortcut px-1.5 py-0.5 rounded bg-surface-container-high text-primary-fixed uppercase tracking-wider font-semibold border border-[#262930]">
                Integrations / Step 01
              </span>
              <span className="w-1 h-1 rounded-full bg-outline-variant"></span>
              <span className="font-label-mono text-kbd-shortcut text-tertiary-fixed-dim flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-tertiary-fixed-dim inline-block animate-pulse"></span>
                GitHub App Registry Ready
              </span>
            </div>
            <h1 className="font-headline-xl text-headline-xl text-primary tracking-tight">
              Connect GitHub Repositories
            </h1>
            <p className="font-body-md text-body-md text-on-surface-variant leading-relaxed">
              CodeGuard operates via an official GitHub App with fine-grained read/write permissions for autonomous
              code review, telemetry scanning, and line-level policy enforcement.
            </p>
          </div>

          {/* Quick Telemetry Stats Card */}
          <div className="flex items-center gap-space-md bg-surface-container-low px-space-md py-space-sm rounded-lg border border-[#262930] shadow-sm">
            <div className="flex flex-col">
              <span className="font-label-mono text-kbd-shortcut uppercase text-outline">Active Webhooks</span>
              <span className="font-headline-md text-headline-md text-primary tracking-tight">
                {repositories.length} / {installations.length > 0 ? installations[0].repository_count : repositories.length}
              </span>
            </div>
            <div className="w-px h-8 bg-surface-container-highest"></div>
            <div className="flex flex-col">
              <span className="font-label-mono text-kbd-shortcut uppercase text-outline">Sandbox Isolation</span>
              <span className="font-label-mono text-label-md text-tertiary-fixed-dim font-semibold flex items-center gap-1">
                <span className="material-symbols-outlined text-[14px]">verified</span>
                Strict Ephemeral
              </span>
            </div>
          </div>
        </div>

        {/* Verified GitHub App Partner Banner */}
        <div className="bg-surface-container-low rounded-xl border border-[#262930] shadow-md p-space-md mb-space-lg">
          <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-space-md pb-space-md">
            {/* Logo Handshake */}
            <div className="flex items-center gap-space-md">
              <div className="flex items-center bg-surface-container-lowest px-3 py-2 rounded-lg border border-[#262930] gap-2.5">
                {/* GitHub SVG Icon */}
                <svg aria-label="GitHub" className="w-6 h-6 text-on-surface fill-current" viewBox="0 0 24 24">
                  <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"></path>
                </svg>
                <span className="text-outline font-label-mono text-label-md">+</span>
                <div className="w-6 h-6 rounded bg-primary-container text-on-primary-container font-bold text-xs flex items-center justify-center font-mono">
                  CG
                </div>
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-headline-sm text-headline-sm text-primary">CodeGuard Bot Engine</span>
                  <span className="inline-flex items-center gap-1 font-label-mono text-kbd-shortcut px-2 py-0.5 rounded bg-tertiary-container/20 text-tertiary-fixed-dim">
                    <span className="material-symbols-outlined text-[13px]">verified_user</span>
                    Verified GitHub App Partner
                  </span>
                </div>
                <span className="font-body-sm text-body-sm text-on-surface-variant">
                  OAuth &amp; App ID: Official GitHub App · Manifest v3.2.0 · Single-Tenant Cryptographic Signatures
                </span>
              </div>
            </div>

            {/* Big High-Contrast Action */}
            <div className="flex items-center gap-2 flex-wrap">
              <button
                onClick={() => setIsConnectModalOpen(true)}
                className="inline-flex items-center justify-center gap-space-sm px-space-md py-2.5 rounded-lg bg-surface-container-high hover:bg-surface-container-highest text-on-surface border border-[#333842] transition-all font-headline-sm text-body-sm"
                type="button"
              >
                <span className="material-symbols-outlined text-[18px]">add</span>
                <span>Select Repositories</span>
              </button>
              <button
                onClick={handleInstallApp}
                className="inline-flex items-center justify-center gap-space-sm px-space-lg py-2.5 rounded-lg bg-primary-container text-on-primary-container hover:bg-primary-fixed-dim transition-all shadow-md font-headline-sm text-body-sm font-semibold"
                type="button"
              >
                <svg className="w-4 h-4 fill-current" viewBox="0 0 24 24">
                  <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"></path>
                </svg>
                <span>Install on Organization</span>
                <span className="material-symbols-outlined text-[16px]">open_in_new</span>
              </button>
            </div>
          </div>

          {/* Permission Transparency Matrix */}
          <div className="mt-space-md pt-space-md bg-surface-container rounded-lg p-space-md border border-[#262930]">
            <div className="flex items-center justify-between pb-space-sm border-b border-[#262930]/60">
              <div className="flex items-center gap-space-xs">
                <span className="material-symbols-outlined text-primary-fixed text-[18px]">security</span>
                <span className="font-headline-sm text-headline-sm text-primary">Permission Transparency Matrix</span>
                <span className="font-label-mono text-kbd-shortcut text-outline px-1.5 py-0.5 rounded bg-surface-container-highest">
                  Zero-Escalation Verified
                </span>
              </div>
              <span className="font-label-mono text-label-mono text-tertiary-fixed-dim">Least-Privilege Enforcement</span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-space-sm pt-space-sm">
              <div className="bg-surface-container-low p-space-sm rounded border border-[#262930] flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-label-mono text-label-md text-primary font-semibold">Repository Contents</span>
                    <span className="px-1.5 py-0.5 rounded bg-surface-container-highest font-label-mono text-kbd-shortcut text-on-surface">
                      READ-ONLY
                    </span>
                  </div>
                  <p className="font-body-sm text-body-sm text-on-surface-variant">
                    Used strictly to fetch changed files, AST syntax trees, and lockfiles per PR commit.
                  </p>
                </div>
                <div className="mt-2 pt-2 flex items-center gap-1 font-label-mono text-kbd-shortcut text-tertiary-fixed-dim">
                  <span className="material-symbols-outlined text-[12px]">check_circle</span>
                  Scope: contents:read
                </div>
              </div>

              <div className="bg-surface-container-low p-space-sm rounded border border-[#262930] flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-label-mono text-label-md text-primary font-semibold">Pull Requests</span>
                    <span className="px-1.5 py-0.5 rounded bg-secondary-container/40 font-label-mono text-kbd-shortcut text-secondary">
                      READ &amp; WRITE
                    </span>
                  </div>
                  <p className="font-body-sm text-body-sm text-on-surface-variant">
                    Posts inline security findings, suggests autofix patches, and updates check-run statuses.
                  </p>
                </div>
                <div className="mt-2 pt-2 flex items-center gap-1 font-label-mono text-kbd-shortcut text-secondary">
                  <span className="material-symbols-outlined text-[12px]">check_circle</span>
                  Scope: pull_requests:write
                </div>
              </div>

              <div className="bg-surface-container-low p-space-sm rounded border border-[#262930] flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-label-mono text-label-md text-primary font-semibold">Issues &amp; Metadata</span>
                    <span className="px-1.5 py-0.5 rounded bg-surface-container-highest font-label-mono text-kbd-shortcut text-on-surface">
                      READ-ONLY
                    </span>
                  </div>
                  <p className="font-body-sm text-body-sm text-on-surface-variant">
                    Resolves cross-referenced tickets, CVE tracker links, and contextual labels.
                  </p>
                </div>
                <div className="mt-2 pt-2 flex items-center gap-1 font-label-mono text-kbd-shortcut text-tertiary-fixed-dim">
                  <span className="material-symbols-outlined text-[12px]">check_circle</span>
                  Scope: issues:read
                </div>
              </div>

              <div className="bg-surface-container-lowest p-space-sm rounded border border-[#262930] flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-label-mono text-label-md text-error font-semibold">Never Requested</span>
                    <span className="px-1.5 py-0.5 rounded bg-error-container/40 font-label-mono text-kbd-shortcut text-error">
                      BLOCKED
                    </span>
                  </div>
                  <p className="font-body-sm text-body-sm text-on-surface-variant">
                    Org admin rights, secrets, production SSH keys, actions runners, or billing records.
                  </p>
                </div>
                <div className="mt-2 pt-2 flex items-center gap-1 font-label-mono text-kbd-shortcut text-error">
                  <span className="material-symbols-outlined text-[12px]">block</span>
                  Full Quarantine
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Repository Selection & Management Section */}
        <div className="bg-surface-container-low rounded-xl border border-[#262930] shadow-md p-space-md space-y-space-md">
          {/* Top Filters, State Pills & Search */}
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-space-md">
            {/* State Toggle Pills */}
            <div className="flex flex-wrap items-center gap-space-xs">
              <button
                onClick={() => setActiveTab("installed")}
                className={`px-3 py-1.5 rounded-md font-label-mono text-label-md transition-colors ${
                  activeTab === "installed"
                    ? "bg-surface-container-highest text-primary-fixed font-semibold"
                    : "bg-surface-container text-on-surface-variant hover:text-on-surface"
                }`}
                type="button"
              >
                Installed &amp; Configured{" "}
                <span className="ml-1 px-1.5 py-0.2 rounded bg-surface-container-lowest text-primary-fixed">
                  {repositories.length}
                </span>
              </button>
              <button
                onClick={() => {
                  setActiveTab("available");
                  setIsConnectModalOpen(true);
                }}
                className={`px-3 py-1.5 rounded-md font-label-mono text-label-md transition-colors ${
                  activeTab === "available"
                    ? "bg-surface-container-highest text-primary-fixed font-semibold"
                    : "bg-surface-container text-on-surface-variant hover:text-on-surface"
                }`}
                type="button"
              >
                Available to Add{" "}
                <span className="ml-1 px-1.5 py-0.2 rounded bg-surface-container-lowest text-on-surface-variant">
                  {installations.length > 0 ? installations[0].repository_count : "+"}
                </span>
              </button>
              <button
                onClick={() => setActiveTab("pending")}
                className={`px-3 py-1.5 rounded-md font-label-mono text-label-md transition-colors ${
                  activeTab === "pending"
                    ? "bg-surface-container-highest text-primary-fixed font-semibold"
                    : "bg-surface-container text-on-surface-variant hover:text-on-surface"
                }`}
                type="button"
              >
                Pending Admin Grant{" "}
                <span className="ml-1 px-1.5 py-0.2 rounded bg-surface-container-lowest text-outline">
                  0
                </span>
              </button>
            </div>

            {/* Global Bulk Action Bar */}
            <div className="flex items-center gap-space-xs">
              <button
                onClick={() => {
                  const updated = { ...autonomousToggles };
                  Object.keys(selectedRepoIds).forEach((id) => {
                    if (selectedRepoIds[id]) updated[id] = true;
                  });
                  setAutonomousToggles(updated);
                  setNotice("Autonomous review enabled for selected repositories.");
                  setTimeout(() => setNotice(null), 3000);
                }}
                className="px-space-md py-1.5 rounded font-label-mono text-label-md bg-surface-container-high text-on-surface hover:text-primary hover:bg-surface-container-highest border border-[#262930] transition-colors flex items-center gap-1.5"
                type="button"
              >
                <span className="material-symbols-outlined text-[16px] text-tertiary-fixed-dim">play_arrow</span>
                Enable Review
              </button>
              <button
                onClick={() => {
                  setNotice("Strict Zero-Day Policy applied to selected codebases.");
                  setTimeout(() => setNotice(null), 3000);
                }}
                className="px-space-md py-1.5 rounded font-label-mono text-label-md bg-surface-container-high text-on-surface hover:text-primary hover:bg-surface-container-highest border border-[#262930] transition-colors flex items-center gap-1.5"
                type="button"
              >
                <span className="material-symbols-outlined text-[16px] text-primary-fixed">shield</span>
                Apply Strict Policy
              </button>
              <button
                onClick={loadData}
                className="p-1.5 rounded bg-surface-container-high hover:bg-surface-container-highest text-on-surface-variant hover:text-on-surface border border-[#262930]"
                title="Refresh sync from GitHub"
                type="button"
              >
                <span className={`material-symbols-outlined text-[18px] ${loading ? "animate-spin" : ""}`}>sync</span>
              </button>
            </div>
          </div>

          {/* Search and Secondary Toolbar */}
          <div className="flex flex-col sm:flex-row items-center gap-space-sm bg-surface-container-lowest p-2 rounded-lg border border-[#262930]">
            <div className="relative w-full flex-1">
              <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-[18px] text-outline">
                search
              </span>
              <input
                className="w-full bg-transparent pl-10 pr-24 py-1.5 font-body-sm text-body-sm text-on-surface placeholder:text-outline outline-none"
                placeholder="Filter repositories (e.g., auth, payments, api)..."
                type="text"
                value={searchFilter}
                onChange={(e) => setSearchFilter(e.target.value)}
              />
              <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1">
                <span className="font-kbd-shortcut text-kbd-shortcut bg-surface-container-high px-1.5 py-0.5 rounded text-outline-variant">
                  ⌘F
                </span>
              </div>
            </div>
            <div className="flex items-center gap-2 w-full sm:w-auto justify-between sm:justify-end px-2">
              <label className="flex items-center gap-2 cursor-pointer select-none">
                <input
                  className="rounded bg-surface-container-highest text-primary-fixed accent-primary-fixed"
                  type="checkbox"
                  checked={allVisibleSelected}
                  onChange={(e) => handleSelectAll(e.target.checked)}
                />
                <span className="font-label-mono text-label-md text-on-surface-variant">Select All Visible</span>
              </label>
              <span className="font-label-mono text-kbd-shortcut text-outline">
                Showing {filteredRepos.length} of {repositories.length}
              </span>
            </div>
          </div>

          {/* Repositories Table */}
          <div className="overflow-x-auto">
            <table className="w-full text-left font-body-sm text-body-sm border-collapse">
              <thead>
                <tr className="bg-surface-container text-on-surface-variant font-label-mono text-kbd-shortcut uppercase tracking-wider">
                  <th className="py-2.5 px-3 rounded-l">
                    <span className="sr-only">Select</span>
                  </th>
                  <th className="py-2.5 px-3">Repository &amp; Default Branch</th>
                  <th className="py-2.5 px-3">Visibility</th>
                  <th className="py-2.5 px-3">Webhook Delivery</th>
                  <th className="py-2.5 px-3">Autonomous Review</th>
                  <th className="py-2.5 px-3">AST Intelligence</th>
                  <th className="py-2.5 px-3 text-right rounded-r">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#262930]/40" id="repoTableBody">
                {loading ? (
                  <tr>
                    <td colSpan={7} className="py-8 text-center text-outline font-label-mono">
                      Loading connected repositories...
                    </td>
                  </tr>
                ) : filteredRepos.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="py-8 text-center">
                      <div className="flex flex-col items-center gap-2">
                        <span className="material-symbols-outlined text-[32px] text-outline">source_environment</span>
                        <p className="text-on-surface font-medium">No connected repositories yet</p>
                        <p className="text-outline text-xs">
                          Install the CodeGuard GitHub App or connect an accessible repository to begin.
                        </p>
                        <button
                          type="button"
                          onClick={() => setIsConnectModalOpen(true)}
                          className="mt-2 px-3 py-1.5 rounded bg-primary-container text-on-primary-container text-xs font-semibold"
                        >
                          Connect First Repository
                        </button>
                      </div>
                    </td>
                  </tr>
                ) : (
                  filteredRepos.map((repo) => {
                    const idx = indices[repo.id];
                    const isIndexing = indexingState[repo.id];
                    const isDisconnecting = disconnectingMap[repo.id];
                    const isAutonomous = autonomousToggles[repo.id] ?? true;

                    return (
                      <tr
                        key={repo.id}
                        className="bg-surface-container-lowest/80 hover:bg-surface-container transition-colors group"
                      >
                        <td className="py-3 px-3 rounded-l">
                          <input
                            checked={!!selectedRepoIds[repo.id]}
                            onChange={(e) =>
                              setSelectedRepoIds((prev) => ({
                                ...prev,
                                [repo.id]: e.target.checked,
                              }))
                            }
                            className="rounded bg-surface-container-high text-primary-fixed accent-primary-fixed"
                            type="checkbox"
                          />
                        </td>
                        <td className="py-3 px-3">
                          <div className="flex items-center gap-2">
                            <span className="material-symbols-outlined text-[18px] text-outline">
                              {repo.is_private ? "lock" : "public"}
                            </span>
                            <div className="flex flex-col">
                              <span className="font-code-inline text-code-inline text-primary font-medium">
                                {repo.full_name}
                              </span>
                              <span className="font-label-mono text-kbd-shortcut text-outline flex items-center gap-1">
                                <span className="material-symbols-outlined text-[12px]">fork_right</span>
                                base: {repo.default_branch}{" "}
                                <span className="text-tertiary-fixed-dim">· monitored</span>
                              </span>
                            </div>
                          </div>
                        </td>
                        <td className="py-3 px-3">
                          <span className="font-label-mono text-kbd-shortcut px-2 py-0.5 rounded bg-surface-container-high text-on-surface border border-[#262930]">
                            {repo.is_private ? "PRIVATE" : "PUBLIC"}
                          </span>
                        </td>
                        <td className="py-3 px-3">
                          <div className="flex items-center gap-1.5 font-label-mono text-label-md text-tertiary-fixed-dim">
                            <span className="w-2 h-2 rounded-full bg-tertiary-fixed-dim"></span>
                            Connected (200 OK)
                          </div>
                        </td>
                        <td className="py-3 px-3">
                          <label className="relative inline-flex items-center cursor-pointer">
                            <input
                              checked={isAutonomous}
                              onChange={() => handleToggleAutonomous(repo.id)}
                              className="sr-only peer"
                              type="checkbox"
                            />
                            <div className="w-9 h-5 bg-surface-container-highest peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-surface-container-lowest after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-primary after:border-surface-container-highest after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-primary-container"></div>
                            <span
                              className={`ml-2 font-label-mono text-kbd-shortcut ${
                                isAutonomous ? "text-tertiary-fixed-dim" : "text-outline"
                              }`}
                            >
                              {isAutonomous ? "ACTIVE" : "PAUSED"}
                            </span>
                          </label>
                        </td>
                        <td className="py-3 px-3">
                          <div className="flex items-center gap-2">
                            {idx ? (
                              <span
                                className={`font-label-mono text-kbd-shortcut px-2 py-0.5 rounded ${
                                  idx.status === "READY"
                                    ? "bg-tertiary-container/20 text-tertiary-fixed-dim"
                                    : idx.status === "INDEXING"
                                    ? "bg-secondary-container/30 text-secondary"
                                    : "bg-surface-container-high text-outline"
                                }`}
                              >
                                {idx.status} ({idx.total_symbols || idx.symbol_count || 0} syms)
                              </span>
                            ) : (
                              <span className="font-label-mono text-kbd-shortcut px-2 py-0.5 rounded bg-surface-container-high text-outline">
                                NOT_INDEXED
                              </span>
                            )}
                            <button
                              type="button"
                              onClick={() => handleTriggerIndex(repo.id)}
                              disabled={isIndexing}
                              className="p-1 rounded bg-surface-container hover:bg-surface-container-high text-outline hover:text-on-surface"
                              title="Trigger AST indexing"
                            >
                              <span
                                className={`material-symbols-outlined text-[14px] ${
                                  isIndexing ? "animate-spin text-primary-fixed" : ""
                                }`}
                              >
                                refresh
                              </span>
                            </button>
                          </div>
                        </td>
                        <td className="py-3 px-3 text-right rounded-r">
                          <div className="flex items-center justify-end gap-1.5">
                            <button
                              type="button"
                              onClick={() => handleDisconnect(repo)}
                              disabled={isDisconnecting}
                              className="px-2.5 py-1 rounded bg-surface-container-high hover:bg-error-container hover:text-on-error-container font-label-mono text-kbd-shortcut text-on-surface transition-colors border border-[#262930]"
                            >
                              {isDisconnecting ? "..." : "Disconnect"}
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <GitHubConnectModal
        isOpen={isConnectModalOpen}
        onClose={() => setIsConnectModalOpen(false)}
        initialInstallationId={modalInstallationId}
        onRepositoryConnected={() => {
          setIsConnectModalOpen(false);
          loadData();
        }}
      />
    </div>
  );
}

export default function RepositoriesPage() {
  return (
    <Suspense
      fallback={
        <div className="p-8 text-center font-label-mono text-outline text-sm">
          Loading repositories workspace...
        </div>
      }
    >
      <RepositoriesContent />
    </Suspense>
  );
}
