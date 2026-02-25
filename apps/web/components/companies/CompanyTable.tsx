"use client";

import { useState } from "react";
import Link from "next/link";
import { Badge } from "@/components/ui/Badge";
import { STAGE_COLORS, getSectorColor } from "@/lib/constants";
import type { Company } from "@/types";
import { Building2, FolderPlus } from "lucide-react";
import { AddToProjectModal } from "@/components/projects/AddToProjectModal";

interface CompanyTableProps {
  companies: Company[];
  loading: boolean;
}

function formatEbitda(low: number | null, high: number | null): string {
  if (!low && !high) return "—";
  const fmt = (n: number) =>
    n >= 1_000_000
      ? `$${(n / 1_000_000).toFixed(1)}M`
      : `$${(n / 1_000).toFixed(0)}K`;
  if (low && high) return `${fmt(low)}–${fmt(high)}`;
  if (low) return `${fmt(low)}+`;
  return `Up to ${fmt(high!)}`;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function SkeletonRow() {
  return (
    <tr className="border-t border-slate-100">
      {[1, 2, 3, 4, 5, 6].map((i) => (
        <td key={i} className="px-4 py-3">
          <div className="h-4 bg-slate-100 rounded animate-pulse" />
        </td>
      ))}
    </tr>
  );
}

export function CompanyTable({ companies, loading }: CompanyTableProps) {
  const [addToProject, setAddToProject] = useState<{ id: string; name: string } | null>(null);

  return (
    <>
    {addToProject && (
      <AddToProjectModal
        companyId={addToProject.id}
        companyName={addToProject.name}
        onClose={() => setAddToProject(null)}
      />
    )}
    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-slate-50 border-b border-slate-200">
            <th className="text-left px-4 py-3 font-medium text-slate-600">
              Company
            </th>
            <th className="text-left px-4 py-3 font-medium text-slate-600">
              Sector
            </th>
            <th className="text-left px-4 py-3 font-medium text-slate-600">
              Stage
            </th>
            <th className="text-left px-4 py-3 font-medium text-slate-600">
              EBITDA
            </th>
            <th className="text-left px-4 py-3 font-medium text-slate-600">
              HQ
            </th>
            <th className="text-left px-4 py-3 font-medium text-slate-600">
              Added
            </th>
            <th className="px-4 py-3" />
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <>
              <SkeletonRow />
              <SkeletonRow />
              <SkeletonRow />
              <SkeletonRow />
              <SkeletonRow />
            </>
          ) : companies.length === 0 ? (
            <tr>
              <td colSpan={6} className="px-4 py-16 text-center">
                <Building2 className="w-8 h-8 text-slate-300 mx-auto mb-3" />
                <p className="text-slate-500 font-medium">No companies found</p>
                <p className="text-slate-400 text-xs mt-1">
                  Try adjusting your filters or add a new company.
                </p>
              </td>
            </tr>
          ) : (
            companies.map((company) => (
              <tr
                key={company.id}
                className="border-t border-slate-100 hover:bg-slate-50 transition-colors"
              >
                <td className="px-4 py-3">
                  <Link
                    href={`/companies/${company.id}`}
                    className="font-medium text-slate-900 hover:underline"
                  >
                    {company.name}
                  </Link>
                  {company.website && (
                    <a
                      href={
                        company.website.startsWith("http")
                          ? company.website
                          : `https://${company.website}`
                      }
                      target="_blank"
                      rel="noopener noreferrer"
                      className="block text-xs text-slate-400 hover:text-slate-600 mt-0.5"
                    >
                      {company.website.replace(/^https?:\/\//, "")}
                    </a>
                  )}
                </td>
                <td className="px-4 py-3">
                  <Badge className={getSectorColor(company.sector)}>
                    {company.sector}
                  </Badge>
                </td>
                <td className="px-4 py-3">
                  <Badge className={STAGE_COLORS[company.stage]}>
                    {company.stage}
                  </Badge>
                </td>
                <td className="px-4 py-3 text-slate-600">
                  {formatEbitda(company.ebitda_low, company.ebitda_high)}
                </td>
                <td className="px-4 py-3 text-slate-600">
                  {company.hq_location ?? "—"}
                </td>
                <td className="px-4 py-3 text-slate-500">
                  {formatDate(company.created_at)}
                </td>
                <td className="px-4 py-3 text-right">
                  <button
                    onClick={() => setAddToProject({ id: company.id, name: company.name })}
                    className="p-1.5 text-slate-300 hover:text-blue-500 hover:bg-blue-50 rounded transition-colors"
                    title="Add to project"
                  >
                    <FolderPlus className="w-4 h-4" />
                  </button>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>

      {!loading && companies.length > 0 && (
        <div className="px-4 py-3 border-t border-slate-100 bg-slate-50">
          <p className="text-xs text-slate-400">
            {companies.length} {companies.length === 1 ? "company" : "companies"}
          </p>
        </div>
      )}
    </div>
    </>
  );
}
