# Runbook: Probe Failure — Slow Startup (CrashLoopBackOff)

Applies to: `k8s/deployment-slow-start.yaml`

---

## Symptoms

- Pod cycles between **Running** and **CrashLoopBackOff**.
- `READY` column never reaches `1/1`.
- `RESTARTS` count climbs with every cycle.
- Back-off delay between restarts grows (10 s → 20 s → 40 s → … → 5 min cap).
- The Service has zero ready endpoints, so all client requests fail.

```
NAME                                  READY   STATUS             RESTARTS      AGE
ai-lab-slow-start-6d8f9b7c45-x2k7p   0/1     CrashLoopBackOff   4 (12s ago)   2m
```

## Signals

### 1. Pod status and restart count

```bash
kubectl get pods -n ai-lab -l scenario=slow-start -w
```

Watch for the STATUS column alternating between `Running` and
`CrashLoopBackOff`, with RESTARTS increasing each cycle.

### 2. Events (probe failure + container kill)

```bash
kubectl describe pod -n ai-lab -l scenario=slow-start
```

Look in the **Events** section for lines like:

```
Warning  Unhealthy  Liveness probe failed: Get "http://10.244.1.5:8080/healthz": dial tcp 10.244.1.5:8080: connect: connection refused
Warning  Unhealthy  Readiness probe failed: Get "http://10.244.1.5:8080/readyz": dial tcp 10.244.1.5:8080: connect: connection refused
Normal   Killing    Container ai-lab failed liveness probe, will be restarted
```

The critical phrase is **"connection refused"** — it means the Flask server
was not listening yet when the probe fired.

### 3. Container logs

```bash
# Current attempt (may be empty if killed too early)
kubectl logs -n ai-lab -l scenario=slow-start --tail=30

# Previous attempt (the one that was killed)
kubectl logs -n ai-lab -l scenario=slow-start --previous --tail=30
```

Expected log output before the kill:

```
Simulating slow startup: sleeping 45 s …
```

The log will *not* contain "Model loaded – server is ready" because the
container is killed at ≈ 20 s, well before the 45 s sleep completes.

### 4. Quick timeline

| Time | What happens |
|------|--------------|
| t=0 s | Container starts, `_load_model()` begins a 45 s `time.sleep()` |
| t=0 s | Readiness probe fires → connection refused → pod marked NotReady |
| t=5 s | Liveness probe fires → connection refused → failure 1/3 |
| t=10 s | Liveness probe fires → connection refused → failure 2/3 |
| t=15 s | Liveness probe fires → connection refused → failure 3/3 |
| t≈16 s | kubelet kills the container |
| t≈16 s | Kubernetes restarts the container, cycle repeats |

## Root cause

`STARTUP_DELAY_SEC=45` causes the application to sleep inside `_load_model()`
*before* `app.run()` is called. While sleeping, the Flask HTTP server is not
listening on port 8080, so every probe request gets **connection refused**.

The liveness probe is configured with:

```yaml
livenessProbe:
  initialDelaySeconds: 5   # first check at t=5 s
  periodSeconds: 5          # check every 5 s
  failureThreshold: 3       # kill after 3 consecutive failures
```

Three failures are reached at t≈15 s. kubelet kills the container at ≈16 s —
29 seconds before the sleep would have finished. On restart the same sequence
repeats, producing CrashLoopBackOff.

The readiness probe (`initialDelaySeconds: 0`, `periodSeconds: 2`,
`failureThreshold: 1`) marks the pod NotReady immediately, so the Service
never routes traffic to it.

## Fix (immediate)

### Option A — Add a startupProbe (recommended)

A `startupProbe` disables both liveness and readiness probes until the
container signals it has finished initialising:

```yaml
startupProbe:
  httpGet:
    path: /healthz
    port: http
  initialDelaySeconds: 0
  periodSeconds: 5
  failureThreshold: 12   # tolerates up to 60 s of startup
```

Apply by editing the deployment, then re-deploy:

```bash
kubectl edit deployment ai-lab-slow-start -n ai-lab
# add the startupProbe block above, save and exit
kubectl rollout status deployment/ai-lab-slow-start -n ai-lab --timeout=120s
```

### Option B — Increase liveness probe tolerance

```yaml
livenessProbe:
  initialDelaySeconds: 60   # wait longer than the 45 s delay
  periodSeconds: 10
  failureThreshold: 5
```

### Option C — Remove the artificial delay (lab reset)

```bash
kubectl set env deployment/ai-lab-slow-start -n ai-lab STARTUP_DELAY_SEC=0
```

## Prevention (long-term)

- **Profile startup time** in staging and set `initialDelaySeconds` with 2×
  headroom above the observed p99 startup latency.
- **Use a `startupProbe`** for any container whose startup time is variable or
  longer than 10 s. This cleanly separates "is the container still booting?"
  from "is the running container healthy?".
- **Monitor restarts**: alert when
  `kube_pod_container_status_restarts_total` increases by more than 3 in
  10 minutes.
- **CI gate**: lint manifests to reject a liveness probe whose
  `initialDelaySeconds` is lower than the known startup time of the image.
- **Avoid blocking `main()`**: move heavy initialisation (model loading) to a
  background thread so the HTTP server starts immediately and readiness
  toggles once loading completes.

## Verification

After applying the fix, confirm the pod stabilises:

```bash
# 1. Pod reaches 1/1 Ready and stays there
kubectl get pods -n ai-lab -l scenario=slow-start -w
#    READY 1/1   STATUS Running   RESTARTS 0

# 2. Readiness endpoint returns 200
kubectl exec -n ai-lab deploy/ai-lab-slow-start -- \
  curl -sf http://localhost:8080/readyz
# → {"status":"ready"}

# 3. Events show no further probe failures
kubectl describe pod -n ai-lab -l scenario=slow-start | grep -i unhealthy
# (no output)

# 4. Restart count is 0 for the current pod
kubectl get pods -n ai-lab -l scenario=slow-start \
  -o jsonpath='{.items[0].status.containerStatuses[0].restartCount}'
# → 0

# 5. Prediction works end-to-end
kubectl exec -n ai-lab deploy/ai-lab-slow-start -- \
  curl -sf -X POST http://localhost:8080/predict \
  -H "Content-Type: application/json" -d '{"x": 5}'
# → {"x":5.0,"y":10.95}
```
