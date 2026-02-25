import type { PipelineStage, OwnershipType } from "@/lib/constants";

export interface User {
  id: string;
  email: string;
  name: string | null;
  avatar_url: string | null;
  role: "GP" | "Analyst" | "Admin";
}

export interface Company {
  id: string;
  name: string;
  website: string | null;
  hq_location: string | null;
  employee_count: number | null;
  sector: string;
  ownership_type: OwnershipType;
  revenue_low: number | null;
  revenue_high: number | null;
  ebitda_low: number | null;
  ebitda_high: number | null;
  stage: PipelineStage;
  ai_fit_score: number | null;
  source: string | null;
  notes: string | null;
  added_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface CompanyCreate {
  name: string;
  website?: string;
  hq_location?: string;
  employee_count?: number;
  sector: string;
  ownership_type?: OwnershipType;
  revenue_low?: number;
  revenue_high?: number;
  ebitda_low?: number;
  ebitda_high?: number;
  stage: PipelineStage;
  source?: string;
  notes?: string;
}

export interface Contact {
  id: string;
  company_id: string;
  name: string;
  title: string | null;
  email: string | null;
  phone: string | null;
  linkedin_url: string | null;
  facebook_url: string | null;
  is_principal_owner: boolean;
  enrichment_status: "pending" | "completed" | "failed" | null;
  enrichment_source: "web" | "apollo" | "manual" | null;
  enriched_at: string | null;
  relationship_owner: string | null;
  last_contact_date: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface ContactCreate {
  company_id: string;
  name: string;
  title?: string;
  email?: string;
  phone?: string;
  linkedin_url?: string;
  notes?: string;
}

export interface SourcingCriteria {
  sector?: string;
  keywords?: string;
  location?: string;
  min_employees?: number;
  max_employees?: number;
  min_revenue?: number;
  max_revenue?: number;
  sources?: string[];
}

export interface SourcingResultItem {
  name: string;
  source: string;
  source_url: string;
  description: string;
  sector: string;
  location: string;
  revenue: string;
  employees: string;
  asking_price: string;
  website: string;
  fit_score: number | null;
  fit_reasons: string[];
  extra: Record<string, unknown>;
}

export interface SourcingResponse {
  results: SourcingResultItem[];
  total: number;
  criteria_used: Record<string, unknown>;
  cached: boolean;
}

export interface Project {
  id: string;
  name: string;
  description: string | null;
  color: string;
  created_by: string | null;
  company_count: number;
  created_at: string;
  updated_at: string;
}

export interface ProjectCompanyEntry {
  id: string;
  company_id: string;
  company_name: string;
  company_sector: string;
  company_stage: string;
  company_location: string | null;
  notes: string | null;
  added_at: string;
}

export interface ProjectDetail extends Project {
  companies: ProjectCompanyEntry[];
}

export type ProjectColor = "slate" | "blue" | "green" | "amber" | "red" | "purple" | "pink" | "indigo" | "teal" | "orange";

export interface CompanyAnalysis {
  mode: "summary" | "deep_dive";
  // Summary
  fit_summary?: string;
  // Deep dive
  business_summary?: string;
  service_lines?: string;
  leadership?: string;
  contact?: string;
  fit_rationale?: string;
  research_sources?: string[];
}

// Enrichment
export interface EnrichmentResult {
  status: "completed" | "failed" | "already_enriched" | "error";
  contact_id?: string;
  name?: string;
  title?: string;
  email?: string;
  phone?: string;
  linkedin_url?: string;
  facebook_url?: string;
  enrichment_source?: string;
  message?: string;
}

export interface EnrichmentStatusResponse {
  status: "not_started" | "pending" | "completed" | "failed" | "unknown";
  contact: {
    id: string;
    name: string;
    title: string | null;
    email: string | null;
    phone: string | null;
    linkedin_url: string | null;
    facebook_url: string | null;
    enrichment_source: string | null;
    enriched_at: string | null;
  } | null;
}

// Outreach
export interface OutreachCampaign {
  id: string;
  project_id: string;
  name: string;
  subject_template: string;
  body_prompt: string;
  sender_email: string;
  status: "draft" | "generating" | "ready" | "sending" | "sent" | "paused";
  created_by: string | null;
  email_count: number;
  created_at: string;
  updated_at: string;
  emails?: OutreachEmail[];
}

export interface OutreachEmail {
  id: string;
  campaign_id: string;
  contact_id: string;
  company_id: string;
  to_email: string;
  subject: string;
  body_html: string;
  status: "draft" | "approved" | "sent" | "failed" | "bounced";
  sent_at: string | null;
  gmail_message_id: string | null;
  error_message: string | null;
  created_at: string;
  contact_name: string | null;
  company_name: string | null;
}

// Thread-based outreach (CRM model)
export type ThreadStatus =
  | "draft"
  | "sent"
  | "awaiting_response"
  | "responded"
  | "meeting_scheduled"
  | "passed";

export type MessageType = "initial" | "follow_up" | "scheduling_reply";
export type MessageStatus = "draft" | "approved" | "sent" | "failed" | "bounced";

export interface ProposedSlot {
  datetime: string;
  label: string;
}

export interface OutreachThread {
  id: string;
  project_id: string;
  company_id: string;
  contact_id: string | null;
  status: ThreadStatus;
  follow_up_count: number;
  next_follow_up_at: string | null;
  last_sent_at: string | null;
  response_received_at: string | null;
  response_summary: string | null;
  proposed_slots: ProposedSlot[] | null;
  created_at: string;
  updated_at: string;
  // Populated by API joins
  company_name?: string;
  company_sector?: string;
  company_location?: string | null;
  contact_name?: string | null;
  contact_email?: string | null;
  contact_title?: string | null;
  messages: OutreachThreadMessage[];
}

export interface OutreachThreadMessage {
  id: string;
  thread_id: string;
  sequence: number;
  message_type: MessageType;
  to_email: string;
  subject: string;
  body_html: string;
  status: MessageStatus;
  sent_at: string | null;
  gmail_message_id: string | null;
  gmail_thread_id: string | null;
  error_message: string | null;
  created_at: string;
}

// Extend NextAuth session types
declare module "next-auth" {
  interface Session {
    user: {
      id: string;
      email: string;
      name: string;
      image?: string;
      role: string;
    };
  }

  interface JWT {
    userId: string;
    role: string;
    googleId: string;
  }
}
