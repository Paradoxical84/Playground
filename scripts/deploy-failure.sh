#!/usr/bin/env bash
set -euo pipefail

SCENARIO="${1:-}"

if [[ -z "$SCENARIO" ]]; then
  echo "Usage: $0 <scenario>"
  echo ""
  echo "Available scenarios:"
  echo "  slow-startup    - Probe failure via 60 s startup delay"
  echo "  oom-killed      - OOMKilled via 64 Mi memory limit"
  echo "  wrong-model-dir - Config error: nonexistent MODEL_DIR"
  echo "  dns-debug       - DNS/service-discovery debug pod"
  echo "  all             - Deploy all failure scenarios"
  echo "  clean           - Delete all failure-scenario resources"
  exit 1
fi

case "$SCENARIO" in
  slow-startup)
    echo "==> Deploying slow-startup scenario"
    kubectl apply -f k8s/failures/slow-startup.yaml
    ;;
  oom-killed)
    echo "==> Deploying OOM scenario"
    kubectl apply -f k8s/failures/oom-killed.yaml
    ;;
  wrong-model-dir)
    echo "==> Deploying wrong-model-dir scenario"
    kubectl apply -f k8s/failures/wrong-model-dir.yaml
    ;;
  dns-debug)
    echo "==> Deploying DNS debug pod"
    kubectl apply -f k8s/failures/dns-debug.yaml
    ;;
  all)
    echo "==> Deploying all failure scenarios"
    kubectl apply -f k8s/failures/
    ;;
  clean)
    echo "==> Cleaning up failure scenarios"
    kubectl delete -f k8s/failures/ --ignore-not-found
    ;;
  *)
    echo "Unknown scenario: $SCENARIO"
    exit 1
    ;;
esac

echo ""
echo "==> Current pods in ai-lab namespace:"
kubectl get pods -n ai-lab -o wide
