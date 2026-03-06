# Cloud AI Troubleshooting Lab (Containers + Kubernetes)

A hands-on lab for practicing real-world container and Kubernetes troubleshooting with an AI/ML workload. The application is a Flask API serving a TensorFlow model, packaged in Docker, and deployed to a local Kubernetes cluster via **kind**.

Four failure-injection scenarios let you practice diagnosing common production issues:

| # | Scenario | Manifest | Runbook |
|---|----------|----------|---------|
| 1 | Probe failure / CrashLoopBackOff (slow startup) | `k8s/failures/slow-startup.yaml` | `runbooks/01-probe-failure-crashloop.md` |
| 2 | OOMKilled (tight memory limit) | `k8s/failures/oom-killed.yaml` | `runbooks/02-oomkilled.md` |
| 3 | Config error (wrong MODEL_DIR) | `k8s/failures/wrong-model-dir.yaml` | `runbooks/03-config-error-wrong-model-dir.md` |
| 4 | DNS / service-discovery check | `k8s/failures/dns-debug.yaml` | `runbooks/04-dns-service-discovery.md` |

## Prerequisites

- **Docker** (20.10+)
- **kind** (v0.20+) — `go install sigs.k8s.io/kind@latest` or `brew install kind`
- **kubectl** (v1.27+)
- **curl** (for testing endpoints)

## Repository Structure

```
.
├── app/
│   ├── __init__.py
│   ├── server.py          # Flask API with health/readiness probes
│   └── train.py           # Model training script
├── k8s/
│   ├── base/
│   │   ├── namespace.yaml
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   └── service-nodeport.yaml
│   └── failures/
│       ├── slow-startup.yaml
│       ├── oom-killed.yaml
│       ├── wrong-model-dir.yaml
│       └── dns-debug.yaml
├── runbooks/
│   ├── 01-probe-failure-crashloop.md
│   ├── 02-oomkilled.md
│   ├── 03-config-error-wrong-model-dir.md
│   └── 04-dns-service-discovery.md
├── scripts/
│   ├── build.sh
│   ├── run-docker.sh
│   ├── kind-setup.sh
│   ├── deploy-failure.sh
│   └── test-endpoints.sh
├── kind-config.yaml
├── Dockerfile
├── requirements.txt
└── README.md
```

## Quick Start

### 1. Build the Docker Image

The multi-stage Dockerfile trains the model in the `train` stage and packages it into the `serve` stage:

```bash
./scripts/build.sh
```

This runs `docker build --target serve -t ai-lab:latest .`

### 2. Run Locally with Docker

```bash
./scripts/run-docker.sh
```

In another terminal, test the endpoints:

```bash
./scripts/test-endpoints.sh
# or manually:
curl http://localhost:8080/healthz
curl http://localhost:8080/readyz
curl http://localhost:8080/info
curl -X POST http://localhost:8080/predict \
  -H "Content-Type: application/json" \
  -d '{"instances": [[0.1, 0.2, 0.3, 0.4]]}'
```

### 3. Create a kind Cluster and Deploy

```bash
./scripts/kind-setup.sh
```

This creates a 3-node kind cluster (`ai-lab`), loads the Docker image, applies the base manifests, and waits for the rollout.

### 4. Access the Service

**Option A — port-forward (recommended):**

```bash
kubectl port-forward -n ai-lab svc/ai-lab 8080:80
curl http://localhost:8080/healthz
```

**Option B — NodePort:**

The `service-nodeport.yaml` exposes port 30080 on the kind host:

```bash
curl http://localhost:30080/healthz
```

### 5. Test All Endpoints

```bash
./scripts/test-endpoints.sh
# or with a custom base URL:
BASE_URL=http://localhost:30080 ./scripts/test-endpoints.sh
```

## Failure Injection Scenarios

### Deploy a Scenario

```bash
# One at a time:
./scripts/deploy-failure.sh slow-startup
./scripts/deploy-failure.sh oom-killed
./scripts/deploy-failure.sh wrong-model-dir
./scripts/deploy-failure.sh dns-debug

# All at once:
./scripts/deploy-failure.sh all
```

### Investigate

Use standard kubectl commands to observe the failures:

```bash
# Pod status overview
kubectl get pods -n ai-lab -o wide

# Detailed events and probe failures
kubectl describe pod -n ai-lab <pod-name>

# Container logs (structured JSON)
kubectl logs -n ai-lab <pod-name> --tail=50

# Previous container logs (useful after restarts)
kubectl logs -n ai-lab <pod-name> --previous

# DNS debugging from the debug pod
kubectl exec -it -n ai-lab dns-debug -- sh
# then: nslookup ai-lab.ai-lab.svc.cluster.local
# then: curl http://ai-lab.ai-lab.svc.cluster.local/healthz
```

Refer to the matching runbook in `runbooks/` for each scenario's symptoms, signals, root cause, fix, and prevention steps.

### Clean Up Failure Scenarios

```bash
./scripts/deploy-failure.sh clean
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/healthz` | Liveness probe — always 200 if process is alive |
| GET | `/readyz` | Readiness probe — 200 after model loads, 503 otherwise |
| GET | `/info` | Runtime metadata (model dir, TF version, hostname) |
| POST | `/predict` | Inference — body: `{"instances": [[f1, f2, f3, f4]]}` |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MODEL_DIR` | `/app/model` | Path to the saved TensorFlow model |
| `PORT` | `8080` | HTTP listen port |
| `STARTUP_DELAY` | `0` | Seconds to sleep before loading model (fault injection) |
| `LOG_LEVEL` | `INFO` | Python log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

## Tear Down

```bash
# Delete the kind cluster
kind delete cluster --name ai-lab

# Remove the Docker image
docker rmi ai-lab:latest
```
