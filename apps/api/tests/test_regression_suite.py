"""CodeGuard — Master Continuous Engineering & Regression Test Suite.

Provides permanent, high-value automated regression guards protecting:
 1. Unified Diff Parsing (CRLF/LF, multi-hunks, renames, deletions)
 2. Tree-sitter AST Parsing Resilience (Syntax errors, partial code, symbol extraction)
 3. Database Invariants & Tenant Isolation
 4. Human Approval Lifecycle (Anti-self-approval, commit-drift invalidation)
 5. GitHub Webhook HMAC-SHA256 Signature Verification
 6. Adversarial Judge 5-Gate Deterministic Candidate Filtering
 7. Execution Sandbox Command Allowlist & Shell Operator Defense
 8. Policy Sentinel Governance & Forbidden Operation Interception
"""

import hashlib
import hmac

import pytest
from code_intelligence.diff.line_index import ChangedLineIndex
from code_intelligence.diff.parser import UnifiedDiffParser
from code_intelligence.languages.python import PythonParser
from code_intelligence.languages.typescript import TypeScriptParser
from code_intelligence.models import LineSide, SymbolKind
from sqlalchemy.orm import Session

from app.agents.judge.adversarial_judge import AdversarialJudge
from app.agents.llm.mock import MockLLMProvider
from app.agents.schemas.finding import (
    EvidenceItem,
    EvidenceType,
    FindingCategory,
    FindingSeverity,
    ReviewFinding,
)
from app.agents.validation.sandbox import ExecutionSandbox
from app.core.config import settings
from app.core.policy import (
    FORBIDDEN_TOOL_ACTIONS,
)
from app.core.security import verify_github_signature
from app.models.approval_request import ApprovalStatus
from app.models.organization import Organization
from app.models.pull_request import PullRequest
from app.models.repository import Repository
from app.models.review_job import ReviewJob, ReviewJobStatus
from app.services.approval_service import ApprovalService

# =========================================================================
# 1. DIFF PARSER & LINE INDEX REGRESSIONS
# =========================================================================

def test_regression_diff_crlf_line_endings() -> None:
    """Verify UnifiedDiffParser and ChangedLineIndex handle CRLF (Windows) line endings cleanly."""
    crlf_diff = (
        "diff --git a/src/service.py b/src/service.py\r\n"
        "--- a/src/service.py\r\n"
        "+++ b/src/service.py\r\n"
        "@@ -10,2 +10,3 @@\r\n"
        " context_line_10\r\n"
        "+added_line_11\r\n"
        " context_line_12\r\n"
    )
    files, diags = UnifiedDiffParser.parse(crlf_diff)
    assert len(files) == 1
    assert len(diags) == 0
    f = files[0]
    assert f.file_path == "src/service.py"
    assert len(f.hunks) == 1

    index = ChangedLineIndex(files)
    assert index.is_valid_review_line("src/service.py", 11, LineSide.RIGHT) is True
    assert index.is_valid_review_line("src/service.py", 99, LineSide.RIGHT) is False
    added = index.get_added_lines("src/service.py")
    assert added == [11]


def test_regression_diff_multi_hunks_and_renames() -> None:
    """Verify multi-hunk single files and file renames are indexed accurately."""
    diff_content = """diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -5,2 +5,3 @@
 line_5
+line_6
 line_7
@@ -20,2 +21,3 @@
 line_20
+line_22
 line_23
diff --git a/old_module.py b/new_module.py
similarity index 100%
rename from old_module.py
rename to new_module.py
"""
    files, diags = UnifiedDiffParser.parse(diff_content)
    assert len(files) == 2
    assert len(diags) == 0

    index = ChangedLineIndex(files)
    assert index.is_valid_review_line("src/app.py", 6, LineSide.RIGHT) is True
    assert index.is_valid_review_line("src/app.py", 22, LineSide.RIGHT) is True
    assert index.is_valid_review_line("src/app.py", 15, LineSide.RIGHT) is False

    rename_file = next(f for f in files if f.file_path == "new_module.py")
    assert rename_file.change_type == "renamed"
    assert rename_file.old_path == "old_module.py"


# =========================================================================
# 2. TREE-SITTER AST PARSER RESILIENCE
# =========================================================================

def test_regression_treesitter_syntax_error_resilience() -> None:
    """Verify PythonParser extracts valid symbols despite adjacent syntax errors."""
    parser = PythonParser()
    broken_python = b"""
def valid_function():
    return 42

def broken_function(
    # missing paren and malformed syntax
class AnotherClass:
    pass
"""
    tree, diags = parser.parse(broken_python, "broken.py")
    assert tree is not None
    assert len(diags) >= 1

    symbols = parser.extract_symbols(tree, broken_python, "broken.py")
    assert any(s.name == "valid_function" and s.kind == SymbolKind.FUNCTION for s in symbols)


