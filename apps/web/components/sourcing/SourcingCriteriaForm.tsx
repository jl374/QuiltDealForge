"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import type { SourcingCriteria } from "@/types";
import { Search, ChevronDown, ChevronUp } from "lucide-react";

const ALL_SOURCES = [
  "QuietLight",
  "EmpireFlippers",
  "DealStream",
  "FE International",
  "Craigslist",
  "Axial",
];

interface Props {
  onSearch: (criteria: SourcingCriteria) => void;
  loading: boolean;
}

export function SourcingCriteriaForm({ onSearch, loading }: Props) {
  const [sector, setSector] = useState("");
  const [keywords, setKeywords] = useState("");
  const [location, setLocation] = useState("");
  const [minEmployees, setMinEmployees] = useState("");
  const [maxEmployees, setMaxEmployees] = useState("");
  const [minRevenue, setMinRevenue] = useState("");
  const [maxRevenue, setMaxRevenue] = useState("");
  const [selectedSources, setSelectedSources] = useState<string[]>(ALL_SOURCES);
  const [showAdvanced, setShowAdvanced] = useState(false);

  function toggleSource(source: string) {
    setSelectedSources((prev) =>
      prev.includes(source)
        ? prev.filter((s) => s !== source)
        : [...prev, source]
    );
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const criteria: SourcingCriteria = {};
    if (sector) criteria.sector = sector;
    if (keywords.trim()) criteria.keywords = keywords.trim();
    if (location.trim()) criteria.location = location.trim();
    if (minEmployees) criteria.min_employees = parseInt(minEmployees);
    if (maxEmployees) criteria.max_employees = parseInt(maxEmployees);
    // Revenue stored in dollars; form input is in millions for UX
    if (minRevenue) criteria.min_revenue = parseFloat(minRevenue) * 1_000_000;
    if (maxRevenue) criteria.max_revenue = parseFloat(maxRevenue) * 1_000_000;
    if (selectedSources.length < ALL_SOURCES.length) {
      criteria.sources = selectedSources;
    }
    onSearch(criteria);
  }

  const canSubmit = !loading && (sector || keywords.trim() || location.trim());

  return (
    <form onSubmit={handleSubmit} className="bg-white border border-slate-200 rounded-xl p-6 space-y-5">
      {/* Primary criteria */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Input
          label="Industry / Sector"
          value={sector}
          onChange={(e) => setSector(e.target.value)}
          placeholder="e.g. accounting, IVF, HOA management"
        />
        <Input
          label="Keywords"
          value={keywords}
          onChange={(e) => setKeywords(e.target.value)}
          placeholder="e.g. recurring revenue, SaaS, B2B"
        />
        <Input
          label="Location"
          value={location}
          onChange={(e) => setLocation(e.target.value)}
          placeholder="e.g. Texas, Southeast, Chicago"
        />
      </div>

      {/* Advanced toggle */}
      <button
        type="button"
        className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 transition-colors"
        onClick={() => setShowAdvanced((v) => !v)}
      >
        {showAdvanced ? (
          <ChevronUp className="w-4 h-4" />
        ) : (
          <ChevronDown className="w-4 h-4" />
        )}
        Advanced filters
      </button>

      {showAdvanced && (
        <div className="space-y-5 pt-1 border-t border-slate-100">
          {/* Size filters */}
          <div>
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-3">
              Company Size
            </p>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <Input
                label="Min Employees"
                type="number"
                value={minEmployees}
                onChange={(e) => setMinEmployees(e.target.value)}
                placeholder="e.g. 10"
              />
              <Input
                label="Max Employees"
                type="number"
                value={maxEmployees}
                onChange={(e) => setMaxEmployees(e.target.value)}
                placeholder="e.g. 250"
              />
              <Input
                label="Min Revenue ($M)"
                type="number"
                step="0.1"
                value={minRevenue}
                onChange={(e) => setMinRevenue(e.target.value)}
                placeholder="e.g. 1"
              />
              <Input
                label="Max Revenue ($M)"
                type="number"
                step="0.1"
                value={maxRevenue}
                onChange={(e) => setMaxRevenue(e.target.value)}
                placeholder="e.g. 50"
              />
            </div>
          </div>

          {/* Source selection */}
          <div>
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-3">
              Search Sources
            </p>
            <div className="flex flex-wrap gap-2">
              {ALL_SOURCES.map((source) => (
                <button
                  key={source}
                  type="button"
                  onClick={() => toggleSource(source)}
                  className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors border ${
                    selectedSources.includes(source)
                      ? "bg-slate-900 text-white border-slate-900"
                      : "bg-white text-slate-500 border-slate-200 hover:border-slate-400"
                  }`}
                >
                  {source}
                </button>
              ))}
            </div>
            {selectedSources.length === 0 && (
              <p className="text-xs text-red-500 mt-1">Select at least one source</p>
            )}
          </div>
        </div>
      )}

      {/* Submit */}
      <div className="flex items-center justify-between pt-2">
        <p className="text-xs text-slate-400">
          Results are sourced in real-time — searches may take 10–20 seconds.
        </p>
        <Button
          type="submit"
          disabled={!canSubmit || selectedSources.length === 0}
        >
          <Search className="w-4 h-4 mr-2" />
          {loading ? "Searching…" : "Search"}
        </Button>
      </div>
    </form>
  );
}
