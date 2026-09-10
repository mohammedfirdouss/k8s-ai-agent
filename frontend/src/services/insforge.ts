import { createClient } from "@insforge/sdk";

// InsForge is optional: when NEXT_PUBLIC_INSFORGE_BASE_URL is not set the app
// runs without login and history. Guard every call with `insforgeConfigured`.
export const insforgeConfigured = Boolean(
  process.env.NEXT_PUBLIC_INSFORGE_BASE_URL
);

export const insforge = insforgeConfigured
  ? createClient({
      baseUrl: process.env.NEXT_PUBLIC_INSFORGE_BASE_URL!,
      anonKey: process.env.NEXT_PUBLIC_INSFORGE_ANON_KEY,
    })
  : null;
