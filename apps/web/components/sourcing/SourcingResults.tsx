"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "next-auth/react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import type { SourcingResultItem, SourcingCriteria, CompanyAnalysis } from "@/types";
import { ExternalLink, ChevronDown, ChevronUp, Plus, CheckCircle, Sparkles, Loader2, FolderPlus } from "lucide-react";
import { getSectorColor } from "@/lib/constants";
import { CompanyDeepDive } from "./CompanyDeepDive";
import { AddToProjectModal } from "@/components/projects/AddToProjectModal";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

// Fit score → color
function scoreColor(score: number | null): string {
  if (score === null) return "bg-slate-100 text-slate-500";
  if (score >= 70) return "bg-green-100 text-green-700";
  if (score >= 45) return "bg-yellow-100 text-yellow-700";
  return "bg-red-100 text-red-600";
}

function scoreLabel(score: number | null): string {
  if (score === null) return "—";
  if (score >= 70) return "Strong fit";
  if (score >= 45) return "Possible fit";
  return "Weak fit";
}

// Source badge colors — active business discovery sources vs deal listing sources
const SOURCE_COLORS: Record<string, string> = {
  // Active business discovery (green family = "these exist")
  "NPPES":          "bg-green-100 text-green-800",
  "OpenStreetMap":  "bg-lime-100 text-lime-800",
  "Google Places":  "bg-teal-100 text-teal-800",
  // Deal listing sources (blue/purple family = "these are for sale")
  QuietLight:         "bg-emerald-50 text-emerald-700",
  EmpireFlippers:     "bg-sky-50 text-sky-700",
  DealStream:         "bg-blue-50 text-blue-700",
  Craigslist:         "bg-purple-50 text-purple-700",
  "FE International": "bg-orange-50 text-orange-700",
  Axial:              "bg-violet-50 text-violet-700",
  "Acquire.com":      "bg-amber-50 text-amber-700",
};

interface ResultCardProps {
  item: SourcingResultItem;
  criteria: SourcingCriteria;
  onImport: (item: SourcingResultItem) => void;
  importing: boolean;
  imported: boolean;
  importedCompanyId?: string; // DB UUID after import, enables "add to project"
}

const ACTIVE_BIZ_SOURCES = new Set(["NPPES", "OpenStreetMap", "Google Places"]);

