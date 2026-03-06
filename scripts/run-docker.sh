#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="${IMAGE_NAME:-ai-lab}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
CONTAINER_NAME="${CONTAINER_NAME:-ai-lab}"
HOST_PORT="${HOST_PORT:-8080}"

echo "==> Running container ${CONTAINER_NAME} on port ${HOST_PORT}"
docker run --rm \
  --name "${CONTAINER_NAME}" \
  -p "${HOST_PORT}:8080" \
  -e MODEL_DIR=/model \
  -e STARTUP_DELAY_SEC=0 \
  "${IMAGE_NAME}:${IMAGE_TAG}"
