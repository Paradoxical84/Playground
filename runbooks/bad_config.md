# Runbook: Configuration Error — Wrong MODEL_DIR

Applies to: `k8s/deployment-bad-config.yaml`

---

## Symptoms

- Pod shows **Running** but **0/1 Ready** — indefinitely.
- `RESTARTS` stays at **0** (the container is not crashing).
- The Service has zero ready endpoints; all client requests get no response
  or a connection error.
- `/healthz` returns 200 (liveness passes).
- `/readyz` returns 503 with an `error` field explaining the failure.

```
NAME                                  READY   STATUS    RESTARTS   AGE
ai-lab-bad-config-5f7d8c9b64-k9m3r   0/1     Running   0          2m
```

This is the subtlest of the three failure modes:

| | Probe failure | OOMKilled | Bad config |
|---|---|---|---|
| STATUS | CrashLoopBackOff | OOMKilled | **Running** |
| READY | 0/1 | 0/1 | **0/1** |
| RESTARTS | Climbing | Climbing | **0** |
| Liveness | Fails (connection refused) | N/A (killed first) | **Passes (200)** |
| Readiness | Fails (connection refused) | N/A (killed first) | **Fails (503)** |
| Logs | Partial / startup msg | Empty | **Full — with error** |

## Signals

### 1. Pod status — Running but not Ready

```bash
kubectl get pods -n ai-lab -l scenario=bad-config -w
```

The pod reaches `Running` quickly but the `READY` column stays `0/1`
and never flips to `1/1`.

### 2. Describe pod — readiness probe failures and env vars

```bash
kubectl describe pod -n ai-lab -l scenario=bad-config
```

Look for two things in the output:

**a) Readiness probe failures in Events:**

```
Warning  Unhealthy  Readiness probe failed: HTTP probe failed with statuscode: 503
```

Unlike the slow-start scenario, the message is **not** "connection refused"
— the server *is* listening and responding; it's just returning 503.

**b) The environment variables section — MODEL_DIR is wrong:**

```
    Environment:
      MODEL_DIR:          /wrong_model_path
      PORT:               8080
      STARTUP_DELAY_SEC:  0
```

This is the smoking gun — compare the value to the correct default (`/model`).

### 3. Container logs — explicit error with exception text

```bash
kubectl logs -n ai-lab -l scenario=bad-config --tail=50
```

Expected output:

```
2026-03-06 12:00:01  INFO      PORT=8080  MODEL_DIR=/wrong_model_path  STARTUP_DELAY_SEC=0
2026-03-06 12:00:01  ERROR     MODEL_DIR path does not exist: /wrong_model_path
2026-03-06 12:00:01  ERROR     Model load failed at startup — readyz will return 503
Traceback (most recent call last):
  File "/app/app.py", line 77, in _load_model
    raise FileNotFoundError(_load_error)
FileNotFoundError: MODEL_DIR path does not exist: /wrong_model_path
2026-03-06 12:00:02  INFO      * Running on http://0.0.0.0:8080
```

The logs are *not* empty (unlike OOMKilled). The full traceback is there.

### 4. Check env vars in the running pod

Because the container is alive and healthy (liveness passes), you can exec
into it to inspect the runtime environment:

```bash
kubectl exec -n ai-lab deploy/ai-lab-bad-config -- env | grep MODEL_DIR
```

Expected output:

```
MODEL_DIR=/wrong_model_path
```

You can also curl the readiness endpoint from inside the pod to see the
error message:

```bash
kubectl exec -n ai-lab deploy/ai-lab-bad-config -- \
  curl -sf http://localhost:8080/readyz
```

Expected output:

```json
{"error":"MODEL_DIR path does not exist: /wrong_model_path","status":"not_ready"}
```

### 5. Confirm the path does not exist inside the container

```bash
kubectl exec -n ai-lab deploy/ai-lab-bad-config -- ls /wrong_model_path
```

Expected output:

```
ls: cannot access '/wrong_model_path': No such file or directory
```

And compare with the correct path:

```bash
kubectl exec -n ai-lab deploy/ai-lab-bad-config -- ls /model
```

Expected output:

```
assets  fingerprint.pb  keras_metadata.pb  saved_model.pb  variables
```

## Root cause

The `MODEL_DIR` environment variable in the deployment manifest is set to
`/wrong_model_path`.  This path does not exist inside the container (the
Dockerfile copies the model to `/model`).

At startup, `_load_model()` checks `Path(MODEL_DIR).exists()`, finds it
missing, and raises `FileNotFoundError`.  The exception is caught in
`main()`, logged with the full traceback, and the server starts anyway
so that `/healthz` works.  But `_ready` is never set to `True`, so
`/readyz` returns 503 for every readiness probe.

The readiness-probe failure means the Endpoints controller never adds the
pod's IP to the Service, so no client traffic reaches the pod despite it
running normally.

## Fix (immediate)

### Option A — Patch the environment variable

```bash
kubectl set env deployment/ai-lab-bad-config -n ai-lab MODEL_DIR=/model
```

This triggers a rolling update with the correct value.

### Option B — Delete the broken overlay and use the base deployment

```bash
kubectl delete -f k8s/deployment-bad-config.yaml
```

The base `k8s/base/deployment.yaml` already sets `MODEL_DIR=/model`.

### Option C — Edit the manifest and re-apply

Fix the value in `k8s/deployment-bad-config.yaml`:

```yaml
env:
  - name: MODEL_DIR
    value: /model          # was /wrong_model_path
```

Then:

```bash
kubectl apply -f k8s/deployment-bad-config.yaml
```

## Prevention (long-term)

- **Use a ConfigMap** for `MODEL_DIR` with a validated default.  Reference
  it via `envFrom` or `valueFrom` so the value lives in one place.
- **Add an init container** that validates the model directory exists before
  the main container starts:

```yaml
initContainers:
  - name: check-model
    image: busybox:1.36
    command: ["sh", "-c", "test -d $MODEL_DIR || (echo MODEL_DIR=$MODEL_DIR not found && exit 1)"]
    env:
      - name: MODEL_DIR
        value: /model
```

- **CI validation**: lint manifests against a schema that checks known env
  vars for valid values (e.g. OPA/Gatekeeper `ConstraintTemplate`).
- **Readiness error surfacing**: the app now includes the error reason in
  the `/readyz` 503 response body, so automated health-check dashboards can
  display the root cause without requiring log access.
- **Alert on long-not-ready pods**: fire when
  `kube_pod_status_ready{condition="false"}` is true for > 5 minutes on a
  pod with zero restarts.  This catches config errors that don't crash.

## Verification

After applying the fix, confirm the pod becomes healthy:

```bash
# 1. Pod reaches 1/1 Ready
kubectl get pods -n ai-lab -l scenario=bad-config
#    READY 1/1   STATUS Running   RESTARTS 0

# 2. Readiness returns 200 with no error field
kubectl exec -n ai-lab deploy/ai-lab-bad-config -- \
  curl -sf http://localhost:8080/readyz
# → {"status":"ready"}

# 3. MODEL_DIR is correct
kubectl exec -n ai-lab deploy/ai-lab-bad-config -- env | grep MODEL_DIR
# → MODEL_DIR=/model

# 4. No readiness-probe failures in recent events
kubectl describe pod -n ai-lab -l scenario=bad-config | grep -i unhealthy
# (no output)

# 5. Prediction works end-to-end
kubectl exec -n ai-lab deploy/ai-lab-bad-config -- \
  curl -sf -X POST http://localhost:8080/predict \
  -H "Content-Type: application/json" -d '{"x": 5}'
# → {"x":5.0,"y":10.95}
```
