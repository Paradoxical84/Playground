#!/usr/bin/env bash
set -euo pipefail

CLUSTER_NAME="ai-lab"
IMAGE_NAME="${IMAGE_NAME:-ai-lab}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

echo "==> Creating kind cluster '${CLUSTER_NAME}'"
kind create cluster --config kind-config.yaml --wait 60s 2>/dev/null || {
  echo "    Cluster already exists or creation failed; continuing..."
}

echo "==> Loading image ${IMAGE_NAME}:${IMAGE_TAG} into kind"
kind load docker-image "${IMAGE_NAME}:${IMAGE_TAG}" --name "${CLUSTER_NAME}"

echo "==> Applying base manifests"
kubectl apply -f k8s/base/namespace.yaml
kubectl apply -f k8s/base/deployment.yaml
kubectl apply -f k8s/base/service.yaml
kubectl apply -f k8s/base/service-nodeport.yaml

echo "==> Waiting for rollout"
kubectl rollout status deployment/ai-lab -n ai-lab --timeout=120s

echo "==> Pods:"
kubectl get pods -n ai-lab -o wide

echo ""
echo "==> Cluster ready. Access via:"
echo "    kubectl port-forward -n ai-lab svc/ai-lab 8080:80"
echo "    curl http://localhost:8080/healthz"
