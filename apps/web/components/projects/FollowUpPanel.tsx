"use client";

import { useState, useMemo } from "react";
import { useSession } from "next-auth/react";
import type { OutreachThread } from "@/types";
import {
  Clock, MessageSquare, Calendar, Loader2, CheckCircle, AlertCircle,
} from "lucide-react";
import { ThreadStatusBadge } from "./ThreadStatusBadge";
import { SchedulingModal } from "./SchedulingModal";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

interface FollowUpPanelProps {
  threads: OutreachThread[];
  onRefresh: () => void;
}

function daysSince(dateStr: string | null): number {
  if (!dateStr) return 0;
  const diff = Date.now() - new Date(dateStr).getTime();
  return Math.floor(diff / (1000 * 60 * 60 * 24));
}

export function FollowUpPanel({ threads, onRefresh }: FollowUpPanelProps) {
  const { data: session } = useSession();
  const [generatingId, setGeneratingId] = useState<string | null>(null);
  const [schedulingThread, setSchedulingThread] = useState<OutreachThread | null>(null);

  const authHeaders = {
    "Content-Type": "application/json",
    "X-User-Id": session?.user?.id ?? "",
    "X-User-Role": session?.user?.role ?? "GP",
  };

  // Categorize threads
  const { needsFollowUp, responded, scheduled } = useMemo(() => {
    const nfu: OutreachThread[] = [];
    const resp: OutreachThread[] = [];
    const sched: OutreachThread[] = [];

    for (const t of threads) {
      if (t.status === "awaiting_response" || t.status === "sent") {
        nfu.push(t);
      } else if (t.status === "responded") {
        resp.push(t);
      } else if (t.status === "meeting_scheduled") {
        sched.push(t);
      }
    }

    // Sort follow-ups by urgency (oldest first)
    nfu.sort((a, b) => daysSince(b.last_sent_at) - daysSince(a.last_sent_at));

    return { needsFollowUp: nfu, responded: resp, scheduled: sched };
  }, [threads]);

  const handleGenerateFollowUp = async (threadId: string) => {
    setGeneratingId(threadId);
    try {
      const res = await fetch(`${API_BASE}/outreach/threads/${threadId}/generate-draft`, {
        method: "POST",
        headers: authHeaders,
        body: JSON.stringify({ message_type: "follow_up" }),
      });
      if (res.ok) onRefresh();
    } finally {
      setGeneratingId(null);
    }
  };

  const handleMarkResponded = async (threadId: string) => {
    const summary = prompt("Brief summary of their response (optional):");
    const res = await fetch(`${API_BASE}/outreach/threads/${threadId}/mark-responded`, {
      method: "POST",
      headers: authHeaders,
      body: JSON.stringify({ response_summary: summary || null }),
    });
    if (res.ok) onRefresh();
  };

  const isEmpty = needsFollowUp.length === 0 && responded.length === 0 && scheduled.length === 0;

  if (isEmpty) {
    return (
      <div className="text-center py-12 text-slate-400">
        <Clock className="w-8 h-8 mx-auto mb-2 opacity-40" />
        <p className="text-sm">No follow-ups needed yet</p>
        <p className="text-xs mt-1">Send some emails first, then track responses here</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Needs Follow-up */}
      {needsFollowUp.length > 0 && (
        <div>
          <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-700 mb-3">
            <AlertCircle className="w-4 h-4 text-amber-500" />
            Needs Follow-up ({needsFollowUp.length})
          </h3>
          <div className="bg-white border border-slate-200 rounded-xl divide-y divide-slate-100">
            {needsFollowUp.map((t) => {
              const days = daysSince(t.last_sent_at);
              const isOverdue = days >= 5;
              return (
                <div key={t.id} className="flex items-center gap-4 px-5 py-3 hover:bg-slate-50">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-slate-700 truncate">{t.company_name}</p>
                    <p className="text-xs text-slate-400">
                      {t.contact_name ?? "Unknown"} · {t.contact_email ?? "No email"}
                    </p>
                  </div>
                  <div className={`text-xs font-medium ${isOverdue ? "text-red-600" : "text-amber-600"}`}>
                    {days}d ago
                  </div>
                  <ThreadStatusBadge status={t.status} />
                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      onClick={() => handleMarkResponded(t.id)}
                      className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-green-700 bg-green-50 hover:bg-green-100 rounded-lg border border-green-200 transition-colors"
                    >
                      <MessageSquare className="w-3 h-3" />
                      Responded
                    </button>
                    <button
                      onClick={() => handleGenerateFollowUp(t.id)}
                      disabled={generatingId === t.id}
                      className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-amber-700 bg-amber-50 hover:bg-amber-100 rounded-lg border border-amber-200 transition-colors disabled:opacity-50"
                    >
                      {generatingId === t.id ? (
                        <Loader2 className="w-3 h-3 animate-spin" />
                      ) : (
                        <Clock className="w-3 h-3" />
                      )}
                      Follow Up
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Responded */}
      {responded.length > 0 && (
        <div>
          <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-700 mb-3">
            <CheckCircle className="w-4 h-4 text-green-500" />
            Responded ({responded.length})
          </h3>
          <div className="bg-white border border-slate-200 rounded-xl divide-y divide-slate-100">
            {responded.map((t) => (
              <div key={t.id} className="flex items-center gap-4 px-5 py-3 hover:bg-slate-50">
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-slate-700 truncate">{t.company_name}</p>
                  <p className="text-xs text-slate-400">
                    {t.contact_name ?? "Unknown"}
                    {t.response_summary && (
                      <span className="ml-2 italic text-slate-500">&ldquo;{t.response_summary}&rdquo;</span>
                    )}
                  </p>
                </div>
                <ThreadStatusBadge status={t.status} />
                <button
                  onClick={() => setSchedulingThread(t)}
                  className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-purple-700 bg-purple-50 hover:bg-purple-100 rounded-lg border border-purple-200 transition-colors shrink-0"
                >
                  <Calendar className="w-3 h-3" />
                  Schedule Meeting
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Meeting Scheduled */}
      {scheduled.length > 0 && (
        <div>
          <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-700 mb-3">
            <Calendar className="w-4 h-4 text-purple-500" />
            Meeting Scheduled ({scheduled.length})
          </h3>
          <div className="bg-white border border-slate-200 rounded-xl divide-y divide-slate-100">
            {scheduled.map((t) => (
              <div key={t.id} className="flex items-center gap-4 px-5 py-3">
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-slate-700 truncate">{t.company_name}</p>
                  <p className="text-xs text-slate-400">{t.contact_name}</p>
                </div>
                <ThreadStatusBadge status={t.status} />
                {t.proposed_slots && t.proposed_slots.length > 0 && (
                  <div className="text-xs text-slate-500">
                    {t.proposed_slots[0].label}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Scheduling Modal */}
      {schedulingThread && (
        <SchedulingModal
          thread={schedulingThread}
          onClose={() => setSchedulingThread(null)}
          onGenerated={() => {
            setSchedulingThread(null);
            onRefresh();
          }}
        />
      )}
    </div>
  );
}
