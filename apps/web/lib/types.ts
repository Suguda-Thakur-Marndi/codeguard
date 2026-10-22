export interface Organization {
  id: string;
  github_installation_id: number;
  github_account_id: number;
  github_account_login: string;
  account_type: string;
  created_at: string;
  updated_at: string;
}

export interface Repository {
  id: string;
  organization_id: string;
  github_repo_id: number;
  owner: string;
  name: string;
  full_name: string;
  default_branch: string;
  is_private: boolean;
  created_at: string;
  updated_at: string;
  organization?: Organization;
}

export interface PullRequest {
  id: string;
  repository_id: string;
  github_pr_id: number;
  number: number;
  title: string;
  description: string | null;
  author_login: string;
  base_sha: string;
  head_sha: string;
  state: string;
  is_draft: boolean;
  created_at: string;
  updated_at: string;
  repository?: Repository;
  latest_review_status?: "PENDING" | "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED" | null;
}

export interface ReviewJob {
  id: string;
  pull_request_id: string;
  status: "PENDING" | "PREPARING" | "COMPREHENDING" | "ANALYZING" | "VALIDATING" | "RUNNING" | "COMPLETED" | "PARTIAL" | "FAILED" | "CANCELLED";
  trigger: string;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  total_tokens?: number;
  estimated_cost?: number;
  agents_executed?: string[];
  created_at: string;
  updated_at: string;
}

