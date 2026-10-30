# CodeGuard — API Contracts & Compatibility Policy

## 1. API Architecture & Versioning Strategy

CodeGuard exposes RESTful endpoints under the `/api/v1` namespace. The API is designed for consumption by the Next.js frontend (`apps/web`), CI/CD webhook integrations, and developer tooling.

### 1.1 Invariants & Versioning Rules
- **Additive Evolution**: All changes to `/api/v1` endpoints must be strictly backward compatible. New response fields are optional; existing response field names and types must never be changed.
- **No Silent Semantics Alteration**: Never change status codes, query parameter semantics, or error formats without formal deprecation.
- **Deprecation Lifecycle**: Deprecated fields or endpoints must be retained for at least two minor release cycles and marked with the HTTP `Sunset` header.
- **Single Master Version**: Do not introduce `/api/v2` unless an incompatible change to core domain authentication or serialization cannot be accommodated via additive schema evolution.

---

## 2. API Contract Inventory (`/api/v1`)

| Endpoint Path | HTTP Method | Request Schema | Response Schema | Auth Required | Minimum Role |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `/health` | `GET` | None | `HealthResponse` | No (Public) | None |
| `/ready` | `GET` | None | `ReadinessResponse` | No (Public) | None |
| `/live` | `GET` | None | `HealthResponse` | No (Public) | None |
| `/metrics` | `GET` | None | Prometheus text | No (Internal) | None |
| `/webhooks/github` | `POST` | GitHub Webhook JSON | `{"status": "accepted"}` | HMAC SHA-256 | GitHub Signer |
| `/organizations` | `GET`, `POST` | `OrganizationCreate` | `OrganizationResponse` | Yes (Bearer) | `ADMIN` (create) |
| `/repositories` | `GET`, `POST` | `RepositoryCreate` | `RepositoryResponse` | Yes (Bearer) | `MEMBER` |
| `/pull-requests` | `GET`, `POST` | `PullRequestCreate` | `PullRequestResponse` | Yes (Bearer) | `MEMBER` |
| `/pull-requests/{id}` | `GET` | None | `PullRequestDetail` | Yes (Bearer) | `MEMBER` |
| `/review-jobs` | `GET`, `POST` | `ReviewJobCreate` | `ReviewJobResponse` | Yes (Bearer) | `MEMBER` |
| `/review-jobs/{id}` | `GET` | None | `ReviewJobDetail` | Yes (Bearer) | `MEMBER` |
| `/findings` | `GET` | Query filters | `List[FindingResponse]` | Yes (Bearer) | `MEMBER` |
| `/approvals` | `GET`, `POST` | `ApprovalCreate` | `ApprovalResponse` | Yes (Bearer) | `REVIEWER` |
| `/approvals/{id}/sign` | `POST` | `ApprovalSignRequest` | `ApprovalDetail` | Yes (Bearer) | `REVIEWER` / `ADMIN` |
| `/publications` | `GET`, `POST` | `PublicationCreate` | `PublicationResponse` | Yes (Bearer) | `REVIEWER` / `ADMIN` |
| `/audit/logs` | `GET` | Query filters | `List[AuditLogResponse]`| Yes (Bearer) | `ADMIN` / `SECURITY` |
| `/policies` | `GET`, `POST` | `PolicyCreate` | `PolicyResponse` | Yes (Bearer) | `ADMIN` |
| `/benchmarks/runs` | `GET`, `POST` | `BenchmarkRunCreate` | `BenchmarkRunResponse` | Yes (Bearer) | `ADMIN` / `AGENT` |

---

## 3. Standard Error Envelope & HTTP Status Codes

All API errors return RFC 7807 compliant JSON envelopes:

```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "Human readable summary of the error",
    "details": [
      {
        "field": "head_sha",
        "issue": "Invalid hexadecimal SHA-1 string"
      }
    ],
    "request_id": "req-9e94d8d0-6dfb-4153-bb50-4e1437a4d8a2"
  }
}
```

### Standard Status Codes
- `200 OK`: Successful synchronous retrieval or state query.
- `201 Created`: Resource successfully created.
- `202 Accepted`: Asynchronous task (review job, webhook ingestion) scheduled.
- `400 Bad Request`: Schema validation failure or malformed payload.
- `401 Unauthorized`: Missing, expired, or invalid Bearer JWT or HMAC signature.
- `403 Forbidden`: Authenticated identity lacks permission for requested resource/tenant.
- `404 Not Found`: Target resource does not exist within the requester's tenant boundary.
- `409 Conflict`: Concurrency conflict (e.g. duplicate webhook event, stale head SHA).
- `422 Unprocessable Entity`: Semantic validation failure (e.g. invalid line number range).
- `429 Too Many Requests`: Rate limit exceeded (returns `Retry-After` header).
- `500 Internal Server Error`: Unhandled system error (stripped of stack trace in production).

---

## 4. Safe API Modification Protocol

Before modifying any API endpoint or schema:

1. **Identify Consumers**: Check `apps/web/` API client calls, webhook consumers, and CLI scripts (`evaluation/cli.py`, `scripts/`).
2. **Verify Backward Compatibility**:
   - Never remove a field from a Pydantic response schema.
   - New fields must provide default values (`Field(default=...)`).
   - New query parameters must be optional (`Optional[str] = None`).
3. **Update Schemas & Tests**:
   - Update `app/schemas/` models.
   - Add test cases in `apps/api/tests/test_api_endpoints.py` verifying both legacy payloads (missing new fields) and modern payloads.
4. **Documentation Sync**: Update this document and OpenAPI docstrings.

---

## 5. External API Integrations & Compatibility

### 5.1 GitHub API Integration
- **API Version**: GitHub REST API `2022-11-28`.
- **Authentication**: GitHub App Installation Access Tokens generated via RS256 JWTs signed with the private key (`GITHUB_PRIVATE_KEY_PATH`).
- **Error Handling**: Rate limit responses (`403` / `429`) trigger exponential backoff with jitter up to 3 retries, respecting `x-ratelimit-reset`.
- **Publication Idempotency**: PR comments check for existing `<!-- codeguard-review-id: <uuid> -->` marker headers before publishing to prevent duplicate comments.

### 5.2 Google Gemini API Integration
- **SDK**: `google-genai` / REST API `v1beta`.
- **Model Versions**: `gemini-1.5-pro` (complex reasoning, synthesis), `gemini-1.5-flash` (fast comprehension, triage).
- **Format**: Structured outputs requested via JSON schema mode (`response_mime_type="application/json"`).
- **Timeouts & Retries**: Requests time out at 60 seconds; retry on HTTP 503 / 429 with exponential backoff (max 3 retries).

### 5.3 Policy Engine Integration
- **Authorization**: Tool execution authorization handled directly by `app.core.policy` (`SentinelPolicy`, `TOOL_RISK_MAP`).
- **Security Boundary**: Backend policy engine validates all consequential actions. Untrusted LLM outputs cannot invoke write/deploy operations without human approval.
