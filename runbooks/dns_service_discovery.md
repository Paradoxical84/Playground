# Runbook: DNS / Service Discovery Failures

Applies to: `k8s/debug-pod.yaml` + base Service `ai-lab` in namespace `ai-lab`

---

## Symptoms

- Requests from one pod to another via the Service name fail with
  **"Could not resolve host"** or **connection timeout**.
- `curl http://ai-lab/healthz` from inside the cluster hangs or errors.
- Pods can reach external IPs (e.g. `curl 1.1.1.1`) but not cluster
  DNS names.
- Application logs show connection-refused or name-resolution errors when
  calling dependent services.

## Signals

### 1. Launch the debug pod

```bash
kubectl apply -f k8s/debug-pod.yaml
kubectl wait --for=condition=Ready pod/debug-pod -n ai-lab --timeout=30s
kubectl exec -it -n ai-lab debug-pod -- sh
```

All commands below run **inside the debug pod shell**.

### 2. DNS resolution — nslookup

```bash
nslookup ai-lab.ai-lab.svc.cluster.local
```

Healthy output:

```
Server:    10.96.0.10
Address:   10.96.0.10#53

Name:   ai-lab.ai-lab.svc.cluster.local
Address: 10.96.XXX.XXX
```

Broken output (wrong name, wrong namespace, or DNS down):

```
** server can't find ai-lab.ai-lab.svc.cluster.local: NXDOMAIN
```

Also test the Kubernetes API service to confirm DNS itself is working:

```bash
nslookup kubernetes.default.svc.cluster.local
```

If this also fails, the problem is cluster DNS, not the application
Service.

### 3. DNS resolution — dig (more detail)

```bash
dig ai-lab.ai-lab.svc.cluster.local
```

Look for:

- `status: NOERROR` and an `ANSWER SECTION` with the ClusterIP → healthy.
- `status: NXDOMAIN` → the Service name or namespace is wrong, or the
  Service does not exist.
- `status: SERVFAIL` → CoreDNS is up but cannot resolve — check CoreDNS
  logs.
- Connection timeout → DNS traffic (UDP/TCP 53) may be blocked by a
  NetworkPolicy.

### 4. HTTP connectivity — curl the Service

```bash
curl -sv http://ai-lab.ai-lab.svc.cluster.local/healthz
```

Expected:

```
< HTTP/1.1 200 OK
{"status":"alive"}
```

If DNS resolves but curl fails:

- **Connection refused** → the Service has no ready endpoints (pods not
  ready, selector mismatch, or deployment scaled to 0).
- **Connection timeout** → a NetworkPolicy is blocking traffic on the
  Service port, or kube-proxy / iptables rules are stale.

Short name works within the same namespace:

```bash
curl -sf http://ai-lab/healthz
curl -sf http://ai-lab/readyz
curl -sf -X POST http://ai-lab/predict \
  -H "Content-Type: application/json" -d '{"x": 5}'
```

### 5. Check endpoints (from outside the debug pod)

```bash
kubectl get endpoints ai-lab -n ai-lab
```

Healthy output — pod IPs listed:

```
NAME     ENDPOINTS                         AGE
ai-lab   10.244.1.5:8080,10.244.2.4:8080   5m
```

Broken output — empty:

```
NAME     ENDPOINTS   AGE
ai-lab   <none>      5m
```

Empty endpoints means no pods match the Service selector **and** are
Ready.

### 6. Compare Service selector vs pod labels

```bash
# What the Service selects
kubectl get svc ai-lab -n ai-lab -o jsonpath='{.spec.selector}' | python3 -m json.tool

# What the pods actually have
kubectl get pods -n ai-lab --show-labels
```

If the selector is `{"app": "ai-lab"}` but the pods have
`app: ai-lab-v2`, nothing matches → zero endpoints.

### 7. Check CoreDNS health

```bash
kubectl get pods -n kube-system -l k8s-app=kube-dns
kubectl logs -n kube-system -l k8s-app=kube-dns --tail=30
```

If CoreDNS pods are in CrashLoopBackOff or not running, all in-cluster
DNS fails.

## Root cause

DNS / service-discovery issues have several distinct root causes.  Use the
signal matrix below to narrow down which one applies:

| Root cause | nslookup result | Endpoints | curl result |
|---|---|---|---|
| **Wrong service name or namespace** | NXDOMAIN | N/A (wrong name) | Could not resolve host |
| **Service selector mismatch** | Resolves (has ClusterIP) | `<none>` | Connection refused |
| **Pods not Ready** (e.g. bad config) | Resolves | `<none>` | Connection refused |
| **Deployment scaled to 0** | Resolves | `<none>` | Connection refused |
| **CoreDNS down** | Timeout / SERVFAIL | N/A | Could not resolve host |
| **NetworkPolicy blocking DNS** | Timeout | N/A | Could not resolve host |
| **NetworkPolicy blocking app port** | Resolves | Has IPs | Connection timeout |

