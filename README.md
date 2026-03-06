# Cloud AI Troubleshooting Lab (Containers + Kubernetes)

A hands-on lab for practising real-world container and Kubernetes
troubleshooting with an AI/ML workload.  The application is a Flask API
serving a TensorFlow regression model, packaged in Docker, and deployable
to a local Kubernetes cluster via **kind**.

## Repository layout

```
.
├── app/
│   ├── app.py               # Flask inference API
│   └── requirements.txt      # Python dependencies
├── model/
│   ├── train_model.py        # Trains & exports a SavedModel
│   └── saved_model/          # (generated) TF SavedModel artefact
├── k8s/
│   ├── base/                 # Namespace, Deployment, Services
│   ├── failures/             # Failure-injection manifests
│   ├── deployment-slow-start.yaml  # Probe-failure overlay (STARTUP_DELAY_SEC=45)
│   ├── deployment-oom.yaml         # OOMKilled overlay (128 Mi limit)
│   ├── deployment-bad-config.yaml  # Wrong MODEL_DIR overlay
│   └── debug-pod.yaml              # netshoot pod for DNS debugging
├── runbooks/
│   ├── TEMPLATE.md           # Runbook authoring template
│   ├── TRIAGE_CHEATSHEET.md  # Symptom → commands → root cause lookup
│   ├── probe_failure.md      # CrashLoopBackOff (slow startup)
│   ├── oom_killed.md         # OOMKilled (memory limit)
│   ├── bad_config.md         # Wrong MODEL_DIR
│   └── dns_service_discovery.md  # DNS / service discovery
├── scripts/                  # Helper scripts (build, deploy, test)
├── Dockerfile
├── kind-config.yaml
└── README.md
```

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/healthz` | Liveness — always 200 while the process is alive |
| GET | `/readyz` | Readiness — 200 after model loads, 503 before |
| POST | `/predict` | Inference — `{"x": number}` → `{"x": …, "y": …}` |

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `MODEL_DIR` | `/model` | Path to the TF SavedModel directory |
| `STARTUP_DELAY_SEC` | `0` | Seconds to sleep before loading the model (fault injection) |
| `PORT` | `8080` | HTTP listen port |

## Triage flow

When something breaks, work through these five steps in order.  Each
step either identifies the problem or tells you where to look next.

**Step 1 — Get the big picture:**

```bash
kubectl get pods -n ai-lab -o wide
kubectl get events -n ai-lab --sort-by=.metadata.creationTimestamp
```

Read STATUS, READY, and RESTARTS.  Skim the events for `Unhealthy`,
`OOMKilling`, `BackOff`, or `FailedScheduling`.

**Step 2 — Zoom into the broken pod:**

```bash
kubectl describe pod -n ai-lab <pod>
```

Check the Events section (probe failures, image pulls, OOM kills), the
container State/Last State (exit code, reason), and the Environment
block (wrong env vars are visible here).

**Step 3 — Read the logs:**

```bash
kubectl logs -n ai-lab <pod> --tail=50
kubectl logs -n ai-lab <pod> --previous --tail=50
```

`--previous` shows the log from the last container that was killed —
critical for CrashLoopBackOff and OOMKilled pods where the current
container may not have written anything yet.

**Step 4 — Exec in for live debugging:**

```bash
kubectl exec -it -n ai-lab <pod> -- sh

# Inside the pod:
curl -sf http://localhost:8080/readyz        # readiness + error reason
env | grep MODEL_DIR                         # check config
ls /model                                    # verify filesystem
nslookup ai-lab.ai-lab.svc.cluster.local     # DNS resolution
curl -sf http://ai-lab/healthz               # service discovery
```

If the target pod is crashing, use the debug pod instead:

```bash
kubectl exec -it -n ai-lab debug-pod -- sh
```

**Step 5 — Check resource limits:**

```bash
kubectl top pods -n ai-lab
kubectl get pod <pod> -n ai-lab \
  -o jsonpath='{.spec.containers[0].resources}'
