"use client";

import { useState, useEffect } from "react";
import { useSession, signOut } from "next-auth/react";
import Image from "next/image";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { LogOut, User } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

interface UserProfile {
  id: string;
  email: string;
  name: string | null;
  avatar_url: string | null;
  role: string;
}

const ROLE_COLORS: Record<string, string> = {
  GP: "bg-indigo-100 text-indigo-700",
  Admin: "bg-red-100 text-red-700",
  Analyst: "bg-slate-100 text-slate-600",
};

export default function ProfilePage() {
  const { data: session, status, update } = useSession();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (status !== "authenticated") return;
    fetch(`${API_BASE}/auth/me`, {
      headers: {
        "X-User-Id": session?.user?.id ?? "",
        "X-User-Role": session?.user?.role ?? "GP",
      },
    })
      .then((r) => r.json())
      .then((data) => {
        if (data.id) {
          setProfile(data);
          setName(data.name ?? "");
        } else {
          setError(data.detail ?? "Could not load profile.");
        }
      })
      .catch(() => setError("Could not load profile."))
      .finally(() => setLoading(false));
  }, [status, session]);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!profile) return;
    setSaving(true);
    setError("");
    setSaved(false);
    try {
      const res = await fetch(`${API_BASE}/auth/me`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          "X-User-Id": session?.user?.id ?? "",
          "X-User-Role": session?.user?.role ?? "GP",
        },
        body: JSON.stringify({ name }),
      });
      const data = await res.json();
      if (res.ok) {
        setProfile(data);
        setSaved(true);
        // Update the session so TopNav reflects the new name
        await update({ name });
        setTimeout(() => setSaved(false), 3000);
      } else {
        setError(data.detail ?? "Failed to save.");
      }
    } catch {
      setError("Failed to save.");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="p-6 max-w-xl mx-auto space-y-4">
        <div className="h-6 w-32 bg-slate-100 rounded animate-pulse" />
        <div className="h-48 bg-slate-100 rounded-xl animate-pulse" />
      </div>
    );
  }

  return (
    <div className="p-6 max-w-xl mx-auto">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-slate-900">Profile</h1>
        <p className="text-sm text-slate-400 mt-0.5">Manage your account details</p>
      </div>

      {/* Avatar + identity */}
      <div className="bg-white border border-slate-200 rounded-xl p-6 mb-4">
        <div className="flex items-center gap-4 mb-6">
          {profile?.avatar_url ? (
            <Image
              src={profile.avatar_url}
              alt={profile.name ?? ""}
              width={64}
              height={64}
              className="rounded-full"
            />
          ) : (
            <div className="w-16 h-16 rounded-full bg-slate-100 flex items-center justify-center">
              <User className="w-7 h-7 text-slate-400" />
            </div>
          )}
          <div>
            <p className="font-medium text-slate-900">{profile?.name ?? "—"}</p>
            <p className="text-sm text-slate-400">{profile?.email}</p>
            <span
              className={`inline-block mt-1 text-xs font-medium px-2 py-0.5 rounded-md ${
                ROLE_COLORS[profile?.role ?? "Analyst"]
              }`}
            >
              {profile?.role}
            </span>
          </div>
        </div>

        {/* Edit form */}
        <form onSubmit={handleSave} className="space-y-4">
          <Input
            label="Display Name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Your name"
          />

          <div className="space-y-1">
            <label className="block text-sm font-medium text-slate-700">
              Email
            </label>
            <p className="text-sm text-slate-500 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2">
              {profile?.email}
              <span className="ml-2 text-xs text-slate-400">(managed by Google)</span>
            </p>
          </div>

          <div className="space-y-1">
            <label className="block text-sm font-medium text-slate-700">
              Role
            </label>
            <p className="text-sm text-slate-500 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2">
              {profile?.role}
              <span className="ml-2 text-xs text-slate-400">(contact an Admin to change)</span>
            </p>
          </div>

          {error && (
            <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              {error}
            </p>
          )}

          {saved && (
            <p className="text-sm text-green-700 bg-green-50 border border-green-200 rounded-lg px-3 py-2">
              Profile saved successfully.
            </p>
          )}

          <div className="flex items-center gap-3 pt-2">
            <Button type="submit" disabled={saving}>
              {saving ? "Saving..." : "Save Changes"}
            </Button>
          </div>
        </form>
      </div>

      {/* Sign out */}
      <div className="bg-white border border-slate-200 rounded-xl p-6">
        <h2 className="text-sm font-medium text-slate-700 mb-1">Sign Out</h2>
        <p className="text-sm text-slate-400 mb-4">
          You'll be redirected to the login page.
        </p>
        <Button
          variant="secondary"
          onClick={() => signOut({ callbackUrl: "/login" })}
        >
          <LogOut className="w-4 h-4 mr-2" />
          Sign Out
        </Button>
      </div>
    </div>
  );
}
