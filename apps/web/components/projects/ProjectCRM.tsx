"use client";

import { useState, useCallback } from "react";
import { useSession } from "next-auth/react";
import type {
  ProjectDetail, ProjectColor, EnrichmentStatusResponse,
  OutreachThread,
} from "@/types";
import {
  Search, UserCheck, UserX, Mail, X, Loader2,
  ChevronDown, ChevronRight,
} from "lucide-react";
import { getSectorColor, STAGE_COLORS } from "@/lib/constants";
import { ThreadStatusBadge } from "./ThreadStatusBadge";
import { CompanyDetailPanel } from "./CompanyDetailPanel";
import { DraftsGrid } from "./DraftsGrid";
import { FollowUpPanel } from "./FollowUpPanel";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type Tab = "pipeline" | "drafts" | "followups";

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

interface ProjectCRMProps {
  project: ProjectDetail;
  enrichmentMap: Record<string, EnrichmentStatusResponse>;
  enrichingIds: Set<string>;
  threads: OutreachThread[];
  bulkEnriching: boolean;
  onEnrichSingle: (companyId: string) => void;
  onEnrichAll: () => void;
  onRemoveCompany: (companyId: string) => void;
  onDeleteProject: () => void;
  onThreadsChanged: () => void;
  onThreadUpdated: (thread: OutreachThread) => void;
  onEnrichmentUpdated: (companyId: string, data: EnrichmentStatusResponse) => void;
}

