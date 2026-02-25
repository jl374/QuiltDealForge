"use client";

import { useState, useEffect, useCallback } from "react";
import { useSession } from "next-auth/react";
import type { SourcingResultItem, SourcingCriteria, CompanyAnalysis } from "@/types";
import {
  X, ExternalLink, Loader2, Phone, MapPin, Globe,
  Users, Building2, Lightbulb, FileText, RefreshCw,
} from "lucide-react";
import { Button } from "@/components/ui/Button";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

interface Props {
  item: SourcingResultItem;
  criteria: SourcingCriteria;
  onClose: () => void;
  onImport: (item: SourcingResultItem) => void;
  importing: boolean;
  imported: boolean;
}

function Section({
  icon: Icon,
  title,
  children,
}: {
  icon: React.ElementType;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <Icon className="w-4 h-4 text-slate-400" />
        <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wide">{title}</h4>
      </div>
      <div className="pl-6 text-sm text-slate-700 leading-relaxed">{children}</div>
    </div>
  );
}

function BulletList({ text }: { text: string }) {
  const lines = text
    .split("\n")
    .map((l) => l.replace(/^[•\-\*]\s*/, "").trim())
    .filter(Boolean);
  return (
    <ul className="space-y-1">
      {lines.map((line, i) => (
        <li key={i} className="flex gap-2">
          <span className="text-slate-300 mt-0.5">•</span>
          <span>{line}</span>
        </li>
      ))}
    </ul>
  );
}

