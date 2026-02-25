"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ChevronLeft } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { STAGE_COLORS, getSectorColor } from "@/lib/constants";
import type { Company } from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

function formatMoney(val: number | null): string {
  if (!val) return "—";
  return val >= 1_000_000
    ? `$${(val / 1_000_000).toFixed(1)}M`
    : `$${(val / 1_000).toFixed(0)}K`;
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex py-3 border-b border-slate-100 last:border-0">
      <span className="w-44 shrink-0 text-sm text-slate-400">{label}</span>
      <span className="text-sm text-slate-900">{value ?? "—"}</span>
    </div>
  );
}

export default function CompanyDetailPage() {
  const { data: session, status } = useSession();
  const params = useParams();
  const id = params.id as string;
  const [company, setCompany] = useState<Company | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    if (status !== "authenticated") return;
    fetch(`${API_BASE}/companies/${id}`, {
      headers: {
        "X-User-Id": session?.user?.id ?? "",
        "X-User-Role": session?.user?.role ?? "GP",
      },
    })
      .then((res) => {
        if (res.status === 404) { setNotFound(true); return null; }
        return res.json();
      })
      .then((data) => { if (data) setCompany(data); })
      .finally(() => setLoading(false));
  }, [id, status, session]);

  if (loading) {
    return (
      <div className="p-6 max-w-3xl mx-auto space-y-4">
        <div className="h-6 w-48 bg-slate-100 rounded animate-pulse" />
        <div className="h-64 bg-slate-100 rounded-xl animate-pulse" />
      </div>
    );
  }

  if (notFound || !company) {
    return (
      <div className="p-6 max-w-3xl mx-auto">
        <p className="text-slate-500">Company not found.</p>
        <Link href="/companies" className="text-sm text-slate-400 hover:text-slate-600 mt-2 inline-block">
          ← Back to Companies
        </Link>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <Link
        href="/companies"
        className="inline-flex items-center gap-1 text-sm text-slate-400 hover:text-slate-600 transition-colors mb-6"
      >
        <ChevronLeft className="w-4 h-4" />
        Back to Companies
      </Link>

      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">{company.name}</h1>
          {company.website && (
            <a
              href={company.website.startsWith("http") ? company.website : `https://${company.website}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-slate-400 hover:text-slate-600 mt-0.5 inline-block"
            >
              {company.website.replace(/^https?:\/\//, "")}
            </a>
          )}
        </div>
        <div className="flex gap-2">
          <Badge className={getSectorColor(company.sector)}>{company.sector}</Badge>
          <Badge className={STAGE_COLORS[company.stage]}>{company.stage}</Badge>
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl p-5 mb-4">
        <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">Overview</h2>
        <Row label="HQ Location" value={company.hq_location} />
        <Row label="Employees" value={company.employee_count?.toLocaleString()} />
        <Row label="Ownership" value={company.ownership_type} />
        <Row label="Source" value={company.source} />
        <Row label="AI Fit Score" value={company.ai_fit_score ? `${company.ai_fit_score}/100` : "—"} />
      </div>

      <div className="bg-white border border-slate-200 rounded-xl p-5 mb-4">
        <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">Financials</h2>
        <Row
          label="Revenue"
          value={
            company.revenue_low || company.revenue_high
              ? `${formatMoney(company.revenue_low)} – ${formatMoney(company.revenue_high)}`
              : "—"
          }
        />
        <Row
          label="EBITDA"
          value={
            company.ebitda_low || company.ebitda_high
              ? `${formatMoney(company.ebitda_low)} – ${formatMoney(company.ebitda_high)}`
              : "—"
          }
        />
      </div>

      {company.notes && (
        <div className="bg-white border border-slate-200 rounded-xl p-5">
          <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">Notes</h2>
          <p className="text-sm text-slate-700 whitespace-pre-wrap">{company.notes}</p>
        </div>
      )}
    </div>
  );
}
