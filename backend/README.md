# AI Kubernetes Troubleshooting Agent — Backend

FastAPI backend for an AI-assisted Kubernetes troubleshooting agent. It will
inspect a cluster (pods, logs, events, deployments, networking) and use an AI
model (via OpenRouter) to suggest a root cause and fix.

This is currently a scaffold: the Kubernetes and AI functions are placeholders.
Only the `/health` endpoint works.

## Run locally

```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in values later
uvicorn app.main:app --reload --port 8000
```

Then check: http://localhost:8000/health

## Run with Docker

```bash
cd backend
docker build -t k8s-ai-agent-backend .
docker run -p 8000:8000 --env-file .env k8s-ai-agent-backend
```

## Project layout

```
app/
  main.py            # app factory, CORS, logging
  api/routes.py      # HTTP endpoints (/health)
  core/config.py     # settings from env vars / .env
  kubernetes/        # cluster inspectors (placeholders)
  ai/                # prompt building + analysis (placeholders)
  services/          # investigation orchestration (placeholder)
  models/schemas.py  # Pydantic response models
```
