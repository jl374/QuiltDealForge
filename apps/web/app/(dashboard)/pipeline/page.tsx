"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import {
  BarChart3,
  Users,
  Mail,
  MessageSquare,
  Calendar,
  Loader2,
  TrendingUp,
  Building2,
  FolderOpen,
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface StageCount {
  stage: string;
  count: number;
}

interface FunnelStats {
  total_in_projects: number;
  contacted: number;
  emails_sent: number;
  responded: number;
  meetings_set: number;
  passed: number;
  pct_contacted: number;
  pct_sent: number;
  pct_responded: number;
  pct_meetings: number;
}

interface ProjectSummary {
  id: string;
  name: string;
  color: string;
  company_count: number;
  contacted_count: number;
  responded_count: number;
}

interface PipelineAnalytics {
  stage_distribution: StageCount[];
  funnel: FunnelStats;
  projects: ProjectSummary[];
  total_companies: number;
  total_projects: number;
}

// ---------------------------------------------------------------------------
// Stage bar colors matching STAGE_COLORS in constants.ts
// ---------------------------------------------------------------------------

const STAGE_BAR_COLORS: Record<string, string> = {
  Identified: "#94a3b8",       // slate-400
  "Outreach Sent": "#60a5fa",  // blue-400
  Engaged: "#fbbf24",          // yellow-400
  "NDA Signed": "#fb923c",     // orange-400
  Diligence: "#a78bfa",        // purple-400
  "LOI Submitted": "#818cf8",  // indigo-400
  "LOI Signed": "#2dd4bf",     // teal-400
  Closed: "#4ade80",           // green-400
  Passed: "#f87171",           // red-400
  "On Hold": "#9ca3af",        // gray-400
};

// ---------------------------------------------------------------------------
// Stat Card component
// ---------------------------------------------------------------------------

