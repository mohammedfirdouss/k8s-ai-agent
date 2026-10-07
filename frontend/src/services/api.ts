import axios from "axios";
import type {
  ClustersResponse,
  HealthResponse,
  InvestigationStatus,
} from "@/types";
import { insforge } from "@/services/insforge";

// Axios instance shared by all API calls.
// Configure the backend URL via NEXT_PUBLIC_API_BASE_URL (see .env.example).
export const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
  timeout: 10_000,
});

// When InsForge is configured the backend requires the signed-in user's
// access token. getValidAccessToken() refreshes it first if it is expiring.
api.interceptors.request.use(async (config) => {
  const token = await insforge?.getHttpClient().getValidAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export async function getHealth(): Promise<HealthResponse> {
  const response = await api.get<HealthResponse>("/health");
  return response.data;
}

// Lists the kubeconfig contexts available on the backend host.
export async function getClusters(): Promise<ClustersResponse> {
  const response = await api.get<ClustersResponse>("/clusters");
  return response.data;
}

// Starts a cluster investigation in the background and returns its id.
// Pass a kubeconfig context name to investigate a specific cluster.
export async function startInvestigation(context?: string | null): Promise<string> {
  const response = await api.post<{ investigation_id: string }>("/investigations", {
    context: context ?? null,
  });
  return response.data.investigation_id;
}

// Progress of an investigation and, once finished, its result. Returns null
// when the backend no longer has it (finished more than 10 minutes ago, or
// the backend restarted); saved results are then in the history.
export async function getInvestigation(
  investigationId: string,
): Promise<InvestigationStatus | null> {
  try {
    const response = await api.get<InvestigationStatus>(
      `/investigations/${investigationId}`,
    );
    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.status === 404) {
      return null;
    }
    throw error;
  }
}

// Turns an axios/unknown error into a short, user-readable message.
export function toErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    if (error.code === "ECONNABORTED") {
      return "The backend took too long to respond. Please try again.";
    }
    if (!error.response) {
      return "Backend unreachable — is it running on :8000?";
    }
    if (error.response.status === 401) {
      return "Your session has expired. Sign out and sign in again.";
    }
    const detail =
      (error.response.data as { detail?: string } | undefined)?.detail;
    return detail ?? `Backend error (HTTP ${error.response.status}).`;
  }
  return error instanceof Error ? error.message : "Unexpected error.";
}
