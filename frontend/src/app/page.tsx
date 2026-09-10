"use client";

import { useEffect, useState } from "react";
import Dashboard from "@/components/Dashboard";
import LoginForm from "@/components/LoginForm";
import { insforge, insforgeConfigured } from "@/services/insforge";

export default function Home() {
  // When InsForge is configured we first check for an existing session.
  const [checkingSession, setCheckingSession] = useState(insforgeConfigured);
  const [userEmail, setUserEmail] = useState<string | null>(null);

  useEffect(() => {
    if (!insforgeConfigured || !insforge) return;
    let cancelled = false;
    (async () => {
      try {
        const { data } = await insforge.auth.getCurrentUser();
        if (!cancelled && data?.user?.email) {
          setUserEmail(data.user.email);
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

  if (insforgeConfigured && !userEmail) {
    return <LoginForm onSignedIn={setUserEmail} />;
  }

  return <Dashboard email={userEmail} onSignedOut={() => setUserEmail(null)} />;
}
