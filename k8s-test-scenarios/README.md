# Kubernetes Failure Test Scenarios

Intentional failure manifests for testing the AI troubleshooting agent
against real Kubernetes problems.

| File | Failure | Cause |
| --- | --- | --- |
| `01-crashloopbackoff.yaml` | CrashLoopBackOff | Missing `DATABASE_URL` environment variable |
| `02-imagepullbackoff.yaml` | ImagePullBackOff | Nonexistent image tag |
| `03-oomkilled.yaml` | OOMKilled | 16Mi memory limit, app needs far more |
| `04-selector-mismatch.yaml` | No service endpoints | Service selector doesn't match pod labels |

## Usage

Apply one scenario at a time so the diagnosis stays focused:

```bash
kubectl apply -f k8s-test-scenarios/01-crashloopbackoff.yaml
# wait ~30-60s for the failure state to develop, then investigate
curl -X POST http://localhost:8000/investigate
```

Clean up a scenario before applying the next:

```bash
kubectl delete -f k8s-test-scenarios/01-crashloopbackoff.yaml
```

Clean up everything:

```bash
kubectl delete -f k8s-test-scenarios/ --ignore-not-found
```