```

Compare actual usage (`top`) against the configured limits.  If usage is
near the limit, an OOM kill is imminent.

**Quick-reference:** see
[`runbooks/TRIAGE_CHEATSHEET.md`](runbooks/TRIAGE_CHEATSHEET.md) for a
symptom-to-root-cause lookup table, and
[`runbooks/TEMPLATE.md`](runbooks/TEMPLATE.md) for the runbook format.

---

## 1 — Local development (venv)

```bash
# Create and activate a virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r app/requirements.txt

# Train the model (writes model/saved_model/)
python model/train_model.py

# Run the server locally (point at the exported model)
MODEL_DIR=model/saved_model python app/app.py
```

In another terminal:

```bash
curl http://localhost:8080/healthz
curl http://localhost:8080/readyz
curl -X POST http://localhost:8080/predict \
  -H "Content-Type: application/json" \
  -d '{"x": 5}'
```

Expected `/predict` response (y ≈ 2·5 + 1 = 11):

```json
{"x": 5.0, "y": 10.95}
```

## 2 — Docker build

> **Pre-requisite:** the model must already be exported (`model/saved_model/`
> must exist).  Run the training step from section 1 first.

```bash
docker build -t ai-lab:latest .
```

## 3 — Docker run + curl tests

```bash
# Start the container
docker run --rm -p 8080:8080 --name ai-lab ai-lab:latest
```

In another terminal:

```bash
# Liveness
curl http://localhost:8080/healthz
# → {"status":"alive"}

# Readiness
curl http://localhost:8080/readyz
# → {"status":"ready"}

# Prediction
curl -X POST http://localhost:8080/predict \
  -H "Content-Type: application/json" \
  -d '{"x": 3}'
# → {"x":3.0,"y":6.98}

# Slow-startup simulation (in a separate run)
docker run --rm -p 8080:8080 -e STARTUP_DELAY_SEC=30 ai-lab:latest
# /readyz will return 503 for ~30 s, then 200

# Bad MODEL_DIR simulation
docker run --rm -p 8080:8080 -e MODEL_DIR=/nonexistent ai-lab:latest
# /readyz returns 503 permanently; check logs for FileNotFoundError
```

## 4 — Kubernetes (kind) deployment

See `scripts/kind-setup.sh` for the automated flow, or run manually:

```bash
# Create a kind cluster
kind create cluster --config kind-config.yaml --wait 60s

# Load the image into kind
kind load docker-image ai-lab:latest --name ai-lab

# Deploy base manifests
kubectl apply -f k8s/base/namespace.yaml
kubectl apply -f k8s/base/deployment.yaml
kubectl apply -f k8s/base/service.yaml

# Wait for rollout
kubectl rollout status deployment/ai-lab -n ai-lab --timeout=120s

# Port-forward and test
kubectl port-forward -n ai-lab svc/ai-lab 8080:80 &
curl http://localhost:8080/healthz
curl -X POST http://localhost:8080/predict \
  -H "Content-Type: application/json" -d '{"x": 7}'
```

## 5 — Failure-injection scenarios

| # | Scenario | Deploy command |
|---|----------|---------------|
| 1 | Probe failure / CrashLoopBackOff | `kubectl apply -f k8s/failures/slow-startup.yaml` |
| 2 | OOMKilled | `kubectl apply -f k8s/failures/oom-killed.yaml` |
| 3 | Config error (wrong MODEL_DIR) | `kubectl apply -f k8s/failures/wrong-model-dir.yaml` |
| 4 | DNS / service-discovery debug | `kubectl apply -f k8s/failures/dns-debug.yaml` |

Each scenario has a matching runbook in `runbooks/`.

---

## Failure Injection: Probe Failure (Slow Startup)

This scenario uses `k8s/deployment-slow-start.yaml` to demonstrate what
happens when a container takes longer to start than its probes allow.
`STARTUP_DELAY_SEC=45` makes the app sleep for 45 seconds before the Flask
server starts listening — but the liveness probe kills the container after
only ≈ 20 seconds, triggering a CrashLoopBackOff.

Full runbook: [`runbooks/probe_failure.md`](runbooks/probe_failure.md)

### Deploy the broken deployment

```bash
# Make sure the namespace exists (idempotent)
kubectl apply -f k8s/base/namespace.yaml

