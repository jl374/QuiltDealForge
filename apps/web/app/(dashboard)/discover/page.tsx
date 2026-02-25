"use client";

import { useState } from "react";
import { useSession } from "next-auth/react";
import { SourcingCriteriaForm } from "@/components/sourcing/SourcingCriteriaForm";
import { SourcingResults } from "@/components/sourcing/SourcingResults";
import type { SourcingCriteria, SourcingResultItem } from "@/types";
import { Telescope, RefreshCw, Clock } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export default function DiscoverPage() {
  const { data: session, status } = useSession();
  const [loading, setLoading] = useState(false);
  const [rescoring, setRescoring] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [results, setResults] = useState<SourcingResultItem[]>([]);
  const [lastCriteria, setLastCriteria] = useState<SourcingCriteria>({});
  const [error, setError] = useState("");
  const [hasSearched, setHasSearched] = useState(false);
  const [isCached, setIsCached] = useState(false);

  const authHeaders = {
    "Content-Type": "application/json",
    "X-User-Id": session?.user?.id ?? "",
    "X-User-Role": session?.user?.role ?? "GP",
  };

  async function handleSearch(criteria: SourcingCriteria) {
    if (status !== "authenticated") return;
    setLoading(true);
    setError("");
    setLastCriteria(criteria);
    setHasSearched(true);
    setIsCached(false);

    try {
      const res = await fetch(`${API_BASE}/sourcing/search`, {
        method: "POST",
        headers: authHeaders,
        body: JSON.stringify(criteria),
      });

      const data = await res.json();
      if (res.ok) {
        setResults(data.results ?? []);
        setIsCached(data.cached ?? false);
      } else {
        setError(data.detail ?? "Search failed. Please try again.");
        setResults([]);
      }
    } catch {
      setError("Search failed. Check that the API is running.");
      setResults([]);
    } finally {
      setLoading(false);
    }
  }

  async function handleRefresh() {
    if (!lastCriteria || status !== "authenticated") return;
    setRefreshing(true);
    try {
      // Clear cache first, then re-run the same search
      await fetch(`${API_BASE}/sourcing/cache/clear`, {
        method: "POST",
        headers: authHeaders,
      });
      await handleSearch(lastCriteria);
    } finally {
      setRefreshing(false);
    }
  }

  async function handleRescore(criteria: SourcingCriteria) {
    if (results.length === 0 || status !== "authenticated") return;
    setRescoring(true);
    setError("");

    try {
      const res = await fetch(`${API_BASE}/sourcing/rescore`, {
        method: "POST",
        headers: authHeaders,
        body: JSON.stringify({
          companies: results,
          criteria,
        }),
      });

      const data = await res.json();
      if (res.ok) {
        setResults(data.results ?? []);
        setLastCriteria(criteria);
      } else {
        setError(data.detail ?? "Re-scoring failed.");
      }
    } catch {
      setError("Re-scoring failed. Check that the API is running.");
    } finally {
      setRescoring(false);
    }
  }

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-start gap-3">
        <div className="w-9 h-9 rounded-lg bg-emerald-500/10 flex items-center justify-center shrink-0 mt-0.5">
          <Telescope className="w-5 h-5 text-emerald-600" />
        </div>
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Discover</h1>
          <p className="text-sm text-slate-400 mt-0.5">
            Scanning the galaxy for acquisition targets — brokerage listings, NPI registries,
            Google Places, and OpenStreetMap. Results scored for fit.
          </p>
        </div>
      </div>

      {/* Criteria form */}
      <SourcingCriteriaForm onSearch={handleSearch} loading={loading} />

      {/* Loading state */}
      {loading && (
        <div className="space-y-3">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="bg-white border border-slate-200 rounded-xl p-5">
              <div className="flex items-start gap-4">
                <div className="w-16 h-14 bg-slate-100 rounded-lg animate-pulse shrink-0" />
                <div className="flex-1 space-y-2">
                  <div className="h-4 w-48 bg-slate-100 rounded animate-pulse" />
                  <div className="h-3 w-32 bg-slate-100 rounded animate-pulse" />
                  <div className="h-3 w-full max-w-sm bg-slate-100 rounded animate-pulse" />
                </div>
              </div>
            </div>
          ))}
          <p className="text-center text-sm text-slate-400 animate-pulse">
            Computing the improbability of finding your perfect deal…
          </p>
        </div>
      )}

      {/* Error */}
      {error && !loading && (
        <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-3">
          {error}
        </div>
      )}

      {/* Empty state after search */}
      {!loading && hasSearched && results.length === 0 && !error && (
        <div className="text-center py-16 text-slate-400">
          <Telescope className="w-10 h-10 mx-auto mb-3 opacity-40" />
          <p className="font-medium text-slate-500">Mostly harmless — no results found</p>
          <p className="text-sm mt-1">
            Try different keywords, a broader location, or perhaps a different sector of the galaxy.
          </p>
        </div>
      )}

      {/* Results */}
      {!loading && results.length > 0 && (
        <div className="space-y-4">
          {/* Cache notice + refresh */}
          {isCached && (
            <div className="flex items-center justify-between bg-slate-50 border border-slate-200 rounded-lg px-4 py-2">
              <div className="flex items-center gap-1.5 text-xs text-slate-500">
                <Clock className="w-3.5 h-3.5" />
                Results served from cache (up to 30 min old)
              </div>
              <button
                onClick={handleRefresh}
                disabled={refreshing}
                className="flex items-center gap-1.5 text-xs text-slate-600 hover:text-slate-900 font-medium transition-colors disabled:opacity-50"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? "animate-spin" : ""}`} />
                {refreshing ? "Refreshing…" : "Refresh"}
              </button>
            </div>
          )}

          <SourcingResults
            results={results}
            criteria={lastCriteria}
            onRescore={handleRescore}
            rescoring={rescoring}
          />
        </div>
      )}
    </div>
  );
}
