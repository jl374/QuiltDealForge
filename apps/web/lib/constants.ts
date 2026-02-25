export const PIPELINE_STAGES = [
  "Identified",
  "Outreach Sent",
  "Engaged",
  "NDA Signed",
  "Diligence",
  "LOI Submitted",
  "LOI Signed",
  "Closed",
  "Passed",
  "On Hold",
] as const;

export type PipelineStage = (typeof PIPELINE_STAGES)[number];

export const OWNERSHIP_TYPES = [
  "Founder-Owned",
  "PE-Backed",
  "Family-Owned",
  "Public",
  "Unknown",
] as const;

export type OwnershipType = (typeof OWNERSHIP_TYPES)[number];

export const STAGE_COLORS: Record<PipelineStage, string> = {
  Identified: "bg-slate-100 text-slate-700",
  "Outreach Sent": "bg-blue-100 text-blue-700",
  Engaged: "bg-yellow-100 text-yellow-700",
  "NDA Signed": "bg-orange-100 text-orange-700",
  Diligence: "bg-purple-100 text-purple-700",
  "LOI Submitted": "bg-indigo-100 text-indigo-700",
  "LOI Signed": "bg-teal-100 text-teal-700",
  Closed: "bg-green-100 text-green-700",
  Passed: "bg-red-100 text-red-700",
  "On Hold": "bg-gray-100 text-gray-500",
};

// Sector is now free-text — any string is valid.
// Known sectors get a specific color; everything else gets a neutral fallback.
const KNOWN_SECTOR_COLORS: Record<string, string> = {
  IVF: "bg-pink-100 text-pink-700",
  SDIRA: "bg-emerald-100 text-emerald-700",
  Accounting: "bg-cyan-100 text-cyan-700",
  HOA: "bg-violet-100 text-violet-700",
  RCM: "bg-amber-100 text-amber-700",
  Defense: "bg-sky-100 text-sky-700",
  Healthcare: "bg-rose-100 text-rose-700",
  Dental: "bg-teal-100 text-teal-700",
  "Mental Health": "bg-indigo-100 text-indigo-700",
  Technology: "bg-blue-100 text-blue-700",
  Veterinary: "bg-lime-100 text-lime-700",
  "Physical Therapy": "bg-orange-100 text-orange-700",
  Pharmacy: "bg-fuchsia-100 text-fuchsia-700",
  Other: "bg-gray-100 text-gray-600",
};

const FALLBACK_SECTOR_COLOR = "bg-gray-100 text-gray-600";

export function getSectorColor(sector: string): string {
  return KNOWN_SECTOR_COLORS[sector] ?? FALLBACK_SECTOR_COLOR;
}

// Common sector suggestions for autocomplete / placeholder hints
export const SECTOR_SUGGESTIONS = [
  "IVF",
  "SDIRA",
  "Accounting",
  "HOA",
  "RCM",
  "Defense",
  "Healthcare",
  "Dental",
  "Mental Health",
  "Veterinary",
  "Physical Therapy",
  "Pharmacy",
  "Technology",
] as const;
