"use client";

import { useState, useEffect, useCallback } from "react";
import { useSession } from "next-auth/react";
import Link from "next/link";
import { CompanyTable } from "@/components/companies/CompanyTable";
import { CompanyFilters } from "@/components/companies/CompanyFilters";
import { Button } from "@/components/ui/Button";
import { Plus } from "lucide-react";
import type { Company } from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

interface Filters {
  sector: string;
  stage: string;
  search: string;
}

export default function CompaniesPage() {
  const { data: session, status } = useSession();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [filters, setFilters] = useState<Filters>({
    sector: "",
    stage: "",
    search: "",
  });
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (status !== "authenticated") return;
    setLoading(true);
    try {
      const filtered = Object.fromEntries(
        Object.entries(filters).filter(([, v]) => v !== "")
      );
      const qs = new URLSearchParams(filtered).toString();
      const res = await fetch(`${API_BASE}/companies/${qs ? `?${qs}` : ""}`, {
        headers: {
          "Content-Type": "application/json",
          "X-User-Id": session?.user?.id ?? "",
          "X-User-Role": session?.user?.role ?? "GP",
        },
      });
      const data = await res.json();
      setCompanies(Array.isArray(data) ? data : []);
    } catch {
      setCompanies([]);
    } finally {
      setLoading(false);
    }
  }, [filters, status, session]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="p-6 space-y-5 max-w-7xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Companies</h1>
          <p className="text-sm text-slate-400 mt-0.5">
            Every entity in the known universe (or at least your database)
          </p>
        </div>
        <Link href="/companies/new">
          <Button>
            <Plus className="w-4 h-4 mr-1.5" />
            Add Company
          </Button>
        </Link>
      </div>

      <CompanyFilters values={filters} onChange={setFilters} />
      <CompanyTable companies={companies} loading={loading} />
    </div>
  );
}