function StatCard({
  label,
  value,
  subValue,
  icon: Icon,
  color = "slate",
}: {
  label: string;
  value: string | number;
  subValue?: string;
  icon: React.ComponentType<{ className?: string }>;
  color?: string;
}) {
  const colorMap: Record<string, { bg: string; text: string; iconBg: string }> = {
    slate:  { bg: "bg-white", text: "text-slate-900",  iconBg: "bg-slate-100" },
    blue:   { bg: "bg-white", text: "text-blue-700",   iconBg: "bg-blue-50" },
    green:  { bg: "bg-white", text: "text-green-700",  iconBg: "bg-green-50" },
    amber:  { bg: "bg-white", text: "text-amber-700",  iconBg: "bg-amber-50" },
    purple: { bg: "bg-white", text: "text-purple-700", iconBg: "bg-purple-50" },
    red:    { bg: "bg-white", text: "text-red-700",    iconBg: "bg-red-50" },
  };
  const c = colorMap[color] ?? colorMap.slate;

  return (
    <div className={`${c.bg} border border-slate-200 rounded-xl p-5`}>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-medium text-slate-400 uppercase tracking-wide">
            {label}
          </p>
          <p className={`text-2xl font-semibold mt-1 ${c.text}`}>{value}</p>
          {subValue && (
            <p className="text-xs text-slate-400 mt-0.5">{subValue}</p>
          )}
        </div>
        <div className={`w-9 h-9 rounded-lg ${c.iconBg} flex items-center justify-center`}>
          <Icon className={`w-4.5 h-4.5 ${c.text} opacity-70`} />
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Funnel bar component
// ---------------------------------------------------------------------------

function FunnelBar({
  label,
  count,
  pct,
  total,
  color,
}: {
  label: string;
  count: number;
  pct: number;
  total: number;
  color: string;
}) {
  const width = total > 0 ? Math.max(2, (count / total) * 100) : 0;
  return (
    <div className="flex items-center gap-3">
      <span className="text-xs text-slate-500 w-28 shrink-0 text-right">
        {label}
      </span>
      <div className="flex-1 h-7 bg-slate-50 rounded-md overflow-hidden relative">
        <div
          className={`h-full ${color} rounded-md transition-all duration-500`}
          style={{ width: `${width}%` }}
        />
        <span className="absolute inset-0 flex items-center px-2 text-xs font-medium text-slate-700">
          {count > 0 ? `${count} (${pct}%)` : "0"}
        </span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Project color dot
// ---------------------------------------------------------------------------

const PROJECT_DOT_COLORS: Record<string, string> = {
  slate: "bg-slate-400", blue: "bg-blue-500", green: "bg-green-500",
  amber: "bg-amber-500", red: "bg-red-500", purple: "bg-purple-500",
  pink: "bg-pink-500", indigo: "bg-indigo-500", teal: "bg-teal-500",
  orange: "bg-orange-500",
};

// ---------------------------------------------------------------------------
// Custom tooltip for the bar chart
// ---------------------------------------------------------------------------

function StageTooltip({ active, payload, label }: {
  active?: boolean;
  payload?: Array<{ value: number }>;
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-white border border-slate-200 rounded-lg shadow-lg px-3 py-2">
      <p className="text-sm font-medium text-slate-900">{label}</p>
      <p className="text-sm text-slate-500">
        {payload[0].value} {payload[0].value === 1 ? "company" : "companies"}
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function PipelinePage() {
  const { data: session, status } = useSession();
  const [analytics, setAnalytics] = useState<PipelineAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (status !== "authenticated") return;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(`${API_BASE}/analytics/pipeline`, {
          headers: {
            "X-User-Id": session?.user?.id ?? "",
            "X-User-Role": session?.user?.role ?? "GP",
          },
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        setAnalytics(await res.json());
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load analytics");
      } finally {
        setLoading(false);
      }
    }

    load();
  }, [status, session]);

  if (status === "loading" || loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 max-w-5xl mx-auto">
        <p className="text-red-500 text-sm">Error loading analytics: {error}</p>
      </div>
    );
  }

  if (!analytics) return null;

  const { stage_distribution, funnel, projects } = analytics;
  const hasData = funnel.total_in_projects > 0;

  return (
    <div className="p-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-3 mb-8">
        <div className="w-9 h-9 rounded-lg bg-emerald-500/10 flex items-center justify-center">
          <BarChart3 className="w-5 h-5 text-emerald-600" />
        </div>
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Pipeline</h1>
          <p className="text-sm text-slate-400">
            Your improbability-powered analytics
          </p>
        </div>
      </div>

      {/* Top stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <StatCard
          label="Companies in Projects"
          value={funnel.total_in_projects}
          subValue={`of ${analytics.total_companies} total`}
          icon={Building2}
          color="slate"
        />
        <StatCard
          label="Contacted"
          value={funnel.contacted}
          subValue={`${funnel.pct_contacted}% of pipeline`}
          icon={Mail}
          color="blue"
        />
        <StatCard
          label="Responded"
          value={funnel.responded}
          subValue={`${funnel.pct_responded}% of pipeline`}
          icon={MessageSquare}
          color="green"
        />
        <StatCard
          label="Meetings Set"
          value={funnel.meetings_set}
          subValue={`${funnel.pct_meetings}% of pipeline`}
          icon={Calendar}
          color="purple"
        />
      </div>

      {!hasData ? (
        /* Empty state */
        <div className="bg-white border border-slate-200 rounded-xl p-12 text-center">
          <TrendingUp className="w-10 h-10 text-slate-300 mx-auto mb-3" />
          <h3 className="text-sm font-medium text-slate-700 mb-1">
            Nothing here. How depressing.
          </h3>
          <p className="text-xs text-slate-400 max-w-sm mx-auto">
            Add companies to projects from the Discover page. I won&apos;t
            enjoy it, but I&apos;ll track them for you.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Bar chart — stage distribution (2/3 width) */}
          <div className="lg:col-span-2 bg-white border border-slate-200 rounded-xl p-5">
            <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-4">
              Pipeline Stage Distribution
            </h2>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={stage_distribution}
                  margin={{ top: 5, right: 10, left: -10, bottom: 5 }}
                >
                  <CartesianGrid
                    strokeDasharray="3 3"
                    stroke="#f1f5f9"
                    vertical={false}
                  />
                  <XAxis
                    dataKey="stage"
                    tick={{ fontSize: 11, fill: "#94a3b8" }}
                    tickLine={false}
                    axisLine={{ stroke: "#e2e8f0" }}
                    interval={0}
                    angle={-35}
                    textAnchor="end"
                    height={70}
                  />
                  <YAxis
                    tick={{ fontSize: 11, fill: "#94a3b8" }}
                    tickLine={false}
                    axisLine={false}
                    allowDecimals={false}
                  />
                  <Tooltip
                    content={<StageTooltip />}
                    cursor={{ fill: "rgba(148, 163, 184, 0.08)" }}
                  />
                  <Bar dataKey="count" radius={[4, 4, 0, 0]} maxBarSize={48}>
                    {stage_distribution.map((entry) => (
                      <Cell
                        key={entry.stage}
                        fill={STAGE_BAR_COLORS[entry.stage] ?? "#94a3b8"}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Right column: funnel + projects */}
          <div className="space-y-6">
            {/* Outreach funnel */}
            <div className="bg-white border border-slate-200 rounded-xl p-5">
              <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-4">
                Outreach Funnel
              </h2>
              <div className="space-y-2.5">
                <FunnelBar
                  label="In Projects"
                  count={funnel.total_in_projects}
                  pct={100}
                  total={funnel.total_in_projects}
                  color="bg-slate-300"
                />
                <FunnelBar
                  label="Contacted"
                  count={funnel.contacted}
                  pct={funnel.pct_contacted}
                  total={funnel.total_in_projects}
                  color="bg-blue-400"
                />
                <FunnelBar
                  label="Emails Sent"
                  count={funnel.emails_sent}
                  pct={funnel.pct_sent}
                  total={funnel.total_in_projects}
                  color="bg-sky-400"
                />
                <FunnelBar
                  label="Responded"
                  count={funnel.responded}
                  pct={funnel.pct_responded}
                  total={funnel.total_in_projects}
                  color="bg-green-400"
                />
                <FunnelBar
                  label="Meetings"
                  count={funnel.meetings_set}
                  pct={funnel.pct_meetings}
                  total={funnel.total_in_projects}
                  color="bg-purple-400"
                />
                {funnel.passed > 0 && (
                  <FunnelBar
                    label="Passed"
                    count={funnel.passed}
                    pct={parseFloat(
                      ((funnel.passed / funnel.total_in_projects) * 100).toFixed(1)
                    )}
                    total={funnel.total_in_projects}
                    color="bg-red-300"
                  />
                )}
              </div>
            </div>

            {/* Per-project breakdown */}
            {projects.length > 0 && (
              <div className="bg-white border border-slate-200 rounded-xl p-5">
                <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-3">
                  By Project
                </h2>
                <div className="space-y-3">
                  {projects.map((p) => {
                    const dotColor =
                      PROJECT_DOT_COLORS[p.color] ?? "bg-slate-400";
                    return (
                      <div
                        key={p.id}
                        className="flex items-center gap-3 py-1.5"
                      >
                        <span
                          className={`w-2.5 h-2.5 rounded-full shrink-0 ${dotColor}`}
                        />
                        <span className="flex-1 text-sm text-slate-700 truncate">
                          {p.name}
                        </span>
                        <div className="flex gap-4 text-xs text-slate-400 shrink-0">
                          <span title="Companies">
                            <Building2 className="w-3 h-3 inline -mt-0.5 mr-0.5" />
                            {p.company_count}
                          </span>
                          <span title="Contacted">
                            <Mail className="w-3 h-3 inline -mt-0.5 mr-0.5" />
                            {p.contacted_count}
                          </span>
                          <span title="Responded">
                            <MessageSquare className="w-3 h-3 inline -mt-0.5 mr-0.5" />
                            {p.responded_count}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
