"use client";

import { useState, useCallback } from "react";
import { useSession } from "next-auth/react";
import type {
  ProjectCompanyEntry, EnrichmentStatusResponse,
  OutreachThread, OutreachThreadMessage,
} from "@/types";
import {
  Mail, Phone, Linkedin, Globe, MapPin, Users, DollarSign,
  Search, Loader2, Clock, MessageSquare, Calendar,
  AlertTriangle, Edit3, Save, X, UserPlus,
} from "lucide-react";
import { getSectorColor } from "@/lib/constants";
import { EmailDraftEditor } from "./EmailDraftEditor";
import { ThreadStatusBadge } from "./ThreadStatusBadge";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

interface CompanyDetailPanelProps {
  company: ProjectCompanyEntry;
  enrichment: EnrichmentStatusResponse | undefined;
  thread: OutreachThread | undefined;
  projectId: string;
  onThreadUpdated: (thread: OutreachThread) => void;
  onEnrich: (companyId: string) => void;
  onEnrichmentUpdated: (companyId: string, data: EnrichmentStatusResponse) => void;
  isEnriching: boolean;
}

export function CompanyDetailPanel({
  company,
  enrichment,
  thread,
  projectId,
  onThreadUpdated,
  onEnrich,
  onEnrichmentUpdated,
  isEnriching,
}: CompanyDetailPanelProps) {
  const { data: session } = useSession();
  const [generating, setGenerating] = useState(false);
  const [sending, setSending] = useState(false);
  const [genError, setGenError] = useState<string | null>(null);

  // Manual contact entry state
  const [showManualEntry, setShowManualEntry] = useState(false);
  const [manualName, setManualName] = useState("");
  const [manualTitle, setManualTitle] = useState("");
  const [manualEmail, setManualEmail] = useState("");
  const [manualPhone, setManualPhone] = useState("");
  const [manualLinkedin, setManualLinkedin] = useState("");
  const [savingContact, setSavingContact] = useState(false);

  // Editing existing contact
  const [editingContact, setEditingContact] = useState(false);
  const [editName, setEditName] = useState("");
  const [editTitle, setEditTitle] = useState("");
  const [editEmail, setEditEmail] = useState("");
  const [editPhone, setEditPhone] = useState("");
  const [editLinkedin, setEditLinkedin] = useState("");

  const authHeaders = {
    "Content-Type": "application/json",
    "X-User-Id": session?.user?.id ?? "",
    "X-User-Role": session?.user?.role ?? "GP",
  };

  const isEnriched = enrichment?.status === "completed";
  const isFailed = enrichment?.status === "failed";
  const contact = enrichment?.contact;
  const hasEmail = !!contact?.email;

  // Get the latest initial draft message from the thread
  const initialDraft = thread?.messages?.find(
    (m) => m.message_type === "initial"
  );
  // Get the latest message of any type
  const latestMessage = thread?.messages?.length
    ? thread.messages[thread.messages.length - 1]
    : null;

  const ensureThread = useCallback(async (): Promise<string> => {
    if (thread) return thread.id;

    const res = await fetch(`${API_BASE}/outreach/threads`, {
      method: "POST",
      headers: authHeaders,
      body: JSON.stringify({ project_id: projectId, company_id: company.company_id }),
    });
    if (!res.ok) throw new Error("Failed to create thread");
    const created: OutreachThread = await res.json();
    onThreadUpdated(created);
    return created.id;
  }, [thread, projectId, company.company_id, authHeaders, onThreadUpdated]);

  const handleGenerateDraft = useCallback(async (messageType: string = "initial") => {
    setGenerating(true);
    setGenError(null);
    try {
      const threadId = await ensureThread();
      const res = await fetch(`${API_BASE}/outreach/threads/${threadId}/generate-draft`, {
        method: "POST",
        headers: authHeaders,
        body: JSON.stringify({ message_type: messageType }),
      });
      if (res.ok) {
        // Reload thread
        const threadRes = await fetch(`${API_BASE}/outreach/threads/${threadId}`, { headers: authHeaders });
        if (threadRes.ok) onThreadUpdated(await threadRes.json());
      } else {
        const err = await res.json().catch(() => ({ detail: "Draft generation failed" }));
        setGenError(err.detail || "Draft generation failed. Please add contact info first.");
      }
    } catch (e) {
      setGenError("Draft generation failed. Check that contact info is available.");
    } finally {
      setGenerating(false);
    }
  }, [ensureThread, authHeaders, onThreadUpdated]);

  const handleSaveMessage = useCallback(async (subject: string, bodyHtml: string) => {
    if (!latestMessage) return;
    await fetch(`${API_BASE}/outreach/messages/${latestMessage.id}`, {
      method: "PATCH",
      headers: authHeaders,
      body: JSON.stringify({ subject, body_html: bodyHtml }),
    });
  }, [latestMessage, authHeaders]);

  const handleSendMessage = useCallback(async () => {
    const msg = initialDraft ?? latestMessage;
    if (!msg || !session) return;
    setSending(true);
    try {
      const token = (session as unknown as { accessToken?: string }).accessToken ?? "";
      const res = await fetch(`${API_BASE}/outreach/messages/${msg.id}/send`, {
        method: "POST",
        headers: { ...authHeaders, "X-Gmail-Token": token },
      });
      if (res.ok && thread) {
        // Reload thread
        const threadRes = await fetch(`${API_BASE}/outreach/threads/${thread.id}`, { headers: authHeaders });
        if (threadRes.ok) onThreadUpdated(await threadRes.json());
      }
    } finally {
      setSending(false);
    }
  }, [initialDraft, latestMessage, session, authHeaders, thread, onThreadUpdated]);

  const handleMarkResponded = useCallback(async () => {
    if (!thread) return;
    const summary = prompt("Brief summary of their response (optional):");
    const res = await fetch(`${API_BASE}/outreach/threads/${thread.id}/mark-responded`, {
      method: "POST",
      headers: authHeaders,
      body: JSON.stringify({ response_summary: summary || null }),
    });
    if (res.ok) onThreadUpdated(await res.json());
  }, [thread, authHeaders, onThreadUpdated]);

  // Save manual contact entry
  const handleSaveManualContact = async () => {
    if (!manualName.trim() && !manualEmail.trim()) return;
    setSavingContact(true);
    try {
      if (contact?.id) {
        // Update existing contact
        const res = await fetch(`${API_BASE}/contacts/${contact.id}`, {
          method: "PATCH",
          headers: authHeaders,
          body: JSON.stringify({
            name: manualName.trim() || undefined,
            title: manualTitle.trim() || undefined,
            email: manualEmail.trim() || undefined,
            phone: manualPhone.trim() || undefined,
            linkedin_url: manualLinkedin.trim() || undefined,
            is_principal_owner: true,
            enrichment_status: "completed",
            enrichment_source: "manual",
          }),
        });
        if (res.ok) {
          // Refresh enrichment status
          const statusRes = await fetch(`${API_BASE}/enrichment/company/${company.company_id}/status`, { headers: authHeaders });
          if (statusRes.ok) {
            onEnrichmentUpdated(company.company_id, await statusRes.json());
          }
          setShowManualEntry(false);
        }
      } else {
        // Create new contact
        const res = await fetch(`${API_BASE}/contacts`, {
          method: "POST",
          headers: authHeaders,
          body: JSON.stringify({
            company_id: company.company_id,
            name: manualName.trim() || `Owner of ${company.company_name}`,
            title: manualTitle.trim() || undefined,
            email: manualEmail.trim() || undefined,
            phone: manualPhone.trim() || undefined,
            linkedin_url: manualLinkedin.trim() || undefined,
          }),
        });
        if (res.ok) {
          const newContact = await res.json();
          // Mark as principal owner + completed
          await fetch(`${API_BASE}/contacts/${newContact.id}`, {
            method: "PATCH",
            headers: authHeaders,
            body: JSON.stringify({
              is_principal_owner: true,
              enrichment_status: "completed",
              enrichment_source: "manual",
            }),
          });
          // Refresh enrichment status
          const statusRes = await fetch(`${API_BASE}/enrichment/company/${company.company_id}/status`, { headers: authHeaders });
          if (statusRes.ok) {
            onEnrichmentUpdated(company.company_id, await statusRes.json());
          }
          setShowManualEntry(false);
        }
      }
    } finally {
      setSavingContact(false);
    }
  };

  // Save edits to existing contact
  const handleSaveEditContact = async () => {
    if (!contact?.id) return;
    setSavingContact(true);
    try {
      const res = await fetch(`${API_BASE}/contacts/${contact.id}`, {
        method: "PATCH",
        headers: authHeaders,
        body: JSON.stringify({
          name: editName.trim() || undefined,
          title: editTitle.trim() || undefined,
          email: editEmail.trim() || undefined,
          phone: editPhone.trim() || undefined,
          linkedin_url: editLinkedin.trim() || undefined,
        }),
      });
      if (res.ok) {
        // Refresh enrichment status
        const statusRes = await fetch(`${API_BASE}/enrichment/company/${company.company_id}/status`, { headers: authHeaders });
        if (statusRes.ok) {
          onEnrichmentUpdated(company.company_id, await statusRes.json());
        }
        setEditingContact(false);
      }
    } finally {
      setSavingContact(false);
    }
  };

  const startEditingContact = () => {
    setEditName(contact?.name ?? "");
    setEditTitle(contact?.title ?? "");
    setEditEmail(contact?.email ?? "");
    setEditPhone(contact?.phone ?? "");
    setEditLinkedin(contact?.linkedin_url ?? "");
    setEditingContact(true);
  };

  return (
    <div className="bg-slate-50 border-t border-b border-slate-200 px-6 py-5">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* LEFT: Contact & Company Profile */}
        <div className="space-y-4">
          {/* Owner info — enriched */}
          {isEnriched && contact && !editingContact ? (
            <div>
              <div className="flex items-center gap-2 mb-1">
                <h4 className="text-base font-semibold text-slate-900">{contact.name}</h4>
                {thread && <ThreadStatusBadge status={thread.status} />}
                <button
                  onClick={startEditingContact}
                  className="p-1 text-slate-300 hover:text-slate-500 rounded"
                  title="Edit contact info"
                >
                  <Edit3 className="w-3.5 h-3.5" />
                </button>
              </div>
              {contact.title && (
                <p className="text-sm text-slate-500">{contact.title}</p>
              )}

              <div className="mt-3 space-y-2">
                {contact.email ? (
                  <a
                    href={`mailto:${contact.email}`}
                    className="flex items-center gap-2 text-sm text-blue-600 hover:text-blue-700"
                  >
                    <Mail className="w-4 h-4 shrink-0" />
                    {contact.email}
                  </a>
                ) : (
                  <div className="flex items-center gap-2 text-sm text-amber-600">
                    <Mail className="w-4 h-4 shrink-0" />
                    <span>No email — </span>
                    <button
                      onClick={startEditingContact}
                      className="text-blue-600 hover:text-blue-700 underline"
                    >
                      add one
                    </button>
                  </div>
                )}
                {contact.phone && (
                  <div className="flex items-center gap-2 text-sm text-slate-600">
                    <Phone className="w-4 h-4 shrink-0" />
                    {contact.phone}
                  </div>
                )}
                {contact.linkedin_url && (
                  <a
                    href={contact.linkedin_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-2 text-sm text-blue-600 hover:text-blue-700"
                  >
                    <Linkedin className="w-4 h-4 shrink-0" />
                    LinkedIn Profile
                  </a>
                )}
              </div>

              {contact.enrichment_source && (
                <p className="mt-2 text-xs text-slate-400">
                  Source: {contact.enrichment_source}
                  {contact.enriched_at && ` · ${new Date(contact.enriched_at).toLocaleDateString()}`}
                </p>
              )}
            </div>
          ) : editingContact && contact ? (
            /* Editing existing contact */
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h4 className="text-sm font-semibold text-slate-700">Edit Contact Info</h4>
                <button
                  onClick={() => setEditingContact(false)}
                  className="p-1 text-slate-400 hover:text-slate-600"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
              <input
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                placeholder="Full name"
                className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <input
                value={editTitle}
                onChange={(e) => setEditTitle(e.target.value)}
                placeholder="Title (CEO, Owner, etc.)"
                className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <input
                value={editEmail}
                onChange={(e) => setEditEmail(e.target.value)}
                placeholder="Email address"
                type="email"
                className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <input
                value={editPhone}
                onChange={(e) => setEditPhone(e.target.value)}
                placeholder="Phone number"
                className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <input
                value={editLinkedin}
                onChange={(e) => setEditLinkedin(e.target.value)}
                placeholder="LinkedIn URL"
                className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <div className="flex gap-2">
                <button
                  onClick={handleSaveEditContact}
                  disabled={savingContact}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-slate-900 hover:bg-slate-800 rounded-lg disabled:opacity-50"
                >
                  {savingContact ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                  Save Changes
                </button>
                <button
                  onClick={() => setEditingContact(false)}
                  className="px-3 py-1.5 text-xs font-medium text-slate-500 hover:text-slate-700 border border-slate-200 rounded-lg"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            /* Not enriched — show enrich button + manual entry option */
            <div className="space-y-3">
              {isFailed ? (
                <div className="flex items-start gap-2 px-3 py-2 bg-amber-50 border border-amber-200 rounded-lg">
                  <AlertTriangle className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" />
                  <div>
                    <p className="text-sm text-amber-800 font-medium">Enrichment incomplete</p>
                    <p className="text-xs text-amber-600 mt-0.5">
                      Could not fully identify the owner from web sources. You can retry or add contact info manually.
                    </p>
                  </div>
                </div>
              ) : (
                <p className="text-sm text-slate-400">Owner info not yet available</p>
              )}

              <div className="flex items-center gap-2">
                <button
                  onClick={() => onEnrich(company.company_id)}
                  disabled={isEnriching}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-purple-700 bg-purple-50 hover:bg-purple-100 rounded-lg border border-purple-200 transition-colors disabled:opacity-50"
                >
                  {isEnriching ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Search className="w-3.5 h-3.5" />
                  )}
                  {isEnriching ? "Enriching..." : isFailed ? "Retry Enrichment" : "Enrich Company"}
                </button>
                <button
                  onClick={() => setShowManualEntry(true)}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-600 bg-white hover:bg-slate-50 rounded-lg border border-slate-200 transition-colors"
                >
                  <UserPlus className="w-3.5 h-3.5" />
                  Add Manually
                </button>
              </div>

              {/* Manual contact entry form */}
              {showManualEntry && (
                <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <h4 className="text-sm font-semibold text-slate-700">Add Contact Manually</h4>
                    <button
                      onClick={() => setShowManualEntry(false)}
                      className="p-1 text-slate-400 hover:text-slate-600"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                  <input
                    value={manualName}
                    onChange={(e) => setManualName(e.target.value)}
                    placeholder="Full name *"
                    className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                  <input
                    value={manualTitle}
                    onChange={(e) => setManualTitle(e.target.value)}
                    placeholder="Title (CEO, Owner, etc.)"
                    className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                  <input
                    value={manualEmail}
                    onChange={(e) => setManualEmail(e.target.value)}
                    placeholder="Email address"
                    type="email"
                    className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                  <input
                    value={manualPhone}
                    onChange={(e) => setManualPhone(e.target.value)}
                    placeholder="Phone number"
                    className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                  <input
                    value={manualLinkedin}
                    onChange={(e) => setManualLinkedin(e.target.value)}
                    placeholder="LinkedIn URL"
                    className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                  <div className="flex gap-2">
                    <button
                      onClick={handleSaveManualContact}
                      disabled={savingContact || (!manualName.trim() && !manualEmail.trim())}
                      className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-slate-900 hover:bg-slate-800 rounded-lg disabled:opacity-50"
                    >
                      {savingContact ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                      Save Contact
                    </button>
                    <button
                      onClick={() => setShowManualEntry(false)}
                      className="px-3 py-1.5 text-xs font-medium text-slate-500 hover:text-slate-700 border border-slate-200 rounded-lg"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Company context */}
          <div className="border-t border-slate-200 pt-3">
            <h5 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Company</h5>
            <div className="space-y-1.5">
              <div className="flex items-center gap-2">
                <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium ${getSectorColor(company.company_sector)}`}>
                  {company.company_sector}
                </span>
              </div>
              {company.company_location && (
                <div className="flex items-center gap-2 text-sm text-slate-600">
                  <MapPin className="w-3.5 h-3.5 shrink-0 text-slate-400" />
                  {company.company_location}
                </div>
              )}
            </div>
          </div>

          {/* Thread history */}
          {thread && thread.messages.length > 1 && (
            <div className="border-t border-slate-200 pt-3">
              <h5 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Message History</h5>
              <div className="space-y-1.5">
                {thread.messages.map((m) => (
                  <div key={m.id} className="flex items-center gap-2 text-xs text-slate-500">
                    <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                      m.status === "sent" ? "bg-green-400" :
                      m.status === "failed" ? "bg-red-400" :
                      "bg-slate-300"
                    }`} />
                    <span className="font-medium capitalize">{m.message_type.replace("_", " ")}</span>
                    <span>— {m.status}</span>
                    {m.sent_at && <span>· {new Date(m.sent_at).toLocaleDateString()}</span>}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Action buttons for thread states */}
          {thread?.status === "awaiting_response" && (
            <div className="border-t border-slate-200 pt-3 space-y-2">
              <button
                onClick={handleMarkResponded}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-green-700 bg-green-50 hover:bg-green-100 rounded-lg border border-green-200 transition-colors"
              >
                <MessageSquare className="w-3.5 h-3.5" />
                Mark as Responded
              </button>
              <button
                onClick={() => handleGenerateDraft("follow_up")}
                disabled={generating}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-amber-700 bg-amber-50 hover:bg-amber-100 rounded-lg border border-amber-200 transition-colors disabled:opacity-50"
              >
                {generating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Clock className="w-3.5 h-3.5" />}
                Generate Follow-up
              </button>
            </div>
          )}

          {thread?.status === "responded" && (
            <div className="border-t border-slate-200 pt-3">
              {thread.response_summary && (
                <p className="text-xs text-slate-500 mb-2 italic">&ldquo;{thread.response_summary}&rdquo;</p>
              )}
              <button
                onClick={() => handleGenerateDraft("scheduling_reply")}
                disabled={generating}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-purple-700 bg-purple-50 hover:bg-purple-100 rounded-lg border border-purple-200 transition-colors disabled:opacity-50"
              >
                {generating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Calendar className="w-3.5 h-3.5" />}
                Draft Scheduling Reply
              </button>
            </div>
          )}
        </div>

        {/* RIGHT: Email Draft Editor */}
        <div className="bg-white border border-slate-200 rounded-xl p-4">
          <h5 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">Email Draft</h5>

          {/* Error message */}
          {genError && (
            <div className="flex items-start gap-2 px-3 py-2 mb-3 bg-red-50 border border-red-200 rounded-lg">
              <AlertTriangle className="w-4 h-4 text-red-500 shrink-0 mt-0.5" />
              <div>
                <p className="text-sm text-red-700">{genError}</p>
                {!hasEmail && isEnriched && (
                  <p className="text-xs text-red-500 mt-1">
                    This contact has no email address.{" "}
                    <button
                      onClick={startEditingContact}
                      className="underline hover:text-red-700"
                    >
                      Add one now
                    </button>
                  </p>
                )}
              </div>
            </div>
          )}

          {/* Warning if no contact at all */}
          {!isEnriched && !isFailed && !enrichment && (
            <div className="flex items-start gap-2 px-3 py-2 mb-3 bg-slate-100 border border-slate-200 rounded-lg">
              <AlertTriangle className="w-4 h-4 text-slate-400 shrink-0 mt-0.5" />
              <p className="text-xs text-slate-500">
                Enrich or add contact info before generating a draft.
              </p>
            </div>
          )}

          <EmailDraftEditor
            message={
              // Show the latest draft or initial message
              thread?.messages?.findLast((m) => m.status === "draft")
              ?? initialDraft
              ?? null
            }
            isGenerating={generating}
            onGenerate={() => handleGenerateDraft("initial")}
            onSave={handleSaveMessage}
            onSend={handleSendMessage}
            onRegenerate={() => handleGenerateDraft(initialDraft?.status === "sent" ? "follow_up" : "initial")}
            companyName={company.company_name}
            recipientName={contact?.name ?? "owner"}
            hasContact={!!contact}
          />
        </div>
      </div>
    </div>
  );
}
