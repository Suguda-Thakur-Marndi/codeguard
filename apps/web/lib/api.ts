import {
  HealthStatus,
  Organization,
  PaginatedResponse,
  PullRequest,
  ReadinessStatus,
  Repository,
  ReviewArtifact,
  ReviewJob,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export const authStorage = {
  getToken: (): string | null => {
    if (typeof window === "undefined") return null;
    return localStorage.getItem("codeguard_auth_token");
  },
  setToken: (token: string) => {
    if (typeof window !== "undefined") {
      localStorage.setItem("codeguard_auth_token", token);
    }
  },
  removeToken: () => {
    if (typeof window !== "undefined") {
      localStorage.removeItem("codeguard_auth_token");
    }
  },
};

export interface RequestOptions extends RequestInit {
  allowNotFound?: boolean;
}

async function request<T>(endpoint: string, options?: RequestOptions): Promise<T> {
  const url = `${API_BASE}${endpoint.startsWith("/") ? endpoint : `/${endpoint}`}`;
  const token = authStorage.getToken();
  const authHeaders: Record<string, string> = token
    ? { Authorization: `Bearer ${token}` }
    : { "X-Dev-Token": "codeguard-dev-token" };

  try {
    const res = await fetch(url, {
      ...options,
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...authHeaders,
        ...(options?.headers || {}),
      },
      cache: "no-store",
    });

    if (!res.ok) {
      if (res.status === 404 && options?.allowNotFound) {
        return null as unknown as T;
      }
      const errorData = await res.json().catch(() => ({}));
      const error = new Error(
        errorData?.error?.message || errorData?.detail || `API error (${res.status})`
      );
      (error as any).status = res.status;
      (error as any).data = errorData;
      throw error;
    }

    return res.json();
  } catch (err: any) {
    if (options?.allowNotFound) {
      return null as unknown as T;
    }
    console.error(`API request error on ${endpoint}:`, err);
    throw err;
  }
}

