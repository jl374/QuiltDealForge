"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Button } from "@/components/ui/Button";
import { api } from "@/lib/api-client";
import {
  PIPELINE_STAGES,
  OWNERSHIP_TYPES,
  SECTOR_SUGGESTIONS,
} from "@/lib/constants";
import type { CompanyCreate } from "@/types";

const stageOptions = PIPELINE_STAGES.map((s) => ({ value: s, label: s }));
const ownershipOptions = OWNERSHIP_TYPES.map((o) => ({ value: o, label: o }));

interface FormErrors {
  name?: string;
  website?: string;
  general?: string;
}

export function AddCompanyForm() {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState<FormErrors>({});

  const [form, setForm] = useState<{
    name: string;
    website: string;
    hq_location: string;
    sector: string;
    stage: string;
    ownership_type: string;
    employee_count: string;
    revenue_low: string;
    revenue_high: string;
    ebitda_low: string;
    ebitda_high: string;
    source: string;
    notes: string;
  }>({
    name: "",
    website: "",
    hq_location: "",
    sector: "Other",
    stage: "Identified",
    ownership_type: "Unknown",
    employee_count: "",
    revenue_low: "",
    revenue_high: "",
    ebitda_low: "",
    ebitda_high: "",
    source: "",
    notes: "",
  });

  function set(key: keyof typeof form, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }));
    if (errors[key as keyof FormErrors]) {
      setErrors((prev) => ({ ...prev, [key]: undefined }));
    }
  }

  function validate(): boolean {
    const errs: FormErrors = {};
    if (!form.name.trim()) errs.name = "Company name is required.";
    if (form.website && !/^https?:\/\/.+/.test(form.website)) {
      errs.website = "Must be a valid URL starting with http:// or https://";
    }
    setErrors(errs);
    return Object.keys(errs).length === 0;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!validate()) return;

    setSubmitting(true);
    setErrors({});

    const payload: CompanyCreate = {
      name: form.name.trim(),
      sector: form.sector.trim() || "Other",
      stage: form.stage as CompanyCreate["stage"],
    };

    if (form.website) payload.website = form.website;
    if (form.hq_location) payload.hq_location = form.hq_location;
    if (form.ownership_type)
      payload.ownership_type =
        form.ownership_type as CompanyCreate["ownership_type"];
    if (form.employee_count)
      payload.employee_count = parseInt(form.employee_count, 10);
    if (form.revenue_low)
      payload.revenue_low = parseFloat(form.revenue_low) * 1_000_000;
    if (form.revenue_high)
      payload.revenue_high = parseFloat(form.revenue_high) * 1_000_000;
    if (form.ebitda_low)
      payload.ebitda_low = parseFloat(form.ebitda_low) * 1_000_000;
    if (form.ebitda_high)
      payload.ebitda_high = parseFloat(form.ebitda_high) * 1_000_000;
    if (form.source) payload.source = form.source;
    if (form.notes) payload.notes = form.notes;

    try {
      await api.companies.create(payload);
      router.push("/companies");
    } catch (err) {
      setErrors({
        general:
          err instanceof Error ? err.message : "Failed to create company.",
      });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-8">
      {errors.general && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
          {errors.general}
        </div>
      )}

      <section>
        <h2 className="text-sm font-semibold text-slate-700 uppercase tracking-wide mb-4">
          Core Info
        </h2>
        <div className="grid grid-cols-2 gap-4">
          <div className="col-span-2">
            <Input
              label="Company Name"
              required
              value={form.name}
              onChange={(e) => set("name", e.target.value)}
              error={errors.name}
              placeholder="Acme Accounting LLC"
            />
          </div>
          <Input
            label="Website"
            value={form.website}
            onChange={(e) => set("website", e.target.value)}
            error={errors.website}
            placeholder="https://example.com"
            type="url"
          />
          <Input
            label="HQ Location"
            value={form.hq_location}
            onChange={(e) => set("hq_location", e.target.value)}
            placeholder="Austin, TX"
          />
        </div>
      </section>

      <section>
        <h2 className="text-sm font-semibold text-slate-700 uppercase tracking-wide mb-4">
          Classification
        </h2>
        <div className="grid grid-cols-3 gap-4">
          <div>
            <Input
              label="Sector"
              value={form.sector}
              onChange={(e) => set("sector", e.target.value)}
              placeholder="e.g. Healthcare, Dental, HVAC…"
              list="sector-suggestions"
            />
            <datalist id="sector-suggestions">
              {SECTOR_SUGGESTIONS.map((s) => (
                <option key={s} value={s} />
              ))}
            </datalist>
          </div>
          <Select
            label="Pipeline Stage"
            required
            options={stageOptions}
            value={form.stage}
            onChange={(e) => set("stage", e.target.value)}
          />
          <Select
            label="Ownership Type"
            options={ownershipOptions}
            value={form.ownership_type}
            onChange={(e) => set("ownership_type", e.target.value)}
          />
        </div>
      </section>

      <section>
        <h2 className="text-sm font-semibold text-slate-700 uppercase tracking-wide mb-4">
          Financials <span className="text-slate-400 normal-case font-normal">(in $M)</span>
        </h2>
        <div className="grid grid-cols-4 gap-4">
          <Input
            label="Revenue Low ($M)"
            value={form.revenue_low}
            onChange={(e) => set("revenue_low", e.target.value)}
            type="number"
            min="0"
            step="0.1"
            placeholder="2"
          />
          <Input
            label="Revenue High ($M)"
            value={form.revenue_high}
            onChange={(e) => set("revenue_high", e.target.value)}
            type="number"
            min="0"
            step="0.1"
            placeholder="10"
          />
          <Input
            label="EBITDA Low ($M)"
            value={form.ebitda_low}
            onChange={(e) => set("ebitda_low", e.target.value)}
            type="number"
            min="0"
            step="0.1"
            placeholder="2"
          />
          <Input
            label="EBITDA High ($M)"
            value={form.ebitda_high}
            onChange={(e) => set("ebitda_high", e.target.value)}
            type="number"
            min="0"
            step="0.1"
            placeholder="5"
          />
        </div>
        <div className="mt-4">
          <Input
            label="Employee Count"
            value={form.employee_count}
            onChange={(e) => set("employee_count", e.target.value)}
            type="number"
            min="1"
            placeholder="50"
            className="max-w-xs"
          />
        </div>
      </section>

      <section>
        <h2 className="text-sm font-semibold text-slate-700 uppercase tracking-wide mb-4">
          Sourcing
        </h2>
        <div className="grid grid-cols-2 gap-4">
          <Input
            label="Source"
            value={form.source}
            onChange={(e) => set("source", e.target.value)}
            placeholder="LinkedIn, Referral — John Lee, Broker"
          />
        </div>
        <div className="mt-4">
          <label className="block text-sm font-medium text-slate-700 mb-1">
            Notes
          </label>
          <textarea
            value={form.notes}
            onChange={(e) => set("notes", e.target.value)}
            rows={3}
            placeholder="Any initial context, flags, or observations..."
            className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-slate-900 focus:border-transparent resize-none"
          />
        </div>
      </section>

      <div className="flex items-center gap-3 pt-2 border-t border-slate-100">
        <Button type="submit" disabled={submitting}>
          {submitting ? "Saving..." : "Add Company"}
        </Button>
        <Button
          type="button"
          variant="secondary"
          onClick={() => router.push("/companies")}
        >
          Cancel
        </Button>
      </div>
    </form>
  );
}