# Apply the slow-start overlay
kubectl apply -f k8s/deployment-slow-start.yaml
```

### Observe the failure

```bash
# Watch the pod cycle through Running → CrashLoopBackOff
kubectl get pods -n ai-lab -l scenario=slow-start -w
```

Expected output (RESTARTS keeps climbing):

```
NAME                                  READY   STATUS    RESTARTS   AGE
ai-lab-slow-start-6d8f9b7c45-x2k7p   0/1     Running   0          3s
ai-lab-slow-start-6d8f9b7c45-x2k7p   0/1     Running   1 (1s ago) 18s
ai-lab-slow-start-6d8f9b7c45-x2k7p   0/1     CrashLoopBackOff   1 (1s ago) 18s
```

### Inspect events and logs

```bash
# Events — look for "Liveness probe failed" and "connection refused"
kubectl describe pod -n ai-lab -l scenario=slow-start

# Current container logs (may be short)
kubectl logs -n ai-lab -l scenario=slow-start --tail=30

# Previous container's logs (the one that was killed)
kubectl logs -n ai-lab -l scenario=slow-start --previous --tail=30
```

### Fix it

Add a `startupProbe` that gives the container enough time to finish
its 45-second initialisation:

```bash
kubectl patch deployment ai-lab-slow-start -n ai-lab --type=json -p='[
  {"op":"add","path":"/spec/template/spec/containers/0/startupProbe","value":{
    "httpGet":{"path":"/healthz","port":"http"},
    "initialDelaySeconds":0,"periodSeconds":5,"failureThreshold":12
  }}
]'
```

Or remove the delay entirely to reset:

```bash
kubectl set env deployment/ai-lab-slow-start -n ai-lab STARTUP_DELAY_SEC=0
```

### Verify the fix

```bash
# Pod should reach 1/1 Ready with 0 restarts
kubectl get pods -n ai-lab -l scenario=slow-start

# Readiness returns 200
kubectl exec -n ai-lab deploy/ai-lab-slow-start -- \
  curl -sf http://localhost:8080/readyz

# No more probe failures in events
kubectl describe pod -n ai-lab -l scenario=slow-start | grep -i unhealthy
```

### Clean up

```bash
kubectl delete -f k8s/deployment-slow-start.yaml
```

---

## Failure Injection: OOMKilled

This scenario uses `k8s/deployment-oom.yaml` to demonstrate what happens
when a container's memory limit is lower than the runtime actually needs.
The limit is set to **128 Mi** — but TensorFlow CPU requires ≈ 300–500 Mi
just for `import tensorflow`.  The kernel OOM killer sends SIGKILL
(exit code 137) before the process finishes starting.

Full runbook: [`runbooks/oom_killed.md`](runbooks/oom_killed.md)

### Deploy the broken deployment

```bash
# Make sure the namespace exists
kubectl apply -f k8s/base/namespace.yaml

# Apply the OOM overlay
kubectl apply -f k8s/deployment-oom.yaml
```

### Observe the failure

```bash
# Watch the pod cycle through OOMKilled → CrashLoopBackOff
kubectl get pods -n ai-lab -l scenario=oom -w
```

Expected output:

```
NAME                            READY   STATUS      RESTARTS      AGE
ai-lab-oom-7b4d9f6c88-tn4w2    0/1     OOMKilled   0             5s
ai-lab-oom-7b4d9f6c88-tn4w2    0/1     CrashLoopBackOff   1 (2s ago)   12s
ai-lab-oom-7b4d9f6c88-tn4w2    0/1     OOMKilled   2 (1s ago)    25s
```

### Inspect events and logs

```bash
# Describe the pod — look for "Reason: OOMKilled" and "Exit Code: 137"
kubectl describe pod -n ai-lab -l scenario=oom

# Namespace events sorted by time — look for the OOMKilling / BackOff cycle
kubectl get events -n ai-lab --sort-by=.metadata.creationTimestamp