export function CompanyDeepDive({ item, criteria, onClose, onImport, importing, imported }: Props) {
  const { data: session } = useSession();
  const [analysis, setAnalysis] = useState<CompanyAnalysis | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const authHeaders = {
    "Content-Type": "application/json",
    "X-User-Id": session?.user?.id ?? "",
    "X-User-Role": session?.user?.role ?? "GP",
  };

  const fetchDeepDive = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${API_BASE}/sourcing/analyze`, {
        method: "POST",
        headers: authHeaders,
        body: JSON.stringify({
          company: item,
          criteria,
          mode: "deep_dive",
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: CompanyAnalysis = await res.json();
      setAnalysis(data);
    } catch (e) {
      setError("Failed to load analysis. Please try again.");
      console.error(e);
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [item.name, item.source]);

  useEffect(() => {
    fetchDeepDive();
  }, [fetchDeepDive]);

  const isActiveBusiness = ["NPPES", "OpenStreetMap", "Google Places"].includes(item.source);
  const phone = item.extra?.phone as string | undefined;
  const address = item.extra?.address as string | undefined;
  const npi = item.extra?.npi as string | undefined;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/30 backdrop-blur-sm z-40"
        onClick={onClose}
      />

      {/* Slide-over panel */}
      <div className="fixed inset-y-0 right-0 w-full max-w-xl bg-white shadow-2xl z-50 flex flex-col">
        {/* Header */}
        <div className="flex items-start justify-between px-6 py-5 border-b border-slate-200">
          <div className="flex-1 min-w-0 pr-4">
            <div className="flex items-center gap-2 mb-1">
              {isActiveBusiness && (
                <span className="inline-flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded-full bg-green-100 text-green-700">
                  <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
                  Active Business
                </span>
              )}
              <span className="text-[10px] text-slate-400">{item.source}</span>
            </div>
            <h2 className="text-lg font-semibold text-slate-900 leading-snug">{item.name}</h2>
            <div className="flex flex-wrap items-center gap-3 mt-1.5 text-xs text-slate-500">
              {item.location && (
                <span className="flex items-center gap-1">
                  <MapPin className="w-3 h-3" /> {item.location}
                </span>
              )}
              {(item.sector && item.sector !== criteria.sector) && (
                <span className="flex items-center gap-1">
                  <Building2 className="w-3 h-3" /> {item.sector}
                </span>
              )}
              {item.asking_price && (
                <span className="font-medium text-slate-700">Asking: {item.asking_price}</span>
              )}
              {item.revenue && (
                <span>Revenue: {item.revenue}</span>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {item.source_url && !isActiveBusiness && (
              <a
                href={item.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
                title="View listing"
              >
                <ExternalLink className="w-4 h-4" />
              </a>
            )}
            <button
              onClick={onClose}
              className="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-6">

          {/* Quick contact strip */}
          {(phone || address || item.source_url) && (
            <div className="bg-slate-50 rounded-xl p-4 space-y-2 text-sm">
              {phone && (
                <div className="flex items-center gap-2 text-slate-700">
                  <Phone className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                  <a href={`tel:${phone}`} className="hover:text-blue-600">{phone}</a>
                </div>
              )}
              {address && (
                <div className="flex items-start gap-2 text-slate-700">
                  <MapPin className="w-3.5 h-3.5 text-slate-400 shrink-0 mt-0.5" />
                  <span>{address}</span>
                </div>
              )}
              {item.website && !isActiveBusiness && (
                <div className="flex items-center gap-2 text-slate-700">
                  <Globe className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                  <a href={item.website} target="_blank" rel="noopener noreferrer" className="hover:text-blue-600 truncate">
                    {item.website.replace(/^https?:\/\//, "")}
                  </a>
                </div>
              )}
              {npi && (
                <div className="flex items-center gap-2 text-slate-500 text-xs">
                  <FileText className="w-3.5 h-3.5 shrink-0" />
                  NPI #{npi}
                </div>
              )}
            </div>
          )}

          {/* AI Analysis */}
          {loading && (
            <div className="flex flex-col items-center justify-center py-16 gap-3 text-slate-400">
              <Loader2 className="w-6 h-6 animate-spin" />
              <p className="text-sm">Researching {item.name}…</p>
              <p className="text-xs">Gathering web data and generating analysis</p>
            </div>
          )}

          {error && (
            <div className="flex items-center gap-3 bg-red-50 border border-red-200 rounded-xl p-4">
              <p className="text-sm text-red-600 flex-1">{error}</p>
              <button
                onClick={fetchDeepDive}
                className="shrink-0 p-1.5 text-red-500 hover:text-red-700 hover:bg-red-100 rounded"
              >
                <RefreshCw className="w-4 h-4" />
              </button>
            </div>
          )}

          {analysis && !loading && (
            <div className="space-y-6">
              {/* Business Summary */}
              {analysis.business_summary && (
                <Section icon={Building2} title="Business Overview">
                  <p>{analysis.business_summary}</p>
                </Section>
              )}

              {/* Service Lines */}
              {analysis.service_lines && (
                <Section icon={FileText} title="Service Lines">
                  <BulletList text={analysis.service_lines} />
                </Section>
              )}

              {/* Leadership */}
              {analysis.leadership && (
                <Section icon={Users} title="Leadership">
                  <p className="whitespace-pre-line">{analysis.leadership}</p>
                </Section>
              )}

              {/* Contact from AI research */}
              {analysis.contact && (
                <Section icon={Phone} title="Contact Information">
                  <p className="whitespace-pre-line">{analysis.contact}</p>
                </Section>
              )}

              {/* Fit Rationale */}
              {analysis.fit_rationale && (
                <Section icon={Lightbulb} title="Why This Fits">
                  <p className="text-slate-700 bg-amber-50 border border-amber-100 rounded-lg p-3">
                    {analysis.fit_rationale}
                  </p>
                </Section>
              )}

              {/* Research sources */}
              {analysis.research_sources && analysis.research_sources.length > 0 && (
                <div className="border-t border-slate-100 pt-4">
                  <p className="text-[11px] text-slate-400 mb-1.5">Research sources</p>
                  <div className="space-y-1">
                    {analysis.research_sources.map((src, i) => (
                      <a
                        key={i}
                        href={src}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="block text-[11px] text-slate-400 hover:text-blue-500 truncate"
                      >
                        {src}
                      </a>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Original description fallback */}
          {!loading && !analysis && !error && item.description && (
            <Section icon={FileText} title="Description">
              <p className="text-slate-600">{item.description}</p>
            </Section>
          )}
        </div>

        {/* Footer actions */}
        <div className="border-t border-slate-200 px-6 py-4 flex items-center gap-3">
          <Button
            onClick={() => onImport(item)}
            disabled={importing || imported}
            className="flex-1"
          >
            {imported ? "✓ Added to Pipeline" : importing ? "Adding…" : "Add to Pipeline"}
          </Button>
          {item.source_url && (
            <a
              href={item.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 border border-slate-200 rounded-lg px-4 py-2 hover:bg-slate-50 transition-colors"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              View source
            </a>
          )}
        </div>
      </div>
    </>
  );
}
