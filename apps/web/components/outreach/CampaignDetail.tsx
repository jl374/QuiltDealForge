"use client";

import { useState, useEffect } from "react";
import { useSession } from "next-auth/react";
import {
  X, Loader2, Mail, Send, Check, AlertCircle, Sparkles,
  ChevronDown, ChevronRight, Pencil,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { EmailPreview } from "@/components/outreach/EmailPreview";
import type { OutreachCampaign, OutreachEmail } from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

interface Props {
  campaignId: string;
  onClose: () => void;
}

export function CampaignDetail({ campaignId, onClose }: Props) {
  const { data: session } = useSession();
  const [campaign, setCampaign] = useState<OutreachCampaign | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [editingEmail, setEditingEmail] = useState<OutreachEmail | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const authHeaders = {
    "Content-Type": "application/json",
    "X-User-Id": session?.user?.id ?? "",
    "X-User-Role": session?.user?.role ?? "GP",
  };

  useEffect(() => { loadCampaign(); }, [campaignId]); // eslint-disable-line react-hooks/exhaustive-deps

  async function loadCampaign() {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/outreach/campaigns/${campaignId}`, { headers: authHeaders });
      if (res.ok) setCampaign(await res.json());
    } finally {
      setLoading(false);
    }
  }

  async function generateEmails() {
    setGenerating(true);
    setError("");
    try {
      const res = await fetch(`${API_BASE}/outreach/campaigns/${campaignId}/generate`, {
        method: "POST",
        headers: authHeaders,
      });
      if (res.ok) {
        await loadCampaign();
      } else {
        const data = await res.json().catch(() => ({}));
        setError(data.detail ?? "Generation failed");
      }
    } catch {
      setError("Network error during generation");
    } finally {
      setGenerating(false);
    }
  }

  async function sendAll() {
    if (!confirm("Send all emails in this campaign? This cannot be undone.")) return;

    const accessToken = (session as any)?.accessToken;
    if (!accessToken) {
      setError("Gmail access token not available. Please sign out and sign in again to grant Gmail permissions.");
      return;
    }

    setSending(true);
    setError("");
    try {
      const res = await fetch(`${API_BASE}/outreach/campaigns/${campaignId}/send`, {
        method: "POST",
        headers: {
          ...authHeaders,
          "X-Gmail-Token": accessToken,
        },
      });
      if (res.ok) {
        await loadCampaign();
      } else {
        const data = await res.json().catch(() => ({}));
        setError(data.detail ?? "Sending failed");
      }
    } catch {
      setError("Network error during sending");
    } finally {
      setSending(false);
    }
  }

  function onEmailUpdated(updated: OutreachEmail) {
    setCampaign((prev) => {
      if (!prev || !prev.emails) return prev;
      return {
        ...prev,
        emails: prev.emails.map((e) => e.id === updated.id ? updated : e),
      };
    });
    setEditingEmail(null);
  }

  const emails = campaign?.emails ?? [];
  const draftCount = emails.filter((e) => e.status === "draft").length;
  const approvedCount = emails.filter((e) => e.status === "approved").length;
  const sentCount = emails.filter((e) => e.status === "sent").length;
  const failedCount = emails.filter((e) => e.status === "failed").length;
  const canSend = campaign?.status === "ready" && emails.length > 0;
  const canGenerate = campaign?.status === "draft" || campaign?.status === "ready";

  const statusIcon = (status: string) => {
    switch (status) {
      case "sent": return <Check className="w-3.5 h-3.5 text-green-500" />;
      case "failed": return <AlertCircle className="w-3.5 h-3.5 text-red-500" />;
      case "approved": return <Check className="w-3.5 h-3.5 text-blue-500" />;
      default: return <Mail className="w-3.5 h-3.5 text-slate-400" />;
    }
  };

  return (
    <>
      <div className="fixed inset-0 bg-black/20 backdrop-blur-sm z-50" onClick={onClose} />
      <div className="fixed inset-y-0 right-0 z-50 w-full max-w-2xl">
        <div className="h-full bg-white shadow-2xl flex flex-col">
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
            <div>
              <h3 className="text-sm font-semibold text-slate-900">{campaign?.name ?? "Campaign"}</h3>
              <p className="text-xs text-slate-400 mt-0.5">
                {emails.length} emails
                {sentCount > 0 && ` · ${sentCount} sent`}
                {failedCount > 0 && ` · ${failedCount} failed`}
              </p>
            </div>
            <div className="flex items-center gap-2">
              {canGenerate && (
                <Button
                  onClick={generateEmails}
                  disabled={generating}
                  className="flex items-center gap-1.5 text-xs h-8"
                >
                  {generating ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Sparkles className="w-3.5 h-3.5" />
                  )}
                  {generating ? "Generating…" : emails.length > 0 ? "Regenerate" : "Generate Emails"}
                </Button>
              )}
              {canSend && (
                <Button
                  onClick={sendAll}
                  disabled={sending}
                  className="flex items-center gap-1.5 text-xs h-8 bg-green-600 hover:bg-green-700"
                >
                  {sending ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Send className="w-3.5 h-3.5" />
                  )}
                  {sending ? "Sending…" : "Send All"}
                </Button>
              )}
              <button onClick={onClose} className="p-1.5 text-slate-400 hover:text-slate-600 rounded-lg hover:bg-slate-100">
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Status bar */}
          {campaign && (
            <div className="px-6 py-2 bg-slate-50 border-b border-slate-100 flex items-center gap-4 text-xs">
              <span className={`px-2 py-0.5 rounded font-medium ${
                campaign.status === "sent" ? "bg-green-100 text-green-700" :
                campaign.status === "ready" ? "bg-blue-100 text-blue-700" :
                campaign.status === "generating" ? "bg-amber-100 text-amber-700" :
                campaign.status === "sending" ? "bg-purple-100 text-purple-700" :
                "bg-slate-100 text-slate-600"
              }`}>
                {campaign.status}
              </span>
              {draftCount > 0 && <span className="text-slate-500">{draftCount} draft</span>}
              {approvedCount > 0 && <span className="text-blue-500">{approvedCount} approved</span>}
              {sentCount > 0 && <span className="text-green-500">{sentCount} sent</span>}
              {failedCount > 0 && <span className="text-red-500">{failedCount} failed</span>}
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="mx-6 mt-3 text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</div>
          )}

          {/* Email list */}
          <div className="flex-1 overflow-y-auto">
            {loading ? (
              <div className="flex items-center justify-center h-40">
                <Loader2 className="w-5 h-5 animate-spin text-slate-400" />
              </div>
            ) : emails.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-40 text-slate-400">
                <Mail className="w-8 h-8 mb-2 opacity-40" />
                <p className="text-sm">No emails generated yet</p>
                <p className="text-xs mt-1">Click "Generate Emails" to create personalized outreach for each contact</p>
              </div>
            ) : (
              <div className="divide-y divide-slate-100">
                {emails.map((email) => {
                  const isExpanded = expandedId === email.id;
                  return (
                    <div key={email.id} className="px-6 py-3">
                      {/* Email row header */}
                      <button
                        onClick={() => setExpandedId(isExpanded ? null : email.id)}
                        className="w-full flex items-center gap-3 text-left"
                      >
                        {statusIcon(email.status)}
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-slate-700 truncate">
                            {email.contact_name ?? "Unknown"} — {email.company_name ?? ""}
                          </p>
                          <p className="text-xs text-slate-400 truncate">{email.subject}</p>
                        </div>
                        <span className="text-xs text-slate-400 shrink-0">{email.to_email}</span>
                        {isExpanded ? (
                          <ChevronDown className="w-3.5 h-3.5 text-slate-300 shrink-0" />
                        ) : (
                          <ChevronRight className="w-3.5 h-3.5 text-slate-300 shrink-0" />
                        )}
                      </button>

                      {/* Expanded: email preview */}
                      {isExpanded && (
                        <div className="mt-3 ml-7 space-y-3">
                          <div className="bg-slate-50 rounded-lg p-4">
                            <p className="text-xs font-medium text-slate-500 mb-1">Subject</p>
                            <p className="text-sm text-slate-800 font-medium">{email.subject}</p>
                            <hr className="my-3 border-slate-200" />
                            <div
                              className="text-sm text-slate-700 prose prose-sm max-w-none"
                              dangerouslySetInnerHTML={{ __html: email.body_html }}
                            />
                          </div>
                          <div className="flex items-center gap-2">
                            <button
                              onClick={() => setEditingEmail(email)}
                              className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-700 px-2 py-1 rounded hover:bg-slate-100"
                            >
                              <Pencil className="w-3 h-3" />
                              Edit
                            </button>
                            {email.status === "failed" && email.error_message && (
                              <span className="text-xs text-red-500">Error: {email.error_message}</span>
                            )}
                            {email.status === "sent" && email.sent_at && (
                              <span className="text-xs text-green-500">
                                Sent {new Date(email.sent_at).toLocaleString()}
                              </span>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Progress bar for sending */}
          {sending && emails.length > 0 && (
            <div className="px-6 py-3 border-t border-slate-100">
              <div className="w-full bg-slate-100 rounded-full h-1.5">
                <div
                  className="bg-blue-500 h-1.5 rounded-full transition-all duration-500 animate-pulse"
                  style={{ width: `${(sentCount / emails.length) * 100}%` }}
                />
              </div>
              <p className="text-xs text-slate-400 mt-1 text-center">
                Sending {sentCount} of {emails.length}…
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Email edit modal */}
      {editingEmail && (
        <EmailPreview
          email={editingEmail}
          onSaved={onEmailUpdated}
          onClose={() => setEditingEmail(null)}
        />
      )}
    </>
  );
}
