"use client";

import { Search } from "lucide-react";
import { PIPELINE_STAGES, SECTOR_SUGGESTIONS } from "@/lib/constants";

interface Filters {
  sector: string;
  stage: string;
  search: string;
}

interface CompanyFiltersProps {
  values: Filters;
  onChange: (filters: Filters) => void;
}

export function CompanyFilters({ values, onChange }: CompanyFiltersProps) {
  const update = (key: keyof Filters, value: string) =>
    onChange({ ...values, [key]: value });

  const hasFilters = values.sector || values.stage || values.search;

  return (
    <div className="flex items-center gap-3 flex-wrap">
      <div className="relative flex-1 min-w-48">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
        <input
          type="text"
          placeholder="Search companies..."
          value={values.search}
          onChange={(e) => update("search", e.target.value)}
          className="w-full pl-9 pr-3 py-2 text-sm border border-slate-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-slate-900 focus:border-transparent"
        />
      </div>

      <div className="relative">
        <input
          type="text"
          placeholder="Filter by sector…"
          value={values.sector}
          onChange={(e) => update("sector", e.target.value)}
          list="sector-filter-suggestions"
          className="px-3 py-2 text-sm border border-slate-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-slate-900 focus:border-transparent w-40"
        />
        <datalist id="sector-filter-suggestions">
          {SECTOR_SUGGESTIONS.map((s) => (
            <option key={s} value={s} />
          ))}
        </datalist>
      </div>

      <select
        value={values.stage}
        onChange={(e) => update("stage", e.target.value)}
        className="px-3 py-2 text-sm border border-slate-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-slate-900 focus:border-transparent"
      >
        <option value="">All stages</option>
        {PIPELINE_STAGES.map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </select>

      {hasFilters && (
        <button
          onClick={() => onChange({ sector: "", stage: "", search: "" })}
          className="text-sm text-slate-400 hover:text-slate-600 transition-colors"
        >
          Clear
        </button>
      )}
    </div>
  );
}
