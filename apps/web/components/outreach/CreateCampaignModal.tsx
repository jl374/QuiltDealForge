"use client";

import { useState } from "react";
import { useSession } from "next-auth/react";
import { X, Send, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import type { OutreachCampaign } from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

interface Props {
  projectId: string;
  projectName: string;
  senderEmail: string;
  onCreated: (campaign: OutreachCampaign) => void;
  onClose: () => void;
}

export function CreateCampaignModal({ projectId, projectName, senderEmail, onCreated, onClose }: Props) {
  const { data: session } = useSession();
  const [name, setName] = useState(`${projectName} Outreach`);
  const [subjectTemplate, setSubjectTemplate] = useState("A personalized, attention-grabbing subject about a potential partnership or acquisition conversation");
  const [bodyPrompt, setBodyPrompt] = useState(
    `Write a warm, professional outreach email introducing our firm and expressing interest in their business. ` +
    `Mention specific details about their company that show we've done our research. ` +
    `The goal is to start a conversation about a potential acquisition or partnership. ` +
    `Keep it concise and genuine — no hard sell.`
  );
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");

  const authHeaders = {
    "Content-Type": "application/json",
    "X-User-Id": session?.user?.id ?? "",
    "X-User-Role": session?.user?.role ?? "GP",
  };

  async function handleCreate() {
    if (!name.trim() || !subjectTemplate.trim() || !bodyPrompt.trim()) return;
    setCreating(true);
    setError("");
    try {
      const res = await fetch(`${API_BASE}/outreach/campaigns`, {
        method: "POST",
        headers: authHeaders,
        body: JSON.stringify({
          project_id: projectId,
          name: name.trim(),
          subject_template: subjectTemplate.trim(),
          body_prompt: bodyPrompt.trim(),
          sender_email: senderEmail,
        }),
      });
      if (res.ok) {
        const campaign: OutreachCampaign = await res.json();
        onCreated(campaign);
      } else {
        const data = await res.json().catch(() => ({}));
        setError(data.detail ?? "Failed to create campaign");
      }
    } catch {
      setError("Network error");
    } finally {
      setCreating(false);
    }
  }

  return (
    <>
      <div className="fixed inset-0 bg-black/20 backdrop-blur-sm z-50" onClick={onClose} />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 pointer-events-none">
        <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg pointer-events-auto">
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
            <div className="flex items-center gap-2">
              <Send className="w-4 h-4 text-blue-500" />
              <h3 className="text-sm font-semibold text-slate-900">Create Outreach Campaign</h3>
            </div>
            <button onClick={onClose} className="p-1 text-slate-400 hover:text-slate-600 rounded">
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="px-6 py-5 space-y-4">
            <p className="text-xs text-slate-400">
              Project: <span className="font-medium text-slate-600">{projectName}</span> ·
              From: <span className="font-medium text-slate-600">{senderEmail}</span>
            </p>

            {/* Campaign name */}
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Campaign Name</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="e.g., IVF Clinic Outreach - Feb 2026"
              />
            </div>

            {/* Subject guidance */}
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Subject Line Guidance</label>
              <input
                value={subjectTemplate}
                onChange={(e) => setSubjectTemplate(e.target.value)}
                className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="Describe the type of subject line you want..."
              />
              <p className="text-xs text-slate-400 mt-1">AI will generate a unique subject for each recipient based on this guidance.</p>
            </div>

            {/* Body prompt */}
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Email Approach</label>
              <textarea
                value={bodyPrompt}
                onChange={(e) => setBodyPrompt(e.target.value)}
                rows={4}
                className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
                placeholder="Describe what the email should say, the angle, the thesis..."
              />
              <p className="text-xs text-slate-400 mt-1">AI will use company data, owner research, and this prompt to craft a unique email for each person.</p>
            </div>

            {error && (
              <div className="text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</div>
            )}
          </div>

          {/* Footer */}
          <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-100">
            <button onClick={onClose} className="text-sm text-slate-500 hover:text-slate-700">
              Cancel
            </button>
            <Button
              onClick={handleCreate}
              disabled={creating || !name.trim() || !bodyPrompt.trim()}
              className="flex items-center gap-2 text-sm"
            >
              {creating ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Send className="w-4 h-4" />
              )}
              {creating ? "Creating…" : "Create Campaign"}
            </Button>
          </div>
        </div>
      </div>
    </>
  );
}
