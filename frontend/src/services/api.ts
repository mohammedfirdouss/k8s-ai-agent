import axios from "axios";
import type { HealthResponse } from "@/types";

// Axios instance shared by all API calls.
// Configure the backend URL via NEXT_PUBLIC_API_BASE_URL (see .env.example).
export const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
  timeout: 10_000,
});

// Placeholder: checks backend health. Replace/extend as the backend grows.
export async function getHealth(): Promise<HealthResponse> {
  const response = await api.get<HealthResponse>("/health");
  return response.data;
}
