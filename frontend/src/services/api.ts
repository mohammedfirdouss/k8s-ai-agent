import axios from "axios";
import type {
  HealthResponse,
  InvestigateResponse,
  ProgressResponse,
} from "@/types";

// Axios instance shared by all API calls.
// Configure the backend URL via NEXT_PUBLIC_API_BASE_URL (see .env.example).
export const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
  timeout: 10_000,
});

export async function getHealth(): Promise<HealthResponse> {
  const response = await api.get<HealthResponse>("/health");
  return response.data;
}

// Runs a full cluster investigation. This can take up to ~2 minutes
// (kubectl collection + LLM analysis), hence the long timeout.
export async function investigate(): Promise<InvestigateResponse> {
  const response = await api.post<InvestigateResponse>("/investigate", null, {
    timeout: 180_000,
  });
  return response.data;
}

// Polls the progress of an in-flight investigation.
export async function getProgress(): Promise<ProgressResponse> {
  const response = await api.get<ProgressResponse>("/investigate/progress");
  return response.data;
}

// Turns an axios/unknown error into a short, user-readable message.
export function toErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    if (error.code === "ECONNABORTED") {
      return "The investigation timed out after 3 minutes. Please try again.";
    }
    if (!error.response) {
      return "Backend unreachable — is it running on :8000?";
    }
    const detail =
      (error.response.data as { detail?: string } | undefined)?.detail;
    return detail ?? `Backend error (HTTP ${error.response.status}).`;
  }
  return error instanceof Error ? error.message : "Unexpected error.";
}
