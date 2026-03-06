#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="${IMAGE_NAME:-ai-lab}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

echo "==> Building Docker image ${IMAGE_NAME}:${IMAGE_TAG}"
docker build \
  --target serve \
  -t "${IMAGE_NAME}:${IMAGE_TAG}" \
  .

echo "==> Done. Image: ${IMAGE_NAME}:${IMAGE_TAG}"
docker images "${IMAGE_NAME}:${IMAGE_TAG}"
