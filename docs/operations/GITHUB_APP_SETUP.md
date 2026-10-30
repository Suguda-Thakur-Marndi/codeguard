# GitHub App Integration Setup Guide

This document provides step-by-step instructions for configuring and connecting a GitHub App with CodeGuard AI for repository analysis and review operations.

---

## 1. Locate Your Numeric GitHub App ID

1. Navigate to GitHub: **Settings** &rarr; **Developer settings** &rarr; **GitHub Apps**.
2. Select your registered GitHub App (e.g., `codeguard-ai-123`).
3. Under the **General** tab, scroll to the **About** section.
4. Locate the **App ID** field (a numeric integer such as `1029384`).
5. Configure this in your local `.env` file:
   ```env
   GITHUB_APP_ID=1029384
   GITHUB_APP_SLUG=codeguard-ai-123
   ```
   > [!IMPORTANT]
   > Do not use `dev-app-id` or alphanumeric placeholders for live operations. PyJWT and the GitHub API require `GITHUB_APP_ID` to be numeric.

---

## 2. Configure the Private Key Locally

1. In the GitHub App's **General** tab, scroll down to **Private keys**.
2. Click **Generate a private key** if you do not already have one. A `.pem` file will download to your machine.
3. Place the `.pem` file in your project root or API directory.
4. Set the path in `.env` using a filename or relative path:
   ```env
   GITHUB_PRIVATE_KEY_PATH=codeguard-ai-123.2026-10-03.private-key.pem
   ```
   CodeGuard AI automatically resolves the key path whether commands are run from the project root or the `apps/api` directory.
   
   Alternatively, you can provide the key inline via `GITHUB_PRIVATE_KEY`:
   ```env
   GITHUB_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----"
   ```

   > [!CAUTION]
   > **NEVER** commit `.pem` files or private key strings to Git. Ensure `*.pem` and `*.private-key.pem` are present in `.gitignore`.
   > Never paste private key contents into chat, pull requests, issues, or ticket logs.

---

## 3. Configure the Webhook Secret

1. In your GitHub App settings under **General** &rarr; **Webhook**, locate the **Webhook secret** field.
2. Generate a cryptographically secure random string (e.g., `openssl rand -hex 32`).
3. Enter this secret in GitHub's **Webhook secret** field.
4. Set the identical secret in your local `.env`:
   ```env
   GITHUB_WEBHOOK_SECRET=your_high_entropy_secret_here
   ```
   Every incoming webhook is verified using constant-time HMAC-SHA256 comparison against `X-Hub-Signature-256`. Requests with missing, invalid, or mismatched signatures are rejected with HTTP 401.

---

## 4. Install the App on a Test Repository & Locate Installation ID

1. In your GitHub App settings, click **Install App** in the left sidebar.
2. Click **Install** next to your target account or organization.
3. Select **Only select repositories** and choose your dedicated test repository.
4. After clicking **Save** / **Install**, GitHub redirects you to an installation URL formatted as:
   ```
   https://github.com/settings/installations/12345678
   ```
   The trailing number (`12345678`) is your **Installation ID**.
5. Verify that this installation is registered with CodeGuard AI:
   ```bash
   curl -X POST http://localhost:8000/api/v1/github/installations/verify \
     -H "Content-Type: application/json" \
     -d '{"installation_id": 12345678}'
   ```

---

## 5. Configure Webhook URL for Local Testing

For local development and integration testing:
1. Use a secure HTTPS reverse tunnel (e.g. cloudflared, tailscale funnel, or smee.io) forwarding to your local backend:
   ```
   Forward to: http://localhost:8000/api/v1/webhooks/github
   ```
2. In your GitHub App settings under **Webhook**:
   - Set **Webhook URL** to `https://<your-secure-tunnel-subdomain>/api/v1/webhooks/github`
   - Set **SSL verification** to **Enable SSL verification**.
3. Under **Permissions & events** &rarr; **Subscribe to events**:
   - Check **Pull request** (triggers on `opened`, `synchronize`, `reopened`, `ready_for_review`).

---

## 6. Verification Without Review Publication (Human Approval Gate)

CodeGuard AI enforces strict zero-trust policy separation between review execution and review publication:

1. When a webhook arrives:
   - HMAC-SHA256 signature is verified.
   - The exact pull request head SHA (`head.sha`) is extracted and recorded.
   - Review analysis, multi-agent evaluation, and adversarial verification execute.
   - Findings are persisted in `review_findings` with statuses (`PUBLISHABLE`, `REJECTED`).
2. **Zero Automated Publication**:
   - Review findings are **never** automatically published or posted as PR comments to GitHub.
   - All publications require explicit human authorization through the CodeGuard AI dashboard or the `/api/v1/approvals` endpoint.
   - Review publication jobs enforce an atomic `ApprovalRequest` check and lock against the current head SHA before any comment reaches GitHub API.
3. You can safely inspect generated findings, AST chunks, and agent execution traces in the local database or dashboard without any risk of polluting GitHub PR comments.

---

## 7. Verify Configuration Readiness

To verify whether your local environment is ready for GitHub operations without exposing secrets:

Run the health check endpoint:
```bash
curl http://localhost:8000/api/v1/github/status
```

Expected response when fully configured:
```json
{
  "ready": true,
  "settings": {
    "GITHUB_APP_ID": "CONFIGURED",
    "GITHUB_APP_SLUG": "CONFIGURED",
    "GITHUB_PRIVATE_KEY": "CONFIGURED",
    "GITHUB_WEBHOOK_SECRET": "CONFIGURED"
  }
}
```

If any setting reports `PLACEHOLDER`, `MISSING`, or `INVALID`, update your `.env` following the steps above.

---

## 8. Security Guardrails Summary

| Threat / Risk | CodeGuard AI Defense |
| :--- | :--- |
| Private Key Leakage | Auto-discovery and resolution without logging; strict `.gitignore` enforcement |
| Replay & Spoofing | Constant-time HMAC-SHA256 signature verification on raw webhook body |
| Token Misuse | 10-minute short-lived RS256 App JWTs with 60s clock drift buffer |
| Accidental PR Comments | Deterministic Human Approval Gate (`ApprovalRequest`) before any GitHub publication |
| Base Commit Confusion | Analysis explicitly locked to `pull_request.head.sha` |
| Multi-Tenant Tampering | Webhook drops events where repository owner does not match installation tenant |
