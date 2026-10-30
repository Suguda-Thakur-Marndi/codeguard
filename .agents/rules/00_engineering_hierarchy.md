# Engineering Hierarchy Rule

## Precedence Order

In all engineering, development, refactoring, and maintenance tasks within CodeGuard, the following authority hierarchy is absolute and binding:

1. **USER REQUIREMENTS**: Direct objectives and operational constraints provided by the user.
2. **EXISTING CODEGUARD ARCHITECTURE**: The modular monorepo boundaries, LangGraph review graph, Zero-Trust PolicyEngine Sentinel, and service architecture.
3. **EXISTING BUSINESS LOGIC**: Core workflow invariants, finding severity models, and approval rules.
4. **SECURITY POLICIES**: Mandatory auth checks, tenant boundaries, SHA validation, and sandbox restrictions.
5. **TESTS & BENCHMARKS**: Authoritative evidence of system correctness and non-regression.
6. **AGENCY AGENTS**: Development assistant roles generating targeted code and proposals.
7. **SERENA & CONTEXT7**: External documentation and codebase indexing assistants.

## Invariant Enforcement

If external library documentation (Context7) or agent suggestions suggest an approach that conflicts with CodeGuard's architecture or security invariants, the **project architecture and security invariants always win**.
