# Cloud AI Troubleshooting Lab (Containers + Kubernetes)

Minimal Flask + TensorFlow CPU inference service designed for troubleshooting practice in Docker and local Kubernetes with kind.

## What this lab includes

- Python 3.11 service using Flask and `tensorflow-cpu==2.15.1`
- Structured JSON logging to stdout
- `/healthz` and `/readyz` endpoints
- Small train-once synthetic regression model
- Docker image for local runs
- Kubernetes manifests for kind with:
  - liveness and readiness probes
  - resource requests and limits
  - failure-injection overlays
  - separate debug pod for DNS and service discovery checks

## Repository layout

```text
app/                    Flask API and model loading
scripts/train_model.py  Creates the local TensorFlow SavedModel
kind/cluster.yaml       kind cluster config with host port mapping
k8s/base/               Healthy deployment and debug pod
k8s/overlays/           Failure scenarios
runbooks/               Troubleshooting templates and scenario guides
```

## Prerequisites

- Python 3.11
- Docker
- kubectl
- kind

## 1) Create a local Python environment

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 2) Train the model

This writes a TensorFlow SavedModel to `models/demo-model`.

```bash
python scripts/train_model.py
```

Quick sanity check:

```bash
python -c "import tensorflow as tf; model=tf.keras.models.load_model('models/demo-model'); print(model.predict([[1.5,-0.5]], verbose=0))"
```

Expected output is a value close to `6.5`.

## 3) Build the Docker image

```bash
docker build -t cloud-ai-lab:local .
```

## 4) Run locally with Docker

### Healthy run

```bash
docker run --rm -p 8080:8080 cloud-ai-lab:local
```

In another terminal:

```bash
curl http://localhost:8080/healthz
curl http://localhost:8080/readyz
curl -X POST http://localhost:8080/predict \
  -H 'Content-Type: application/json' \
  -d '{"features":[1.5,-0.5]}'
```

### Failure injection with Docker

#### Slow startup

```bash
docker run --rm -p 8080:8080 -e STARTUP_DELAY_SECONDS=45 cloud-ai-lab:local
```

#### Config error

```bash
docker run --rm -p 8080:8080 -e MODEL_DIR=/app/models/does-not-exist cloud-ai-lab:local
```

Then check:

```bash
curl http://localhost:8080/readyz
```

#### Memory pressure

This simulates an OOM-style crash by allocating more memory than a tight container limit allows.

```bash
docker run --rm -p 8080:8080 --memory=256m -e MEMORY_HOG_MIB=384 cloud-ai-lab:local
```

## 5) Create a kind cluster

The supplied kind config maps host port `8080` to the Kubernetes service NodePort `30080`.

```bash
kind create cluster --name ai-lab --config kind/cluster.yaml
```

## 6) Load the image into kind

```bash
kind load docker-image cloud-ai-lab:local --name ai-lab
```

## 7) Deploy the healthy Kubernetes base

```bash
kubectl apply -k k8s/base
kubectl rollout status deployment/lab-api -n ai-lab
kubectl get pods -n ai-lab
kubectl get svc -n ai-lab
```

## 8) Test the Kubernetes deployment

From the host:

```bash
curl http://localhost:8080/healthz
curl http://localhost:8080/readyz
curl -X POST http://localhost:8080/predict \
  -H 'Content-Type: application/json' \
  -d '{"features":[1.5,-0.5]}'
```

From inside the cluster using the debug pod:

```bash
kubectl exec -n ai-lab debug-shell -- nslookup lab-api.ai-lab.svc.cluster.local
kubectl exec -n ai-lab debug-shell -- wget -qO- http://lab-api.ai-lab.svc.cluster.local/healthz
kubectl exec -n ai-lab debug-shell -- wget -qO- http://lab-api.ai-lab.svc.cluster.local/readyz
```

## 9) Failure-injection scenarios on Kubernetes

Start from a healthy deployment, then apply one overlay at a time.

### A. Probe failures from slow startup

```bash
kubectl delete -k k8s/base
kubectl apply -k k8s/overlays/slow-startup
kubectl get pods -n ai-lab -w
kubectl describe pod -n ai-lab -l app=lab-api
kubectl logs -n ai-lab deploy/lab-api --previous
```

What to expect:
- restart loop
- probe failures in pod events
- delayed startup message in logs

### B. OOMKilled from a tight memory limit

```bash
kubectl delete -k k8s/base
kubectl apply -k k8s/overlays/oomkill
kubectl get pods -n ai-lab -w
kubectl describe pod -n ai-lab -l app=lab-api
kubectl logs -n ai-lab deploy/lab-api --previous
```

What to expect:
- `OOMKilled` in the pod status
- repeated restarts

### C. Config error from the wrong `MODEL_DIR`

```bash
kubectl delete -k k8s/base
kubectl apply -k k8s/overlays/config-error
kubectl get pods -n ai-lab
curl http://localhost:8080/readyz
kubectl logs -n ai-lab deploy/lab-api
```

What to expect:
- pod stays running
- readiness returns `503`
- logs show model loading failure

### D. DNS and service discovery checks from the debug pod

Keep either the healthy base or the config-error overlay deployed, then run:

```bash
kubectl exec -n ai-lab debug-shell -- nslookup lab-api.ai-lab.svc.cluster.local
kubectl exec -n ai-lab debug-shell -- wget -qO- http://lab-api.ai-lab.svc.cluster.local/healthz
kubectl get endpoints -n ai-lab lab-api
```

## Reset back to healthy

```bash
kubectl delete -k k8s/overlays/slow-startup --ignore-not-found
kubectl delete -k k8s/overlays/oomkill --ignore-not-found
kubectl delete -k k8s/overlays/config-error --ignore-not-found
kubectl apply -k k8s/base
kubectl rollout status deployment/lab-api -n ai-lab
```

## Useful troubleshooting commands

```bash
kubectl get all -n ai-lab
kubectl describe deployment -n ai-lab lab-api
kubectl describe pod -n ai-lab -l app=lab-api
kubectl logs -n ai-lab deploy/lab-api
kubectl logs -n ai-lab deploy/lab-api --previous
kubectl exec -n ai-lab deploy/lab-api -- printenv | sort
```

## Runbooks

- `runbooks/incident-template.md`
- `runbooks/slow-startup-probe-failure.md`
- `runbooks/oomkilled-memory-limit.md`
- `runbooks/model-dir-config-error.md`
- `runbooks/dns-service-discovery.md`

## Cleanup

```bash
kind delete cluster --name ai-lab
docker rmi cloud-ai-lab:local
```