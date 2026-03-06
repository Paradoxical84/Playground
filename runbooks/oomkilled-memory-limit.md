# Runbook: OOMKilled from Tight Memory Limit

## Symptoms
- The `lab-api` pod repeatedly restarts and may enter `CrashLoopBackOff`.
- `kubectl get pods -n ai-lab` shows restart counts increasing.
- The API never becomes healthy even though the manifest looks valid.

## Signals
- `kubectl describe pod -n ai-lab <pod>` shows `Last State: Terminated` with reason `OOMKilled`.
- The overlay sets `MEMORY_HOG_MIB=384` while the container memory limit is only `256Mi`.
- `kubectl logs -n ai-lab deploy/lab-api --previous` shows the memory allocation log message before the container dies.
- `kubectl top pod -n ai-lab` shows memory pressure if metrics-server is installed.

## Root Cause
- The container intentionally allocates more memory than the configured limit, so the kernel OOM killer terminates it.

## Fix
- Revert to the base manifest or raise the memory limit above the expected working set.
- Recovery commands:

```bash
kubectl delete -k k8s/overlays/oomkill
kubectl apply -k k8s/base
kubectl rollout status deployment/lab-api -n ai-lab
```

- Confirm recovery:

```bash
kubectl get pod -n ai-lab
curl http://localhost:8080/healthz
```

- Expected result: the pod is `Running` with low restart count and `/healthz` returns HTTP 200.

## Prevention
- Set memory requests and limits from real measurements, not hopeful estimates.
- Budget for TensorFlow import overhead and model size, not just inference payload size.
- Alert on restart spikes and OOMKilled reasons so resource regressions are caught early.
