import type { NextAuthOptions } from "next-auth";
import GoogleProvider from "next-auth/providers/google";

const ALLOWED_DOMAIN = "quilt-cap.com";

export const authOptions: NextAuthOptions = {
  providers: [
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID!,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
      authorization: {
        params: {
          prompt: "select_account",
          hd: ALLOWED_DOMAIN,
          access_type: "offline",
          scope: "openid email profile https://www.googleapis.com/auth/gmail.send",
        },
      },
    }),
  ],

  callbacks: {
    async signIn({ profile }) {
      const email = profile?.email ?? "";
      if (!email.endsWith(`@${ALLOWED_DOMAIN}`)) {
        return false;
      }
      return true;
    },

    async jwt({ token, account, profile }) {
      if (account && profile) {
        token.googleId = (profile as { sub?: string }).sub ?? "";
        token.email = profile.email ?? "";
        token.name = profile.name ?? "";
        token.picture = (profile as { picture?: string }).picture ?? "";
        token.accessToken = account.access_token ?? "";

        try {
          const apiBase = process.env.API_BASE_URL ?? "http://localhost:8000";
          const internalKey = process.env.INTERNAL_API_KEY ?? "";
          console.log("[auth] calling upsert-user at", apiBase, "with key length", internalKey.length);
          const res = await fetch(
            `${apiBase}/auth/upsert-user`,
            {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
                "X-Internal-Key": internalKey,
              },
              body: JSON.stringify({
                google_id: token.googleId,
                email: token.email,
                name: token.name,
                avatar_url: token.picture,
              }),
            }
          );
          const body = await res.json();
          console.log("[auth] upsert-user response:", res.status, JSON.stringify(body));
          if (res.ok) {
            token.userId = body.id;
            token.role = body.role;
          } else {
            // fallback so session is still usable
            token.userId = token.googleId as string;
            token.role = "GP";
          }
        } catch (err) {
          console.error("[auth] upsert-user failed:", err);
          token.userId = token.googleId as string;
          token.role = "GP";
        }
      }
      return token;
    },

    async session({ session, token }) {
      session.user.id = token.userId as string;
      session.user.role = token.role as string;
      (session as any).accessToken = token.accessToken as string;
      return session;
    },
  },

  pages: {
    signIn: "/login",
    error: "/login",
  },

  session: {
    strategy: "jwt",
    maxAge: 8 * 60 * 60, // 8-hour workday sessions
  },
};
