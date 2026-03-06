# Runbook: Probe Failure / CrashLoopBackOff (Slow Startup)

## Symptoms

- `kubectl get pods -n ai-lab` shows the pod in **CrashLoopBackOff**.
- `restartCount` keeps climbing.
- The pod never reaches `1/1 Ready`.

## Signals

```bash
# Check pod status and restart count
kubectl get pods -n ai-lab -l scenario=slow-startup

# Check events for probe failure messages
kubectl describe pod -n ai-lab -l scenario=slow-startup

# Check container logs for the "Simulating slow startup" message
kubectl logs -n ai-lab -l scenario=slow-startup --tail=50
```

**What to look for:**

- Events: `Liveness probe failed: ...` or `Readiness probe failed: ...`
- Logs: `Simulating slow startup: sleeping 60 seconds`
- The container is killed before the sleep finishes.

## Root Cause

The `STARTUP_DELAY=60` environment variable causes the application to sleep for
60 seconds before loading the model. The liveness probe has
`initialDelaySeconds=5` and `failureThreshold=3` with `periodSeconds=5`, so
after ~20 seconds kubelet kills the container — well before the app finishes
starting.

## Fix

**Option A — Increase liveness probe timing:**

```yaml
livenessProbe:
  initialDelaySeconds: 90
  periodSeconds: 10
  failureThreshold: 5
```

**Option B — Add a startup probe (preferred for slow-starting containers):**

```yaml
startupProbe:
  httpGet:
    path: /healthz
    port: http
  initialDelaySeconds: 5
  periodSeconds: 10
  failureThreshold: 12     # allows up to 125 s to start
```

**Option C — Remove the artificial delay:**

```yaml
env:
  - name: STARTUP_DELAY
    value: "0"
```

## Prevention

- Always profile real startup time and set probe timings with margin.
- Use `startupProbe` for containers that need long initialization.
- Monitor `kube_pod_container_status_restarts_total` in Prometheus.
- Set alerts on restart count > N within a time window.
