# Runbook: Wrong MODEL_DIR Configuration

## Symptoms
- The pod is running but never becomes ready.
- `/healthz` succeeds while `/readyz` returns HTTP 503.
- `/predict` returns a service-not-ready error.

## Signals
- `kubectl logs -n ai-lab deploy/lab-api` shows `Model failed to load`.
- `kubectl exec -n ai-lab deploy/lab-api -- printenv MODEL_DIR` shows the wrong path.
- `curl http://localhost:8080/readyz` returns a JSON payload containing the bad `model_dir` and the load error.
- The config-error overlay changes `MODEL_DIR` to `/app/models/does-not-exist`.

## Root Cause
- The application was configured with a model path that does not exist in the container image, so readiness never becomes true.

## Fix
- Revert the config overlay or correct the `MODEL_DIR` value.
- Recovery commands:

```bash
kubectl delete -k k8s/overlays/config-error
kubectl apply -k k8s/base
kubectl rollout status deployment/lab-api -n ai-lab
```

- Confirm recovery:

```bash
curl http://localhost:8080/readyz
curl -X POST http://localhost:8080/predict -H 'Content-Type: application/json' -d '{"features":[1.5,-0.5]}'
```

- Expected result: readiness returns HTTP 200 and prediction returns HTTP 200 with a numeric output.

## Prevention
- Validate required file paths at startup and surface failures through readiness checks.
- Keep config in a ConfigMap or Helm values file with code review on path changes.
- Add a smoke test that verifies the expected model path exists in the built image.
