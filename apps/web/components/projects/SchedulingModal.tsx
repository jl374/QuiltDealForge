"use client";

import { useState } from "react";
import { useSession } from "next-auth/react";
import type { OutreachThread, OutreachThreadMessage } from "@/types";
import { X, Plus, Trash2, Loader2, Send, Calendar } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

interface Slot {
  date: string;
  time: string;
  label: string;
}

interface SchedulingModalProps {
  thread: OutreachThread;
  onClose: () => void;
  onGenerated: () => void;
}

export function SchedulingModal({ thread, onClose, onGenerated }: SchedulingModalProps) {
  const { data: session } = useSession();
  const [slots, setSlots] = useState<Slot[]>([
    { date: "", time: "10:00", label: "" },
    { date: "", time: "14:00", label: "" },
  ]);
  const [assistantName, setAssistantName] = useState("");
  const [generating, setGenerating] = useState(false);
  const [generatedMessage, setGeneratedMessage] = useState<OutreachThreadMessage | null>(null);
  const [sending, setSending] = useState(false);

  const authHeaders = {
    "Content-Type": "application/json",
    "X-User-Id": session?.user?.id ?? "",
    "X-User-Role": session?.user?.role ?? "GP",
  };

  const updateSlot = (index: number, field: keyof Slot, value: string) => {
    setSlots((prev) => prev.map((s, i) => i === index ? { ...s, [field]: value } : s));
  };

  const addSlot = () => {
    if (slots.length >= 5) return;
    setSlots((prev) => [...prev, { date: "", time: "10:00", label: "" }]);
  };

  const removeSlot = (index: number) => {
    if (slots.length <= 2) return;
    setSlots((prev) => prev.filter((_, i) => i !== index));
  };

  const handleGenerate = async () => {
    const validSlots = slots
      .filter((s) => s.date)
      .map((s) => ({
        datetime: `${s.date}T${s.time}`,
        label: s.label || formatSlotLabel(s.date, s.time),
      }));

    if (validSlots.length < 2) {
      alert("Please provide at least 2 time slots.");
      return;
    }

    setGenerating(true);
    try {
      const res = await fetch(
        `${API_BASE}/outreach/threads/${thread.id}/generate-scheduling-reply`,
        {
          method: "POST",
          headers: authHeaders,
          body: JSON.stringify({
            proposed_slots: validSlots,
            assistant_name: assistantName || undefined,
          }),
        }
      );
      if (res.ok) {
        const msg: OutreachThreadMessage = await res.json();
        setGeneratedMessage(msg);
      }
    } finally {
      setGenerating(false);
    }
  };

  const handleSend = async () => {
    if (!generatedMessage || !session) return;
    setSending(true);
    try {
      const token = (session as unknown as { accessToken?: string }).accessToken ?? "";
      const res = await fetch(`${API_BASE}/outreach/messages/${generatedMessage.id}/send`, {
        method: "POST",
        headers: { ...authHeaders, "X-Gmail-Token": token },
      });
      if (res.ok) {
        // Update thread status to meeting_scheduled
        await fetch(`${API_BASE}/outreach/threads/${thread.id}`, {
          method: "PATCH",
          headers: authHeaders,
          body: JSON.stringify({ status: "meeting_scheduled" }),
        });
        onGenerated();
      }
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg max-h-[80vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200">
          <div className="flex items-center gap-2">
            <Calendar className="w-5 h-5 text-purple-600" />
            <h3 className="text-base font-semibold text-slate-900">Schedule Meeting</h3>
          </div>
          <button
            onClick={onClose}
            className="p-1 text-slate-400 hover:text-slate-600 rounded-lg hover:bg-slate-100"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="px-6 py-4 space-y-4">
          <p className="text-sm text-slate-500">
            Propose meeting times for <span className="font-medium text-slate-700">{thread.contact_name}</span> at{" "}
            <span className="font-medium text-slate-700">{thread.company_name}</span>
          </p>

          {/* Time slots */}
          <div className="space-y-3">
            <label className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Proposed Time Slots
            </label>
            {slots.map((slot, i) => (
              <div key={i} className="flex items-center gap-2">
                <input
                  type="date"
                  value={slot.date}
                  onChange={(e) => updateSlot(i, "date", e.target.value)}
                  className="flex-1 text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <input
                  type="time"
                  value={slot.time}
                  onChange={(e) => updateSlot(i, "time", e.target.value)}
                  className="w-28 text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <input
                  value={slot.label}
                  onChange={(e) => updateSlot(i, "label", e.target.value)}
                  placeholder="Label (optional)"
                  className="flex-1 text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                {slots.length > 2 && (
                  <button
                    onClick={() => removeSlot(i)}
                    className="p-1.5 text-slate-300 hover:text-red-400 rounded"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                )}
              </div>
            ))}
            {slots.length < 5 && (
              <button
                onClick={addSlot}
                className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-700 font-medium"
              >
                <Plus className="w-3 h-3" />
                Add Slot
              </button>
            )}
          </div>

          {/* Assistant name */}
          <div>
            <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">
              Assistant Name (optional)
            </label>
            <input
              value={assistantName}
              onChange={(e) => setAssistantName(e.target.value)}
              placeholder="e.g. Sarah from Quilt Capital"
              className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Generate button */}
          {!generatedMessage && (
            <button
              onClick={handleGenerate}
              disabled={generating}
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-medium text-white bg-purple-600 hover:bg-purple-700 rounded-lg transition-colors disabled:opacity-50"
            >
              {generating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Calendar className="w-4 h-4" />}
              {generating ? "Generating Reply..." : "Generate Scheduling Reply"}
            </button>
          )}

          {/* Preview generated message */}
          {generatedMessage && (
            <div className="border border-slate-200 rounded-xl overflow-hidden">
              <div className="px-4 py-2 bg-slate-50 border-b border-slate-200">
                <p className="text-xs text-slate-400">Preview</p>
                <p className="text-sm font-medium text-slate-700">{generatedMessage.subject}</p>
              </div>
              <div
                className="px-4 py-3 prose prose-sm max-w-none text-slate-600"
                dangerouslySetInnerHTML={{ __html: generatedMessage.body_html }}
              />
              <div className="px-4 py-3 border-t border-slate-100 flex items-center gap-2">
                <button
                  onClick={handleGenerate}
                  disabled={generating}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-600 hover:text-slate-700 border border-slate-200 rounded-lg"
                >
                  Regenerate
                </button>
                <button
                  onClick={handleSend}
                  disabled={sending}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg ml-auto disabled:opacity-50"
                >
                  {sending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
                  {sending ? "Sending..." : "Send Reply"}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function formatSlotLabel(date: string, time: string): string {
  try {
    const d = new Date(`${date}T${time}`);
    return d.toLocaleDateString("en-US", { weekday: "long", month: "short", day: "numeric" }) +
      " at " + d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
  } catch {
    return `${date} ${time}`;
  }
}
