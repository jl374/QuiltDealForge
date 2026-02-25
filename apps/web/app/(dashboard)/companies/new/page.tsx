import { AddCompanyForm } from "@/components/companies/AddCompanyForm";
import Link from "next/link";
import { ChevronLeft } from "lucide-react";

export default function NewCompanyPage() {
  return (
    <div className="p-6 max-w-3xl mx-auto">
      <Link
        href="/companies"
        className="inline-flex items-center gap-1 text-sm text-slate-400 hover:text-slate-600 transition-colors mb-6"
      >
        <ChevronLeft className="w-4 h-4" />
        Back to Companies
      </Link>

      <div className="mb-6">
        <h1 className="text-xl font-semibold text-slate-900">Add Company</h1>
        <p className="text-sm text-slate-400 mt-0.5">
          Add a new acquisition target to the database
        </p>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl p-6">
        <AddCompanyForm />
      </div>
    </div>
  );
}
