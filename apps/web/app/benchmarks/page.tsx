"use client";

import React, { useEffect, useState } from "react";
import { api } from "../../lib/api";
import {
  BenchmarkComparison,
  BenchmarkRunDetail,
  BenchmarkRunItem,
} from "../../lib/types";

export default function BenchmarksPage() {
  const [runs, setRuns] = useState<BenchmarkRunItem[]>([]);
  const [selectedRun, setSelectedRun] = useState<BenchmarkRunDetail | null>(null);
  const [comparison, setComparison] = useState<BenchmarkComparison | null>(null);
  const [baselineRunId, setBaselineRunId] = useState<string>("");
  const [candidateRunId, setCandidateRunId] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [inspecting, setInspecting] = useState(false);
  const [comparing, setComparing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadBenchmarkRuns() {
    try {
      setLoading(true);
      setError(null);
      const res = await api.getBenchmarkRuns(1, 50);
      const items = res.items || [];
      setRuns(items);
      if (items.length >= 2) {
        setBaselineRunId(items[1].id);
        setCandidateRunId(items[0].id);
      } else if (items.length === 1) {
        setBaselineRunId(items[0].id);
        setCandidateRunId(items[0].id);
      }
    } catch (err: any) {
      setError(err.message || "Failed to load benchmark evaluation data");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadBenchmarkRuns();
  }, []);

  const handleInspectRun = async (runId: string) => {
    try {
      setInspecting(true);
      const detail = await api.getBenchmarkRun(runId);
      setSelectedRun(detail);
      setComparison(null);
    } catch (err: any) {
      alert(`Failed to load benchmark details: ${err.message}`);
    } finally {
      setInspecting(false);
    }
  };

  const handleCompare = async () => {
    if (!baselineRunId || !candidateRunId) {
      alert("Please select both a baseline run and a candidate run to compare.");
      return;
    }
    try {
      setComparing(true);
      const comp = await api.compareBenchmarkRuns(baselineRunId, candidateRunId);
      setComparison(comp);
      setSelectedRun(null);
    } catch (err: any) {
      alert(`Comparison failed: ${err.message}`);
    } finally {
      setComparing(false);
    }
  };

  const latestRun = runs.length > 0 ? runs[0] : null;
  const metrics = latestRun?.metrics_summary;

  return (
    <div className="flex flex-col w-full pb-16 space-y-space-md">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-space-md border-b border-[#262930]">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="font-headline-lg text-headline-lg text-primary tracking-tight">
              Evaluation &amp; Benchmark Telemetry
            </h1>
            <span className="font-label-mono text-kbd-shortcut px-2 py-0.5 rounded bg-tertiary-container/20 text-tertiary-fixed-dim font-semibold border border-[#262930]">
              Empirical Real Data Gate
            </span>
          </div>
          <p className="font-body-sm text-body-sm text-outline mt-0.5">
            Strict ground-truth evaluations, precision/recall curves, and regression gates. Zero metric fabrication.
          </p>
        </div>

        <button
          type="button"
          onClick={loadBenchmarkRuns}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded bg-surface-container hover:bg-surface-container-high text-on-surface font-label-mono text-label-md border border-[#262930]"
        >
          <span className={`material-symbols-outlined text-[16px] ${loading ? "animate-spin" : ""}`}>sync</span>
          <span>Refresh Runs</span>
        </button>
      </div>

      {error && (
        <div className="p-space-md rounded bg-error-container/20 border border-error text-error font-body-sm flex items-center justify-between">
          <span>{error}</span>
          <button
            type="button"
            onClick={loadBenchmarkRuns}
            className="px-2.5 py-1 rounded bg-error-container text-on-error-container font-label-mono text-kbd-shortcut"
          >
            Retry
          </button>
        </div>
      )}

      {/* Real Summary Metrics Strip (Only rendered if runs exist) */}
      {runs.length > 0 && metrics ? (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-space-sm">
          <div className="p-space-md rounded bg-surface-container-low border border-[#262930] flex flex-col justify-between">
            <span className="font-label-mono text-kbd-shortcut uppercase text-outline">Total Runs</span>
            <span className="font-headline-md text-headline-md text-primary font-bold mt-1">
              {runs.length}
            </span>
            <span className="font-label-mono text-kbd-shortcut text-outline">Evaluated in DB</span>
          </div>
          <div className="p-space-md rounded bg-surface-container-low border border-[#262930] flex flex-col justify-between">
            <span className="font-label-mono text-kbd-shortcut uppercase text-outline">Precision</span>
            <span className="font-headline-md text-headline-md text-tertiary-fixed-dim font-bold mt-1">
              {metrics.precision ? `${(metrics.precision * 100).toFixed(1)}%` : "N/A"}
            </span>
            <span className="font-label-mono text-kbd-shortcut text-tertiary-fixed-dim">TP / (TP + FP)</span>
          </div>
          <div className="p-space-md rounded bg-surface-container-low border border-[#262930] flex flex-col justify-between">
            <span className="font-label-mono text-kbd-shortcut uppercase text-outline">Recall</span>
            <span className="font-headline-md text-headline-md text-primary-fixed font-bold mt-1">
              {metrics.recall ? `${(metrics.recall * 100).toFixed(1)}%` : "N/A"}
            </span>
            <span className="font-label-mono text-kbd-shortcut text-primary-fixed">TP / (TP + FN)</span>
          </div>
          <div className="p-space-md rounded bg-surface-container-low border border-[#262930] flex flex-col justify-between">
            <span className="font-label-mono text-kbd-shortcut uppercase text-outline">F1 Score</span>
            <span className="font-headline-md text-headline-md text-secondary font-bold mt-1">
              {metrics.f1_score ? `${(metrics.f1_score * 100).toFixed(1)}%` : "N/A"}
            </span>
            <span className="font-label-mono text-kbd-shortcut text-secondary">Harmonic Mean</span>
          </div>
          <div className="p-space-md rounded bg-surface-container-low border border-[#262930] flex flex-col justify-between">
            <span className="font-label-mono text-kbd-shortcut uppercase text-outline">Latency P50</span>
            <span className="font-headline-md text-headline-md text-on-surface font-bold mt-1">
              {metrics.latency_p50_ms ? `${metrics.latency_p50_ms}ms` : "N/A"}
            </span>
            <span className="font-label-mono text-kbd-shortcut text-outline">Median execution</span>
          </div>
        </div>
      ) : null}

      {/* Main Content Area */}
      {loading ? (
        <div className="p-16 text-center font-label-mono text-outline text-sm bg-surface-container-lowest rounded-lg border border-[#262930]">
          Loading empirical benchmark records from PostgreSQL...
        </div>
      ) : runs.length === 0 ? (
        /* Honest, Non-Fabricated Empty State */
        <div className="p-10 rounded-xl bg-surface-container-lowest border border-[#262930] text-center space-y-4 max-w-2xl mx-auto shadow-lg">
          <div className="w-12 h-12 rounded-lg bg-surface-container-high border border-[#333842] flex items-center justify-center mx-auto text-primary-fixed">
            <span className="material-symbols-outlined text-[28px]">speed</span>
          </div>
          <h2 className="font-headline-md text-headline-md text-primary">
            No Benchmark Runs Recorded in Database
          </h2>
          <p className="font-body-md text-body-md text-on-surface-variant max-w-lg mx-auto">
            CodeGuard strictly refuses to fabricate performance metrics or benchmark numbers. All metrics must be
            empirically calculated by running the benchmark evaluation suite against real ground-truth scenarios.
          </p>
          <div className="p-space-sm rounded bg-surface-container-low border border-[#262930] text-left font-code-block text-code-block max-w-md mx-auto space-y-1">
            <p className="text-outline uppercase text-[10px] font-label-mono">To execute benchmark evaluation:</p>
            <p className="text-primary-fixed font-mono select-all">
              .\.venv\Scripts\python.exe verify_benchmarks.py
            </p>
            <p className="text-outline text-[11px]">
              Or run the evaluation runner to record empirical F1, precision, and latency metrics to this dashboard.
            </p>
          </div>
        </div>
      ) : (
        <div className="space-y-space-md">
          {/* Comparison Bar */}
          <div className="p-space-sm rounded-lg bg-surface-container-low border border-[#262930] flex flex-col md:flex-row items-center justify-between gap-space-sm">
            <div className="flex items-center gap-space-sm w-full md:w-auto">
              <span className="font-label-mono text-kbd-shortcut uppercase text-outline">Compare Runs:</span>
              <select
                value={baselineRunId}
                onChange={(e) => setBaselineRunId(e.target.value)}
                className="bg-surface-container text-on-surface font-label-mono text-kbd-shortcut px-2 py-1 rounded border border-[#262930] outline-none"
              >
                <option value="">Select Baseline</option>
                {runs.map((r) => (
                  <option key={r.id} value={r.id}>
                    Baseline: {r.name} ({r.model_name})
                  </option>
                ))}
              </select>
              <span className="text-outline">vs</span>
              <select
                value={candidateRunId}
                onChange={(e) => setCandidateRunId(e.target.value)}
                className="bg-surface-container text-on-surface font-label-mono text-kbd-shortcut px-2 py-1 rounded border border-[#262930] outline-none"
              >
                <option value="">Select Candidate</option>
                {runs.map((r) => (
                  <option key={r.id} value={r.id}>
                    Candidate: {r.name} ({r.model_name})
                  </option>
                ))}
              </select>
            </div>
            <button
              type="button"
              onClick={handleCompare}
              disabled={comparing || !baselineRunId || !candidateRunId}
              className="px-3 py-1.5 rounded bg-primary-container text-on-primary-container font-label-mono text-kbd-shortcut font-semibold hover:brightness-105 active:scale-95 transition-all shadow-sm"
            >
              {comparing ? "Comparing..." : "Run Delta Comparison"}
            </button>
          </div>

          {/* Comparison Results Card */}
          {comparison && (
            <div className="p-space-md rounded-xl bg-surface-container-low border border-primary-fixed/40 shadow-lg space-y-3">
              <div className="flex items-center justify-between border-b border-[#262930] pb-2">
                <div className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-[18px] text-primary-fixed">compare_arrows</span>
                  <h3 className="font-headline-sm text-body-sm text-primary font-semibold">
                    Regression Delta: {comparison.candidate_run.name} vs {comparison.baseline_run.name}
                  </h3>
                </div>
                {comparison.is_regression ? (
                  <span className="px-2 py-0.5 rounded bg-error-container text-on-error-container font-label-mono text-kbd-shortcut font-bold">
                    REGRESSION DETECTED
                  </span>
                ) : (
                  <span className="px-2 py-0.5 rounded bg-tertiary-container text-on-tertiary-container font-label-mono text-kbd-shortcut font-bold">
                    NO REGRESSION (PASSED)
                  </span>
                )}
              </div>

              {comparison.regressions && comparison.regressions.length > 0 && (
                <div className="p-2 rounded bg-error-container/20 border border-error/40 text-error font-mono text-xs">
                  {comparison.regressions.map((reg, i) => (
                    <div key={i}>• {reg}</div>
                  ))}
                </div>
              )}

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
                <div className="p-2 rounded bg-surface-container-lowest border border-[#262930]">
                  <span className="text-[10px] font-label-mono text-outline uppercase">F1 Delta</span>
                  <p
                    className={`font-mono text-sm font-bold ${
                      comparison.delta.f1_delta >= 0 ? "text-tertiary-fixed-dim" : "text-error"
                    }`}
                  >
                    {comparison.delta.f1_delta > 0 ? "+" : ""}
                    {(comparison.delta.f1_delta * 100).toFixed(2)}%
                  </p>
                </div>
                <div className="p-2 rounded bg-surface-container-lowest border border-[#262930]">
                  <span className="text-[10px] font-label-mono text-outline uppercase">Precision Delta</span>
                  <p
                    className={`font-mono text-sm font-bold ${
                      comparison.delta.precision_delta >= 0 ? "text-tertiary-fixed-dim" : "text-error"
                    }`}
                  >
                    {comparison.delta.precision_delta > 0 ? "+" : ""}
                    {(comparison.delta.precision_delta * 100).toFixed(2)}%
                  </p>
                </div>
                <div className="p-2 rounded bg-surface-container-lowest border border-[#262930]">
                  <span className="text-[10px] font-label-mono text-outline uppercase">Recall Delta</span>
                  <p
                    className={`font-mono text-sm font-bold ${
                      comparison.delta.recall_delta >= 0 ? "text-tertiary-fixed-dim" : "text-error"
                    }`}
                  >
                    {comparison.delta.recall_delta > 0 ? "+" : ""}
                    {(comparison.delta.recall_delta * 100).toFixed(2)}%
                  </p>
                </div>
                <div className="p-2 rounded bg-surface-container-lowest border border-[#262930]">
                  <span className="text-[10px] font-label-mono text-outline uppercase">Latency Delta</span>
                  <p className="font-mono text-sm font-bold text-on-surface">
                    {comparison.delta.latency_p50_delta_ms}ms
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Runs List Table */}
          <div className="bg-surface-container-lowest rounded-lg border border-[#262930] overflow-hidden shadow-sm">
            <table className="w-full text-left font-body-sm text-body-sm border-collapse">
              <thead>
                <tr className="bg-surface-container text-on-surface-variant font-label-mono text-kbd-shortcut uppercase tracking-wider">
                  <th className="py-2.5 px-4">Benchmark Run</th>
                  <th className="py-2.5 px-3">Model</th>
                  <th className="py-2.5 px-3">Dataset</th>
                  <th className="py-2.5 px-3">Scenarios Passed</th>
                  <th className="py-2.5 px-3">Metrics (P / R / F1)</th>
                  <th className="py-2.5 px-3">Executed</th>
                  <th className="py-2.5 px-4 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#262930]/40">
                {runs.map((r) => {
                  const m = r.metrics_summary || {};
                  return (
                    <tr key={r.id} className="hover:bg-surface-container transition-colors group">
                      <td className="py-3 px-4">
                        <div className="flex flex-col">
                          <span className="font-semibold text-primary">{r.name}</span>
                          <span className="font-mono text-[10px] text-outline">
                            SHA: {r.git_revision ? r.git_revision.slice(0, 7) : "HEAD"}
                          </span>
                        </div>
                      </td>
                      <td className="py-3 px-3">
                        <span className="font-label-mono text-kbd-shortcut bg-surface-container-high px-2 py-0.5 rounded text-on-surface-variant border border-[#262930]">
                          {r.model_name}
                        </span>
                      </td>
                      <td className="py-3 px-3 font-label-mono text-kbd-shortcut text-outline">
                        {r.dataset_version}
                      </td>
                      <td className="py-3 px-3">
                        <span className="font-label-mono text-kbd-shortcut text-tertiary-fixed-dim">
                          {r.scenarios_passed} / {r.scenarios_total}
                        </span>
                      </td>
                      <td className="py-3 px-3 font-label-mono text-kbd-shortcut text-on-surface">
                        {m.precision ? (m.precision * 100).toFixed(0) : 0}% /{" "}
                        {m.recall ? (m.recall * 100).toFixed(0) : 0}% /{" "}
                        {m.f1_score ? (m.f1_score * 100).toFixed(0) : 0}%
                      </td>
                      <td className="py-3 px-3 font-label-mono text-kbd-shortcut text-outline">
                        {new Date(r.created_at).toLocaleDateString()}
                      </td>
                      <td className="py-3 px-4 text-right">
                        <button
                          type="button"
                          onClick={() => handleInspectRun(r.id)}
                          className="font-label-mono text-kbd-shortcut px-2.5 py-1 rounded bg-surface-container-high hover:bg-primary-container hover:text-on-primary-container text-on-surface transition-colors border border-[#262930]"
                        >
                          Inspect
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Detailed Run Inspector Card */}
          {selectedRun && (
            <div className="p-space-md rounded-xl bg-surface-container-low border border-[#262930] shadow-xl space-y-3">
              <div className="flex items-center justify-between border-b border-[#262930] pb-2">
                <div>
                  <h3 className="font-headline-sm text-body-sm text-primary font-semibold">
                    Detailed Scenarios: {selectedRun.name} ({selectedRun.model_name})
                  </h3>
                  <p className="font-label-mono text-[11px] text-outline">
                    Dataset {selectedRun.dataset_version} · Status: {selectedRun.status}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setSelectedRun(null)}
                  className="text-outline hover:text-on-surface text-xs font-label-mono"
                >
                  Close ✕
                </button>
              </div>

              <div className="border border-[#262930] rounded-lg divide-y divide-[#262930]/40 max-h-72 overflow-y-auto">
                {selectedRun.results && selectedRun.results.length > 0 ? (
                  selectedRun.results.map((res) => (
                    <div
                      key={res.id}
                      className="p-2.5 bg-surface-container-lowest/70 flex items-center justify-between hover:bg-surface-container-low text-xs"
                    >
                      <div className="flex flex-col">
                        <span className="font-mono text-primary font-medium">{res.scenario_id}</span>
                        <span className="font-label-mono text-[10px] text-outline">
                          {res.language} · {res.category} · {res.scenario_type}
                        </span>
                      </div>
                      <div className="flex items-center gap-3 font-mono text-[11px]">
                        <span>{res.latency_ms}ms</span>
                        <span className="text-tertiary-fixed-dim">TP: {res.tp_count}</span>
                        <span className="text-surface-tint">FP: {res.fp_count}</span>
                        <span className="text-error">FN: {res.fn_count}</span>
                        <span
                          className={`px-1.5 py-0.5 rounded text-[10px] ${
                            res.status === "PASSED"
                              ? "bg-tertiary-container/20 text-tertiary-fixed-dim"
                              : "bg-error-container text-on-error-container"
                          }`}
                        >
                          {res.status}
                        </span>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="p-4 text-center text-outline text-xs font-mono">
                    No scenario evaluation records attached to this run.
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
