# Runbook: Slow Startup Causing Probe Failures

## Symptoms
- The `lab-api` pod never reaches `Running` and stable `Ready`.
- `kubectl get pods -n ai-lab -w` shows repeated restarts.
- The service returns connection failures or never becomes healthy.

## Signals
- `kubectl describe pod -n ai-lab <pod>` shows failed liveness or readiness probes.
- Pod events include `Liveness probe failed` or `Readiness probe failed`.
- `kubectl logs -n ai-lab deploy/lab-api --previous` shows the startup delay log entry.
- `kubectl get deploy -n ai-lab lab-api -o yaml` shows aggressive probe timing combined with `STARTUP_DELAY_SECONDS=45`.

## Root Cause
- The container startup path is intentionally delayed long enough that Kubernetes begins probing before the Flask process is ready to accept traffic.

## Fix
- Revert to the base manifests or relax probe timing.
- Recovery commands:

```bash
kubectl delete -k k8s/overlays/slow-startup
kubectl apply -k k8s/base
kubectl rollout status deployment/lab-api -n ai-lab
```

- Confirm recovery:

```bash
curl http://localhost:8080/readyz
```

- Expected result: HTTP 200 with `"ready": true`.

## Prevention
- Set probe thresholds from measured startup time, not guesses.
- Use startup probes or longer initial delays for services with heavy imports like TensorFlow.
- Track application startup latency in logs or metrics before tightening probe values.
