# Runbook: OOMKilled — Memory Limit Too Low

Applies to: `k8s/deployment-oom.yaml`

---

## Symptoms

- Pod shows status **OOMKilled** (or oscillates between `Running` →
  `OOMKilled` → `CrashLoopBackOff`).
- `READY` column stays at `0/1`.
- `RESTARTS` count climbs; back-off delay grows to the 5-minute cap.
- Container exit code is **137** (128 + SIGKILL signal 9).
- Container logs are empty or truncated — the process was killed mid-flight.

```
NAME                            READY   STATUS      RESTARTS      AGE
ai-lab-oom-7b4d9f6c88-tn4w2    0/1     OOMKilled   3 (28s ago)   90s
```

## Signals

### 1. Pod status and last termination reason

```bash
kubectl get pods -n ai-lab -l scenario=oom -w
```

Look for `STATUS` switching to **OOMKilled** and RESTARTS increasing.

```bash
kubectl get pod -n ai-lab -l scenario=oom \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.containerStatuses[0].lastState.terminated.reason}{"\t"}exit={.status.containerStatuses[0].lastState.terminated.exitCode}{"\n"}{end}'
```

Expected output:

```
ai-lab-oom-7b4d9f6c88-tn4w2    OOMKilled    exit=137
```

### 2. Describe pod — termination details and events

```bash
kubectl describe pod -n ai-lab -l scenario=oom
```

Key fragments to look for in the output:

```
    Last State:     Terminated
      Reason:       OOMKilled
      Exit Code:    137
    ...
    Limits:
      memory:  128Mi
    Requests:
      memory:  64Mi
```

### 3. Namespace events sorted by time

```bash
kubectl get events -n ai-lab --sort-by=.metadata.creationTimestamp
```

Look for:

```
Warning  OOMKilling  pod/ai-lab-oom-...  Memory cgroup out of memory: Killed process ...
Normal   Pulled      pod/ai-lab-oom-...  Container image "ai-lab:latest" already present on machine
Normal   Created     pod/ai-lab-oom-...  Created container ai-lab
Normal   Started     pod/ai-lab-oom-...  Started container ai-lab
Warning  BackOff     pod/ai-lab-oom-...  Back-off restarting failed container ai-lab ...
```

The repeated `Created → Started → OOMKilling → BackOff` cycle confirms the
OOM pattern.

### 4. Previous container logs

```bash
kubectl logs -n ai-lab -l scenario=oom --previous --tail=50
```

Expect either an empty result or a partial first log line.  TensorFlow is
killed during `import tensorflow` — before the application writes any
structured log output.  An empty `--previous` log combined with exit
code 137 is the hallmark of an early-startup OOM.

### 5. Node-level confirmation (if you have node access)

```bash
# On the kind worker node:
docker exec -it ai-lab-worker bash
dmesg | grep -i "oom\|killed" | tail -20
```

Look for kernel messages like:

```
Memory cgroup out of memory: Killed process 12345 (python)
```

## Root cause

The deployment sets `resources.limits.memory: 128Mi`.  When Kubernetes
creates the container it places the process in a memory cgroup with a
128 MiB hard ceiling.

TensorFlow CPU 2.15 needs approximately 300–500 MiB just to finish
`import tensorflow` (shared libraries, BLAS initialization, protobuf
schema registration).  With a 128 MiB limit the kernel OOM killer fires
a SIGKILL (signal 9 → exit code 137) before the Python interpreter even
reaches `_load_model()`.

This is fundamentally different from a probe failure:

| | Probe failure | OOMKilled |
|---|---|---|
| Who kills the container? | kubelet | kernel OOM killer |
| Exit code | 137 (SIGKILL from kubelet) | 137 (SIGKILL from kernel) |
| Reason in `describe` | `Error` + liveness event | `OOMKilled` |
| Logs available? | Usually yes (partial) | Often empty |
| Fix category | Timing (probes) | Sizing (memory) |

## Fix (immediate)

### Option A — Raise the memory limit (fastest)

