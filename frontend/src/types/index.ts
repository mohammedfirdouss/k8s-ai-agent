// Shared API types for the AI Kubernetes Agent frontend.

export interface HealthResponse {
  status: string;
  service: string;
}

export type Severity = "critical" | "high" | "medium" | "low";

// One independent problem found in the cluster.
export interface Incident {
  workload: string | null;
  namespace: string | null;
  severity: Severity;
  root_cause: string;
  explanation: string | null;
  fix: string | null;
  kubectl_commands: string[];
  prevention: string | null;
  confidence: number | null;
  confidence_reasoning: string | null;
  evidence: string[];
}

// AI diagnosis returned by POST /investigate. Incidents are most severe
// first; root_cause/confidence are a one-line headline. When `error` is set,
// AI analysis failed and the other fields are empty.
export interface Diagnosis {
  summary: string | null;
  incidents: Incident[];
  root_cause: string | null;
  confidence: number | null;
  error: string | null;
  // Extra read-only kubectl commands the agent chose to run.
  commands_run: string[];
}

export interface InvestigateResponse {
  investigation_id: string;
  status: string;
  // True when the backend saved this investigation to the user's history.
  saved: boolean;
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

// GET /investigations/{id}: live progress, then the result once finished.
export interface InvestigationStatus {
  investigation_id: string;
  running: boolean;
  steps: ProgressStep[];
  result: InvestigateResponse | null;
}

// Row shape of the InsForge `investigations` table (columns the UI reads).
export interface InvestigationRow {
  id: string;
  created_at: string;
  root_cause: string | null;
  cluster_context: string | null;
  confidence: number | null;
  status: string | null;
}

// The signed-in InsForge user.
export interface SignedInUser {
  id: string;
  email: string;
}
