# Incident Runbook Template

Use this structure for every lab exercise or real incident review.

## Symptoms
- What broke from the user's point of view?
- Which endpoint, pod, or workflow failed?
- When did the problem start?

## Signals
- What do `kubectl get pods -n ai-lab` and `kubectl describe pod -n ai-lab <pod>` show?
- What do readiness and liveness endpoints return?
- What do container logs show?
- What changed recently: image, config, manifest, resource limit, or probe settings?

## Root Cause
- State the single most likely technical cause in one sentence.
- Include the exact object or setting involved, such as `MODEL_DIR`, memory limit, or probe timing.

## Fix
- List the shortest path to restore service.
- Include the exact command or manifest change used.
- Confirm recovery with one command and one expected output.

## Prevention
- Add one durable improvement for configuration validation, alerting, documentation, or safer defaults.
