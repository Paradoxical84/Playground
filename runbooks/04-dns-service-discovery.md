# Runbook: DNS / Service Discovery Failures

## Symptoms

- Application logs show connection errors to other services.
- `curl http://ai-lab.ai-lab.svc.cluster.local/healthz` times out or
  returns `Could not resolve host`.
- Pods can reach external IPs but not cluster DNS names.

## Signals

```bash
# Deploy the debug pod
kubectl apply -f k8s/failures/dns-debug.yaml

# Shell into it
kubectl exec -it -n ai-lab dns-debug -- sh

# Inside the debug pod:
nslookup ai-lab.ai-lab.svc.cluster.local
nslookup kubernetes.default.svc.cluster.local
dig ai-lab.ai-lab.svc.cluster.local
curl -s http://ai-lab.ai-lab.svc.cluster.local/healthz

# Check CoreDNS pods
kubectl get pods -n kube-system -l k8s-app=kube-dns
kubectl logs -n kube-system -l k8s-app=kube-dns --tail=30
```

**What to look for:**

- `nslookup` returning `NXDOMAIN` or `server can't find ...`
- CoreDNS pods not running or in CrashLoopBackOff.
- NetworkPolicy blocking DNS traffic on port 53.
- Service selector not matching any pod labels.

## Root Cause (Common Cases)

| Cause | Signal |
|---|---|
| Service selector mismatch | `kubectl get endpoints ai-lab -n ai-lab` shows no endpoints |
| CoreDNS down | Pods in `kube-system` not ready |
| NetworkPolicy blocking DNS | Port 53 UDP/TCP blocked |
| Wrong namespace in FQDN | `nslookup` returns NXDOMAIN |
| Pod not in same cluster network | `ip route` shows no cluster CIDR |

## Fix

Depends on root cause:

1. **Selector mismatch:** Align `spec.selector` in the Service with pod labels.
2. **CoreDNS down:** `kubectl rollout restart deployment/coredns -n kube-system`.
3. **NetworkPolicy:** Add an egress rule allowing UDP/TCP port 53.
4. **Wrong namespace:** Use the correct FQDN:
   `<service>.<namespace>.svc.cluster.local`.

## Prevention

- Always verify `kubectl get endpoints` after creating a Service.
- Include DNS connectivity checks in readiness probes of dependent services.
- Monitor CoreDNS error rate and latency.
- Use short names (`ai-lab`) within the same namespace; use FQDNs cross-namespace.