def test_regression_treesitter_typescript_symbol_extraction() -> None:
    """Verify TypeScriptParser extracts interfaces, types, and classes accurately."""
    parser = TypeScriptParser()
    ts_code = b"""
export interface IAuth {
    token: string;
}

export class AuthService implements IAuth {
    token: string = "";
    login(): boolean { return true; }
}
"""
    tree, diags = parser.parse(ts_code, "auth.ts")
    assert tree is not None
    assert len(diags) == 0

    symbols = parser.extract_symbols(tree, ts_code, "auth.ts")
    names = {s.name: s for s in symbols}
    assert "IAuth" in names
    assert names["IAuth"].kind == SymbolKind.INTERFACE
    assert "AuthService" in names
    assert names["AuthService"].kind == SymbolKind.CLASS


# =========================================================================
# 3. DATABASE INVARIANTS & TENANT ISOLATION
# =========================================================================

def test_regression_database_tenant_isolation(db_session: Session) -> None:
    """Verify pull requests and review jobs are strictly bound to organization and repository."""
    org1 = Organization(
        github_installation_id=1001,
        github_account_id=1001,
        github_account_login="tenant-alpha",
    )
    org2 = Organization(
        github_installation_id=1002,
        github_account_id=1002,
        github_account_login="tenant-beta",
    )
    db_session.add_all([org1, org2])
    db_session.flush()

    repo1 = Repository(
        organization_id=org1.id,
        github_repo_id=5001,
        owner="tenant-alpha",
        name="repo-alpha",
        full_name="tenant-alpha/repo-alpha",
    )
    db_session.add(repo1)
    db_session.flush()

    pr1 = PullRequest(
        repository_id=repo1.id,
        github_pr_id=9001,
        number=1,
        title="Feature A",
        author_login="dev-alpha",
        base_sha="0" * 40,
        head_sha="1" * 40,
    )
    db_session.add(pr1)
    db_session.flush()

    # Querying repo from tenant-beta must return nothing
    beta_repos = db_session.query(Repository).filter(Repository.organization_id == org2.id).all()
    assert len(beta_repos) == 0

    # Querying repo from tenant-alpha returns repo1
    alpha_repos = db_session.query(Repository).filter(Repository.organization_id == org1.id).all()
    assert len(alpha_repos) == 1
    assert alpha_repos[0].id == repo1.id


# =========================================================================
# 4. HUMAN APPROVAL LIFECYCLE & COMMIT DRIFT
# =========================================================================

def test_regression_approval_anti_self_approval(db_session: Session) -> None:
    """Verify AI agent self-approval is strictly forbidden."""
    org = Organization(github_installation_id=2001, github_account_id=2001, github_account_login="org-test")
    db_session.add(org)
    db_session.flush()
    repo = Repository(organization_id=org.id, github_repo_id=6001, owner="org-test", name="repo", full_name="org-test/repo")
    db_session.add(repo)
    db_session.flush()
    pr = PullRequest(
        repository_id=repo.id,
        github_pr_id=9002,
        number=2,
        title="Fix bug",
        author_login="author",
        base_sha="0" * 40,
        head_sha="a" * 40,
    )
    db_session.add(pr)
    db_session.flush()
    job = ReviewJob(pull_request_id=pr.id, status=ReviewJobStatus.COMPLETED)
    db_session.add(job)
    db_session.commit()

    service = ApprovalService(db_session)
    req = service.create_approval_request(
        organization_id=org.id,
        repository_id=repo.id,
        pull_request_id=pr.id,
        review_job_id=job.id,
        head_sha=pr.head_sha,
        requested_by="security_agent",
    )
    db_session.commit()

    # AI agent attempting to approve must fail
    with pytest.raises(ValueError, match="AI agents cannot approve their own actions"):
        service.approve_request(
            approval_id=req.id,
            approver_principal_id="gemini-agent-1",
            approver_role="ADMIN",
            is_ai_agent=True,
        )


