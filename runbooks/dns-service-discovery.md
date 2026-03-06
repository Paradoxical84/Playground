# Runbook: DNS and Service Discovery Check

## Symptoms
- The application pod is healthy, but another workload cannot reach it by service name.
- Calls fail with DNS resolution errors, timeouts, or `Connection refused`.
- The issue only appears inside Kubernetes, not from the host.

## Signals
- `kubectl exec -n ai-lab debug-shell -- nslookup lab-api.ai-lab.svc.cluster.local` shows whether cluster DNS resolves the service.
- `kubectl exec -n ai-lab debug-shell -- wget -qO- http://lab-api.ai-lab.svc.cluster.local/healthz` tests in-cluster HTTP reachability.
- `kubectl get svc -n ai-lab lab-api -o wide` confirms the service and cluster IP exist.
- `kubectl get endpoints -n ai-lab lab-api` confirms the service has backing pod endpoints.

## Root Cause
- DNS or service discovery fails because the service name is wrong, the service has no ready endpoints, or cluster networking is unhealthy.

## Fix
- Check the service name first, then confirm endpoints, then verify CoreDNS if name resolution is failing.
- Debug commands:

```bash
kubectl exec -n ai-lab debug-shell -- nslookup lab-api.ai-lab.svc.cluster.local
kubectl exec -n ai-lab debug-shell -- wget -qO- http://lab-api.ai-lab.svc.cluster.local/readyz
kubectl get endpoints -n ai-lab lab-api
```

- Expected result: `nslookup` returns a cluster IP and `wget` returns a JSON response.

## Prevention
- Use stable service names and document the fully qualified in-cluster DNS name.
- Include a simple debug pod in non-production environments for rapid DNS and HTTP checks.
- Alert on ready endpoint count dropping to zero for critical services.
