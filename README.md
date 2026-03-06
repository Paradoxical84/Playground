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
│   └── failures/             # Failure-injection manifests
├── runbooks/                 # Troubleshooting runbooks
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

## Tear-down

```bash
kind delete cluster --name ai-lab
docker rmi ai-lab:latest
```
