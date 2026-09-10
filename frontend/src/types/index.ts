// Shared API types for the AI Kubernetes Agent frontend.

export interface HealthResponse {
  status: "ok" | "degraded" | "down";
  version?: string;
  timestamp?: string;
}

export interface InvestigationResult {
  id: string;
  cluster: string;
  summary: string;
  findings: string[];
  recommendations: string[];
  createdAt: string;
}
