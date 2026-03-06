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

echo "--- POST /predict ---"
curl -s -w "\nHTTP %{http_code}\n" \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"x": 5}' \
  "${BASE_URL}/predict" | python3 -m json.tool 2>/dev/null || \
  curl -s -w "\nHTTP %{http_code}\n" \
    -X POST \
    -H "Content-Type: application/json" \
    -d '{"x": 5}' \
    "${BASE_URL}/predict"
echo ""

echo "==> All endpoint tests complete."