# Previous container logs — usually empty because the process was killed
# before writing any output
kubectl logs -n ai-lab -l scenario=oom --previous --tail=50
```

An empty `--previous` log combined with exit code 137 is the hallmark of
an early-startup OOM — the process never got far enough to emit a log line.

### Fix it

Raise the memory limit to match real usage:

```bash
kubectl set resources deployment/ai-lab-oom -n ai-lab \
  --limits=memory=1Gi --requests=memory=512Mi
```

Or delete the broken overlay and rely on the base deployment:

```bash
kubectl delete -f k8s/deployment-oom.yaml
```

### Verify the fix

```bash
# Pod should reach 1/1 Ready with 0 restarts
kubectl get pods -n ai-lab -l app=ai-lab-oom

# No OOMKilled in recent events
kubectl get events -n ai-lab --sort-by=.metadata.creationTimestamp | grep -i oom

# Readiness returns 200
kubectl exec -n ai-lab deploy/ai-lab-oom -- \
  curl -sf http://localhost:8080/readyz

# Memory usage is within the new limit
kubectl top pod -n ai-lab -l app=ai-lab-oom
```

### Clean up

```bash
kubectl delete -f k8s/deployment-oom.yaml
```

---

## Failure Injection: Bad Configuration (Wrong MODEL_DIR)

This scenario uses `k8s/deployment-bad-config.yaml` to demonstrate a
misconfigured environment variable.  `MODEL_DIR` is set to
`/wrong_model_path`, which does not exist in the container.  The app logs
an explicit error with the exception text, Flask starts normally
(`/healthz` → 200), but `/readyz` returns 503 forever because the model
never loads.

The pod shows **Running 0/1 Ready** with **zero restarts** — the subtlest
failure mode.  No traffic is routed to it.

Full runbook: [`runbooks/bad_config.md`](runbooks/bad_config.md)

### Deploy the broken deployment

```bash
# Make sure the namespace exists
kubectl apply -f k8s/base/namespace.yaml

# Apply the bad-config overlay
kubectl apply -f k8s/deployment-bad-config.yaml
```

### Observe the failure

```bash
# Watch — the pod will be Running but 0/1 Ready, with 0 restarts
kubectl get pods -n ai-lab -l scenario=bad-config -w
```

Expected output:

```
NAME                                  READY   STATUS    RESTARTS   AGE
ai-lab-bad-config-5f7d8c9b64-k9m3r   0/1     Running   0          10s
```

### Troubleshoot

**Check the logs — look for the explicit error message and traceback:**

```bash
kubectl logs -n ai-lab -l scenario=bad-config --tail=50
```

Expected:

```
PORT=8080  MODEL_DIR=/wrong_model_path  STARTUP_DELAY_SEC=0
MODEL_DIR path does not exist: /wrong_model_path
Model load failed at startup — readyz will return 503
Traceback (most recent call last):
  ...
FileNotFoundError: MODEL_DIR path does not exist: /wrong_model_path
```

**Describe the pod — look for readiness probe 503s and the env vars:**

```bash
kubectl describe pod -n ai-lab -l scenario=bad-config
```

Look for `Readiness probe failed: HTTP probe failed with statuscode: 503`
in Events, and `MODEL_DIR: /wrong_model_path` in the Environment section.

**Check env vars in the running pod:**

```bash
kubectl exec -n ai-lab deploy/ai-lab-bad-config -- env | grep MODEL_DIR
# → MODEL_DIR=/wrong_model_path
```

**Curl readyz from inside the pod — the error message is in the response:**

```bash
kubectl exec -n ai-lab deploy/ai-lab-bad-config -- \
  curl -sf http://localhost:8080/readyz
# → {"error":"MODEL_DIR path does not exist: /wrong_model_path","status":"not_ready"}
```

**Confirm the path doesn't exist:**

```bash
kubectl exec -n ai-lab deploy/ai-lab-bad-config -- ls /wrong_model_path
# → No such file or directory