```bash
kubectl set resources deployment/ai-lab-oom -n ai-lab \
  --limits=memory=1Gi --requests=memory=512Mi
```

Or patch the manifest directly:

```yaml
resources:
  requests:
    cpu: 250m
    memory: 512Mi
  limits:
    cpu: "1"
    memory: 1Gi
```

Then re-apply:

```bash
kubectl apply -f k8s/base/deployment.yaml   # uses the healthy values
kubectl delete -f k8s/deployment-oom.yaml    # remove the broken overlay
```

### Option B — Reduce model memory footprint

- **Convert to TensorFlow Lite:**
  `tf.lite.TFLiteConverter.from_saved_model()` produces a `.tflite`
  flatbuffer that the TFLite interpreter can run in < 50 MiB.
- **Quantise the model:** post-training INT8 quantisation cuts weights by 4×.
- **Prune or distil:** replace large layers with smaller approximations.

### Option C — Lazy-load the model

Move model loading out of `main()` into the first `/predict` call so the
server starts with minimal memory and loads on demand:

```python
@app.route("/predict", methods=["POST"])
def predict():
    global _model, _ready
    if _model is None:
        _model = tf.keras.models.load_model(MODEL_DIR)
        _ready = True
    ...
```

This doesn't lower peak memory, but it lets the process pass liveness
probes while it is still light.

### Option D — Limit batch size

If the OOM happens during inference rather than import, cap the maximum
batch size or stream results to avoid allocating large intermediate
tensors all at once.

### Option E — Switch to a lighter runtime

For a tiny regression model like this lab's, you can export the weights
to plain NumPy and avoid the TensorFlow runtime entirely:

```python
import numpy as np
weights = [np.load(f) for f in sorted(Path(MODEL_DIR).glob("*.npy"))]
```

Peak RSS drops from ~400 MiB to ~30 MiB.

## Prevention (long-term)

- **Profile first, set limits second.**  Run `docker run --memory 1g`
  locally, exercise the full workload, then read peak RSS from
  `docker stats` or `/sys/fs/cgroup/memory/memory.max_usage_in_bytes`.
- **Set requests ≈ p50 usage, limits ≈ p99 + 25 % headroom.**  Avoid
  setting limits far below requests — it causes unpredictable kills under
  load.
- **Use VPA in recommendation mode** (`VerticalPodAutoscaler` with
  `updateMode: "Off"`) to get continuous sizing suggestions without
  automatic changes.
- **Alert on memory pressure:**
  `container_memory_working_set_bytes / container_spec_memory_limit_bytes > 0.85`
  — fire a warning before the kernel fires SIGKILL.
- **CI gate:** compare the image's documented memory floor against the
  limit in every manifest; fail the pipeline if limit < floor.
- **Consider `resources.requests` ≈ `resources.limits`** for ML workloads
  whose memory usage is predictable and flat.  This gives the pod a
  Guaranteed QoS class and makes it the last to be evicted.

## Verification

After applying the fix, confirm the pod is healthy:

```bash
# 1. Pod reaches 1/1 Ready with 0 restarts
kubectl get pods -n ai-lab -l app=ai-lab-oom
#    READY 1/1   STATUS Running   RESTARTS 0

# 2. No OOMKilled in last termination state
kubectl get pod -n ai-lab -l app=ai-lab-oom \
  -o jsonpath='{.items[0].status.containerStatuses[0].lastState}'
# → {} (empty — no previous termination)

# 3. Events are clean
kubectl get events -n ai-lab --sort-by=.metadata.creationTimestamp | grep -i oom
# (no output)

# 4. Readiness returns 200
kubectl exec -n ai-lab deploy/ai-lab-oom -- \
  curl -sf http://localhost:8080/readyz
# → {"status":"ready"}

# 5. Current memory usage is well within the new limit
kubectl top pod -n ai-lab -l app=ai-lab-oom
#    NAME                          CPU(cores)   MEMORY(bytes)
#    ai-lab-oom-...                12m          410Mi          (comfortably under 1 Gi)
```
