"use client";

import { useSession, signOut } from "next-auth/react";
import Image from "next/image";
import Link from "next/link";
import { LogOut } from "lucide-react";

export function TopNav() {
  const { data: session } = useSession();

  return (
    <header className="h-14 border-b border-slate-200 bg-white flex items-center justify-between px-6">
      {/* Left side — subtle HHGTTG flair */}
      <p className="text-[11px] text-slate-300 italic hidden md:block">
        The answer is 42. The question is what you do with it.
      </p>

      {session?.user && (
        <div className="flex items-center gap-3 ml-auto">
          <Link href="/profile" className="flex items-center gap-3 hover:opacity-80 transition-opacity">
            <div className="text-right">
              <p className="text-sm font-medium text-slate-900">
                {session.user.name}
              </p>
              <p className="text-xs text-slate-400">{session.user.role}</p>
            </div>
            {session.user.image ? (
              <Image
                src={session.user.image}
                alt={session.user.name ?? ""}
                width={32}
                height={32}
                className="rounded-full"
              />
            ) : (
              <div className="w-8 h-8 rounded-full bg-slate-200 flex items-center justify-center text-sm font-medium text-slate-600">
                {session.user.name?.[0] ?? "?"}
              </div>
            )}
          </Link>
          <button
            onClick={() => signOut({ callbackUrl: "/login" })}
            className="text-slate-400 hover:text-slate-600 transition-colors"
            title="Sign out"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      )}
    </header>
  );
}
