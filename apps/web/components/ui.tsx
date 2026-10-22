"use client";

import React from "react";

// ── Skeleton primitives ──────────────────────────────
export const SkeletonLine: React.FC<{ w?: string; h?: string }> = ({
  w = "w-full",
  h = "h-3",
}) => <div className={`skeleton ${w} ${h} rounded`} />;

export const SkeletonCard: React.FC = () => (
  <div className="bg-surface-container-lowest p-4 rounded-lg border border-[#262930] flex flex-col gap-3">
    <SkeletonLine w="w-24" h="h-2.5" />
    <SkeletonLine w="w-16" h="h-8" />
    <SkeletonLine w="w-32" h="h-2.5" />
  </div>
);

// ── Panel card wrapper ───────────────────────────────
interface PanelCardProps {
  title: string;
  description?: string;
  badge?: React.ReactNode;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  noPad?: boolean;
}

export const PanelCard: React.FC<PanelCardProps> = ({
  title,
  description,
  badge,
  action,
  children,
  className = "",
  noPad = false,
}) => (
  <div
    className={`bg-surface-container-lowest rounded-lg border border-[#262930] shadow-sm ${className}`}
  >
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 px-4 py-3 border-b border-[#262930]">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <h3 className="font-headline-sm text-headline-sm text-on-surface truncate">
            {title}
          </h3>
          {badge}
        </div>
        {description && (
          <p className="font-body-sm text-body-sm text-outline mt-0.5 truncate">
            {description}
          </p>
        )}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
    <div className={noPad ? "" : "p-4"}>{children}</div>
  </div>
);

// ── Empty state ──────────────────────────────────────
interface EmptyStateProps {
  icon?: string;
  title: string;
  description?: string;
  action?: React.ReactNode;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  icon = "inbox",
  title,
  description,
  action,
}) => (
  <div className="flex flex-col items-center justify-center gap-2 py-10 text-center">
    <span className="material-symbols-outlined text-[32px] text-outline">{icon}</span>
    <p className="font-body-sm text-on-surface-variant font-medium">{title}</p>
    {description && (
      <p className="font-label-mono text-kbd-shortcut text-outline max-w-sm">{description}</p>
    )}
    {action && <div className="mt-2">{action}</div>}
  </div>
);

// ── Error state ──────────────────────────────────────
interface ErrorStateProps {
  message: string;
  onRetry?: () => void;
}

export const ErrorState: React.FC<ErrorStateProps> = ({ message, onRetry }) => (
  <div className="flex flex-col items-center justify-center gap-2 py-8 text-center">
    <span className="material-symbols-outlined text-[28px] text-[#f87171]">error</span>
    <p className="font-body-sm text-[#f87171]">{message}</p>
    {onRetry && (
      <button
        type="button"
        onClick={onRetry}
        className="mt-1 px-3 py-1 rounded bg-surface-container-high text-on-surface font-label-mono text-kbd-shortcut hover:bg-surface-container-highest border border-[#262930] transition-colors"
      >
        Retry
      </button>
    )}
  </div>
);

// ── Metric card ──────────────────────────────────────
interface DashMetricCardProps {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  trend?: React.ReactNode;
  icon?: string;
  iconColor?: string;
  loading?: boolean;
}

export const DashMetricCard: React.FC<DashMetricCardProps> = ({
  label,
  value,
  sub,
  trend,
  icon,
  iconColor = "text-outline",
  loading = false,
}) => {
  if (loading) return <SkeletonCard />;
  return (
    <div className="bg-surface-container-lowest p-4 rounded-lg border border-[#262930] shadow-sm flex flex-col gap-1 hover:bg-surface-container-low transition-colors group">
      <div className="flex items-center justify-between mb-1">
        <span className="font-label-mono text-[11px] uppercase tracking-wider text-outline">
          {label}
        </span>
        {icon && (
          <span className={`material-symbols-outlined text-[18px] ${iconColor}`}>{icon}</span>
        )}
      </div>
      <div className="flex items-baseline gap-2">
        <span className="font-headline-xl text-headline-xl text-on-surface font-bold tracking-tight">
          {value}
        </span>
      </div>
      {sub && (
        <div className="font-label-mono text-[11px] text-outline mt-0.5">{sub}</div>
      )}
      {trend && <div className="mt-1">{trend}</div>}
    </div>
  );
};

