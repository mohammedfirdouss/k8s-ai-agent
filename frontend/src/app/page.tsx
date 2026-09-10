"use client";

export default function Home() {
  const handleInvestigate = () => {
    // Placeholder: will trigger a cluster investigation via the backend API.
    console.log("Investigate Cluster clicked");
  };

  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-6">
      <div className="w-full max-w-md text-center">
        <h1 className="text-3xl font-semibold tracking-tight text-slate-900">
          AI Kubernetes Agent
        </h1>
        <p className="mt-3 text-base text-slate-600">
          Troubleshoot Kubernetes with AI
        </p>

        <button
          type="button"
          onClick={handleInvestigate}
          className="mt-8 rounded-md bg-slate-900 px-6 py-3 text-sm font-medium text-white transition-colors hover:bg-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2"
        >
          Investigate Cluster
        </button>

        <p className="mt-8 text-sm text-slate-500">System Status: Ready</p>
      </div>
    </main>
  );
}