### Wrong service name or namespace

The most common mistake.  Kubernetes DNS follows a strict hierarchy:

```
<service>.<namespace>.svc.cluster.local
```

- `ai-lab` — works only from within the `ai-lab` namespace.
- `ai-lab.ai-lab` — works from any namespace.
- `ai-lab.ai-lab.svc.cluster.local` — the fully qualified form.
- `ai-lab.default.svc.cluster.local` — wrong namespace → NXDOMAIN.

### Service selector mismatch

The Service `spec.selector` must match labels on the pod template, not
on the Deployment itself.  A common mistake is changing pod labels in the
Deployment without updating the Service.

### Endpoints empty (pods not Ready)

Even when the selector matches, the Endpoints controller only adds pod
IPs that are in the `Ready` condition.  If every pod is `0/1 Ready` (for
example due to a bad-config scenario), the endpoint list is empty and the
Service returns connection refused.

### NetworkPolicy (concept)

A `NetworkPolicy` can block either egress to port 53 (breaking DNS) or
ingress on the application port (breaking curl).  This lab does not
deploy any NetworkPolicies, but in production they are a common hidden
cause.  Diagnose by checking:

```bash
kubectl get networkpolicy -n ai-lab
kubectl describe networkpolicy -n ai-lab
```

If policies exist, verify they allow:
- **Egress** UDP + TCP port 53 to `kube-system` (for DNS).
- **Ingress** TCP on the application port from the source namespace/pod.

## Fix (immediate)

### Wrong service name / namespace

Use the correct FQDN:

```bash
curl http://ai-lab.ai-lab.svc.cluster.local/healthz
```

### Selector mismatch

Align the Service selector with the pod labels:

```bash
kubectl patch svc ai-lab -n ai-lab -p '{"spec":{"selector":{"app":"ai-lab"}}}'
```

Verify:

```bash
kubectl get endpoints ai-lab -n ai-lab
```

### Pods not Ready

Fix the underlying pod issue (bad config, failing probes, etc.) —
see the other runbooks.  Once pods become Ready the endpoints populate
automatically.

### CoreDNS down

```bash
kubectl rollout restart deployment/coredns -n kube-system
kubectl rollout status deployment/coredns -n kube-system --timeout=60s
```

### NetworkPolicy blocking traffic

Add an allow rule or delete the blocking policy:

```bash
kubectl delete networkpolicy <name> -n ai-lab
```

Or add a targeted ingress/egress rule — see the Kubernetes NetworkPolicy
documentation.

## Prevention (long-term)

- **Always verify endpoints** after creating or updating a Service:
  `kubectl get endpoints <svc> -n <ns>`.
- **Use short names within the same namespace** (`ai-lab`) and FQDNs
  cross-namespace (`ai-lab.ai-lab.svc.cluster.local`) to avoid ambiguity.
- **Include a DNS liveness check** in CI or smoke tests:
  deploy a debug pod, resolve the Service, curl the health endpoint.
- **Monitor CoreDNS** error rate and latency; alert if p99 resolution time
  exceeds 100 ms or error rate exceeds 1 %.
- **Label hygiene**: enforce that Service selectors and Deployment pod
  labels are generated from the same source (Helm values, Kustomize
  commonLabels) so they cannot drift apart.
- **NetworkPolicy auditing**: maintain a policy inventory and test
  connectivity in staging after every policy change.

## Verification

After applying the fix, confirm from inside the debug pod:

```bash
kubectl exec -it -n ai-lab debug-pod -- sh
```

```bash
# 1. DNS resolves to a ClusterIP
nslookup ai-lab.ai-lab.svc.cluster.local
# → Address: 10.96.XXX.XXX

# 2. dig returns NOERROR
dig +short ai-lab.ai-lab.svc.cluster.local
# → 10.96.XXX.XXX

# 3. Healthz returns 200
curl -sf http://ai-lab.ai-lab.svc.cluster.local/healthz
# → {"status":"alive"}

# 4. Readyz returns 200
curl -sf http://ai-lab/readyz
# → {"status":"ready"}

# 5. Prediction works end-to-end
curl -sf -X POST http://ai-lab/predict \
  -H "Content-Type: application/json" -d '{"x": 5}'
# → {"x":5.0,"y":10.95}
```

From outside the debug pod:

```bash
# 6. Endpoints are populated
kubectl get endpoints ai-lab -n ai-lab
# → ENDPOINTS   10.244.1.5:8080,10.244.2.4:8080

# 7. CoreDNS pods are healthy
kubectl get pods -n kube-system -l k8s-app=kube-dns
# → READY 1/1   STATUS Running
```
