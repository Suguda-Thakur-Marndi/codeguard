---
name: codeguard-workflow-orchestrator
description: >-
  10-step multi-agent orchestration workflow combining Agency Agents, Serena,
  and Context7 for reliable, human-quality software engineering in CodeGuard.
---

# CodeGuard Workflow Orchestrator

This skill describes the master 10-step software engineering pipeline used to develop and maintain CodeGuard.

## The 10-Step Workflow

```text
Step 1: Architect Agent Analysis
   │   - Understand problem, inspect boundaries, formulate minimal plan
   ▼
Step 2: Serena Codebase Discovery
   │   - Locate symbols, trace callers, analyze dependency graph
   ▼
Step 3: Context7 Documentation Retrieval
   │   - Fetch version-specific documentation for external APIs
   ▼
Step 4: Specialized Engineering Agent Implementation
   │   - Backend / Frontend / Policy & Governance / DB / AI / DevOps agent drafts minimal change
   ▼
Step 5: Testing Agent Validation
   │   - Author unit/integration tests and run targeted test suite
   ▼
Step 6: Security Agent Review
   │   - Assess zero-trust compliance, verify boundaries, attempt bypass
   ▼
Step 7: Independent Review Agent Gate
   │   - Conduct rigorous code review; reject flawed implementations
   ▼
Step 8: Final Integration Agent Verification
   │   - Validate cross-service compatibility and eliminate duplication
   ▼
Step 9: Full Regression Test Execution
   │   - Execute full test suite and verify zero regressions
   ▼
Step 10: Final Diff Inspection
       - Final inspection and structured report generation
```

## Team Sizing & Efficiency

Do not invoke all agents for every task. Select the minimal appropriate team:

- **Simple Typo / Documentation**: Single specialized agent + Review Agent.
- **Backend Service Fix**: Architect + Serena + Backend Agent + Testing Agent + Review Agent.
- **Security / Policy Boundary Update**: Architect + Serena + Context7 + Policy/Security Agent + Testing Agent + Review Agent + Final Integration Agent.
- **Cross-Cutting Feature**: Full 10-step pipeline with all relevant specialists.
