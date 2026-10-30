"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { api } from "../lib/api";
import { Repository } from "../lib/types";

interface SidebarProps {
  isOpen?: boolean;
  onClose?: () => void;
}

// Nav group definition
interface NavItem {
  href: string;
  label: string;
  icon: string;
  badge?: string;
  badgeVariant?: "default" | "danger";
  activeMatch: (p: string) => boolean;
}

interface NavGroup {
  label: string;
  items: NavItem[];
}

export const Sidebar: React.FC<SidebarProps> = ({ isOpen, onClose }) => {
  const pathname = usePathname();
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [selectedRepo, setSelectedRepo] = useState<Repository | null>(null);
  const [prCount, setPrCount] = useState<number>(0);
  const [pendingApprovalCount, setPendingApprovalCount] = useState<number>(0);
  const [githubConnected, setGithubConnected] = useState<boolean>(false);
  const [engineStatus, setEngineStatus] = useState<string>("Online");
  const [repoDropdownOpen, setRepoDropdownOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    Promise.allSettled([
      api.getRepositories(1, 20),
      api.getPullRequests(1, 1),
      api.getApprovals(1, 1, undefined, undefined, "PENDING"),
      api.getGitHubInstallations(),
      api.getReadiness(),
    ]).then(([reposRes, prsRes, appsRes, instRes, readyRes]) => {
      if (reposRes.status === "fulfilled" && reposRes.value?.items) {
        setRepositories(reposRes.value.items);
        if (reposRes.value.items.length > 0) setSelectedRepo(reposRes.value.items[0]);
      }
      if (prsRes.status === "fulfilled" && prsRes.value) {
        setPrCount(prsRes.value.total || prsRes.value.items?.length || 0);
      }
      if (appsRes.status === "fulfilled" && appsRes.value) {
        setPendingApprovalCount((appsRes.value as any).total || (appsRes.value as any).items?.length || 0);
      }
      if (instRes.status === "fulfilled" && Array.isArray(instRes.value)) {
        setGithubConnected(instRes.value.length > 0);
      }
      if (readyRes.status === "fulfilled" && readyRes.value) {
        setEngineStatus(readyRes.value.status === "ready" ? "Operational" : "Degraded");
      }
    });
  }, []);

  const navGroups: NavGroup[] = [
    {
      label: "Analytics",
      items: [
        {
          href: "/dashboard",
          label: "Overview",
          icon: "grid_view",
          activeMatch: (p) => p === "/" || p === "/dashboard",
        },
        {
          href: "/repositories",
          label: "Repositories",
          icon: "source_environment",
          badge: repositories.length > 0 ? String(repositories.length) : undefined,
          activeMatch: (p) => p.startsWith("/repositories"),
        },
        {
          href: "/pull-requests",
          label: "Pull Requests",
          icon: "merge",
          badge: prCount > 0 ? String(prCount) : undefined,
          activeMatch: (p) => p.startsWith("/pull-requests"),
        },
        {
          href: "/reviews",
          label: "Reviews",
          icon: "rate_review",
          activeMatch: (p) => p.startsWith("/reviews"),
        },
        {
          href: "/findings",
          label: "Findings",
          icon: "bug_report",
          activeMatch: (p) => p.startsWith("/findings"),
        },
        {
          href: "/diff-review",
          label: "Code Diff",
          icon: "difference",
          activeMatch: (p) => p.startsWith("/diff-review"),
        },
      ],
    },
    {
      label: "Governance",
      items: [
        {
          href: "/policies",
          label: "Policies",
          icon: "verified_user",
          activeMatch: (p) => p.startsWith("/policies"),
        },
        {
          href: "/approvals",
          label: "Approvals",
          icon: "assignment_turned_in",
          badge: pendingApprovalCount > 0 ? String(pendingApprovalCount) : undefined,
          badgeVariant: "danger",
          activeMatch: (p) => p.startsWith("/approvals"),
        },
        {
          href: "/audit",
          label: "Audit Logs",
          icon: "history_edu",
          activeMatch: (p) => p.startsWith("/audit"),
        },
        {
          href: "/benchmarks",
          label: "Benchmarks",
          icon: "speed",
          activeMatch: (p) => p.startsWith("/benchmarks"),
        },
      ],
    },
  ];

  const isActive = (item: NavItem) => item.activeMatch(pathname);

  return (
    <>
      {/* Mobile backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/60 z-40 md:hidden backdrop-blur-sm"
          onClick={onClose}
          aria-hidden
        />
      )}

      <aside
        className={`fixed left-0 top-0 h-screen bg-surface-container-lowest z-50 flex flex-col border-r border-[#262930] select-none transition-all duration-200 ease-in-out ${
          isOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"
        } ${collapsed ? "w-14" : "w-60"}`}
        aria-label="Primary navigation"
      >
        {/* ── Logo + collapse toggle ─────────────── */}
        <div className="h-13 flex items-center justify-between px-3 py-2 border-b border-[#262930] bg-surface-container-low">
          {!collapsed && (
            <Link
              href="/dashboard"
              className="flex items-center gap-2.5 min-w-0"
              onClick={onClose}
            >
              <div className="w-7 h-7 rounded-md bg-primary-container text-on-primary-container flex items-center justify-center font-label-mono font-bold text-[11px] tracking-tight shrink-0">
                CG
              </div>
              <div className="flex flex-col min-w-0">
                <span className="font-headline-sm text-[13px] text-on-surface font-semibold truncate leading-tight">
                  CodeGuard
                </span>
                <span className="font-label-mono text-[9px] uppercase tracking-widest text-outline">
                  Autonomous Core
                </span>
              </div>
            </Link>
          )}
          {collapsed && (
            <Link
              href="/dashboard"
              className="w-7 h-7 rounded-md bg-primary-container text-on-primary-container flex items-center justify-center font-label-mono font-bold text-[11px] mx-auto"
              onClick={onClose}
              aria-label="CodeGuard home"
            >
              CG
            </Link>
          )}
          {!collapsed && (
            <button
              type="button"
              onClick={() => setCollapsed(true)}
              className="text-outline hover:text-on-surface transition-colors p-1 rounded hover:bg-surface-container-high"
              aria-label="Collapse sidebar"
            >
              <span className="material-symbols-outlined text-[16px]">chevron_left</span>
            </button>
          )}
        </div>

        {/* Expand button when collapsed */}
        {collapsed && (
          <button
            type="button"
            onClick={() => setCollapsed(false)}
            className="w-full py-2 flex items-center justify-center text-outline hover:text-on-surface hover:bg-surface-container transition-colors border-b border-[#262930]"
            aria-label="Expand sidebar"
          >
            <span className="material-symbols-outlined text-[16px]">chevron_right</span>
          </button>
        )}

        {/* ── Repository switcher (hidden when collapsed) ─── */}
        {!collapsed && (
          <div className="p-2 border-b border-[#262930] relative">
            <button
              type="button"
              className="w-full flex items-center justify-between px-2.5 py-1.5 rounded-md bg-surface-container hover:bg-surface-container-high transition-colors border border-[#262930] text-left"
              onClick={() => setRepoDropdownOpen(!repoDropdownOpen)}
              aria-expanded={repoDropdownOpen}
              aria-haspopup="listbox"
            >
              <div className="flex items-center gap-2 min-w-0">
                <span className="material-symbols-outlined text-[14px] text-outline shrink-0">
                  folder_open
                </span>
                <div className="flex flex-col min-w-0">
                  <span className="font-label-mono text-[11px] text-on-surface truncate">
                    {selectedRepo ? selectedRepo.full_name : "All Repositories"}
                  </span>
                  <span className="font-label-mono text-[9px] text-outline">
                    {selectedRepo
                      ? `${selectedRepo.default_branch} · monitored`
                      : "Multi-repo view"}
                  </span>
                </div>
              </div>
              <span className="material-symbols-outlined text-[14px] text-outline shrink-0">
                unfold_more
              </span>
            </button>

            {repoDropdownOpen && (
              <div
                role="listbox"
                className="absolute top-full left-2 right-2 mt-0.5 bg-surface-container-high border border-[#262930] rounded-md shadow-xl z-50 max-h-48 overflow-y-auto py-1"
              >
                <div
                  role="option"
                  aria-selected={selectedRepo === null}
                  tabIndex={0}
                  className="px-3 py-1.5 font-label-mono text-[11px] text-on-surface hover:bg-surface-container cursor-pointer"
                  onClick={() => {
                    setSelectedRepo(null);
                    setRepoDropdownOpen(false);
                  }}
                >
                  All Repositories
                </div>
                {repositories.map((repo) => (
                  <div
                    key={repo.id}
                    role="option"
                    aria-selected={selectedRepo?.id === repo.id}
                    tabIndex={0}
                    className="px-3 py-1.5 font-label-mono text-[11px] text-on-surface hover:bg-surface-container cursor-pointer truncate"
                    onClick={() => {
                      setSelectedRepo(repo);
                      setRepoDropdownOpen(false);
                    }}
                  >
                    {repo.full_name}
                  </div>
                ))}
                <Link
                  href="/repositories"
                  className="block px-3 py-1.5 mt-0.5 border-t border-[#262930] text-[10px] font-label-mono text-primary-fixed hover:underline"
                  onClick={() => setRepoDropdownOpen(false)}
                >
                  + Add / Connect Repo
                </Link>
              </div>
            )}
          </div>
        )}

        {/* ── Navigation groups ─────────────────── */}
        <nav className="flex-1 overflow-y-auto py-2 space-y-4" aria-label="Sidebar navigation">
          {navGroups.map((group) => (
            <div key={group.label}>
              {!collapsed && (
                <div className="px-3 pb-1">
                  <span className="font-label-mono text-[9px] uppercase tracking-widest text-outline">
                    {group.label}
                  </span>
                </div>
              )}
              <div className="px-1.5 space-y-0.5">
                {group.items.map((item) => {
                  const active = isActive(item);
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      onClick={onClose}
                      title={collapsed ? item.label : undefined}
                      aria-current={active ? "page" : undefined}
                      className={`flex items-center gap-2.5 rounded-md transition-colors ${
                        collapsed ? "justify-center px-2 py-2" : "px-2.5 py-1.5"
                      } ${
                        active
                          ? "bg-surface-container-high text-on-surface font-semibold"
                          : "text-on-surface-variant hover:bg-surface-container hover:text-on-surface"
                      }`}
                    >
                      <span
                        className={`material-symbols-outlined text-[17px] shrink-0 ${
                          active ? "text-primary-fixed" : ""
                        }`}
                      >
                        {item.icon}
                      </span>
                      {!collapsed && (
                        <>
                          <span className="font-body-sm text-[13px] truncate">{item.label}</span>
                          {item.badge && (
                            <span
                              className={`ml-auto font-label-mono text-[10px] px-1.5 py-0.5 rounded shrink-0 ${
                                item.badgeVariant === "danger"
                                  ? "bg-[rgba(248,113,113,0.15)] text-[#f87171]"
                                  : "bg-surface-container-high text-on-surface-variant"
                              }`}
                            >
                              {item.badge}
                            </span>
                          )}
                        </>
                      )}
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>

        {/* ── Bottom status footer ──────────────── */}
        {!collapsed && (
          <div className="p-2 border-t border-[#262930] space-y-1.5">
            {/* Integration status */}
            <div className="flex items-center justify-between px-2.5 py-1.5 rounded-md bg-surface-container border border-[#262930]">
              <div className="flex items-center gap-2">
                <span
                  className={`w-1.5 h-1.5 rounded-full ${
                    githubConnected ? "bg-[#4ade80]" : "bg-[#fb923c]"
                  }`}
                />
                <span className="font-label-mono text-[10px] text-on-surface-variant">
                  {githubConnected ? "GitHub Connected" : "GitHub Not Connected"}
                </span>
              </div>
            </div>

            {/* Engine status */}
            <div className="flex items-center justify-between px-2.5 py-1.5 rounded-md bg-surface-container border border-[#262930]">
              <span className="font-label-mono text-[10px] text-on-surface-variant">
                Engine: {engineStatus}
              </span>
              <span className="font-label-mono text-[9px] text-outline">v3.4</span>
            </div>

            {/* Debug link */}
            <Link
              href="/debug"
              className="flex items-center justify-between px-2.5 py-1 rounded-md text-on-surface-variant hover:text-on-surface hover:bg-surface-container font-label-mono text-[10px] transition-colors"
            >
              <span className="flex items-center gap-1.5">
                <span className="material-symbols-outlined text-[13px]">terminal</span>
                System Debug
              </span>
              <span className="bg-surface-container-high px-1 py-0.5 rounded text-[9px] text-outline font-bold">
                F1
              </span>
            </Link>
          </div>
        )}

        {/* Collapsed footer — just status dots */}
        {collapsed && (
          <div className="p-2 border-t border-[#262930] flex flex-col items-center gap-2">
            <span
              title={githubConnected ? "GitHub Connected" : "GitHub Not Connected"}
              className={`w-2 h-2 rounded-full ${
                githubConnected ? "bg-[#4ade80]" : "bg-[#fb923c]"
              }`}
            />
            <Link
              href="/debug"
              title="System Debug"
              className="text-outline hover:text-on-surface transition-colors"
            >
              <span className="material-symbols-outlined text-[15px]">terminal</span>
            </Link>
          </div>
        )}
      </aside>
    </>
  );
};