export function ProjectCRM({
  project,
  enrichmentMap,
  enrichingIds,
  threads,
  bulkEnriching,
  onEnrichSingle,
  onEnrichAll,
  onRemoveCompany,
  onDeleteProject,
  onThreadsChanged,
  onThreadUpdated,
  onEnrichmentUpdated,
}: ProjectCRMProps) {
  const { data: session } = useSession();
  const [activeTab, setActiveTab] = useState<Tab>("pipeline");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [bulkGenerating, setBulkGenerating] = useState(false);

  const authHeaders = {
    "Content-Type": "application/json",
    "X-User-Id": session?.user?.id ?? "",
    "X-User-Role": session?.user?.role ?? "GP",
  };

  const colors = COLOR_MAP[project.color as ProjectColor] ?? COLOR_MAP.slate;

  const enrichedCount = project.companies.filter(
    (c) => enrichmentMap[c.company_id]?.status === "completed"
  ).length;

  // Build thread map: company_id -> thread
  const threadMap: Record<string, OutreachThread> = {};
  for (const t of threads) {
    threadMap[t.company_id] = t;
  }

  const handleBulkGenerate = useCallback(async () => {
    setBulkGenerating(true);
    try {
      const enrichedCompanyIds = project.companies
        .filter((c) => enrichmentMap[c.company_id]?.contact?.email)
        .map((c) => c.company_id);

      if (enrichedCompanyIds.length === 0) {
        alert("No enriched companies with email addresses. Enrich companies first.");
        return;
      }

      await fetch(`${API_BASE}/outreach/threads/bulk-generate`, {
        method: "POST",
        headers: authHeaders,
        body: JSON.stringify({
          project_id: project.id,
          company_ids: enrichedCompanyIds,
          message_type: "initial",
        }),
      });
      onThreadsChanged();
    } finally {
      setBulkGenerating(false);
    }
  }, [project, enrichmentMap, authHeaders, onThreadsChanged]);

  const tabs: { key: Tab; label: string; count?: number }[] = [
    { key: "pipeline", label: "Pipeline", count: project.companies.length },
    { key: "drafts", label: "Drafts", count: threads.reduce((n, t) => n + t.messages.length, 0) },
    { key: "followups", label: "Follow-ups", count: threads.filter((t) => ["awaiting_response", "responded", "meeting_scheduled", "sent"].includes(t.status)).length },
  ];

  return (
    <div className="space-y-0">
      {/* Project header */}
      <div className={`px-6 py-4 rounded-t-xl border ${colors.bg} ${colors.border}`}>
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-slate-900">{project.name}</h2>
            {project.description && (
              <p className="text-sm text-slate-500 mt-0.5">{project.description}</p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={onEnrichAll}
              disabled={bulkEnriching || project.companies.length === 0}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-purple-700 bg-purple-50 hover:bg-purple-100 rounded-lg border border-purple-200 transition-colors disabled:opacity-50"
            >
              {bulkEnriching ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Search className="w-3.5 h-3.5" />}
              {bulkEnriching ? "Enriching..." : "Enrich All"}
            </button>
            <button
              onClick={onDeleteProject}
              className="p-2 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors"
              title="Delete project"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
        <p className="text-xs text-slate-400 mt-2">
          {project.company_count} {project.company_count === 1 ? "company" : "companies"}
          {enrichedCount > 0 && ` · ${enrichedCount} enriched`}
          {threads.length > 0 && ` · ${threads.length} threads`}
          {" "}· Created {new Date(project.created_at).toLocaleDateString()}
        </p>
      </div>

      {/* Tabs */}
      <div className="flex border-x border-slate-200 bg-white">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`flex-1 py-2.5 text-sm font-medium text-center transition-colors border-b-2 ${
              activeTab === tab.key
                ? "border-slate-900 text-slate-900"
                : "border-transparent text-slate-400 hover:text-slate-600"
            }`}
          >
            {tab.label}
            {tab.count !== undefined && tab.count > 0 && (
              <span className="ml-1.5 text-xs text-slate-400">({tab.count})</span>
            )}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="bg-white border border-t-0 border-slate-200 rounded-b-xl overflow-hidden">
        {activeTab === "pipeline" && (
          <div>
            {project.companies.length === 0 ? (
              <div className="py-16 text-center text-slate-400">
                <p className="text-sm">No companies yet</p>
                <p className="text-xs mt-1">Add companies from the Discover or Pipeline pages.</p>
              </div>
            ) : (
              <div className="divide-y divide-slate-100">
                {project.companies.map((pc) => {
                  const enrichment = enrichmentMap[pc.company_id];
                  const isEnriching = enrichingIds.has(pc.company_id);
                  const isEnriched = enrichment?.status === "completed";
                  const isFailed = enrichment?.status === "failed";
                  const ownerContact = enrichment?.contact;
                  const thread = threadMap[pc.company_id];
                  const isExpanded = expandedId === pc.company_id;

                  return (
                    <div key={pc.id}>
                      {/* Company row */}
                      <div
                        className={`flex items-center gap-3 px-6 py-3 cursor-pointer transition-colors ${
                          isExpanded ? "bg-slate-50" : "hover:bg-slate-50"
                        }`}
                        onClick={() => setExpandedId(isExpanded ? null : pc.company_id)}
                      >
                        {/* Expand chevron */}
                        <div className="shrink-0 text-slate-300">
                          {isExpanded ? (
                            <ChevronDown className="w-4 h-4" />
                          ) : (
                            <ChevronRight className="w-4 h-4" />
                          )}
                        </div>

                        {/* Enrichment indicator */}
                        <div className="shrink-0" onClick={(e) => e.stopPropagation()}>
                          {isEnriching ? (
                            <Loader2 className="w-4 h-4 animate-spin text-purple-400" />
                          ) : isEnriched ? (
                            <UserCheck className="w-4 h-4 text-green-500" />
                          ) : isFailed ? (
                            <button
                              onClick={() => onEnrichSingle(pc.company_id)}
                              className="p-0.5 text-red-400 hover:text-red-500 transition-colors"
                              title="Enrichment failed — click to retry"
                            >
                              <UserX className="w-4 h-4" />
                            </button>
                          ) : (
                            <button
                              onClick={() => onEnrichSingle(pc.company_id)}
                              className="p-0.5 text-slate-300 hover:text-purple-500 transition-colors"
                              title="Find owner info"
                            >
                              <Search className="w-4 h-4" />
                            </button>
                          )}
                        </div>

                        {/* Company info */}
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-slate-900 truncate">
                            {pc.company_name}
                          </p>
                          <div className="flex items-center gap-2 mt-0.5">
                            <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium ${getSectorColor(pc.company_sector)}`}>
                              {pc.company_sector}
                            </span>
                            <span className="text-xs text-slate-400">{pc.company_location}</span>
                          </div>
                          {isEnriched && ownerContact && (
                            <div className="flex items-center gap-2 mt-1">
                              <span className="text-xs text-slate-500">
                                {ownerContact.name}
                                {ownerContact.title && ` — ${ownerContact.title}`}
                              </span>
                              {ownerContact.email && (
                                <span className="flex items-center gap-1 text-xs text-blue-500">
                                  <Mail className="w-3 h-3" />
                                  {ownerContact.email}
                                </span>
                              )}
                            </div>
                          )}
                        </div>

                        {/* Thread status */}
                        {thread && <ThreadStatusBadge status={thread.status} />}

                        {/* Stage badge */}
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium ${(STAGE_COLORS as Record<string, string>)[pc.company_stage] ?? "bg-slate-100 text-slate-600"}`}>
                          {pc.company_stage}
                        </span>

                        {/* Remove button */}
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            onRemoveCompany(pc.company_id);
                          }}
                          className="p-1.5 text-slate-300 hover:text-red-400 hover:bg-red-50 rounded transition-colors"
                          title="Remove from project"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </div>

                      {/* Expanded detail panel */}
                      {isExpanded && (
                        <CompanyDetailPanel
                          company={pc}
                          enrichment={enrichment}
                          thread={thread}
                          projectId={project.id}
                          onThreadUpdated={(updated) => {
                            onThreadUpdated(updated);
                          }}
                          onEnrich={onEnrichSingle}
                          onEnrichmentUpdated={onEnrichmentUpdated}
                          isEnriching={isEnriching}
                        />
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {activeTab === "drafts" && (
          <div className="p-4">
            <DraftsGrid
              threads={threads}
              projectId={project.id}
              onBulkGenerate={handleBulkGenerate}
              onRefresh={onThreadsChanged}
              isBulkGenerating={bulkGenerating}
            />
          </div>
        )}

        {activeTab === "followups" && (
          <div className="p-4">
            <FollowUpPanel
              threads={threads}
              onRefresh={onThreadsChanged}
            />
          </div>
        )}
      </div>
    </div>
  );
}
