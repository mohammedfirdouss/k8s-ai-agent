# AI Kubernetes Agent — Frontend

Next.js frontend for the AI Kubernetes Troubleshooting Agent. Built with
Next.js 15 (App Router), TypeScript, Tailwind CSS v4, Axios, and React Query.

Currently a foundation: a simple homepage plus a placeholder API service.
No auth, no realtime, no live backend integration yet.

## Local development

```bash
npm install
cp .env.example .env.local   # point NEXT_PUBLIC_API_BASE_URL at your backend
npm run dev
```

Open http://localhost:3000.

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
