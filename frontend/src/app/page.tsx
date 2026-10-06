"use client";

import { useEffect, useState } from "react";
import Dashboard from "@/components/Dashboard";
import LoginForm from "@/components/LoginForm";
import { insforge, insforgeConfigured } from "@/services/insforge";
import type { SignedInUser } from "@/types";

export default function Home() {
  // When InsForge is configured we first check for an existing session.
  const [checkingSession, setCheckingSession] = useState(insforgeConfigured);
  const [user, setUser] = useState<SignedInUser | null>(null);

  useEffect(() => {
    if (!insforgeConfigured || !insforge) return;
    let cancelled = false;
    (async () => {
      try {
        const { data } = await insforge.auth.getCurrentUser();
        if (!cancelled && data?.user?.id) {
          setUser({ id: data.user.id, email: data.user.email });
        }
      } catch {
        // No session or InsForge unreachable — fall through to the login form.
      }
      if (!cancelled) setCheckingSession(false);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (checkingSession) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="text-sm text-slate-500">Loading...</p>
      </main>
    );
  }

  if (insforgeConfigured && !user) {
    return <LoginForm onSignedIn={setUser} />;
  }

  return <Dashboard user={user} onSignedOut={() => setUser(null)} />;
}
