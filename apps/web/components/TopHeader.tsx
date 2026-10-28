"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { api, authStorage } from "../lib/api";

interface TopHeaderProps {
  onToggleMobileSidebar: () => void;
}

// Map of route segments to human-readable labels
const ROUTE_LABELS: Record<string, string> = {
  dashboard: "Overview",
  repositories: "Repositories",
  "pull-requests": "Pull Requests",
  reviews: "Reviews",
  findings: "Findings",
  "diff-review": "Code Diff",
  policies: "Policies",
  approvals: "Approvals",
  audit: "Audit Logs",
  benchmarks: "Benchmarks",
  debug: "Debug",
  github: "GitHub",
};

export const TopHeader: React.FC<TopHeaderProps> = ({ onToggleMobileSidebar }) => {
  const pathname = usePathname();
  const [currentUser, setCurrentUser] = useState<{
    id: string;
    login: string;
    email?: string;
    role: string;
    picture?: string;
  } | null>(null);
  const [activePrsCount, setActivePrsCount] = useState<number>(0);
  const [criticalCount, setCriticalCount] = useState<number>(0);
  const [userDropdownOpen, setUserDropdownOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  useEffect(() => {
    // Consume token from OAuth callback URL
    if (typeof window !== "undefined") {
      const urlParams = new URLSearchParams(window.location.search);
      const token = urlParams.get("token");
      if (token) {
        authStorage.setToken(token);
        window.history.replaceState({}, document.title, window.location.pathname);
      }
    }

    api
      .getAuthMe()
      .then((res) => {
        if (res.authenticated && res.user) setCurrentUser(res.user);
      })
      .catch(() => setCurrentUser(null));

    Promise.allSettled([
      api.getPullRequests(1, 20),
      api.getApprovals(1, 10, undefined, undefined, "PENDING"),
    ]).then(([prsRes, appsRes]) => {
      if (prsRes.status === "fulfilled" && prsRes.value) {
        setActivePrsCount(prsRes.value.total || prsRes.value.items?.length || 0);
      }
      if (appsRes.status === "fulfilled" && appsRes.value) {
        setCriticalCount((appsRes.value as any).total || 0);
      }
    });
  }, []);

  const handleLogout = async () => {
    try {
      await api.logout();
    } catch {
      authStorage.removeToken();
    }
    setCurrentUser(null);
    window.location.href = "/login";
  };

  // Build breadcrumbs from URL path
  const breadcrumbs = (() => {
    const parts = pathname.split("/").filter(Boolean);
    if (parts.length === 0 || parts[0] === "dashboard") {
      return [{ label: "Overview", href: "/dashboard" }];
    }
    return parts.map((part, i) => ({
      label: ROUTE_LABELS[part] ?? (part.charAt(0).toUpperCase() + part.slice(1).replace(/-/g, " ")),
      href: "/" + parts.slice(0, i + 1).join("/"),
    }));
  })();

  return (
    <header
      className="fixed top-0 left-0 md:left-60 right-0 h-13 bg-surface-container-lowest/90 backdrop-blur-md z-40 flex items-center justify-between px-4 sm:px-5 border-b border-[#262930]"
      style={{ height: "52px" }}
    >
      {/* ── Left: hamburger + breadcrumbs + search ── */}
      <div className="flex items-center gap-3 min-w-0">
        {/* Mobile hamburger */}
        <button
          type="button"
          onClick={onToggleMobileSidebar}
          className="md:hidden p-1.5 rounded hover:bg-surface-container text-on-surface-variant hover:text-on-surface"
          aria-label="Toggle navigation menu"
        >
          <span className="material-symbols-outlined text-[20px]">menu</span>
        </button>

        {/* Breadcrumbs */}
        <nav
          aria-label="Breadcrumb"
          className="hidden sm:flex items-center gap-1.5 font-label-mono text-[12px] text-on-surface-variant"
        >
          <Link
            href="/dashboard"
            className="text-outline hover:text-on-surface transition-colors"
            aria-label="Home"
          >
            <span className="material-symbols-outlined text-[14px]">home</span>
          </Link>
          {breadcrumbs.map((crumb, i) => (
            <React.Fragment key={crumb.href + i}>
              <span className="text-outline" aria-hidden>/</span>
              <Link
                href={crumb.href}
                className={
                  i === breadcrumbs.length - 1
                    ? "text-on-surface font-semibold"
                    : "text-on-surface-variant hover:text-on-surface transition-colors"
                }
                aria-current={i === breadcrumbs.length - 1 ? "page" : undefined}
              >
                {crumb.label}
              </Link>
            </React.Fragment>
          ))}
        </nav>

        {/* Global search */}
        <div className="relative hidden lg:flex items-center ml-1">
          <span className="material-symbols-outlined absolute left-2.5 text-[14px] text-outline pointer-events-none">
            search
          </span>
          <input
            id="global-search"
            type="text"
            className="bg-surface-container text-on-surface placeholder:text-outline font-body-sm text-[13px] pl-8 pr-12 py-1 rounded-md w-52 focus:w-72 transition-all outline-none border border-[#262930] focus:border-primary-fixed"
            placeholder="Search PRs, findings, repos…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            aria-label="Global search"
          />
          <span className="absolute right-2 font-label-mono text-[9px] bg-surface-container-high px-1.5 py-0.5 rounded text-outline">
            ⌘K
          </span>
        </div>
      </div>

      {/* ── Right: telemetry pills + user ─────────── */}
      <div className="flex items-center gap-2">
        {/* Live telemetry pills (desktop only) */}
        <div className="hidden xl:flex items-center gap-1.5">
          <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md bg-surface-container font-label-mono text-[11px] text-on-surface border border-[#262930]">
            <span className="w-1.5 h-1.5 rounded-full bg-[#60a5fa]" />
            {activePrsCount} PRs Active
          </span>
          {criticalCount > 0 ? (
            <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md bg-[rgba(248,113,113,0.10)] font-label-mono text-[11px] text-[#f87171] border border-[#f87171]/20">
              <span className="w-1.5 h-1.5 rounded-full bg-[#f87171]" />
              {criticalCount} Pending Approval
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md bg-surface-container font-label-mono text-[11px] text-[#4ade80] border border-[#262930]">
              <span className="w-1.5 h-1.5 rounded-full bg-[#4ade80]" />
              All Clear
            </span>
          )}
        </div>

        {/* User profile */}
        <div className="relative">
          {currentUser ? (
            <>
              <button
                type="button"
                id="user-menu-button"
                onClick={() => setUserDropdownOpen(!userDropdownOpen)}
                aria-expanded={userDropdownOpen}
                aria-haspopup="menu"
                aria-controls="user-dropdown"
                className="flex items-center gap-2 pl-1 pr-2.5 py-1 rounded-md bg-surface-container hover:bg-surface-container-high transition-colors border border-[#262930]"
              >
                {currentUser.picture ? (
                  <img
                    alt={currentUser.login}
                    className="w-6 h-6 rounded-full object-cover"
                    src={currentUser.picture}
                  />
                ) : (
                  <div className="w-6 h-6 rounded-full bg-primary-container text-on-primary-container font-label-mono font-bold text-[10px] flex items-center justify-center">
                    {currentUser.login?.charAt(0).toUpperCase() ?? "U"}
                  </div>
                )}
                <span className="font-label-mono text-[12px] text-on-surface font-semibold truncate max-w-[100px]">
                  {currentUser.login || currentUser.email}
                </span>
                <span className="material-symbols-outlined text-[14px] text-outline">
                  expand_more
                </span>
              </button>

              {userDropdownOpen && (
                <div
                  id="user-dropdown"
                  role="menu"
                  aria-labelledby="user-menu-button"
                  className="absolute right-0 top-full mt-1.5 w-48 bg-surface-container-high border border-[#262930] rounded-lg shadow-2xl py-1 z-50"
                >
                  <div className="px-3 py-2 border-b border-[#262930]">
                    <p className="text-[12px] font-semibold text-on-surface">{currentUser.login}</p>
                    <p className="text-[10px] font-label-mono text-outline truncate">{currentUser.email}</p>
                    <span className="mt-1 inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-label-mono uppercase tracking-wide bg-primary-container text-on-primary-container">
                      {currentUser.role}
                    </span>
                  </div>
                  <Link
                    href="/policies"
                    role="menuitem"
                    className="flex items-center gap-2 px-3 py-1.5 text-[12px] text-on-surface-variant hover:text-on-surface hover:bg-surface-container transition-colors"
                    onClick={() => setUserDropdownOpen(false)}
                  >
                    <span className="material-symbols-outlined text-[14px]">security</span>
                    Security Policies
                  </Link>
                  <Link
                    href="/audit"
                    role="menuitem"
                    className="flex items-center gap-2 px-3 py-1.5 text-[12px] text-on-surface-variant hover:text-on-surface hover:bg-surface-container transition-colors"
                    onClick={() => setUserDropdownOpen(false)}
                  >
                    <span className="material-symbols-outlined text-[14px]">history</span>
                    Audit Trail
                  </Link>
                  <button
                    type="button"
                    role="menuitem"
                    onClick={handleLogout}
                    className="w-full flex items-center gap-2 px-3 py-1.5 text-[12px] text-[#f87171] hover:bg-[rgba(248,113,113,0.06)] transition-colors border-t border-[#262930] mt-1"
                  >
                    <span className="material-symbols-outlined text-[14px]">logout</span>
                    Sign Out
                  </button>
                </div>
              )}
            </>
          ) : (
            <a
              href={`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1"}/auth/google/login`}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md font-label-mono text-[12px] bg-surface-container text-on-surface hover:bg-surface-container-high border border-[#262930] transition-colors"
            >
              <span className="material-symbols-outlined text-[15px]">login</span>
              Sign in
            </a>
          )}
        </div>
      </div>
    </header>
  );
};
