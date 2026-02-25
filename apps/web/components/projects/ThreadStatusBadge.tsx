"use client";

import type { ThreadStatus } from "@/types";

const STATUS_STYLES: Record<ThreadStatus, { bg: string; text: string; label: string }> = {
  draft:             { bg: "bg-slate-100",  text: "text-slate-600",  label: "Draft" },
  sent:              { bg: "bg-blue-100",   text: "text-blue-700",   label: "Sent" },
  awaiting_response: { bg: "bg-amber-100",  text: "text-amber-700",  label: "Awaiting Reply" },
  responded:         { bg: "bg-green-100",  text: "text-green-700",  label: "Responded" },
  meeting_scheduled: { bg: "bg-purple-100", text: "text-purple-700", label: "Meeting Set" },
  passed:            { bg: "bg-red-100",    text: "text-red-700",    label: "Passed" },
};

interface Props {
  status: ThreadStatus;
  className?: string;
}

export function ThreadStatusBadge({ status, className = "" }: Props) {
  const s = STATUS_STYLES[status] ?? STATUS_STYLES.draft;
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium ${s.bg} ${s.text} ${className}`}
    >
      {s.label}
    </span>
  );
}
