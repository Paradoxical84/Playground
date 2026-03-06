# Runbook: OOMKilled

## Symptoms

- `kubectl get pods -n ai-lab` shows the pod with status **OOMKilled**.
- Pod keeps restarting; `restartCount` climbs.
- The container exits with code `137`.

## Signals

```bash
# Check pod status — look for OOMKilled in "Last State"
kubectl get pods -n ai-lab -l scenario=oom-killed
kubectl describe pod -n ai-lab -l scenario=oom-killed

# Check the previous container's logs (may be empty if OOM hit early)
kubectl logs -n ai-lab -l scenario=oom-killed --previous --tail=50

# Node-level: check kernel OOM messages (if you have node access)
# dmesg | grep -i "oom\|killed"
```

**What to look for:**

- `describe pod` output: `Last State: Terminated / Reason: OOMKilled / Exit Code: 137`
- Events: `Container ai-lab exceeded its memory limit`
- The memory limit in the manifest is `64Mi`, far below what TensorFlow needs.

## Root Cause

The deployment sets `resources.limits.memory: 64Mi`. TensorFlow alone requires
several hundred megabytes to initialize. The kernel OOM killer terminates the
process as soon as RSS exceeds 64 MiB.

## Fix

Increase memory limits to match actual usage:

```yaml
resources:
  requests:
    memory: 512Mi
  limits:
    memory: 1Gi
```

## Prevention

- Profile memory usage locally: `docker stats` or `/proc/<pid>/status`.
- Set requests ≈ p50 usage, limits ≈ p99 usage + headroom.
- Use Vertical Pod Autoscaler (VPA) in recommendation mode.
- Alert on `container_memory_working_set_bytes` approaching the limit.
- Avoid setting limits far below requests — it causes unpredictable kills.