// ── SVG Donut chart ──────────────────────────────────
export interface DonutSlice {
  label: string;
  count: number;
  color: string;
}

interface DonutChartProps {
  slices: DonutSlice[];
  size?: number;
}

export const DonutChart: React.FC<DonutChartProps> = ({ slices, size = 120 }) => {
  const total = slices.reduce((s, x) => s + x.count, 0);
  if (total === 0) return <div className="text-outline text-xs text-center py-4">No data</div>;

  const r = 40;
  const cx = 60;
  const cy = 60;
  const circ = 2 * Math.PI * r;

  let offset = 0;
  const arcs = slices.map((sl) => {
    const pct = sl.count / total;
    const dash = pct * circ;
    const arc = { ...sl, dash, offset: circ - offset, pct };
    offset += dash;
    return arc;
  });

  return (
    <div className="flex items-center gap-4">
      <svg width={size} height={size} viewBox="0 0 120 120" className="shrink-0">
        <circle cx={cx} cy={cy} r={r} fill="transparent" stroke="#262930" strokeWidth={18} />
        {arcs.map((arc, i) => (
          <circle
            key={i}
            cx={cx}
            cy={cy}
            r={r}
            className="donut-ring"
            stroke={arc.color}
            strokeDasharray={`${arc.dash} ${circ}`}
            strokeDashoffset={arc.offset}
            transform="rotate(-90 60 60)"
          />
        ))}
        <text
          x={cx}
          y={cy + 4}
          textAnchor="middle"
          fontSize="14"
          fontWeight="700"
          fill="#e3e2e6"
          fontFamily="Inter, sans-serif"
        >
          {total}
        </text>
      </svg>
      <div className="flex flex-col gap-1.5 min-w-0">
        {arcs.map((arc, i) => (
          <div key={i} className="flex items-center gap-2 min-w-0">
            <span
              className="w-2 h-2 rounded-full shrink-0"
              style={{ background: arc.color }}
            />
            <span className="font-label-mono text-[11px] text-on-surface-variant truncate">
              {arc.label}
            </span>
            <span className="font-label-mono text-[11px] text-on-surface font-semibold ml-auto shrink-0">
              {arc.count}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};

// ── Horizontal bar chart ─────────────────────────────
export interface BarSegment {
  label: string;
  count: number;
  color: string;
}

interface HBarChartProps {
  segments: BarSegment[];
  total?: number;
}

export const SeverityBar: React.FC<HBarChartProps> = ({ segments, total }) => {
  const sum = total ?? segments.reduce((s, x) => s + x.count, 0);
  if (sum === 0)
    return <div className="text-outline text-xs text-center py-2">No findings</div>;

  return (
    <div className="flex flex-col gap-2">
      {/* stacked bar */}
      <div className="w-full h-2 rounded-full overflow-hidden flex">
        {segments.map((seg, i) => {
          const w = Math.round((seg.count / sum) * 100);
          return (
            <div
              key={i}
              className="h-full"
              style={{ width: `${w}%`, background: seg.color }}
              title={`${seg.label}: ${seg.count} (${w}%)`}
            />
          );
        })}
      </div>
      {/* legend */}
      <div className="flex flex-wrap gap-x-3 gap-y-1">
        {segments.map((seg, i) => (
          <div key={i} className="flex items-center gap-1.5">
            <span
              className="w-2 h-2 rounded-full"
              style={{ background: seg.color }}
            />
            <span className="font-label-mono text-[11px] text-on-surface-variant">
              {seg.label}
            </span>
            <span className="font-label-mono text-[11px] text-on-surface font-semibold">
              {seg.count}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};
