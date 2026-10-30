# CodeGuard — AI Model Change Management & Prompt Governance Policy

## 1. Prime Directive for AI Model Changes

AI models in CodeGuard are **untrusted reasoning engines subject to deterministic validation**. Upgrading, changing, or tuning an AI model (e.g. Gemini 1.5 Pro, Gemini 1.5 Flash, or future model generations) must be governed by rigorous empirical evaluation.

### Mandatory Rules
1. **Never Promote Merely Because It Is Newer**: A newer model version will not be deployed without documented benchmark evidence proving non-regression.
2. **Comparable Dataset Isolation**: Benchmark comparisons must run against the identical versioned scenario dataset (`evaluation/datasets/v1/`). Comparing candidate results on a different dataset is invalid.
3. **Strict Publication Isolation**: Model evaluations and benchmarks must execute in hermetic test mode (`CODEGUARD_BENCHMARK_MODE=true`). They must **NEVER** publish comments to real customer repositories or invoke external webhook side-effects.
4. **Mark Unverified Models as NOT TESTED**: If API credentials or quota are unavailable for a candidate model, the evaluation must be explicitly classified as `NOT TESTED — DEPENDENCY UNAVAILABLE`.

---

## 2. The 10-Step AI Model Change Evaluation Procedure

Before modifying `GEMINI_MODEL_PRO` or `GEMINI_MODEL_FLASH` in production configuration:

1. **Record Existing Baseline**: Capture the active model configuration, prompt versions, and existing benchmark metrics (`benchmark_report.json`).
2. **Configure Candidate Environment**: Set candidate model identifier in an isolated evaluation config.
3. **Execute Scenario Evaluation**: Run all 12 ground-truth benchmark scenarios using `python benchmark.py run --dataset v1 --name <candidate-model-run>`.
4. **Run Statistical Regression Check**:
   ```bash
   python benchmark.py regression --baseline benchmark_report.json --candidate <candidate_report.json>
   ```
5. **Evaluate Multi-Dimensional Quality Metrics**:
   - **Precision**: Minimum acceptable = 95.0% (baseline = 100.0%).
   - **Recall**: Minimum acceptable = 95.0% (baseline = 100.0%).
   - **F1 Score**: Must not drop by more than `0.05` (`Delta F1 >= -0.05`).
   - **Line Accuracy**: Findings must target valid diff hunk lines with > 90% accuracy.
   - **Severity Classification Accuracy**: Severity alignment with ground truth must exceed 90%.
6. **Inspect False Positives & False Negatives**: Perform manual review of all misclassifications. Any hallucinated finding bypassing the Adversarial Judge requires immediate rejection.
7. **Inspect Prompt-Injection Scenarios**: Run adversarial security scenarios (`scenario_security_injection_01`) to verify prompt isolation and instructions boundary integrity.
8. **Inspect Malformed JSON Handling**: Verify the candidate model adheres to schema constraints (`response_mime_type="application/json"`) without truncation.
9. **Compare Cost & Latency**: Calculate average latency delta (`Delta Latency`) and estimated token consumption per review.
10. **Document & Authorize**: Compile results into an evaluation decision memo signed by the AI Lead and Security Lead before promoting configuration.

---

## 3. Prompt Versioning & Registry Architecture

Prompts are version-controlled in the codebase and decoupled from model client code.

### 3.1 Prompt Version Tracking Contract
Every prompt used by agent specialists must declare metadata:
- `prompt_id`: Unique identifier (e.g. `specialist_security_v1`)
- `version`: SemVer string (e.g. `1.2.0`)
- `target_model`: Target LLM architecture (e.g. `gemini-1.5-pro`)
- `schema_version`: Output JSON schema contract version
- `hash`: SHA-256 digest of the prompt text template

### 3.2 Evaluation Traceability Invariant
When a review job executes, the review record stores:
- `model_name` (e.g. `gemini-1.5-pro`)
- `prompt_version_map` (mapping of specialist agents to prompt hashes)
- `temperature` and `top_p` settings
- Token counts (input tokens, output tokens, total tokens)

This ensures any finding can be reconstructed and debugged against the exact prompt and model configuration that generated it.

---

## 4. Benchmark Reproducibility & Metadata Standards

To ensure benchmark reproducibility, every benchmark run output (`benchmark_report.json`) captures:

```json
{
  "run_id": "run-20260928-131716",
  "git_commit": "8a0f1a57ed32971d60a2120ad82e45a05a43ecc8",
  "dataset_version": "v1",
  "scenario_count": 12,
  "model_config": {
    "pro_model": "gemini-1.5-pro",
    "flash_model": "gemini-1.5-flash",
    "temperature": 0.0
  },
  "metrics": {
    "precision": 1.0,
    "recall": 1.0,
    "f1": 1.0,
    "avg_latency_ms": 15.03,
    "estimated_cost_usd": 0.0
  },
  "timestamp_utc": "2026-09-28T13:17:16Z"
}
```

---

## 5. Quality Regression Thresholds

The automated regression detector (`evaluation/metrics/regression.py`) applies these hard gates:

| Metric | Tolerance Threshold | Failure Action |
| :--- | :--- | :--- |
| **Delta F1** | `< -0.02` | Immediate Build Failure / Release Block |
| **Delta Precision** | `< -0.05` | Immediate Build Failure / Release Block |
| **Delta Recall** | `< -0.05` | Immediate Build Failure / Release Block |
| **Hallucination Rate** | `> 0.0%` (0 tolerated) | Rejection: Judge must intercept 100% of hallucinations |
| **Prompt Injection Bypass**| `> 0` | Security Rejection |
| **Average Latency Surge** | `> +50%` | Warning / Optimization Required |
