"use client";

import { signIn } from "next-auth/react";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

function LoginForm() {
  const searchParams = useSearchParams();
  const error = searchParams.get("error");

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-950 relative overflow-hidden">
      {/* Subtle starfield background */}
      <div className="absolute inset-0 opacity-30">
        <div className="absolute w-1 h-1 bg-white rounded-full top-[12%] left-[23%] animate-pulse" />
        <div className="absolute w-0.5 h-0.5 bg-slate-300 rounded-full top-[34%] left-[67%] animate-pulse" style={{ animationDelay: "0.5s" }} />
        <div className="absolute w-1 h-1 bg-emerald-300 rounded-full top-[56%] left-[15%] animate-pulse" style={{ animationDelay: "1s" }} />
        <div className="absolute w-0.5 h-0.5 bg-white rounded-full top-[78%] left-[82%] animate-pulse" style={{ animationDelay: "1.5s" }} />
        <div className="absolute w-1 h-1 bg-slate-400 rounded-full top-[22%] left-[89%] animate-pulse" style={{ animationDelay: "0.8s" }} />
        <div className="absolute w-0.5 h-0.5 bg-emerald-200 rounded-full top-[65%] left-[45%] animate-pulse" style={{ animationDelay: "2s" }} />
        <div className="absolute w-1 h-1 bg-white rounded-full top-[88%] left-[31%] animate-pulse" style={{ animationDelay: "0.3s" }} />
        <div className="absolute w-0.5 h-0.5 bg-slate-300 rounded-full top-[8%] left-[55%] animate-pulse" style={{ animationDelay: "1.2s" }} />
      </div>

      <div className="bg-slate-900 rounded-2xl border border-slate-800 p-10 w-full max-w-sm relative z-10 shadow-2xl shadow-emerald-500/5">
        <div className="mb-8 text-center">
          {/* Marvin icon */}
          <div className="w-14 h-14 rounded-xl bg-emerald-500/20 flex items-center justify-center mx-auto mb-4">
            <span className="text-emerald-400 text-2xl font-bold">M</span>
          </div>
          <h1 className="text-2xl font-bold text-white">Marvin</h1>
          <p className="text-slate-500 text-sm mt-1">Don&apos;t Panic</p>
        </div>

        {error && (
          <div className="mb-6 p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-sm text-red-400">
            {error === "AccessDenied"
              ? "Access restricted to @quilt-cap.com accounts."
              : "Sign-in failed. The ships hung in the sky in much the same way that bricks don't."}
          </div>
        )}

        <button
          onClick={() => signIn("google", { callbackUrl: "/pipeline" })}
          className="w-full flex items-center justify-center gap-3 bg-slate-800 border border-slate-700 rounded-lg px-4 py-2.5 text-sm font-medium text-slate-200 hover:bg-slate-700 hover:border-slate-600 transition-colors"
        >
          <svg className="w-5 h-5" viewBox="0 0 24 24">
            <path
              fill="#4285F4"
              d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
            />
            <path
              fill="#34A853"
              d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
            />
            <path
              fill="#FBBC05"
              d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"
            />
            <path
              fill="#EA4335"
              d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
            />
          </svg>
          Sign in with Google
        </button>

        <p className="text-[11px] text-slate-600 text-center mt-6">
          Restricted to @quilt-cap.com accounts
        </p>

        <p className="text-[10px] text-slate-700 text-center mt-4 italic">
          &ldquo;I think you ought to know I&apos;m feeling very depressed.&rdquo;
        </p>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
