# AI Kubernetes Troubleshooting Agent — Backend

FastAPI backend that inspects a cluster (pods, logs, events, deployments,
networking) with kubectl and asks an LLM (via OpenRouter) for a root cause,
fix, and confidence score.

## Run locally

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in values
uvicorn app.main:app --reload --port 8000
```

Then check: http://localhost:8000/health

## Authentication

- **`INSFORGE_URL` set:** every endpoint except `/health` requires
  `Authorization: Bearer <InsForge user access token>`. Tokens are checked
  against InsForge and cached for 60s.
- **`INSFORGE_URL` empty:** local single-user mode with **no authentication**.
  Only use this on your own machine — never expose it to a network.

Set `INSFORGE_API_KEY` (the project's admin key, server-side only) to save each
investigation to the caller's history. The browser never writes history rows.

## API

| Method | Path | Description |
| --- | --- | --- |
| GET | `/health` | Liveness check (public) |
| GET | `/clusters` | kubeconfig contexts available to the backend |
| POST | `/investigate` | Body `{"investigation_id": "<uuid>", "context": "<optional>"}`; returns diagnosis + evidence |
| GET | `/investigations/{id}/progress` | Live step progress for one of your investigations |

## Agent tools

After collecting the standard evidence, the model may call read-only kubectl
tools to dig deeper, for example reading a pod's YAML to see its command,
probes or env. It gets up to `AGENT_MAX_TOOL_CALLS` calls per investigation
(default `0`, meaning single-shot diagnosis). Tool use is experimental: the evals
support it (`python -m evals.run` compares against `--no-tools`), but it has not been measured yet.

The model never writes kubectl commands itself. It picks from four tools
(`describe`, `get_yaml`, `list`, `logs`) and fills in typed arguments:

- Kinds come from an allowlist that excludes Secrets.
- Names must be valid Kubernetes names, so nothing can be passed as a flag.
- Every output is redacted and truncated before the model sees it.

The commands the agent ran are returned as `commands_run` and shown in the UI.

Pod logs and event messages are scrubbed of likely secrets (URL credentials,
tokens, `*_PASSWORD=` style values, private keys) before they are sent to the LLM.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

## Evals

`evals/` measures how often the agent diagnoses the
[test scenarios](../k8s-test-scenarios) correctly. Each diagnosis is scored
against a rubric: did it name the broken workload, give the right cause and
give the right fix?

```bash
# Replay recorded kubectl output (no cluster needed; uses the LLM in .env)
python -m evals.run --repeat 3

# Re-record fixtures from a dedicated test cluster (after changing inspectors)
kind create cluster --name k8s-ai-test
python -m evals.run --live --context kind-k8s-ai-test --record
```

`--no-tools` runs single-shot diagnosis (no agent tool calls) for comparison.

Fixtures (`evals/fixtures/`) store raw kubectl output, so replay runs the real
inspectors and inspector changes get evaluated too. Results are written to
`evals/results/` (gitignored). `--min-pass 0.8` makes the run exit non-zero
below an 80% pass rate, for CI.

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
  api/routes.py      # HTTP endpoints
  core/config.py     # settings from env vars / .env
  core/auth.py       # InsForge token verification
  kubernetes/        # kubectl runner, cluster inspectors, secret redaction
  ai/                # prompt building + LLM analysis
  services/          # investigation orchestration, progress, history
  models/schemas.py  # Pydantic request/response models
```
