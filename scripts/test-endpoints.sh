#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8080}"

echo "==> Testing endpoints at ${BASE_URL}"
echo ""

echo "--- GET /healthz ---"
curl -s -w "\nHTTP %{http_code}\n" "${BASE_URL}/healthz"
echo ""

echo "--- GET /readyz ---"
curl -s -w "\nHTTP %{http_code}\n" "${BASE_URL}/readyz"
echo ""

echo "--- GET /info ---"
curl -s -w "\nHTTP %{http_code}\n" "${BASE_URL}/info" | python3 -m json.tool 2>/dev/null || \
  curl -s -w "\nHTTP %{http_code}\n" "${BASE_URL}/info"
echo ""

echo "--- POST /predict ---"
curl -s -w "\nHTTP %{http_code}\n" \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"instances": [[0.1, 0.2, 0.3, 0.4], [0.9, 0.8, 0.7, 0.6]]}' \
  "${BASE_URL}/predict" | python3 -m json.tool 2>/dev/null || \
  curl -s -w "\nHTTP %{http_code}\n" \
    -X POST \
    -H "Content-Type: application/json" \
    -d '{"instances": [[0.1, 0.2, 0.3, 0.4], [0.9, 0.8, 0.7, 0.6]]}' \
    "${BASE_URL}/predict"
echo ""

echo "==> All endpoint tests complete."
