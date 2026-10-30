"use client";

import React, { useEffect, useState } from "react";
import { api } from "../lib/api";
import {
  GitHubAccessibleRepository,
  GitHubInstallation,
  Repository,
} from "../lib/types";

interface GitHubConnectModalProps {
  isOpen: boolean;
  onClose: () => void;
  onRepositoryConnected: (repo: Repository) => void;
  initialInstallationId?: number | null;
}

export const GitHubConnectModal: React.FC<GitHubConnectModalProps> = ({
  isOpen,
  onClose,
  onRepositoryConnected,
  initialInstallationId,
}) => {
  const [installations, setInstallations] = useState<GitHubInstallation[]>([]);
  const [selectedInstallationId, setSelectedInstallationId] = useState<number | null>(null);
  const [repositories, setRepositories] = useState<GitHubAccessibleRepository[]>([]);
  const [loading, setLoading] = useState(false);
  const [connectingMap, setConnectingMap] = useState<Record<number, boolean>>({});
  const [searchQuery, setSearchQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [installing, setInstalling] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    loadInstallations();
  }, [isOpen, initialInstallationId]);

  async function loadInstallations() {
    try {
      setLoading(true);
      setError(null);
      const items = await api.getGitHubInstallations().catch(() => []);
      setInstallations(items);

      const targetId =
        initialInstallationId ||
        (items.length > 0 ? items[0].installation_id : null);

      if (targetId) {
        setSelectedInstallationId(targetId);
        await loadRepositoriesForInstallation(targetId);
      }
    } catch (err: any) {
      setError(err.message || "Failed to load GitHub installations");
    } finally {
      setLoading(false);
    }
  }

  async function loadRepositoriesForInstallation(instId: number) {
    try {
      setLoading(true);
      setError(null);
      const res = await api.getGitHubInstallationRepositories(instId);
      setRepositories(res.repositories || []);
    } catch (err: any) {
      setError(err.message || "Failed to fetch repositories for installation");
      setRepositories([]);
    } finally {
      setLoading(false);
    }
  }

  const handleSelectInstallation = (instId: number) => {
    setSelectedInstallationId(instId);
    setSuccessMessage(null);
    loadRepositoriesForInstallation(instId);
  };

  const handleConnect = async (repo: GitHubAccessibleRepository) => {
    if (!selectedInstallationId) return;

    try {
      setConnectingMap((prev) => ({ ...prev, [repo.github_repo_id]: true }));
      setError(null);

      const connectedRepo = await api.connectGitHubRepository({
        installation_id: selectedInstallationId,
        github_repo_id: repo.github_repo_id,
        owner: repo.owner,
        name: repo.name,
        full_name: repo.full_name,
        default_branch: repo.default_branch,
        is_private: repo.is_private,
      });

      setRepositories((prev) =>
        prev.map((r) =>
          r.github_repo_id === repo.github_repo_id
            ? { ...r, is_connected: true, codeguard_repo_id: connectedRepo.id }
            : r
        )
      );

      setSuccessMessage(`Connected '${repo.full_name}'. CodeGuard is now actively monitoring Pull Requests.`);
      onRepositoryConnected(connectedRepo);
    } catch (err: any) {
      setError(err.message || `Failed to connect repository '${repo.full_name}'`);
    } finally {
      setConnectingMap((prev) => ({ ...prev, [repo.github_repo_id]: false }));
    }
  };

  const handleInstallNew = async () => {
    try {
      setInstalling(true);
      const { install_url } = await api.getGitHubInstallUrl();
      if (install_url) {
        window.location.href = install_url;
      }
    } catch (err: any) {
      alert(`Failed to get GitHub App install URL: ${err.message}`);
      setInstalling(false);
    }
  };

  if (!isOpen) return null;

  const filteredRepositories = repositories.filter(
    (r) =>
      r.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      r.full_name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
      <div className="w-full max-w-2xl bg-surface-container border border-[#333842] rounded-xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Modal Header */}
        <div className="p-space-md border-b border-[#262930] flex items-center justify-between bg-surface-container-low">
          <div className="flex items-center gap-space-xs">
            <span className="material-symbols-outlined text-primary-fixed text-[20px]">
              add_moderator
            </span>
            <h2 className="font-headline-sm text-headline-sm text-primary">
              Connect GitHub Repositories
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded text-outline hover:text-on-surface hover:bg-surface-container transition-colors"
          >
            <span className="material-symbols-outlined text-[20px]">close</span>
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-space-md space-y-space-md overflow-y-auto flex-1">
          {error && (
            <div className="p-3 rounded bg-error-container/20 border border-error text-error text-xs font-mono space-y-2">
              <div>{error}</div>
              {(error.includes("not installed") || error.includes("404") || error.includes("Not Found")) && (
                <div className="pt-1">
                  <button
                    type="button"
                    onClick={handleInstallNew}
                    className="inline-flex items-center gap-1.5 px-3 py-1 bg-primary text-on-primary rounded text-xs font-semibold hover:bg-primary/90 transition-colors"
                  >
                    <span className="material-symbols-outlined text-[14px]">open_in_new</span>
                    <span>Install App on GitHub</span>
                  </button>
                </div>
              )}
            </div>
          )}

          {successMessage && (
            <div className="p-3 rounded bg-surface-container-high border border-tertiary-fixed-dim/40 text-tertiary-fixed-dim text-xs font-label-mono flex items-center gap-2">
              <span className="material-symbols-outlined text-[16px]">check_circle</span>
              <span>{successMessage}</span>
            </div>
          )}

          {/* Installation Selector or New Install Action */}
          <div className="space-y-space-xs">
            <div className="flex items-center justify-between">
              <label className="font-label-mono text-kbd-shortcut uppercase text-outline">
                GitHub Organization / Account
              </label>
              <button
                type="button"
                onClick={handleInstallNew}
                disabled={installing}
                className="text-xs font-label-mono text-primary-fixed hover:underline flex items-center gap-1"
              >
                <span className="material-symbols-outlined text-[14px]">open_in_new</span>
                <span>{installing ? "Redirecting..." : "+ Install on Another Org"}</span>
              </button>
            </div>

            {installations.length === 0 && !loading ? (
              <div className="p-space-md rounded bg-surface-container-low border border-[#262930] text-center space-y-2">
                <p className="text-on-surface-variant text-sm">
                  No GitHub App installations found for your organization.
                </p>
                <button
                  type="button"
                  onClick={handleInstallNew}
                  className="px-4 py-2 rounded bg-primary-container text-on-primary-container text-xs font-semibold hover:brightness-105"
                >
                  Install Official CodeGuard GitHub App
                </button>
              </div>
            ) : (
              <div className="flex flex-wrap gap-2">
                {installations.map((inst) => (
                  <button
                    key={inst.installation_id}
                    type="button"
                    onClick={() => handleSelectInstallation(inst.installation_id)}
                    className={`px-3 py-1.5 rounded font-label-mono text-label-md transition-colors flex items-center gap-2 border ${
                      selectedInstallationId === inst.installation_id
                        ? "bg-surface-container-high text-primary-fixed border-primary-fixed/50 font-semibold"
                        : "bg-surface-container-low text-on-surface-variant border-[#262930] hover:bg-surface-container hover:text-on-surface"
                    }`}
                  >
                    <span className="material-symbols-outlined text-[16px]">domain</span>
                    <span>{inst.account_login}</span>
                    <span className="text-[10px] text-outline">({inst.repository_count} repos)</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Search Repositories Filter */}
          {selectedInstallationId && (
            <div className="space-y-2">
              <div className="relative">
                <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-[16px] text-outline">
                  search
                </span>
                <input
                  type="text"
                  placeholder="Filter accessible repositories by name..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full bg-surface-container-lowest text-on-surface placeholder:text-outline font-body-sm text-body-sm pl-9 pr-4 py-2 rounded border border-[#262930] focus:border-primary-fixed outline-none"
                />
              </div>

              {/* Repositories List */}
              <div className="border border-[#262930] rounded-lg divide-y divide-[#262930] max-h-64 overflow-y-auto">
                {loading ? (
                  <div className="p-6 text-center text-outline font-label-mono text-xs">
                    Discovering accessible repositories from GitHub API...
                  </div>
                ) : filteredRepositories.length === 0 ? (
                  <div className="p-6 text-center text-outline font-label-mono text-xs">
                    {searchQuery ? "No matching repositories found." : "No repositories accessible."}
                  </div>
                ) : (
                  filteredRepositories.map((repo) => (
                    <div
                      key={repo.github_repo_id}
                      className="p-3 bg-surface-container-lowest/80 flex items-center justify-between hover:bg-surface-container-low transition-colors"
                    >
                      <div className="flex flex-col min-w-0 pr-2">
                        <div className="flex items-center gap-2">
                          <span className="font-code-inline text-code-inline text-primary font-medium truncate">
                            {repo.full_name}
                          </span>
                          {repo.is_private && (
                            <span className="px-1.5 py-0.2 rounded font-label-mono text-[9px] bg-surface-container-high text-outline">
                              PRIVATE
                            </span>
                          )}
                        </div>
                        <span className="font-label-mono text-kbd-shortcut text-outline">
                          default branch: {repo.default_branch}
                        </span>
                      </div>

                      <div>
                        {repo.is_connected ? (
                          <span className="inline-flex items-center gap-1 font-label-mono text-kbd-shortcut text-tertiary-fixed-dim px-2 py-1 rounded bg-tertiary-container/20">
                            <span className="w-1.5 h-1.5 rounded-full bg-tertiary-fixed-dim"></span>
                            Connected
                          </span>
                        ) : (
                          <button
                            type="button"
                            onClick={() => handleConnect(repo)}
                            disabled={connectingMap[repo.github_repo_id]}
                            className="px-3 py-1 rounded bg-primary-container text-on-primary-container hover:brightness-105 active:scale-95 transition-all font-label-mono text-kbd-shortcut font-semibold shadow-sm"
                          >
                            {connectingMap[repo.github_repo_id] ? "Connecting..." : "Connect"}
                          </button>
                        )}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="p-space-md border-t border-[#262930] flex items-center justify-between bg-surface-container-low">
          <span className="font-label-mono text-kbd-shortcut text-outline">
            Fine-grained Least Privilege: contents:read, pull_requests:write
          </span>
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 rounded bg-surface-container-high hover:bg-surface-container text-on-surface font-label-mono text-label-md border border-[#262930]"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
