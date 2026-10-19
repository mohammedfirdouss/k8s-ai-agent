"use client";

import { useState } from "react";
import { insforge } from "@/services/insforge";
import type { SignedInUser } from "@/types";

type LoginFormProps = {
  onSignedIn: (user: SignedInUser) => void;
};

type Mode = "signin" | "signup" | "verify";

// Keep in sync with [auth.password] min_length in insforge.toml.
const MIN_PASSWORD_LENGTH = 8;

type AuthUserLike = { id: string; email: string } | null | undefined;

export default function LoginForm({ onSignedIn }: LoginFormProps) {
  const [mode, setMode] = useState<Mode>("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function finish(user: AuthUserLike) {
    if (!user?.id) {
      setError("Signed in, but no user session was returned. Please try again.");
      return;
    }
    onSignedIn({ id: user.id, email: user.email });
  }

  // Switches to the code step; the backend has emailed a 6-digit code.
  function askForCode(message: string) {
    setMode("verify");
    setCode("");
    setNotice(message);
  }

  async function signUp() {
    const { data, error: signUpError } = await insforge!.auth.signUp({
      email,
      password,
      name: email.split("@")[0],
    });
    if (signUpError) {
      setError(signUpError.message ?? "Sign up failed.");
      return;
    }
    if (data?.requireEmailVerification) {
      askForCode(`We sent a 6-digit code to ${email}. Enter it to finish creating your account.`);
      return;
    }
    finish(data?.user);
  }

  async function signIn() {
    const { data, error: signInError } = await insforge!.auth.signInWithPassword({
      email,
      password,
    });
    if (signInError) {
      // Accounts that haven't verified their email can't sign in yet. Other
      // errors (wrong password, a 403 for another reason) are shown as-is.
      if (/verif/i.test(signInError.message ?? "")) {
        await insforge!.auth.resendVerificationEmail({ email });
        askForCode(`Your email isn't verified yet. We sent a new 6-digit code to ${email}.`);
        return;
      }
      setError(signInError.message ?? "Sign in failed.");
      return;
    }
    finish(data?.user);
  }

  async function verify() {
    const { data, error: verifyError } = await insforge!.auth.verifyEmail({ email, otp: code });
    if (verifyError) {
      setError(
        verifyError.statusCode === 400
          ? "That code is invalid or has expired. Check it, or send a new one."
          : (verifyError.message ?? "Verification failed."),
      );
      return;
    }
    // verifyEmail() signs the user in.
    finish(data?.user);
  }

  async function resendCode() {
    if (!insforge || submitting) return;
    setError(null);
    const { error: resendError } = await insforge.auth.resendVerificationEmail({ email });
    if (resendError) {
      setError(resendError.message ?? "Could not send a new code.");
    } else {
      setNotice(`We sent a new 6-digit code to ${email}.`);
    }
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!insforge || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      if (mode === "signup") await signUp();
      else if (mode === "verify") await verify();
      else await signIn();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed.");
    } finally {
      setSubmitting(false);
    }
  }

  function switchMode(next: Mode) {
    setMode(next);
    setError(null);
    setNotice(null);
  }

  const inputClass =
    "mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-slate-900 focus:outline-none";

  return (
    <main className="flex min-h-screen items-center justify-center px-6">
      <div className="w-full max-w-sm rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
        <h1 className="text-xl font-semibold tracking-tight text-slate-900">
          AI Kubernetes Agent
        </h1>
        <p className="mt-1 text-sm text-slate-600">
          {mode === "signin"
            ? "Sign in to continue"
            : mode === "signup"
              ? "Create an account to continue"
              : "Verify your email"}
        </p>

        <form onSubmit={handleSubmit} className="mt-6 space-y-4">
          {mode === "verify" ? (
            <div>
              <label htmlFor="code" className="block text-sm font-medium text-slate-700">
                Verification code
              </label>
              <input
                id="code"
                inputMode="numeric"
                autoComplete="one-time-code"
                pattern="[0-9]{6}"
                maxLength={6}
                required
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                className={`${inputClass} tracking-[0.4em]`}
              />
            </div>
          ) : (
            <>
              <div>
                <label htmlFor="email" className="block text-sm font-medium text-slate-700">
                  Email
                </label>
                <input
                  id="email"
                  type="email"
                  required
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className={inputClass}
                />
              </div>
              <div>
                <label htmlFor="password" className="block text-sm font-medium text-slate-700">
                  Password
                </label>
                <input
                  id="password"
                  type="password"
                  required
                  minLength={mode === "signup" ? MIN_PASSWORD_LENGTH : undefined}
                  autoComplete={mode === "signin" ? "current-password" : "new-password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className={inputClass}
                />
                {mode === "signup" && (
                  <p className="mt-1 text-xs text-slate-500">
                    At least {MIN_PASSWORD_LENGTH} characters.
                  </p>
                )}
              </div>
            </>
          )}

          {notice && !error && (
            <p className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">
              {notice}
            </p>
          )}
          {error && (
            <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submitting
              ? "Please wait..."
              : mode === "signin"
                ? "Sign in"
                : mode === "signup"
                  ? "Create account"
                  : "Verify and continue"}
          </button>
        </form>

        {mode === "verify" ? (
          <div className="mt-4 flex justify-between text-sm text-slate-600">
            <button type="button" onClick={resendCode} className="underline-offset-2 hover:underline">
              Send a new code
            </button>
            <button type="button" onClick={() => switchMode("signin")} className="underline-offset-2 hover:underline">
              Back to sign in
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => switchMode(mode === "signin" ? "signup" : "signin")}
            className="mt-4 text-sm text-slate-600 underline-offset-2 hover:underline"
          >
            {mode === "signin"
              ? "Need an account? Create one"
              : "Already have an account? Sign in"}
          </button>
        )}
      </div>
    </main>
  );
}
