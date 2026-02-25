"use client";

import { useState } from "react";
import { useSession } from "next-auth/react";
import { X, Save, Loader2, Mail } from "lucide-react";
import { Button } from "@/components/ui/Button";
import type { OutreachEmail } from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

interface Props {
  email: OutreachEmail;
  onSaved: (email: OutreachEmail) => void;
  onClose: () => void;
}

export function EmailPreview({ email, onSaved, onClose }: Props) {
  const { data: session } = useSession();
  const [subject, setSubject] = useState(email.subject);
  const [bodyHtml, setBodyHtml] = useState(email.body_html);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const authHeaders = {
    "Content-Type": "application/json",
    "X-User-Id": session?.user?.id ?? "",
    "X-User-Role": session?.user?.role ?? "GP",
  };

  async function handleSave() {
    setSaving(true);
    setError("");
    try {
      const res = await fetch(`${API_BASE}/outreach/emails/${email.id}`, {
        method: "PATCH",
        headers: authHeaders,
        body: JSON.stringify({ subject, body_html: bodyHtml }),
      });
      if (res.ok) {
        const updated: OutreachEmail = await res.json();
        onSaved(updated);
      } else {
        setError("Failed to save changes");
      }
    } catch {
      setError("Network error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <div className="fixed inset-0 bg-black/30 backdrop-blur-sm z-[60]" onClick={onClose} />
      <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 pointer-events-none">
        <div className="bg-white rounded-2xl shadow-2xl w-full max-w-xl pointer-events-auto max-h-[80vh] flex flex-col">
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 shrink-0">
            <div className="flex items-center gap-2">
              <Mail className="w-4 h-4 text-blue-500" />
              <div>
                <h3 className="text-sm font-semibold text-slate-900">Edit Email</h3>
                <p className="text-xs text-slate-400">
                  To: {email.to_email} · {email.contact_name} at {email.company_name}
                </p>
              </div>
            </div>
            <button onClick={onClose} className="p-1 text-slate-400 hover:text-slate-600 rounded">
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Body */}
          <div className="px-6 py-5 space-y-4 overflow-y-auto flex-1">
            {/* Subject */}
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Subject Line</label>
              <input
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            {/* Body */}
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Email Body (HTML)</label>
              <textarea
                value={bodyHtml}
                onChange={(e) => setBodyHtml(e.target.value)}
                rows={10}
                className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono resize-none"
              />
            </div>

            {/* Preview */}
            <div>
              <p className="text-xs font-medium text-slate-600 mb-1">Preview</p>
              <div className="bg-slate-50 rounded-lg p-4 border border-slate-200">
                <p className="text-xs text-slate-500 mb-2">Subject: <span className="font-medium text-slate-700">{subject}</span></p>
                <hr className="mb-3 border-slate-200" />
                <div
                  className="text-sm text-slate-700 prose prose-sm max-w-none"
                  dangerouslySetInnerHTML={{ __html: bodyHtml }}
                />
              </div>
            </div>

            {error && (
              <div className="text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</div>
            )}
          </div>

          {/* Footer */}
          <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-100 shrink-0">
            <button onClick={onClose} className="text-sm text-slate-500 hover:text-slate-700">
              Cancel
            </button>
            <Button
              onClick={handleSave}
              disabled={saving}
              className="flex items-center gap-2 text-sm"
            >
              {saving ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Save className="w-4 h-4" />
              )}
              {saving ? "Saving…" : "Save Changes"}
            </Button>
          </div>
        </div>
      </div>
    </>
  );
}