function AiFitSummary({
  item,
  criteria,
}: {
  item: SourcingResultItem;
  criteria: SourcingCriteria;
}) {
  const { data: session } = useSession();
  const [summary, setSummary] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [fetched, setFetched] = useState(false);

  const load = useCallback(async () => {
    if (fetched || loading) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/sourcing/analyze`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-User-Id": session?.user?.id ?? "",
          "X-User-Role": session?.user?.role ?? "GP",
        },
        body: JSON.stringify({ company: item, criteria, mode: "summary" }),
      });
      if (res.ok) {
        const data: CompanyAnalysis = await res.json();
        setSummary(data.fit_summary ?? null);
      }
    } catch {
      // silently fail — summary is optional
    } finally {
      setLoading(false);
      setFetched(true);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetched]);

  // Auto-load summary when card is rendered
  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return (
      <div className="flex items-center gap-1.5 text-xs text-slate-400 mt-2">
        <Loader2 className="w-3 h-3 animate-spin" />
        <span>Generating fit summary…</span>
      </div>
    );
  }
  if (!summary) return null;
  return (
    <div className="mt-2 flex items-start gap-1.5">
      <Sparkles className="w-3 h-3 text-amber-400 shrink-0 mt-0.5" />
      <p className="text-xs text-slate-600 italic leading-snug">{summary}</p>
    </div>
  );
}

function ResultCard({ item, criteria, onImport, importing, imported, importedCompanyId }: ResultCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [showDeepDive, setShowDeepDive] = useState(false);
  const [showAddToProject, setShowAddToProject] = useState(false);
  const [prevImported, setPrevImported] = useState(imported);

  // Auto-open AddToProject modal right after a successful pipeline import
  if (imported && !prevImported && importedCompanyId) {
    setPrevImported(true);
    setShowAddToProject(true);
  }

  const isActiveBusiness = ACTIVE_BIZ_SOURCES.has(item.source);
  const sectorColor = getSectorColor(item.sector);

  // Extra fields for active businesses
  const phone = (item.extra as Record<string, unknown>)?.phone as string | undefined;
  const address = (item.extra as Record<string, unknown>)?.address as string | undefined;

  return (
    <div className={`bg-white border rounded-xl overflow-hidden ${
      isActiveBusiness ? "border-green-200" : "border-slate-200"
    }`}>
      {/* Active business banner */}
      {isActiveBusiness && (
        <div className="bg-green-50 border-b border-green-200 px-5 py-1.5 flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-green-500 inline-block" />
          <span className="text-[11px] font-medium text-green-700">Active business — not listed for sale</span>
        </div>
      )}

      {/* Top bar — score + name */}
      <div className="flex items-start gap-4 px-5 py-4">
        {/* Fit score pill */}
        <div className="shrink-0 text-center w-16">
          <div
            className={`rounded-lg px-2 py-1.5 text-xl font-bold leading-none ${scoreColor(item.fit_score)}`}
          >
            {item.fit_score ?? "?"}
          </div>
          <p className={`text-[10px] mt-0.5 font-medium ${
            item.fit_score !== null
              ? item.fit_score >= 70
                ? "text-green-600"
                : item.fit_score >= 45
                ? "text-yellow-600"
                : "text-red-500"
              : "text-slate-400"
          }`}>
            {scoreLabel(item.fit_score)}
          </p>
        </div>

        {/* Main info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h3 className="font-semibold text-slate-900 text-sm leading-snug truncate">
                {item.name}
              </h3>
              <div className="flex flex-wrap items-center gap-1.5 mt-1.5">
                <span
                  className={`inline-block text-[10px] font-medium px-2 py-0.5 rounded ${
                    SOURCE_COLORS[item.source] ?? "bg-slate-100 text-slate-500"
                  }`}
                >
                  {item.source}
                </span>
                {item.sector && (
                  <Badge className={`text-[10px] ${sectorColor}`}>{item.sector}</Badge>
                )}
                {item.location && (
                  <span className="text-xs text-slate-400">{item.location}</span>
                )}
                {phone && (
                  <span className="text-xs text-slate-500 font-mono">{phone}</span>
                )}
              </div>
              {address && (
                <p className="text-[11px] text-slate-400 mt-0.5 truncate">{address}</p>
              )}
            </div>

            {/* Action buttons */}
            <div className="flex items-center gap-2 shrink-0">
              {item.source_url && !ACTIVE_BIZ_SOURCES.has(item.source) && (
                <a
                  href={item.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-slate-400 hover:text-slate-600 transition-colors"
                  title="Open source listing"
                >
                  <ExternalLink className="w-4 h-4" />
                </a>
              )}
              <Button
                variant="secondary"
                onClick={() => onImport(item)}
                disabled={importing || imported}
                className="text-xs py-1 px-2.5"
              >
                {imported ? (
                  <>
                    <CheckCircle className="w-3.5 h-3.5 mr-1 text-green-600" />
                    Added
                  </>
                ) : importing ? (
                  "Adding…"
                ) : (
                  <>
                    <Plus className="w-3.5 h-3.5 mr-1" />
                    Pipeline
                  </>
                )}
              </Button>

              {/* Add to project — available once imported into pipeline */}
              {imported && importedCompanyId && (
                <Button
                  variant="secondary"
                  onClick={() => setShowAddToProject(true)}
                  className="text-xs py-1 px-2.5"
                  title="Add to a project folder"
                >
                  <FolderPlus className="w-3.5 h-3.5 mr-1" />
                  Project
                </Button>
              )}
            </div>
          </div>

          {/* Add to project modal */}
          {showAddToProject && importedCompanyId && (
            <AddToProjectModal
              companyId={importedCompanyId}
              companyName={item.name}
              onClose={() => setShowAddToProject(false)}
            />
          )}

          {/* Key financial data */}
          <div className="flex flex-wrap gap-x-4 gap-y-0.5 mt-2">
            {item.revenue && (
              <span className="text-xs text-slate-500">
                <span className="text-slate-400">Revenue:</span> {item.revenue}
              </span>
            )}
            {item.employees && (
              <span className="text-xs text-slate-500">
                <span className="text-slate-400">Employees:</span> {item.employees}
              </span>
            )}
            {item.asking_price && (
              <span className="text-xs text-slate-500">
                <span className="text-slate-400">Asking:</span> {item.asking_price}
              </span>
            )}
          </div>

          {/* AI fit summary — auto-loaded */}
          <AiFitSummary item={item} criteria={criteria} />
        </div>
      </div>

      {/* Footer: fit reasons + view details */}
      <div className="border-t border-slate-100 flex items-stretch">
        {item.fit_reasons.length > 0 && (
          <button
            type="button"
            className="flex flex-1 items-center gap-1.5 px-5 py-2 text-xs text-slate-400 hover:bg-slate-50 transition-colors"
            onClick={() => setExpanded((v) => !v)}
          >
            {expanded ? (
              <ChevronUp className="w-3.5 h-3.5" />
            ) : (
              <ChevronDown className="w-3.5 h-3.5" />
            )}
            <span>Scoring signals ({item.fit_reasons.length})</span>
          </button>
        )}
        <button
          type="button"
          onClick={() => setShowDeepDive(true)}
          className="flex items-center gap-1.5 px-4 py-2 text-xs text-slate-500 hover:text-slate-900 hover:bg-slate-50 border-l border-slate-100 transition-colors font-medium"
        >
          <Sparkles className="w-3.5 h-3.5 text-amber-400" />
          Deep dive
        </button>
      </div>

      {expanded && item.fit_reasons.length > 0 && (
        <div className="px-5 pb-4 border-t border-slate-50">
          <ul className="space-y-0.5 pt-2">
            {item.fit_reasons.map((reason, i) => (
              <li key={i} className="text-xs text-slate-600">
                {reason}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Deep dive panel */}
      {showDeepDive && (
        <CompanyDeepDive
          item={item}
          criteria={criteria}
          onClose={() => setShowDeepDive(false)}
          onImport={onImport}
          importing={importing}
          imported={imported}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------

interface Props {
  results: SourcingResultItem[];
  criteria: SourcingCriteria;
  onRescore: (criteria: SourcingCriteria) => void;
  rescoring: boolean;
}

type FilterMode = "all" | "strong" | "possible";

export function SourcingResults({ results, criteria, onRescore, rescoring }: Props) {
  const router = useRouter();
  const { data: session } = useSession();

  const [filterMode, setFilterMode] = useState<FilterMode>("all");
  const [importingIds, setImportingIds] = useState<Set<string>>(new Set());
  const [importedIds, setImportedIds] = useState<Set<string>>(new Set());
  // Maps item key → DB company UUID (populated after successful import)
  const [importedCompanyIds, setImportedCompanyIds] = useState<Map<string, string>>(new Map());
  const [importError, setImportError] = useState("");

  const filtered = results.filter((r) => {
    if (filterMode === "strong") return (r.fit_score ?? 0) >= 70;
    if (filterMode === "possible") return (r.fit_score ?? 0) >= 45;
    return true;
  });

  const strongCount = results.filter((r) => (r.fit_score ?? 0) >= 70).length;
  const possibleCount = results.filter(
    (r) => (r.fit_score ?? 0) >= 45 && (r.fit_score ?? 0) < 70
  ).length;

  async function handleImport(item: SourcingResultItem) {
    const key = `${item.name}::${item.source}`;
    setImportingIds((prev) => new Set(prev).add(key));
    setImportError("");

    // Map sourced result → Company create payload
    // Sector is now free-text — pass through as-is
    const sector = item.sector || criteria.sector || "Other";

    const payload: Record<string, unknown> = {
      name: item.name,
      sector,
      stage: "Identified",
      source: item.source,
      notes: [
        item.description ? `From ${item.source}: ${item.description}` : "",
        item.source_url ? `Source URL: ${item.source_url}` : "",
        item.asking_price ? `Asking Price: ${item.asking_price}` : "",
        item.fit_score !== null ? `AI Fit Score (sourcing): ${item.fit_score}/100` : "",
      ]
        .filter(Boolean)
        .join("\n"),
    };

    if (item.website || item.source_url) {
      const url = item.website || item.source_url;
      payload.website = url.startsWith("http") ? url : `https://${url}`;
    }
    if (item.location) payload.hq_location = item.location;
    if (item.fit_score !== null) payload.ai_fit_score = item.fit_score;

    try {
      const res = await fetch(`${API_BASE}/companies/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-User-Id": session?.user?.id ?? "",
          "X-User-Role": session?.user?.role ?? "GP",
        },
        body: JSON.stringify(payload),
      });

      if (res.ok) {
        const data = await res.json();
        setImportedIds((prev) => new Set(prev).add(key));
        if (data?.id) {
          setImportedCompanyIds((prev) => new Map(prev).set(key, data.id));
        }
      } else {
        const data = await res.json().catch(() => ({}));
        const detail = data.detail;
        if (Array.isArray(detail)) {
          setImportError(detail.map((e: { msg?: string }) => e.msg ?? "Validation error").join("; "));
        } else {
          setImportError(typeof detail === "string" ? detail : "Failed to add company.");
        }
      }
    } catch {
      setImportError("Failed to add company. Check your connection.");
    } finally {
      setImportingIds((prev) => {
        const next = new Set(prev);
        next.delete(key);
        return next;
      });
    }
  }

  if (results.length === 0) return null;

  return (
    <div className="space-y-4">
      {/* Stats + filter bar */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <p className="text-sm text-slate-500">
            <span className="font-semibold text-slate-900">{results.length}</span> results
          </p>
          <span className="text-slate-300">·</span>
          <span className="text-xs text-green-700 bg-green-50 px-2 py-0.5 rounded">
            {strongCount} strong fit
          </span>
          <span className="text-xs text-yellow-700 bg-yellow-50 px-2 py-0.5 rounded">
            {possibleCount} possible
          </span>
        </div>

        <div className="flex items-center gap-1.5">
          {(["all", "strong", "possible"] as FilterMode[]).map((mode) => (
            <button
              key={mode}
              type="button"
              onClick={() => setFilterMode(mode)}
              className={`text-xs px-3 py-1.5 rounded-lg font-medium transition-colors ${
                filterMode === mode
                  ? "bg-slate-900 text-white"
                  : "bg-white border border-slate-200 text-slate-600 hover:border-slate-400"
              }`}
            >
              {mode === "all" ? "All" : mode === "strong" ? "Strong (70+)" : "Possible (45+)"}
            </button>
          ))}
        </div>
      </div>

      {importError && (
        <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-2">
          {importError}
        </div>
      )}

      {/* Results list */}
      <div className="space-y-3">
        {filtered.map((item, idx) => {
          const key = `${item.name}::${item.source}`;
          return (
            <ResultCard
              key={`${key}-${idx}`}
              item={item}
              criteria={criteria}
              onImport={handleImport}
              importing={importingIds.has(key)}
              imported={importedIds.has(key)}
              importedCompanyId={importedCompanyIds.get(key)}
            />
          );
        })}
      </div>

      {filtered.length === 0 && (
        <div className="text-center py-12 text-slate-400 text-sm">
          No results match the current filter.
        </div>
      )}
    </div>
  );
}
