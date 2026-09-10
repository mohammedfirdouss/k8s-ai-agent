// Shared API types for the AI Kubernetes Agent frontend.

export interface HealthResponse {
  status: "ok" | "degraded" | "down";
  version?: string;
  timestamp?: string;
}

// AI diagnosis returned by POST /investigate. All fields are nullable; when
// `error` is set, AI analysis failed and the other fields are null.
export interface Diagnosis {
  root_cause: string | null;
  explanation: string | null;
  fix: string | null;
  kubectl_commands: string[] | null;
  prevention: string | null;
  confidence: number | null;
  confidence_reasoning: string | null;
  error: string | null;
}

export interface InvestigateResponse {
  status: string;
  diagnosis: Diagnosis;
  // Set when the selected cluster was unreachable. Contains a
  // beginner-friendly multi-line message; the diagnosis is empty then.
  cluster_error: string | null;
  investigation: {
    pods?: unknown;
    logs?: unknown;
    events?: unknown;
    deployments?: unknown;
    network?: unknown;
  };
}

// Kubeconfig contexts available on the backend host (GET /clusters).
export interface ClustersResponse {
  clusters: string[];
  current: string | null;
  error: string | null;
}

export interface ProgressStep {
  name: string;
  status: "pending" | "running" | "done";
}

export interface ProgressResponse {
  running: boolean;
  steps: ProgressStep[];
}

// Row shape of the InsForge `investigations` table.
export interface InvestigationRow {
  id: string;
  created_at: string;
  root_cause: string | null;
  namespace: string | null;
  confidence: number | null;
  status: string | null;
}
