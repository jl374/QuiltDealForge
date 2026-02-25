import { getSession } from "next-auth/react";
import type {
  Company, CompanyCreate, Contact, ContactCreate,
  EnrichmentResult, EnrichmentStatusResponse,
  OutreachCampaign, OutreachEmail,
  OutreachThread, OutreachThreadMessage, ProposedSlot,
  MessageType,
} from "@/types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function apiFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const session = await getSession();

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-User-Id": session?.user?.id ?? "",
      "X-User-Role": session?.user?.role ?? "Analyst",
      ...options.headers,
    },
  });

  if (!res.ok) {
    const error = await res
      .json()
      .catch(() => ({ detail: `HTTP ${res.status}` }));
    throw new Error(error.detail ?? `API error ${res.status}`);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

export interface CompanyListParams {
  sector?: string;
  stage?: string;
  search?: string;
  limit?: number;
  offset?: number;
}

export const api = {
  companies: {
    list: (params: CompanyListParams = {}) => {
      const filtered = Object.fromEntries(
        Object.entries(params).filter(([, v]) => v !== undefined && v !== "")
      );
      const qs = new URLSearchParams(
        filtered as Record<string, string>
      ).toString();
      return apiFetch<Company[]>(`/companies${qs ? `?${qs}` : ""}`);
    },
    create: (data: CompanyCreate) =>
      apiFetch<Company>("/companies", {
        method: "POST",
        body: JSON.stringify(data),
      }),
    get: (id: string) => apiFetch<Company>(`/companies/${id}`),
    update: (id: string, data: Partial<CompanyCreate>) =>
      apiFetch<Company>(`/companies/${id}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      }),
    delete: (id: string) =>
      apiFetch<void>(`/companies/${id}`, { method: "DELETE" }),
  },

  contacts: {
    list: (companyId: string) =>
      apiFetch<Contact[]>(`/contacts?company_id=${companyId}`),
    create: (data: ContactCreate) =>
      apiFetch<Contact>("/contacts", {
        method: "POST",
        body: JSON.stringify(data),
      }),
  },

  enrichment: {
    enrichCompany: (companyId: string) =>
      apiFetch<EnrichmentResult>(`/enrichment/company/${companyId}`, { method: "POST" }),
    enrichProject: (projectId: string) =>
      apiFetch<{ total: number; enriched: number; failed: number; skipped: number }>(
        `/enrichment/project/${projectId}`, { method: "POST" }
      ),
    getStatus: (companyId: string) =>
      apiFetch<EnrichmentStatusResponse>(`/enrichment/company/${companyId}/status`),
  },

  outreach: {
    createCampaign: (data: { project_id: string; name: string; subject_template: string; body_prompt: string; sender_email: string }) =>
      apiFetch<OutreachCampaign>("/outreach/campaigns", {
        method: "POST",
        body: JSON.stringify(data),
      }),
    listCampaigns: (projectId: string) =>
      apiFetch<OutreachCampaign[]>(`/outreach/campaigns?project_id=${projectId}`),
    getCampaign: (campaignId: string) =>
      apiFetch<OutreachCampaign>(`/outreach/campaigns/${campaignId}`),
    generateEmails: (campaignId: string) =>
      apiFetch<{ total: number; generated: number; skipped: number; errors: number }>(
        `/outreach/campaigns/${campaignId}/generate`, { method: "POST" }
      ),
    updateEmail: (emailId: string, data: Partial<{ subject: string; body_html: string; status: string }>) =>
      apiFetch<OutreachEmail>(`/outreach/emails/${emailId}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      }),
    sendCampaign: (campaignId: string, gmailToken: string) =>
      apiFetch<{ total: number; sent: number; failed: number }>(
        `/outreach/campaigns/${campaignId}/send`,
        {
          method: "POST",
          headers: { "X-Gmail-Token": gmailToken },
        }
      ),
  },

  // Thread-based outreach (CRM model)
  threads: {
    list: (projectId: string, status?: string) =>
      apiFetch<OutreachThread[]>(
        `/outreach/threads?project_id=${projectId}${status ? `&status=${status}` : ""}`
      ),
    get: (threadId: string) =>
      apiFetch<OutreachThread>(`/outreach/threads/${threadId}`),
    create: (data: { project_id: string; company_id: string; contact_id?: string }) =>
      apiFetch<OutreachThread>("/outreach/threads", {
        method: "POST",
        body: JSON.stringify(data),
      }),
    update: (threadId: string, data: Partial<{
      status: string;
      next_follow_up_at: string;
      proposed_slots: ProposedSlot[];
      response_summary: string;
    }>) =>
      apiFetch<OutreachThread>(`/outreach/threads/${threadId}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      }),
    delete: (threadId: string) =>
      apiFetch<void>(`/outreach/threads/${threadId}`, { method: "DELETE" }),
    generateDraft: (threadId: string, data: {
      message_type: MessageType;
      custom_prompt?: string;
      proposed_slots?: ProposedSlot[];
    }) =>
      apiFetch<OutreachThreadMessage>(`/outreach/threads/${threadId}/generate-draft`, {
        method: "POST",
        body: JSON.stringify(data),
      }),
    bulkGenerate: (data: {
      project_id: string;
      company_ids: string[];
      message_type: MessageType;
    }) =>
      apiFetch<{ total: number; generated: number; skipped: number; errors: number }>(
        "/outreach/threads/bulk-generate",
        { method: "POST", body: JSON.stringify(data) }
      ),
    markResponded: (threadId: string, data?: { response_summary?: string }) =>
      apiFetch<OutreachThread>(`/outreach/threads/${threadId}/mark-responded`, {
        method: "POST",
        body: JSON.stringify(data ?? {}),
      }),
    generateSchedulingReply: (threadId: string, data: {
      proposed_slots: ProposedSlot[];
      assistant_name?: string;
    }) =>
      apiFetch<OutreachThreadMessage>(
        `/outreach/threads/${threadId}/generate-scheduling-reply`,
        { method: "POST", body: JSON.stringify(data) }
      ),
    bulkSend: (messageIds: string[], senderEmail: string, gmailToken: string) =>
      apiFetch<{ total: number; sent: number; failed: number }>(
        "/outreach/threads/bulk-send",
        {
          method: "POST",
          body: JSON.stringify({ message_ids: messageIds, sender_email: senderEmail }),
          headers: { "X-Gmail-Token": gmailToken },
        }
      ),
  },

  messages: {
    update: (messageId: string, data: Partial<{
      subject: string;
      body_html: string;
      status: string;
    }>) =>
      apiFetch<OutreachThreadMessage>(`/outreach/messages/${messageId}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      }),
    send: (messageId: string, gmailToken: string) =>
      apiFetch<{ message_id: string; gmail_message_id: string; gmail_thread_id: string }>(
        `/outreach/messages/${messageId}/send`,
        {
          method: "POST",
          headers: { "X-Gmail-Token": gmailToken },
        }
      ),
  },
};
