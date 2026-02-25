"use client";

import { useState, useEffect } from "react";
import type { OutreachThreadMessage } from "@/types";
import { Loader2, Pencil, Eye, RefreshCw, Send, Save } from "lucide-react";
import { Button } from "@/components/ui/Button";

interface EmailDraftEditorProps {
  message: OutreachThreadMessage | null;
  isGenerating: boolean;
  onGenerate: () => void;
  onSave: (subject: string, bodyHtml: string) => void;
  onSend: () => void;
  onRegenerate: () => void;
  companyName: string;
  recipientName: string;
  hasContact?: boolean;
}

export function EmailDraftEditor({
  message,
  isGenerating,
  onGenerate,
  onSave,
  onSend,
  onRegenerate,
  companyName,
  recipientName,
  hasContact = true,
}: EmailDraftEditorProps) {
  const [subject, setSubject] = useState(message?.subject ?? "");
  const [bodyHtml, setBodyHtml] = useState(message?.body_html ?? "");
  const [editMode, setEditMode] = useState(false);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    setSubject(message?.subject ?? "");
    setBodyHtml(message?.body_html ?? "");
    setDirty(false);
    setEditMode(false);
  }, [message?.id, message?.subject, message?.body_html]);

  if (isGenerating) {
    return (
      <div className="flex flex-col items-center justify-center py-8 text-slate-400 gap-2">
        <Loader2 className="w-5 h-5 animate-spin" />
        <p className="text-sm">Drafting email to {recipientName}...</p>
      </div>
    );
  }

  if (!message) {
    return (
      <div className="flex flex-col items-center justify-center py-8 gap-3">
        <p className="text-sm text-slate-400">No draft yet for {companyName}</p>
        {!hasContact ? (
          <p className="text-xs text-slate-400 text-center px-4">
            Add contact info (left panel) before generating a draft
          </p>
        ) : (
          <Button onClick={onGenerate} className="flex items-center gap-2">
            <Pencil className="w-4 h-4" />
            Generate Draft
          </Button>
        )}
      </div>
    );
  }

  const isSent = message.status === "sent";
  const missingEmail = !message.to_email;

  return (
    <div className="space-y-3">
      {/* Missing email warning */}
      {missingEmail && !isSent && (
        <div className="flex items-center gap-2 px-3 py-2 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-700">
          <span>No recipient email set — add email to the contact before sending</span>
        </div>
      )}

      {/* Subject */}
      <div>
        <label className="block text-xs font-medium text-slate-500 mb-1">Subject</label>
        <input
          value={subject}
          onChange={(e) => { setSubject(e.target.value); setDirty(true); }}
          disabled={isSent}
          className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-slate-50 disabled:text-slate-500"
        />
      </div>

      {/* Body */}
      <div>
        <div className="flex items-center justify-between mb-1">
          <label className="text-xs font-medium text-slate-500">Body</label>
          {!isSent && (
            <button
              onClick={() => setEditMode(!editMode)}
              className="flex items-center gap-1 text-xs text-slate-400 hover:text-slate-600"
            >
              {editMode ? <Eye className="w-3 h-3" /> : <Pencil className="w-3 h-3" />}
              {editMode ? "Preview" : "Edit HTML"}
            </button>
          )}
        </div>
        {editMode && !isSent ? (
          <textarea
            value={bodyHtml}
            onChange={(e) => { setBodyHtml(e.target.value); setDirty(true); }}
            rows={10}
            className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        ) : (
          <div
            className="prose prose-sm max-w-none border border-slate-200 rounded-lg px-4 py-3 bg-white text-slate-700 max-h-64 overflow-y-auto"
            dangerouslySetInnerHTML={{ __html: bodyHtml }}
          />
        )}
      </div>

      {/* Actions */}
      {!isSent && (
        <div className="flex items-center gap-2 pt-1">
          {dirty && (
            <button
              onClick={() => { onSave(subject, bodyHtml); setDirty(false); }}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors"
            >
              <Save className="w-3.5 h-3.5" />
              Save
            </button>
          )}
          <button
            onClick={onRegenerate}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-amber-700 bg-amber-50 hover:bg-amber-100 rounded-lg border border-amber-200 transition-colors"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Regenerate
          </button>
          <button
            onClick={onSend}
            disabled={missingEmail}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors ml-auto disabled:opacity-50 disabled:cursor-not-allowed"
            title={missingEmail ? "Add recipient email first" : "Send email"}
          >
            <Send className="w-3.5 h-3.5" />
            Send
          </button>
        </div>
      )}

      {isSent && (
        <div className="flex items-center gap-2 px-3 py-2 bg-green-50 border border-green-200 rounded-lg text-xs text-green-700">
          <span>Sent {message.sent_at ? `on ${new Date(message.sent_at).toLocaleDateString()}` : ""}</span>
        </div>
      )}
    </div>
  );
}
