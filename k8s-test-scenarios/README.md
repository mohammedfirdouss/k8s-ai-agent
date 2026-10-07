# Kubernetes Failure Test Scenarios

Intentional failure manifests for testing the AI troubleshooting agent
against real Kubernetes problems.

| File | Failure | Cause |
| --- | --- | --- |
| `01-crashloopbackoff.yaml` | CrashLoopBackOff | Missing `DATABASE_URL` environment variable |
| `02-imagepullbackoff.yaml` | ImagePullBackOff | Nonexistent image tag |
| `03-oomkilled.yaml` | OOMKilled | 16Mi memory limit, app needs far more |
| `04-selector-mismatch.yaml` | No service endpoints | Service selector doesn't match pod labels |
| `05-readiness-probe.yaml` | Pod never Ready | Readiness probe checks `/healthz`, which returns 404 |
| `06-pending-resources.yaml` | Pending | Requests 64 CPUs, more than any node has |
| `07-missing-configmap.yaml` | CreateContainerConfigError | `envFrom` references a ConfigMap that doesn't exist |
| `08-liveness-probe.yaml` | Restart loop | Liveness probe targets port 8080; nginx listens on 80 |
| `09-silent-crash.yaml` | CrashLoopBackOff | Exits 1 with no logs — the cause is unknowable, so confidence should be low |
| `10-healthy.yaml` | *(none)* | Healthy control: any reported incident is a false alarm |

## Usage

Manifests don't set a namespace, so they go to `default` unless you pass `-n`.
The eval harness (`backend/evals/`) applies each one to its own namespace and
scores the agent's diagnosis. See the backend README.

Apply one scenario at a time so the diagnosis stays focused:

```bash
kubectl apply -f k8s-test-scenarios/01-crashloopbackoff.yaml
# wait ~30-60s for the failure state to develop, then investigate
# (local no-login mode; with INSFORGE_URL set, add -H "Authorization: Bearer <token>")
curl -X POST http://localhost:8000/investigate \
  -H 'Content-Type: application/json' \
  -d "{\"investigation_id\": \"$(uuidgen)\"}"
```

Clean up a scenario before applying the next:

```bash
kubectl delete -f k8s-test-scenarios/01-crashloopbackoff.yaml
```

Clean up everything:

```bash
kubectl delete -f k8s-test-scenarios/ --ignore-not-found
```
