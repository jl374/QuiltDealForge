"use client";

import { X, Mail, Phone, Linkedin, Globe, ExternalLink } from "lucide-react";
import type { EnrichmentStatusResponse } from "@/types";

interface Props {
  data: EnrichmentStatusResponse;
  companyName: string;
  onClose: () => void;
}

export function OwnerDetail({ data, companyName, onClose }: Props) {
  const contact = data.contact;
  if (!contact) return null;

  return (
    <>
      <div className="fixed inset-0 bg-black/20 backdrop-blur-sm z-50" onClick={onClose} />
      <div className="fixed inset-y-0 right-0 z-50 w-full max-w-md">
        <div className="h-full bg-white shadow-2xl flex flex-col">
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
            <div>
              <h3 className="text-sm font-semibold text-slate-900">{contact.name}</h3>
              <p className="text-xs text-slate-400">{companyName}</p>
            </div>
            <button onClick={onClose} className="p-1.5 text-slate-400 hover:text-slate-600 rounded-lg hover:bg-slate-100">
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
            {/* Title */}
            {contact.title && (
              <div>
                <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-1">Title</p>
                <p className="text-sm text-slate-700">{contact.title}</p>
              </div>
            )}

            {/* Contact Info */}
            <div>
              <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-2">Contact Information</p>
              <div className="space-y-2">
                {contact.email && (
                  <a
                    href={`mailto:${contact.email}`}
                    className="flex items-center gap-2.5 text-sm text-slate-700 hover:text-blue-600 transition-colors"
                  >
                    <Mail className="w-4 h-4 text-slate-400" />
                    {contact.email}
                  </a>
                )}
                {contact.phone && (
                  <a
                    href={`tel:${contact.phone}`}
                    className="flex items-center gap-2.5 text-sm text-slate-700 hover:text-blue-600 transition-colors"
                  >
                    <Phone className="w-4 h-4 text-slate-400" />
                    {contact.phone}
                  </a>
                )}
                {contact.linkedin_url && (
                  <a
                    href={contact.linkedin_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-2.5 text-sm text-blue-600 hover:text-blue-700 transition-colors"
                  >
                    <Linkedin className="w-4 h-4" />
                    LinkedIn Profile
                    <ExternalLink className="w-3 h-3" />
                  </a>
                )}
                {contact.facebook_url && (
                  <a
                    href={contact.facebook_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-2.5 text-sm text-blue-600 hover:text-blue-700 transition-colors"
                  >
                    <Globe className="w-4 h-4" />
                    Facebook
                    <ExternalLink className="w-3 h-3" />
                  </a>
                )}
                {!contact.email && !contact.phone && !contact.linkedin_url && !contact.facebook_url && (
                  <p className="text-sm text-slate-400 italic">No contact information found</p>
                )}
              </div>
            </div>

            {/* Enrichment Metadata */}
            <div>
              <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-2">Enrichment Details</p>
              <div className="bg-slate-50 rounded-lg p-3 space-y-1.5">
                <div className="flex justify-between text-xs">
                  <span className="text-slate-500">Source</span>
                  <span className="font-medium text-slate-700 capitalize">{contact.enrichment_source ?? "—"}</span>
                </div>
                {contact.enriched_at && (
                  <div className="flex justify-between text-xs">
                    <span className="text-slate-500">Enriched</span>
                    <span className="font-medium text-slate-700">
                      {new Date(contact.enriched_at).toLocaleDateString()}
                    </span>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