kubectl exec -n ai-lab deploy/ai-lab-bad-config -- ls /model
# → assets  fingerprint.pb  keras_metadata.pb  saved_model.pb  variables
```

### Fix it

Patch the environment variable to the correct path:

```bash
kubectl set env deployment/ai-lab-bad-config -n ai-lab MODEL_DIR=/model
```

Or delete the overlay:

```bash
kubectl delete -f k8s/deployment-bad-config.yaml
```

### Verify the fix

```bash
# Pod should reach 1/1 Ready
kubectl get pods -n ai-lab -l scenario=bad-config

# Readiness returns 200
kubectl exec -n ai-lab deploy/ai-lab-bad-config -- \
  curl -sf http://localhost:8080/readyz

# Prediction works
kubectl exec -n ai-lab deploy/ai-lab-bad-config -- \
  curl -sf -X POST http://localhost:8080/predict \
  -H "Content-Type: application/json" -d '{"x": 5}'
```

### Clean up

```bash
kubectl delete -f k8s/deployment-bad-config.yaml
```

---

## DNS / Service Discovery Checks

This section uses `k8s/debug-pod.yaml` — a lightweight pod running
[nicolaka/netshoot](https://github.com/nicolaka/netshoot) with `curl`,
`dig`, `nslookup`, `wget`, `ping`, `ip`, and `tcpdump` pre-installed.
Use it to verify cluster DNS and end-to-end connectivity to the `ai-lab`
Service.

Full runbook: [`runbooks/dns_service_discovery.md`](runbooks/dns_service_discovery.md)

### Prerequisites

The base deployment and Service must be running:

```bash
kubectl apply -f k8s/base/namespace.yaml
kubectl apply -f k8s/base/deployment.yaml
kubectl apply -f k8s/base/service.yaml
kubectl rollout status deployment/ai-lab -n ai-lab --timeout=120s
```

### Launch the debug pod

```bash
kubectl apply -f k8s/debug-pod.yaml
kubectl wait --for=condition=Ready pod/debug-pod -n ai-lab --timeout=30s
```

### Shell into the debug pod

```bash
kubectl exec -it -n ai-lab debug-pod -- sh
```

### DNS resolution

Inside the debug pod:

```bash
# nslookup — basic name resolution
nslookup ai-lab.ai-lab.svc.cluster.local

# dig — detailed query with status code and answer section
dig ai-lab.ai-lab.svc.cluster.local

# Verify cluster DNS itself is working (Kubernetes API service)
nslookup kubernetes.default.svc.cluster.local
```

Expected `nslookup` output:

```
Server:    10.96.0.10
Address:   10.96.0.10#53

Name:   ai-lab.ai-lab.svc.cluster.local
Address: 10.96.XXX.XXX
```

If you get `NXDOMAIN`, the service name or namespace is wrong.  If the
query times out, CoreDNS may be down or a NetworkPolicy is blocking
port 53.

### HTTP connectivity

Inside the debug pod:

```bash
# Full FQDN (works from any namespace)
curl -sf http://ai-lab.ai-lab.svc.cluster.local/healthz
# → {"status":"alive"}

# Short name (works from the same namespace)
curl -sf http://ai-lab/readyz
# → {"status":"ready"}

# Prediction via the Service
curl -sf -X POST http://ai-lab/predict \
  -H "Content-Type: application/json" -d '{"x": 5}'
# → {"x":5.0,"y":10.95}
```

### Inspect endpoints and selectors

From your local terminal (not inside the debug pod):

```bash
# Endpoints — should list pod IPs
kubectl get endpoints ai-lab -n ai-lab

# Service selector
kubectl get svc ai-lab -n ai-lab -o jsonpath='{.spec.selector}'
# → {"app":"ai-lab"}

# Pod labels (must match the selector)
kubectl get pods -n ai-lab --show-labels

# CoreDNS health
kubectl get pods -n kube-system -l k8s-app=kube-dns
```

If `endpoints` shows `<none>`, either no pods match the Service selector
or all matching pods are not Ready.  See
[`runbooks/dns_service_discovery.md`](runbooks/dns_service_discovery.md)
for the full root-cause matrix.

### Clean up

```bash
kubectl delete -f k8s/debug-pod.yaml
```

---

## Tear-down

```bash
kind delete cluster --name ai-lab
docker rmi ai-lab:latest
```