export const api = {
  getHealth: () => request<HealthStatus>("/health"),
  getReadiness: () => request<ReadinessStatus>("/ready"),

  getOrganizations: (page = 1, pageSize = 20) =>
    request<PaginatedResponse<Organization>>(`/organizations?page=${page}&page_size=${pageSize}`),

  getRepositories: (page = 1, pageSize = 20, organizationId?: string) => {
    const query = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    });
    if (organizationId) query.append("organization_id", organizationId);
    return request<PaginatedResponse<Repository>>(`/repositories?${query.toString()}`);
  },

  getRepository: (id: string) => request<Repository>(`/repositories/${id}`),

  getPullRequests: (page = 1, pageSize = 20, repositoryId?: string, state?: string) => {
    const query = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    });
    if (repositoryId) query.append("repository_id", repositoryId);
    if (state) query.append("state", state);
    return request<PaginatedResponse<PullRequest>>(`/pull-requests?${query.toString()}`);
  },

  getPullRequest: (id: string) => request<PullRequest>(`/pull-requests/${id}`),

  getPullRequestReviews: (prId: string, page = 1, pageSize = 20) =>
    request<PaginatedResponse<ReviewJob>>(
      `/pull-requests/${prId}/reviews?page=${page}&page_size=${pageSize}`
    ),

  getReviewJob: (jobId: string) => request<ReviewJob>(`/review-jobs/${jobId}`),

  getReviewJobArtifacts: (jobId: string) =>
    request<ReviewArtifact[]>(`/review-jobs/${jobId}/artifacts`),

  // Code Intelligence API
  getRepositoryIndex: (repoId: string) =>
    request<import("./types").RepositoryIndex | null>(`/repositories/${repoId}/index`, {
      allowNotFound: true,
    }),

  triggerRepositoryIndex: (repoId: string, commitSha?: string) =>
    request<import("./types").RepositoryIndex>(`/repositories/${repoId}/index`, {
      method: "POST",
      body: JSON.stringify({ commit_sha: commitSha }),
    }),

  getRepositorySymbols: (
    repoId: string,
    page = 1,
    pageSize = 50,
    kind?: string,
    filePath?: string
  ) => {
    const query = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    });
    if (kind) query.append("kind", kind);
    if (filePath) query.append("file_path", filePath);
    return request<PaginatedResponse<import("./types").CodeSymbol>>(
      `/repositories/${repoId}/symbols?${query.toString()}`
    );
  },

  getFileDependencies: (repoId: string, filePath: string) =>
    request<import("./types").FileDependency[]>(
      `/repositories/${repoId}/files/${encodeURIComponent(filePath)}/dependencies`
    ),

  getRepositoryContext: (
    repoId: string,
    changedFile: string,
    commitSha?: string,
    changedSymbol?: string
  ) => {
    const query = new URLSearchParams({ changed_file: changedFile });
    if (commitSha) query.append("commit_sha", commitSha);
    if (changedSymbol) query.append("changed_symbol", changedSymbol);
    return request<import("./types").RelevantContext>(
      `/repositories/${repoId}/context?${query.toString()}`
    );
  },

  getReviewJobDiff: (jobId: string) =>
    request<import("./types").DiffFile[]>(`/review-jobs/${jobId}/diff`),

  getReviewJobChunks: (jobId: string) =>
    request<import("./types").ASTChunk[]>(`/review-jobs/${jobId}/chunks`),

  getReviewJobChangedLines: (jobId: string) =>
    request<import("./types").ChangedLineIndexData>(`/review-jobs/${jobId}/changed-lines`),

  getReviewJobAgents: (jobId: string) =>
    request<import("./types").AgentRun[]>(`/review-jobs/${jobId}/agents`),

  getReviewJobFindings: (
    jobId: string,
    filters?: { severity?: string; category?: string; status?: string }
  ) => {
    const query = new URLSearchParams();
    if (filters?.severity) query.append("severity", filters.severity);
    if (filters?.category) query.append("category", filters.category);
    if (filters?.status) query.append("status_filter", filters.status);
    const qs = query.toString() ? `?${query.toString()}` : "";
    return request<import("./types").ReviewFinding[]>(`/review-jobs/${jobId}/findings${qs}`);
  },

  getReviewJobFinding: (jobId: string, findingId: string) =>
    request<import("./types").ReviewFinding>(`/review-jobs/${jobId}/findings/${findingId}`),

  getReviewJobTrace: (jobId: string) =>
    request<import("./types").AgentTrace[]>(`/review-jobs/${jobId}/trace`),

  getReviewJobUsage: (jobId: string) =>
    request<import("./types").ReviewUsage>(`/review-jobs/${jobId}/usage`),

  rerunReviewJob: (jobId: string) =>
    request<import("./types").ReviewJob>(`/review-jobs/${jobId}/rerun`, { method: "POST" }),

  // Phase 4: Adversarial Verification & Validation APIs
  getVerificationSummary: (jobId: string) =>
    request<import("./types").VerificationSummary>(`/review-jobs/${jobId}/verification`),

  getJudgeRuns: (jobId: string) =>
    request<import("./types").JudgeRun[]>(`/review-jobs/${jobId}/judge`),

  getValidationScenarios: (jobId: string) =>
    request<import("./types").ValidationScenario[]>(`/review-jobs/${jobId}/validation`),

  getFinding: (findingId: string) =>
    request<import("./types").ReviewFinding>(`/findings/${findingId}`),

  getFindingEvidence: (findingId: string) =>
    request<import("./types").FindingEvidence[]>(`/findings/${findingId}/evidence`),

  getFindingHistory: (findingId: string) =>
    request<import("./types").VerificationEvent[]>(`/findings/${findingId}/history`),

  verifyFinding: (findingId: string) =>
    request<import("./types").ReviewFinding>(`/findings/${findingId}/verify`, { method: "POST" }),

  rerunValidation: (findingId: string) =>
    request<import("./types").ReviewFinding>(`/findings/${findingId}/rerun-validation`, { method: "POST" }),

  // Phase 5: Governance, Approvals, Publishing, & Audit APIs
  getApprovals: (page = 1, pageSize = 20, organizationId?: string, repositoryId?: string, status?: string) => {
    const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (organizationId) query.append("organization_id", organizationId);
    if (repositoryId) query.append("repository_id", repositoryId);
    if (status) query.append("status", status);
    return request<import("./types").PaginatedResponse<import("./types").ApprovalRequest>>(`/approvals?${query.toString()}`);
  },

  getApproval: (approvalId: string) =>
    request<import("./types").ApprovalRequest>(`/approvals/${approvalId}`),

  approveApproval: (approvalId: string, comment?: string) =>
    request<import("./types").ApprovalRequest>(`/approvals/${approvalId}/approve`, {
      method: "POST",
      body: JSON.stringify({ comment: comment || "Approved by reviewer" }),
    }),

  rejectApproval: (approvalId: string, reason: string) =>
    request<import("./types").ApprovalRequest>(`/approvals/${approvalId}/reject`, {
      method: "POST",
      body: JSON.stringify({ reason: reason || "Rejected by reviewer" }),
    }),

  getReviewJobPublication: async (jobId: string) => {
    const res = await request<any>(`/review-jobs/${jobId}/publication`);
    return (res?.publication ?? res) as import("./types").GitHubReviewPublication;
  },

  requestJobApproval: (jobId: string, findingId?: string, action: string = "COMMENT") =>
    request<{ approval_id: string; status: string }>(`/review-jobs/${jobId}/publication/request-approval`, {
      method: "POST",
      body: JSON.stringify({ finding_id: findingId, action }),
    }),

  publishReviewJob: (jobId: string, action: string = "COMMENT") =>
    request<import("./types").GitHubReviewPublication>(`/review-jobs/${jobId}/publication/publish`, {
      method: "POST",
      body: JSON.stringify({ action }),
    }),

  getReviewJobAudit: async (jobId: string) => {
    const res = await request<any>(`/review-jobs/${jobId}/audit`);
    return (res?.items ?? res) as import("./types").ToolExecutionAudit[];
  },

  getAuditLogs: (page = 1, pageSize = 50, organizationId?: string, repositoryId?: string, toolName?: string) => {
    const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (organizationId) query.append("organization_id", organizationId);
    if (repositoryId) query.append("repository_id", repositoryId);
    if (toolName) query.append("tool_name", toolName);
    return request<import("./types").PaginatedResponse<import("./types").ToolExecutionAudit>>(`/audit?${query.toString()}`);
  },

  getOrganizationPolicies: async (orgId: string) => {
    const res = await request<any>(`/organizations/${orgId}/policies`);
    return (res?.policy ?? res) as import("./types").OrganizationReviewPolicy;
  },

  updateOrganizationPolicies: async (
    orgId: string,
    update: Partial<import("./types").OrganizationReviewPolicy>
  ) => {
    const res = await request<any>(`/organizations/${orgId}/policies`, {
      method: "PATCH",
      body: JSON.stringify(update),
    });
    return (res?.policy ?? res) as import("./types").OrganizationReviewPolicy;
  },

  getAuthMe: () =>
    request<{ authenticated: boolean; user: { id: string; login: string; email?: string; role: string; picture?: string } }>("/auth/me"),

  getGoogleLoginUrl: (returnTo = "/dashboard") => {
    const safeReturn = returnTo.startsWith("/") && !returnTo.startsWith("//") && !returnTo.includes(":") ? returnTo : "/dashboard";
    return `${API_BASE}/auth/google/login?redirect_url=${encodeURIComponent(safeReturn)}`;
  },

  logout: () => {
    authStorage.removeToken();
    return request<{ success: boolean; message: string }>("/auth/logout", { method: "POST" });
  },

  // GitHub App Connection & Repository Discovery
  getGitHubInstallUrl: () =>
    request<import("./types").GitHubInstallUrlResponse>("/github/install-url"),

  getGitHubInstallations: () =>
    request<import("./types").GitHubInstallation[]>("/github/installations"),

  verifyGitHubInstallation: (installationId: number) =>
    request<import("./types").GitHubInstallation>("/github/installations/verify", {
      method: "POST",
      body: JSON.stringify({ installation_id: installationId }),
    }),

  getGitHubInstallationRepositories: (installationId: number) =>
    request<import("./types").GitHubAccessibleRepositoriesResponse>(
      `/github/installations/${installationId}/repositories`
    ),

  connectGitHubRepository: (data: import("./types").GitHubConnectRepositoryRequest) =>
    request<Repository>("/github/repositories/connect", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  disconnectRepository: (repositoryId: string) =>
    request<import("./types").GitHubDisconnectResponse>(`/repositories/${repositoryId}`, {
      method: "DELETE",
    }),

  // Benchmark API
  getBenchmarkRuns: (page = 1, pageSize = 20) =>
    request<{
      items: import("./types").BenchmarkRunItem[];
      total: number;
      page: number;
      page_size: number;
    }>(`/benchmarks/runs?page=${page}&page_size=${pageSize}`),

  getBenchmarkRun: async (runId: string) => {
    const res = await request<any>(`/benchmarks/runs/${runId}`);
    return (res?.run ?? res) as import("./types").BenchmarkRunDetail;
  },

  compareBenchmarkRuns: (baselineRunId: string, candidateRunId: string) =>
    request<import("./types").BenchmarkComparison>(
      `/benchmarks/compare?baseline_run_id=${baselineRunId}&candidate_run_id=${candidateRunId}`
    ),
};


