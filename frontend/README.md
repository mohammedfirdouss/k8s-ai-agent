# AI Kubernetes Agent — Frontend

Next.js frontend for the AI Kubernetes Troubleshooting Agent. Built with
Next.js 15 (App Router), TypeScript, Tailwind CSS v4, Axios, and React Query.

Features: one-click cluster investigation with live progress steps, an AI
diagnosis card (root cause, fix, kubectl commands, confidence), and optional
login + investigation history backed by InsForge.

## Local development

```bash
npm install
cp .env.example .env.local   # point NEXT_PUBLIC_API_BASE_URL at your backend
npm run dev
```

Open http://localhost:3000. The backend must be running (default
http://localhost:8000) for investigations to work.

## InsForge (optional)

Auth and investigation history use [InsForge](https://insforge.dev). Set these
env vars in `.env.local`:

```
NEXT_PUBLIC_INSFORGE_BASE_URL=   # your InsForge project URL
NEXT_PUBLIC_INSFORGE_ANON_KEY=   # anon key (optional)
```

When `NEXT_PUBLIC_INSFORGE_BASE_URL` is empty, the app runs without login and
history and shows a small notice instead.

The `investigations` table, its owner-only RLS policies and the per-user
realtime channel are defined in `migrations/` at the repo root. History rows are
written by the backend (which needs `INSFORGE_URL` and `INSFORGE_API_KEY`); the
frontend only reads the signed-in user's rows. API calls to the backend carry
the user's InsForge access token.

## Docker

```bash
docker build -t ai-kubernetes-agent-frontend .
docker run -p 3000:3000 ai-kubernetes-agent-frontend
```

## Structure

- `src/app/` — App Router pages, layout, React Query provider
- `src/components/` — UI components
- `src/services/api.ts` — Axios instance and API functions
- `src/hooks/` — React Query hooks
- `src/types/` — shared TypeScript types
