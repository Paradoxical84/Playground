# Runbook: Configuration Error — Wrong MODEL_DIR

## Symptoms

- `kubectl get pods -n ai-lab` shows the pod as **Running** but **0/1 Ready**.
- `/readyz` returns `503 Not Ready`.
- `/healthz` returns `200 OK` (the process is alive, just misconfigured).
- No traffic is routed to the pod.

## Signals

```bash
# Pod is running but not ready
kubectl get pods -n ai-lab -l scenario=wrong-model-dir

# Events may show readiness probe failures
kubectl describe pod -n ai-lab -l scenario=wrong-model-dir

# Logs contain the actual error
kubectl logs -n ai-lab -l scenario=wrong-model-dir --tail=50
```

**What to look for:**

- Logs: `MODEL_DIR not found: /nonexistent-model`
- Logs: `FileNotFoundError` stack trace
- The container stays running (liveness passes) but never becomes ready.

## Root Cause

The `MODEL_DIR` environment variable is set to `/nonexistent-model`, which
does not exist in the container filesystem. The app catches the error, logs it,
and continues running, but `_ready` stays `False`.

## Fix

Correct the environment variable in the manifest:

```yaml
env:
  - name: MODEL_DIR
    value: /model
```

Then redeploy:

```bash
kubectl apply -f k8s/base/deployment.yaml
```

## Prevention

- Validate configuration at CI time (lint manifests for known-good values).
- Use ConfigMaps with a known-good default and override only when needed.
- Add an init container that verifies the model directory exists before
  the main container starts.
- Alert on pods in `Running` state with `0/N` ready containers for > 5 minutes.
