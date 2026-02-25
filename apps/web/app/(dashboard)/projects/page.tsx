"use client";

import { useState, useEffect, useCallback } from "react";
import { useSession } from "next-auth/react";
import type {
  Project, ProjectDetail, ProjectColor,
  EnrichmentStatusResponse, OutreachThread,
} from "@/types";
import {
  FolderOpen, Plus, ChevronRight, Loader2,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { ProjectCRM } from "@/components/projects/ProjectCRM";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

// Color config
const COLOR_MAP: Record<ProjectColor, { dot: string; bg: string; text: string; border: string }> = {
  slate:  { dot: "bg-slate-400",  bg: "bg-slate-50",  text: "text-slate-700",  border: "border-slate-200" },
  blue:   { dot: "bg-blue-500",   bg: "bg-blue-50",   text: "text-blue-700",   border: "border-blue-200"  },
  green:  { dot: "bg-green-500",  bg: "bg-green-50",  text: "text-green-700",  border: "border-green-200" },
  amber:  { dot: "bg-amber-500",  bg: "bg-amber-50",  text: "text-amber-700",  border: "border-amber-200" },
  red:    { dot: "bg-red-500",    bg: "bg-red-50",    text: "text-red-700",    border: "border-red-200"   },
  purple: { dot: "bg-purple-500", bg: "bg-purple-50", text: "text-purple-700", border: "border-purple-200"},
  pink:   { dot: "bg-pink-500",   bg: "bg-pink-50",   text: "text-pink-700",   border: "border-pink-200"  },
  indigo: { dot: "bg-indigo-500", bg: "bg-indigo-50", text: "text-indigo-700", border: "border-indigo-200"},
  teal:   { dot: "bg-teal-500",   bg: "bg-teal-50",   text: "text-teal-700",   border: "border-teal-200"  },
  orange: { dot: "bg-orange-500", bg: "bg-orange-50", text: "text-orange-700", border: "border-orange-200"},
};
const COLORS = Object.keys(COLOR_MAP) as ProjectColor[];

function ColorPicker({ value, onChange }: { value: ProjectColor; onChange: (c: ProjectColor) => void }) {
  return (
    <div className="flex items-center gap-2 flex-wrap">
      {COLORS.map((c) => (
        <button
          key={c}
          type="button"
          onClick={() => onChange(c)}
          className={`w-6 h-6 rounded-full ${COLOR_MAP[c].dot} ${value === c ? "ring-2 ring-offset-1 ring-slate-900" : "opacity-70 hover:opacity-100"} transition-all`}
          title={c}
        />
      ))}
    </div>
  );
}

export default function ProjectsPage() {
  const { data: session, status } = useSession();
  const [projects, setProjects] = useState<Project[]>([]);
  const [selected, setSelected] = useState<ProjectDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [newColor, setNewColor] = useState<ProjectColor>("blue");
  const [creating, setCreating] = useState(false);

  // Enrichment state
  const [enrichmentMap, setEnrichmentMap] = useState<Record<string, EnrichmentStatusResponse>>({});
  const [enrichingIds, setEnrichingIds] = useState<Set<string>>(new Set());
  const [bulkEnriching, setBulkEnriching] = useState(false);

  // Thread state (CRM)
  const [threads, setThreads] = useState<OutreachThread[]>([]);

  const authHeaders = {
    "Content-Type": "application/json",
    "X-User-Id": session?.user?.id ?? "",
    "X-User-Role": session?.user?.role ?? "GP",
  };

  // --- Projects CRUD ---
  const loadProjects = useCallback(async () => {
    if (status !== "authenticated") return;
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/projects`, { headers: authHeaders });
      if (res.ok) setProjects(await res.json());
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  useEffect(() => { loadProjects(); }, [loadProjects]);

  const loadThreads = useCallback(async (projectId: string) => {
    try {
      const res = await fetch(`${API_BASE}/outreach/threads?project_id=${projectId}`, { headers: authHeaders });
      if (res.ok) setThreads(await res.json());
    } catch { /* ignore */ }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session]);

  async function openProject(p: Project) {
    setDetailLoading(true);
    try {
      const res = await fetch(`${API_BASE}/projects/${p.id}`, { headers: authHeaders });
      if (res.ok) {
        const detail: ProjectDetail = await res.json();
        setSelected(detail);
        loadEnrichmentStatuses(detail.companies.map((c) => c.company_id));
        loadThreads(p.id);
      }
    } finally {
      setDetailLoading(false);
    }
  }

  async function createProject() {
    if (!newName.trim()) return;
    setCreating(true);
    try {
      const res = await fetch(`${API_BASE}/projects`, {
        method: "POST",
        headers: authHeaders,
        body: JSON.stringify({ name: newName.trim(), description: newDesc.trim() || null, color: newColor }),
      });
      if (res.ok) {
        const p: Project = await res.json();
        setProjects((prev) => [p, ...prev]);
        setShowCreate(false);
        setNewName("");
        setNewDesc("");
        setNewColor("blue");
        openProject(p);
      }
    } finally {
      setCreating(false);
    }
  }

  async function deleteProject() {
    if (!selected) return;
    if (!confirm(`Delete project "${selected.name}"? Companies will not be deleted.`)) return;
    await fetch(`${API_BASE}/projects/${selected.id}`, { method: "DELETE", headers: authHeaders });
    setProjects((prev) => prev.filter((x) => x.id !== selected.id));
    setSelected(null);
    setThreads([]);
  }

  async function removeCompany(companyId: string) {
    if (!selected) return;
    await fetch(`${API_BASE}/projects/${selected.id}/companies/${companyId}`, {
      method: "DELETE",
      headers: authHeaders,
    });
    setSelected((prev) =>
      prev ? { ...prev, companies: prev.companies.filter((c) => c.company_id !== companyId) } : null
    );
    setProjects((prev) =>
      prev.map((p) => p.id === selected.id ? { ...p, company_count: p.company_count - 1 } : p)
    );
  }

  // --- Enrichment ---
  async function loadEnrichmentStatuses(companyIds: string[]) {
    const results: Record<string, EnrichmentStatusResponse> = {};
    await Promise.all(
      companyIds.map(async (cid) => {
        try {
          const res = await fetch(`${API_BASE}/enrichment/company/${cid}/status`, { headers: authHeaders });
          if (res.ok) results[cid] = await res.json();
        } catch { /* ignore */ }
      })
    );
    setEnrichmentMap(results);
  }

  async function enrichSingle(companyId: string) {
    setEnrichingIds((prev) => new Set([...prev, companyId]));
    try {
      const res = await fetch(`${API_BASE}/enrichment/company/${companyId}`, {
        method: "POST",
        headers: authHeaders,
      });
      if (res.ok) {
        const statusRes = await fetch(`${API_BASE}/enrichment/company/${companyId}/status`, { headers: authHeaders });
        if (statusRes.ok) {
          const data = await statusRes.json();
          setEnrichmentMap((prev) => ({ ...prev, [companyId]: data }));
        }
      }
    } finally {
      setEnrichingIds((prev) => {
        const next = new Set(prev);
        next.delete(companyId);
        return next;
      });
    }
  }

  async function enrichAll() {
    if (!selected) return;
    setBulkEnriching(true);
    try {
      await fetch(`${API_BASE}/enrichment/project/${selected.id}`, {
        method: "POST",
        headers: authHeaders,
      });
      loadEnrichmentStatuses(selected.companies.map((c) => c.company_id));
    } finally {
      setBulkEnriching(false);
    }
  }

  // --- Thread handlers ---
  const handleThreadsChanged = useCallback(() => {
    if (selected) loadThreads(selected.id);
  }, [selected, loadThreads]);

  const handleThreadUpdated = useCallback((updated: OutreachThread) => {
    setThreads((prev) => {
      const exists = prev.find((t) => t.id === updated.id);
      if (exists) {
        return prev.map((t) => t.id === updated.id ? updated : t);
      }
      return [updated, ...prev];
    });
  }, []);

  const handleEnrichmentUpdated = useCallback((companyId: string, data: EnrichmentStatusResponse) => {
    setEnrichmentMap((prev) => ({ ...prev, [companyId]: data }));
  }, []);

  // --- Render ---
  if (status === "loading" || loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
      </div>
    );
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-emerald-500/10 flex items-center justify-center">
            <FolderOpen className="w-5 h-5 text-emerald-600" />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-slate-900">Projects</h1>
            <p className="text-sm text-slate-400">Enrich contacts, draft outreach, and manage the pipeline</p>
          </div>
        </div>
        <Button onClick={() => setShowCreate(true)} className="flex items-center gap-2">
          <Plus className="w-4 h-4" />
          New Project
        </Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Left: project list */}
        <div className="space-y-2">
          {showCreate && (
            <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-3">
              <input
                autoFocus
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && createProject()}
                placeholder="Project name…"
                className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <input
                value={newDesc}
                onChange={(e) => setNewDesc(e.target.value)}
                placeholder="Description (optional)"
                className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <ColorPicker value={newColor} onChange={setNewColor} />
              <div className="flex gap-2">
                <Button onClick={createProject} disabled={creating || !newName.trim()} className="flex-1 text-sm">
                  {creating ? "Creating…" : "Create"}
                </Button>
                <button
                  onClick={() => setShowCreate(false)}
                  className="px-3 py-1.5 text-sm text-slate-500 hover:text-slate-700 border border-slate-200 rounded-lg"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {projects.length === 0 && !showCreate ? (
            <div className="text-center py-16 text-slate-400">
              <FolderOpen className="w-8 h-8 mx-auto mb-2 opacity-40" />
              <p className="text-sm">No projects yet. Life, don&apos;t talk to me about life.</p>
              <button
                onClick={() => setShowCreate(true)}
                className="mt-2 text-xs text-emerald-600 hover:text-emerald-700 font-medium"
              >
                Create your first project →
              </button>
            </div>
          ) : (
            projects.map((p) => {
              const c = COLOR_MAP[p.color as ProjectColor] ?? COLOR_MAP.slate;
              const isActive = selected?.id === p.id;
              return (
                <button
                  key={p.id}
                  onClick={() => openProject(p)}
                  className={`w-full text-left flex items-center gap-3 px-4 py-3 rounded-xl border transition-all ${
                    isActive
                      ? `${c.bg} ${c.border} border`
                      : "bg-white border-slate-200 hover:border-slate-300 hover:bg-slate-50"
                  }`}
                >
                  <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${c.dot}`} />
                  <span className={`flex-1 text-sm font-medium truncate ${isActive ? c.text : "text-slate-700"}`}>
                    {p.name}
                  </span>
                  <span className="text-xs text-slate-400 shrink-0">{p.company_count}</span>
                  <ChevronRight className="w-3.5 h-3.5 text-slate-300 shrink-0" />
                </button>
              );
            })
          )}
        </div>

        {/* Right: CRM view */}
        <div className="lg:col-span-3">
          {detailLoading && (
            <div className="flex items-center justify-center h-40">
              <Loader2 className="w-5 h-5 animate-spin text-slate-400" />
            </div>
          )}

          {!detailLoading && !selected && (
            <div className="h-full flex items-center justify-center text-slate-400 text-sm py-24">
              Select a project to open the outreach CRM
            </div>
          )}

          {!detailLoading && selected && (
            <ProjectCRM
              project={selected}
              enrichmentMap={enrichmentMap}
              enrichingIds={enrichingIds}
              threads={threads}
              bulkEnriching={bulkEnriching}
              onEnrichSingle={enrichSingle}
              onEnrichAll={enrichAll}
              onRemoveCompany={removeCompany}
              onDeleteProject={deleteProject}
              onThreadsChanged={handleThreadsChanged}
              onThreadUpdated={handleThreadUpdated}
              onEnrichmentUpdated={handleEnrichmentUpdated}
            />
          )}
        </div>
      </div>
    </div>
  );
}