export interface ReviewArtifact {
  id: string;
  review_job_id: string;
  artifact_type: "PR_METADATA" | "DIFF" | string;
  content: string;
  metadata_json: Record<string, any>;
  created_at: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface HealthStatus {
  status: string;
  app: string;
  version: string;
}

export interface ReadinessStatus {
  status: "ready" | "degraded";
  postgres: "connected" | "disconnected";
  redis: "connected" | "disconnected";
}

// ==========================================
// Phase 2 — Code Intelligence Types
// ==========================================

export interface RepositoryIndex {
  id: string;
  repository_id: string;
  commit_sha: string;
  status: "NOT_INDEXED" | "INDEXING" | "READY" | "PARTIAL" | "FAILED";
  index_started_at: string | null;
  index_completed_at: string | null;
  files_processed: number;
  files_failed: number;
  error_count: number;
  total_symbols?: number;
  total_references?: number;
  symbol_count?: number;
}

export interface CodeSymbol {
  id: string;
  repository_id: string;
  commit_sha: string;
  file_path: string;
  name: string;
  kind: string;
  language: string;
  start_line: number;
  end_line: number;
  signature: string | null;
  return_type: string | null;
  parent_symbol: string | null;
}

export interface SymbolReference {
  id?: string;
  source_symbol: string;
  target_symbol: string;
  source_file: string;
  target_file: string | null;
  line_number: number;
  reference_type: string;
  resolved: boolean;
}

export interface FileDependency {
  id?: string;
  source_file: string;
  target_file: string;
  dependency_type: string;
  is_external: boolean;
}

export interface DiffLine {
  type: "ADDED" | "DELETED" | "CONTEXT";
  old_line: number | null;
  new_line: number | null;
  content: string;
}

export interface DiffHunk {
  old_start: number;
  old_count: number;
  new_start: number;
  new_count: number;
  lines: DiffLine[];
}

export interface DiffFile {
  file_path: string;
  old_path: string;
  new_path: string;
  change_type: string;
  hunks: DiffHunk[];
  additions?: number;
  deletions?: number;
  patch?: string;
}

export interface ASTChunk {
  id: string;
  repository_id: string;
  file_path: string;
  language: string;
  node_type: string;
  symbol_name: string;
  start_line: number;
  end_line: number;
  start_byte: number;
  end_byte: number;
  source_code: string;
  parent_symbol: string | null;
  signature: string | null;
  return_type: string | null;
  parameters: string[];
  imports: string[];
  metadata: Record<string, any>;
}

export interface ChangedLineIndexData {
  index: Record<string, { RIGHT: number[]; LEFT: number[] }>;
}

export interface RelevantContextItem {
  entity_id: string;
  entity_type: string;
  name: string;
  file_path: string;
  relevance_score: number;
  reasons: string[];
  char_count: number;
}

export interface RelevantContext {
  repository_id: string;
  commit_sha: string;
  changed_file: string;
  changed_symbol: string | null;
  changed_chunk: ASTChunk | null;
  parent_entity: string | null;
  relevant_imports: string[];
  direct_callers: string[];
  direct_dependencies: string[];
  relevant_types: string[];
  related_files: string[];
  symbol_signatures: Record<string, string>;
  ranked_items: RelevantContextItem[];
  total_characters: number;
}

// ==========================================
// Phase 3 — Agentic AI Review Engine Types
// ==========================================

export type FindingCategory =
  | "SECURITY"
  | "BUG"
  | "ERROR_HANDLING"
  | "TEST_COVERAGE"
  | "CONTRACT"
  | "PERFORMANCE"
  | "ARCHITECTURE";

export type FindingSeverity =
  | "CRITICAL"
  | "HIGH"
  | "MEDIUM"
  | "LOW"
  | "ADVISORY";

export type FindingStatus =
  | "CANDIDATE"
  | "VALID"
  | "INVALID"
  | "VALIDATED"
  | "EXECUTION_VERIFIED"
  | "REJECTED"
  | "PUBLISHABLE"
  | "PUBLISHED";

export interface EvidenceItem {
  type: "CODE" | "AST" | "CALLER" | "DEPENDENCY" | "IMPORT" | "TEST" | "DIFF" | "STATIC_ANALYSIS" | "RUNTIME" | string;
  file: string;
  line_start?: number | null;
  line_end?: number | null;
  symbol?: string | null;
  description: string;
}

export interface JudgeDecision {
  id: string;
  finding_id: string;
  judge_run_id: string;
  decision: "ACCEPT" | "REJECT" | "NEEDS_EXECUTION_VALIDATION";
  final_severity: FindingSeverity;
  final_confidence: number;
  boundary_passed: boolean;
  factuality_passed: boolean;
  actionability_passed: boolean;
  severity_passed: boolean;
  duplicate_of?: string | null;
  root_cause_id?: string | null;
  verification_summary: string;
  rejection_reason?: string | null;
  created_at: string;
}

export interface ValidationResult {
  id: string;
  scenario_id: string;
  status: "PASS" | "FAIL" | "TIMEOUT" | "ERROR" | "SKIPPED";
  exit_code?: number | null;
  stdout_summary?: string | null;
  stderr_summary?: string | null;
  duration_ms: number;
  evidence: any[];
  created_at: string;
}

export interface ValidationScenario {
  id: string;
  finding_id: string;
  scenario_type: "BEHAVIORAL" | "STRUCTURAL" | "STATIC";
  description: string;
  command: string;
  environment: Record<string, any>;
  timeout_seconds: number;
  expected_behavior: string;
  results: ValidationResult[];
  created_at: string;
}

export interface FindingEvidence {
  id: string;
  finding_id: string;
  evidence_type: string;
  file_path: string;
  line_start?: number | null;
  line_end?: number | null;
  symbol_name?: string | null;
  snippet?: string | null;
  description: string;
  source_type?: string | null;
  created_at: string;
}

export interface VerificationEvent {
  id: string;
  review_job_id: string;
  finding_id?: string | null;
  event_type: string;
  metadata_json: Record<string, any>;
  created_at: string;
}

export interface VerificationSummary {
  review_job_id: string;
  candidate_count: number;
  verified_count: number;
  rejected_count: number;
  needs_validation_count: number;
  publishable_count: number;
  judge_runs_count: number;
  total_judge_tokens: number;
  total_judge_cost: number;
  rejection_rate: number;
}

export interface JudgeRun {
  id: string;
  review_job_id: string;
  model_name: string;
  prompt_version: string;
  status: string;
  started_at: string;
  completed_at?: string | null;
  latency_ms: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  estimated_cost: number;
  decisions?: JudgeDecision[];
  created_at: string;
}

export interface ReviewFinding {
  id: string;
  review_job_id: string;
  agent_run_id?: string | null;
  file_path: string;
  line_number: number;
  side: string;
  start_line?: number | null;
  start_side?: string | null;
  category: FindingCategory;
  severity: FindingSeverity;
  original_severity?: string | null;
  final_severity?: string | null;
  title: string;
  description: string;
  impact: string;
  recommendation: string;
  confidence: number;
  specialist_confidence?: number;
  judge_confidence?: number | null;
  final_confidence?: number;
  evidence: EvidenceItem[];
  affected_symbol?: string | null;
  related_files: string[];
  related_symbols: string[];
  agent_name: string;
  source_agents?: string[];
  duplicate_of?: string | null;
  root_cause_id?: string | null;
  finding_group_id?: string | null;
  status: FindingStatus;
  validation_notes?: string | null;
  judge_decisions?: JudgeDecision[];
  validation_scenarios?: ValidationScenario[];
  grounding_evidence?: FindingEvidence[];
  rule_id?: string | null;
  suggested_fix?: string | null;
  created_at: string;
}

export interface AgentRun {
  id: string;
  review_job_id: string;
  agent_name: string;
  agent_version: string;
  model_name: string;
  prompt_version: string;
  status: "PENDING" | "RUNNING" | "COMPLETED" | "FAILED" | "SKIPPED" | "RETRYING" | string;
  started_at: string;
  completed_at?: string | null;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  estimated_cost: number;
  latency_ms: number;
  retry_count: number;
  error_message?: string | null;
  created_at: string;
}

export interface AgentTrace {
  id: string;
  review_job_id: string;
  agent_run_id?: string | null;
  node_name: string;
  agent_name: string;
  status: string;
  start_time: string;
  end_time: string;
  duration_ms: number;
  model_name?: string | null;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  retry_count: number;
  error_message?: string | null;
  created_at: string;
}

export interface AgentUsageBreakdown {
  agent_name: string;
  model_name: string;
  status: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  estimated_cost: number;
  latency_ms: number;
  retry_count: number;
}

export interface ReviewUsage {
  review_job_id: string;
  agent_runs_count: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  estimated_cost: number;
  total_latency_ms: number;
  breakdown_by_agent: AgentUsageBreakdown[];
}

// ==========================================
// Phase 5 — Governance, Approvals, & Publishing
// ==========================================

export interface ApprovalRequest {
  id: string;
  organization_id: string;
  repository_id: string;
  pull_request_id: string;
  review_job_id: string;
  finding_id: string;
  requested_action: "COMMENT" | "REQUEST_CHANGES";
  risk_level: "READ_ONLY" | "LOW_RISK" | "CONSEQUENTIAL" | "HIGH_RISK" | string;
  status: "PENDING" | "APPROVED" | "REJECTED" | "EXPIRED" | "CANCELLED";
  requested_by: string;
  approved_by: string | null;
  reason: string | null;
  created_at: string;
  expires_at: string;
  resolved_at: string | null;
  repository_name?: string;
  pull_request_number?: number;
  finding_title?: string;
  finding_severity?: string;
  head_sha?: string;
}

export interface GitHubReviewComment {
  id: string;
  publication_id: string;
  finding_id: string;
  github_comment_id: number | null;
  file_path: string;
  line_number: number;
  side: string;
  body: string;
  status: string;
  created_at: string;
}

export interface GitHubReviewPublication {
  id: string;
  review_job_id: string;
  repository_id: string;
  pull_request_id: string;
  head_sha: string;
  github_review_id: number | null;
  event: "COMMENT" | "REQUEST_CHANGES";
  status: "PENDING" | "APPROVAL_REQUIRED" | "PUBLISHING" | "PUBLISHED" | "FAILED" | "STALE";
  comment_count: number;
  published_at: string | null;
  error_message: string | null;
  created_at: string;
  comments?: GitHubReviewComment[];
}

export interface PublicationJob {
  id: string;
  publication_id: string;
  status: "PENDING" | "RUNNING" | "COMPLETED" | "FAILED" | "STALE";
  attempt: number;
  max_attempts: number;
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
  created_at: string;
}

export interface ToolExecutionAudit {
  id: string;
  principal_id: string;
  organization_id: string;
  repository_id: string | null;
  tool_name: string;
  resource_type: string;
  resource_id: string;
  risk_level: "READ_ONLY" | "LOW_RISK" | "CONSEQUENTIAL" | "HIGH_RISK" | string;
  authorization_decision: "ALLOW" | "DENY" | "REQUIRE_APPROVAL";
  approval_id: string | null;
  execution_status: string;
  started_at: string;
  completed_at: string;
  error_code: string | null;
  metadata_json: Record<string, any>;
  created_at: string;
}

export interface OrganizationReviewPolicy {
  id: string;
  organization_id: string;
  auto_publish_advisory: boolean;
  auto_publish_low: boolean;
  require_approval_for_high: boolean;
  require_approval_for_critical: boolean;
  allow_request_changes: boolean;
  allow_ai_github_comments: boolean;
  approval_expiry_minutes: number;
  created_at: string;
  updated_at: string;
}

// ==========================================
// GitHub App Connection & Repository Discovery
// ==========================================

export interface GitHubInstallUrlResponse {
  install_url: string;
  app_slug: string;
  app_id: string;
}

export interface GitHubInstallation {
  id: string;
  installation_id: number;
  account_id: number;
  account_login: string;
  account_type: string;
  repository_count: number;
  created_at: string;
}

export interface GitHubAccessibleRepository {
  github_repo_id: number;
  name: string;
  full_name: string;
  owner: string;
  default_branch: string;
  is_private: boolean;
  html_url: string;
  description: string | null;
  is_connected: boolean;
  codeguard_repo_id: string | null;
}

export interface GitHubAccessibleRepositoriesResponse {
  installation_id: number;
  account_login: string;
  total_count: number;
  repositories: GitHubAccessibleRepository[];
}

export interface GitHubConnectRepositoryRequest {
  installation_id: number;
  github_repo_id: number;
  owner: string;
  name: string;
  full_name: string;
  default_branch?: string;
  is_private?: boolean;
}

export interface GitHubDisconnectResponse {
  success: boolean;
  message: string;
  repository_id: string;
}

// ==========================================
// Benchmarks & Evaluation Types
// ==========================================

export interface BenchmarkEvaluation {
  finding_id: string;
  classification: string;
  predicted_category?: string;
  expected_category?: string;
  category_matched?: boolean;
  predicted_severity?: string;
  expected_severity?: string;
  severity_matched?: boolean;
  line_matched?: boolean;
  semantic_similarity?: number;
  reasons?: string[];
}

export interface BenchmarkScenarioResult {
  id: string;
  scenario_id: string;
  status: string;
  language: string;
  category: string;
  scenario_type: string;
  latency_ms: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost: number;
  raw_findings_count: number;
  final_findings_count: number;
  tp_count: number;
  fp_count: number;
  fn_count: number;
  error_message?: string | null;
  evaluations: BenchmarkEvaluation[];
}

export interface BenchmarkMetricsSummary {
  precision?: number;
  recall?: number;
  f1_score?: number;
  accuracy?: number;
  latency_p50_ms?: number;
  latency_p95_ms?: number;
  total_cost?: number;
  total_tokens?: number;
  total_scenarios?: number;
  passed_scenarios?: number;
  failed_scenarios?: number;
  tp_total?: number;
  fp_total?: number;
  fn_total?: number;
  [key: string]: any;
}

export interface BenchmarkRunItem {
  id: string;
  name: string;
  dataset_version: string;
  model_name: string;
  status: string;
  git_revision: string;
  scenarios_total: number;
  scenarios_passed: number;
  scenarios_failed: number;
  metrics_summary: BenchmarkMetricsSummary;
  completed_at: string | null;
  created_at: string;
}

export interface BenchmarkRunDetail extends BenchmarkRunItem {
  configuration?: Record<string, any>;
  results: BenchmarkScenarioResult[];
}

export interface BenchmarkComparison {
  baseline_run: {
    id: string;
    name: string;
    metrics: BenchmarkMetricsSummary;
  };
  candidate_run: {
    id: string;
    name: string;
    metrics: BenchmarkMetricsSummary;
  };
  delta: {
    precision_delta: number;
    recall_delta: number;
    f1_delta: number;
    latency_p50_delta_ms: number;
    total_cost_delta: number;
  };
  is_regression: boolean;
  regressions: string[];
}


