"use client";

import { useState, useEffect, useCallback } from "react";
import { useSession } from "next-auth/react";
import type { Project, ProjectColor } from "@/types";
import { FolderOpen, Plus, Check, Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/Button";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

const COLOR_DOT: Record<ProjectColor, string> = {
  slate: "bg-slate-400", blue: "bg-blue-500", green: "bg-green-500",
  amber: "bg-amber-500", red: "bg-red-500", purple: "bg-purple-500",
  pink: "bg-pink-500", indigo: "bg-indigo-500", teal: "bg-teal-500",
  orange: "bg-orange-500",
};

interface Props {
  companyId: string;
  companyName: string;
  onClose: () => void;
}

export function AddToProjectModal({ companyId, companyName, onClose }: Props) {
  const { data: session } = useSession();
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState<string | null>(null); // project id being added
  const [added, setAdded] = useState<Set<string>>(new Set());
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);

  const authHeaders = {
    "Content-Type": "application/json",
    "X-User-Id": session?.user?.id ?? "",
    "X-User-Role": session?.user?.role ?? "GP",
  };

  const loadProjects = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/projects`, { headers: authHeaders });
      if (res.ok) setProjects(await res.json());
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { loadProjects(); }, [loadProjects]);

  async function addToProject(projectId: string) {
    if (adding || added.has(projectId)) return;
    setAdding(projectId);
    try {
      const res = await fetch(`${API_BASE}/projects/${projectId}/companies`, {
        method: "POST",
        headers: authHeaders,
        body: JSON.stringify({ company_id: companyId }),
      });
      if (res.ok) {
        setAdded((prev) => new Set([...prev, projectId]));
        setProjects((prev) =>
          prev.map((p) =>
            p.id === projectId ? { ...p, company_count: p.company_count + 1 } : p
          )
        );
      }
    } finally {
      setAdding(null);
    }
  }

  async function createAndAdd() {
    if (!newName.trim()) return;
    setCreating(true);
    try {
      const res = await fetch(`${API_BASE}/projects`, {
        method: "POST",
        headers: authHeaders,
        body: JSON.stringify({ name: newName.trim(), color: "blue" }),
      });
      if (res.ok) {
        const p: Project = await res.json();
        setProjects((prev) => [p, ...prev]);
        setNewName("");
        setShowCreate(false);
        await addToProject(p.id);
      }
    } finally {
      setCreating(false);
    }
  }

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/20 backdrop-blur-sm z-50" onClick={onClose} />

      {/* Modal */}
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 pointer-events-none">
        <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm pointer-events-auto">
          {/* Header */}
          <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
            <div className="flex items-center gap-2">
              <FolderOpen className="w-4 h-4 text-slate-500" />
              <h3 className="text-sm font-semibold text-slate-900">Add to project</h3>
            </div>
            <button onClick={onClose} className="p-1 text-slate-400 hover:text-slate-600 rounded">
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="px-5 py-2">
            <p className="text-xs text-slate-400 py-2 truncate">
              <span className="font-medium text-slate-600">{companyName}</span>
            </p>
          </div>

          {/* Project list */}
          <div className="max-h-64 overflow-y-auto px-5 pb-2 space-y-1">
            {loading ? (
              <div className="flex justify-center py-6">
                <Loader2 className="w-5 h-5 animate-spin text-slate-400" />
              </div>
            ) : projects.length === 0 ? (
              <p className="text-sm text-slate-400 text-center py-4">No projects yet</p>
            ) : (
              projects.map((p) => {
                const isAdded = added.has(p.id);
                const isAdding = adding === p.id;
                return (
                  <button
                    key={p.id}
                    onClick={() => addToProject(p.id)}
                    disabled={isAdded || isAdding}
                    className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-colors ${
                      isAdded
                        ? "bg-green-50 cursor-default"
                        : "hover:bg-slate-50 active:bg-slate-100"
                    }`}
                  >
                    <span className={`w-2 h-2 rounded-full shrink-0 ${COLOR_DOT[p.color as ProjectColor] ?? "bg-slate-400"}`} />
                    <span className="flex-1 text-sm text-slate-700 truncate">{p.name}</span>
                    <span className="text-xs text-slate-400 shrink-0">{p.company_count}</span>
                    {isAdding ? (
                      <Loader2 className="w-4 h-4 animate-spin text-slate-400 shrink-0" />
                    ) : isAdded ? (
                      <Check className="w-4 h-4 text-green-500 shrink-0" />
                    ) : null}
                  </button>
                );
              })
            )}
          </div>

          {/* Create new project inline */}
          <div className="px-5 pb-5 pt-3 border-t border-slate-100 mt-2">
            {showCreate ? (
              <div className="space-y-2">
                <input
                  autoFocus
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && createAndAdd()}
                  placeholder="New project name…"
                  className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <div className="flex gap-2">
                  <Button
                    onClick={createAndAdd}
                    disabled={creating || !newName.trim()}
                    className="flex-1 text-sm h-8"
                  >
                    {creating ? "Creating…" : "Create & add"}
                  </Button>
                  <button
                    onClick={() => { setShowCreate(false); setNewName(""); }}
                    className="text-sm text-slate-500 hover:text-slate-700"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <button
                onClick={() => setShowCreate(true)}
                className="flex items-center gap-2 text-sm text-slate-500 hover:text-slate-700 transition-colors"
              >
                <Plus className="w-4 h-4" />
                New project
              </button>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
