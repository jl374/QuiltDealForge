"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { UserCircle, Telescope, FolderOpen, BarChart3, Building2 } from "lucide-react";
import { clsx } from "clsx";

const nav = [
  { href: "/pipeline", label: "Pipeline", icon: BarChart3 },
  { href: "/companies", label: "Companies", icon: Building2 },
  { href: "/discover", label: "Discover", icon: Telescope },
  { href: "/projects", label: "Projects", icon: FolderOpen },
];

const bottomNav = [
  { href: "/profile", label: "Profile", icon: UserCircle },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-56 shrink-0 bg-slate-900 flex flex-col h-screen sticky top-0">
      {/* Brand */}
      <div className="px-5 py-5 border-b border-slate-800">
        <div className="flex items-center gap-2.5">
          {/* Marvin icon — a small depressed robot circle */}
          <div className="w-8 h-8 rounded-lg bg-emerald-500/20 flex items-center justify-center">
            <span className="text-emerald-400 text-base font-bold leading-none">M</span>
          </div>
          <div>
            <span className="font-bold text-white text-lg tracking-tight">Marvin</span>
            <span className="block text-[10px] text-slate-500 tracking-wide uppercase">
              Don&apos;t Panic
            </span>
          </div>
        </div>
      </div>

      {/* Nav links */}
      <nav className="flex-1 px-3 py-4 space-y-0.5">
        {nav.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={clsx(
              "flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors",
              pathname.startsWith(href)
                ? "bg-slate-800 text-emerald-400 font-medium"
                : "text-slate-400 hover:bg-slate-800/50 hover:text-slate-200"
            )}
          >
            <Icon className="w-4 h-4" />
            {label}
          </Link>
        ))}
      </nav>

      {/* Bottom nav */}
      <div className="px-3 py-4 border-t border-slate-800 space-y-0.5">
        {bottomNav.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={clsx(
              "flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors",
              pathname.startsWith(href)
                ? "bg-slate-800 text-emerald-400 font-medium"
                : "text-slate-400 hover:bg-slate-800/50 hover:text-slate-200"
            )}
          >
            <Icon className="w-4 h-4" />
            {label}
          </Link>
        ))}
      </div>

      {/* Marvin footer quote */}
      <div className="px-4 py-3 border-t border-slate-800">
        <p className="text-[10px] text-slate-600 italic leading-relaxed">
          &ldquo;Here I am, brain the size of a planet, and they ask me to find deals.&rdquo;
        </p>
      </div>
    </aside>
  );
}
