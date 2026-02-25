"use client";

import { useState, useMemo } from "react";
import { useSession } from "next-auth/react";
import type { OutreachThread, OutreachThreadMessage } from "@/types";
import {
  Send, Loader2, CheckSquare, Square, RefreshCw, Pencil, Eye,
} from "lucide-react";
import { ThreadStatusBadge } from "./ThreadStatusBadge";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type StatusFilter = "all" | "draft" | "sent" | "failed";

interface DraftsGridProps {
  threads: OutreachThread[];
  projectId: string;
  onBulkGenerate: () => void;
  onRefresh: () => void;
  isBulkGenerating: boolean;
}

export function DraftsGrid({
  threads,
  projectId,
  onBulkGenerate,
  onRefresh,
  isBulkGenerating,
}: DraftsGridProps) {
  const { data: session } = useSession();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState<StatusFilter>("all");
  const [sending, setSending] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editSubject, setEditSubject] = useState("");
  const [editBody, setEditBody] = useState("");
  const [previewId, setPreviewId] = useState<string | null>(null);

  const authHeaders = {
    "Content-Type": "application/json",
    "X-User-Id": session?.user?.id ?? "",
    "X-User-Role": session?.user?.role ?? "GP",
  };

  // Flatten threads into message rows with company context
  const rows = useMemo(() => {
    const items: {
      thread: OutreachThread;
      message: OutreachThreadMessage;
    }[] = [];

    for (const t of threads) {
      for (const m of t.messages) {
        if (filter === "all" || m.status === filter) {
          items.push({ thread: t, message: m });
        }
      }
    }
    return items;
  }, [threads, filter]);

  // Count stats
  const stats = useMemo(() => {
    let drafts = 0, sent = 0, failed = 0;
    for (const t of threads) {
      for (const m of t.messages) {
        if (m.status === "draft" || m.status === "approved") drafts++;
        else if (m.status === "sent") sent++;
        else if (m.status === "failed") failed++;
      }
    }
    return { drafts, sent, failed, total: drafts + sent + failed };
  }, [threads]);

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectAll = () => {
    const sendable = rows.filter((r) => r.message.status === "draft" || r.message.status === "approved");
    if (selected.size === sendable.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(sendable.map((r) => r.message.id)));
    }
  };

  const handleBulkSend = async () => {
    if (selected.size === 0 || !session) return;
    setSending(true);
    try {
      const token = (session as unknown as { accessToken?: string }).accessToken ?? "";
      const res = await fetch(`${API_BASE}/outreach/threads/bulk-send`, {
        method: "POST",
        headers: { ...authHeaders, "X-Gmail-Token": token },
        body: JSON.stringify({
          message_ids: Array.from(selected),
          sender_email: session.user.email,
        }),
      });
      if (res.ok) {
        setSelected(new Set());
        onRefresh();
      }
    } finally {
      setSending(false);
    }
  };

  const handleSaveEdit = async () => {
    if (!editingId) return;
    await fetch(`${API_BASE}/outreach/messages/${editingId}`, {
      method: "PATCH",
      headers: authHeaders,
      body: JSON.stringify({ subject: editSubject, body_html: editBody }),
    });
    setEditingId(null);
    onRefresh();
  };

  const sendableCount = rows.filter(
    (r) => selected.has(r.message.id) && (r.message.status === "draft" || r.message.status === "approved")
  ).length;

  return (
    <div className="space-y-4">
      {/* Top bar */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <button
            onClick={onBulkGenerate}
            disabled={isBulkGenerating}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-700 bg-white hover:bg-slate-50 rounded-lg border border-slate-200 transition-colors disabled:opacity-50"
          >
            {isBulkGenerating ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <RefreshCw className="w-3.5 h-3.5" />
            )}
            {isBulkGenerating ? "Generating..." : "Generate All Drafts"}
          </button>

          {sendableCount > 0 && (
            <button
              onClick={handleBulkSend}
              disabled={sending}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors disabled:opacity-50"
            >
              {sending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
              Send {sendableCount} Selected
            </button>
          )}
        </div>

        <div className="flex items-center gap-2">
          {/* Filter tabs */}
          {(["all", "draft", "sent", "failed"] as StatusFilter[]).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors ${
                filter === f
                  ? "bg-slate-900 text-white"
                  : "text-slate-500 hover:text-slate-700 hover:bg-slate-100"
              }`}
            >
              {f === "all" ? `All (${stats.total})` :
               f === "draft" ? `Drafts (${stats.drafts})` :
               f === "sent" ? `Sent (${stats.sent})` :
               `Failed (${stats.failed})`}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      {rows.length === 0 ? (
        <div className="text-center py-12 text-slate-400">
          <p className="text-sm">No messages yet. Click &ldquo;Generate All Drafts&rdquo; to create outreach emails.</p>
        </div>
      ) : (
        <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
          {/* Header */}
          <div className="grid grid-cols-[40px_1fr_1fr_2fr_100px_80px] gap-2 px-4 py-2 border-b border-slate-100 text-xs font-medium text-slate-400 uppercase tracking-wider">
            <div>
              <button onClick={selectAll} className="p-0.5 text-slate-400 hover:text-slate-600">
                {selected.size > 0 && selected.size === rows.filter((r) => r.message.status === "draft" || r.message.status === "approved").length
                  ? <CheckSquare className="w-4 h-4" />
                  : <Square className="w-4 h-4" />}
              </button>
            </div>
            <div>Company</div>
            <div>Contact</div>
            <div>Subject</div>
            <div>Status</div>
            <div>Actions</div>
          </div>

          {/* Rows */}
          <div className="divide-y divide-slate-50">
            {rows.map(({ thread, message }) => {
              const isSendable = message.status === "draft" || message.status === "approved";
              return (
                <div key={message.id}>
                  <div className="grid grid-cols-[40px_1fr_1fr_2fr_100px_80px] gap-2 px-4 py-2.5 items-center hover:bg-slate-50">
                    <div>
                      {isSendable && (
                        <button
                          onClick={() => toggleSelect(message.id)}
                          className="p-0.5 text-slate-400 hover:text-slate-600"
                        >
                          {selected.has(message.id) ? (
                            <CheckSquare className="w-4 h-4 text-blue-600" />
                          ) : (
                            <Square className="w-4 h-4" />
                          )}
                        </button>
                      )}
                    </div>
                    <div className="text-sm font-medium text-slate-700 truncate">
                      {thread.company_name}
                    </div>
                    <div className="text-sm text-slate-500 truncate">
                      {thread.contact_name ?? "—"}
                    </div>
                    <div className="text-sm text-slate-600 truncate">{message.subject}</div>
                    <div>
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium ${
                        message.status === "sent" ? "bg-green-100 text-green-700" :
                        message.status === "failed" ? "bg-red-100 text-red-700" :
                        message.status === "approved" ? "bg-blue-100 text-blue-700" :
                        "bg-slate-100 text-slate-600"
                      }`}>
                        {message.status}
                      </span>
                    </div>
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => {
                          if (previewId === message.id) {
                            setPreviewId(null);
                          } else {
                            setPreviewId(message.id);
                            setEditingId(null);
                          }
                        }}
                        className="p-1 text-slate-400 hover:text-slate-600 rounded"
                        title="Preview"
                      >
                        <Eye className="w-3.5 h-3.5" />
                      </button>
                      {isSendable && (
                        <button
                          onClick={() => {
                            if (editingId === message.id) {
                              setEditingId(null);
                            } else {
                              setEditingId(message.id);
                              setEditSubject(message.subject);
                              setEditBody(message.body_html);
                              setPreviewId(null);
                            }
                          }}
                          className="p-1 text-slate-400 hover:text-slate-600 rounded"
                          title="Edit"
                        >
                          <Pencil className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Preview expand */}
                  {previewId === message.id && (
                    <div className="px-6 py-4 bg-slate-50 border-t border-slate-100">
                      <p className="text-xs font-medium text-slate-400 mb-1">To: {message.to_email}</p>
                      <p className="text-sm font-medium text-slate-700 mb-2">{message.subject}</p>
                      <div
                        className="prose prose-sm max-w-none text-slate-600"
                        dangerouslySetInnerHTML={{ __html: message.body_html }}
                      />
                    </div>
                  )}

                  {/* Edit expand */}
                  {editingId === message.id && (
                    <div className="px-6 py-4 bg-amber-50/50 border-t border-slate-100 space-y-3">
                      <input
                        value={editSubject}
                        onChange={(e) => setEditSubject(e.target.value)}
                        className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                      />
                      <textarea
                        value={editBody}
                        onChange={(e) => setEditBody(e.target.value)}
                        rows={6}
                        className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
                      />
                      <div className="flex gap-2">
                        <button
                          onClick={handleSaveEdit}
                          className="px-3 py-1.5 text-xs font-medium text-white bg-slate-900 hover:bg-slate-800 rounded-lg"
                        >
                          Save Changes
                        </button>
                        <button
                          onClick={() => setEditingId(null)}
                          className="px-3 py-1.5 text-xs font-medium text-slate-500 hover:text-slate-700 border border-slate-200 rounded-lg"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
