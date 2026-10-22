import React from "react";
import { FindingSeverity, FindingStatus } from "../lib/types";

interface SeverityBadgeProps {
  severity?: FindingSeverity | string | null;
  size?: "sm" | "md";
}

const SEV_CLASSES: Record<string, string> = {
  CRITICAL: "sev-critical",
  HIGH:     "sev-high",
  MEDIUM:   "sev-medium",
  LOW:      "sev-low",
  ADVISORY: "sev-advisory",
  INFO:     "sev-advisory",
};

export const SeverityBadge: React.FC<SeverityBadgeProps> = ({ severity, size = "md" }) => {
  if (!severity) return null;
  const key = severity.toUpperCase();
  const cls = SEV_CLASSES[key] ?? "sev-advisory";
  const textSize = size === "sm" ? "text-[10px]" : "text-[11px]";
  return (
    <span
      className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded font-label-mono font-semibold uppercase tracking-wide ${cls} ${textSize}`}
    >
      <span
        className="w-1.5 h-1.5 rounded-full shrink-0"
        style={{ background: "currentColor" }}
      />
      {key}
    </span>
  );
};

interface StatusChipProps {
  status?: FindingStatus | string | null;
  size?: "sm" | "md";
}

const STATUS_CLASSES: Record<string, string> = {
  PUBLISHED:           "sev-resolved",
  PUBLISHABLE:         "sev-resolved",
  EXECUTION_VERIFIED:  "sev-resolved",
  VALIDATED:           "sev-resolved",
  VALID:               "sev-low",
  CANDIDATE:           "sev-advisory",
  REJECTED:            "sev-high",
  INVALID:             "sev-critical",
};

export const FindingStatusChip: React.FC<StatusChipProps> = ({ status, size = "md" }) => {
  if (!status) return null;
  const key = status.toUpperCase();
  const cls = STATUS_CLASSES[key] ?? "sev-advisory";
  const textSize = size === "sm" ? "text-[10px]" : "text-[11px]";
  return (
    <span
      className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded font-label-mono font-medium uppercase tracking-wide ${cls} ${textSize}`}
    >
      {key.replace(/_/g, " ")}
    </span>
  );
};