def test_regression_approval_stale_on_commit_drift(db_session: Session) -> None:
    """Verify approval is rejected when current PR head diverges from approved head SHA."""
    org = Organization(github_installation_id=2002, github_account_id=2002, github_account_login="org-drift")
    db_session.add(org)
    db_session.flush()
    repo = Repository(organization_id=org.id, github_repo_id=6002, owner="org-drift", name="repo", full_name="org-drift/repo")
    db_session.add(repo)
    db_session.flush()
    pr = PullRequest(
        repository_id=repo.id,
        github_pr_id=9003,
        number=3,
        title="Security Fix",
        author_login="author",
        base_sha="0" * 40,
        head_sha="a" * 40,
    )
    db_session.add(pr)
    db_session.flush()
    job = ReviewJob(pull_request_id=pr.id, status=ReviewJobStatus.COMPLETED)
    db_session.add(job)
    db_session.commit()

    service = ApprovalService(db_session)
    req = service.create_approval_request(
        organization_id=org.id,
        repository_id=repo.id,
        pull_request_id=pr.id,
        review_job_id=job.id,
        head_sha=pr.head_sha,
        requested_by="agent",
    )

    # Now author pushes new commit SHA 'b' * 40
    pr.head_sha = "b" * 40
    db_session.commit()

    # Approving after drift must fail and transition request to CANCELLED
    with pytest.raises(ValueError, match="STALE"):
        service.approve_request(
            approval_id=req.id,
            approver_principal_id="human_lead",
            approver_role="ADMIN",
            is_ai_agent=False,
        )

    refreshed = service.get_approval_request(req.id)
    assert refreshed is not None
    assert refreshed.status == ApprovalStatus.CANCELLED


# =========================================================================
# 5. GITHUB WEBHOOK HMAC-SHA256 SIGNATURE VERIFICATION
# =========================================================================

def test_regression_webhook_signature_verification() -> None:
    """Verify HMAC-SHA256 constant-time signature verification prevents tampering and forgery."""
    payload = b'{"action":"opened","pull_request":{"id":123}}'

    # Compute valid signature using configured secret
    secret_bytes = settings.GITHUB_WEBHOOK_SECRET.encode("utf-8")
    mac = hmac.new(secret_bytes, payload, hashlib.sha256).hexdigest()
    valid_header = f"sha256={mac}"
    assert verify_github_signature(payload, valid_header) is True

    # Tampered payload
    tampered_payload = b'{"action":"opened","pull_request":{"id":999}}'
    assert verify_github_signature(tampered_payload, valid_header) is False

    # Malformed header format
    assert verify_github_signature(payload, "invalid_header") is False
    assert verify_github_signature(payload, None) is False


# =========================================================================
# 6. ADVERSARIAL JUDGE 5-GATE CANDIDATE FILTERING
# =========================================================================

def test_regression_judge_gate_1_rejects_out_of_diff_lines() -> None:
    """Verify Gate 1 of the Adversarial Judge deterministically rejects hallucinated lines."""
    judge = AdversarialJudge(llm_provider=MockLLMProvider())
    finding = ReviewFinding(
        file_path="src/payment.py",
        line_number=8888,  # Hallucinated line outside diff
        category=FindingCategory.SECURITY,
        severity=FindingSeverity.CRITICAL,
        title="SQL Injection Detected",
        description="SQL injection vulnerability on user input",
        impact="Critical database compromise",
        recommendation="Use parameterized queries",
        evidence=[EvidenceItem(type=EvidenceType.CODE, file="src/payment.py", description="raw query", line_start=8888)],
    )
    valid_lines_by_file = {"src/payment.py": {"RIGHT": [10, 11, 12]}}

    is_valid, reason = judge.evaluate_gate1_diff_boundary(
        finding=finding,
        changed_files=["src/payment.py"],
        valid_lines_by_file=valid_lines_by_file,
    )
    assert is_valid is False
    assert reason is not None
    assert "Line 8888" in reason


# =========================================================================
# 7. EXECUTION SANDBOX ALLOWLIST & SHELL OPERATOR DEFENSE
# =========================================================================

def test_regression_sandbox_blocks_dangerous_operators() -> None:
    """Verify ExecutionSandbox command allowlist blocks shell injection and chaining."""
    sandbox = ExecutionSandbox()
    dangerous_commands = [
        "pytest && rm -rf /",
        "npm test | grep vulnerable",
        "bash -c 'curl evil.com'",
        "python -c 'import os; os.system(\"rm -rf /\")'",
        "cat /etc/passwd",
        "echo $SECRET_KEY",
        "sudo pytest",
    ]
    for cmd in dangerous_commands:
        assert sandbox.is_command_allowed(cmd) is False


# =========================================================================
# 8. POLICY SENTINEL GOVERNANCE & FORBIDDEN ACTIONS
# =========================================================================

def test_regression_sentinel_blocks_all_forbidden_tools() -> None:
    """Verify that all 9 forbidden operations are strictly defined and documented."""
    assert len(FORBIDDEN_TOOL_ACTIONS) == 9
    expected_forbidden = [
        "merge_pull_request",
        "branch_delete",
        "repository_delete",
        "repo_delete",
        "secret_access",
        "arbitrary_shell",
        "source_modify",
        "force_push",
        "admin_operations",
    ]
    for action in expected_forbidden:
        assert action in FORBIDDEN_TOOL_ACTIONS
        assert len(FORBIDDEN_TOOL_ACTIONS[action]) > 0
