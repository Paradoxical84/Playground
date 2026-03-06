# Runbook: <Title — one-line description of the failure>

Applies to: `<path to the k8s manifest or component>`

---

## Symptoms

What does the engineer see at a glance?

- Pod STATUS in `kubectl get pods` (CrashLoopBackOff, OOMKilled, Running 0/1, etc.)
- READY column (0/1 vs 1/1)
- RESTARTS count (climbing vs 0)
- User-facing impact (503s, timeouts, connection refused)

Paste the exact `kubectl get pods` output that characterises this failure.

## Signals

Numbered investigation steps.  Each step = one command + what to look for
in the output.

### 1. <command category>

```bash
kubectl <exact command>
```

What the output means when the failure is present vs healthy.

### 2. <next command>

```bash
kubectl <exact command>
```

Key fragments to search for in the output.

_(Continue numbering as needed.  Typically 3–7 steps.)_

## Root cause

One or two paragraphs explaining **why** the failure happens at the
system level.  Reference the specific config value, probe timing,
resource limit, or DNS name that is wrong.

If useful, include a comparison table showing how this failure differs
from similar-looking ones.

## Fix (immediate)

### Option A — <fastest fix>

Exact command to run.  Prefer `kubectl set ...` / `kubectl patch ...`
one-liners that can be copy-pasted.

### Option B — <alternative fix>

Different approach (edit manifest, delete overlay, etc.).

_(Include as many options as are practical.)_

## Prevention (long-term)

Bullet list of practices that stop this failure from recurring:

- Monitoring / alerting (which metric, what threshold)
- CI checks (what to lint or validate)
- Architecture changes (startupProbe, init containers, ConfigMaps, etc.)

## Verification

After applying the fix, numbered steps that confirm the pod is healthy.
Each step = one command + expected output.

```bash
# 1. Pod is Ready
kubectl get pods -n <ns> -l <selector>
# → READY 1/1   STATUS Running   RESTARTS 0

# 2. Endpoint returns 200
kubectl exec -n <ns> deploy/<name> -- curl -sf http://localhost:8080/readyz
# → {"status":"ready"}

# 3. No error events
kubectl describe pod -n <ns> -l <selector> | grep -i <error keyword>
# (no output)
```
