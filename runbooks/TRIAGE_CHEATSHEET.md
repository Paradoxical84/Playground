# Triage Cheatsheet

Quick-reference for on-call engineers.  Find the symptom, run the three
commands, check what to look for, jump to the runbook.

---

## Symptom → Commands → What to look for → Likely cause

### Pod in CrashLoopBackOff, RESTARTS climbing

```bash
kubectl describe pod -n ai-lab <pod>          # events: "Liveness probe failed"
kubectl logs -n ai-lab <pod> --previous       # last output before kill
kubectl get pod <pod> -n ai-lab -o jsonpath='{.status.containerStatuses[0].lastState.terminated}'
```

| Look for | Likely cause | Runbook |
|---|---|---|
| "connection refused" in liveness event | Server not listening yet — startup too slow for probe timing | [`probe_failure.md`](probe_failure.md) |
| `Reason: OOMKilled`, exit code 137, empty `--previous` logs | Memory limit too low for the runtime | [`oom_killed.md`](oom_killed.md) |
| `Reason: Error`, exit code 1, traceback in logs | Application crash (import error, bad code) | Check logs for stack trace |

### Pod Running but 0/1 Ready, RESTARTS = 0

```bash
kubectl logs -n ai-lab <pod> --tail=50        # look for ERROR lines
kubectl describe pod -n ai-lab <pod>          # readiness events + env vars
kubectl exec -n ai-lab <pod> -- curl -sf http://localhost:8080/readyz
```

| Look for | Likely cause | Runbook |
|---|---|---|
| "Readiness probe failed … statuscode: 503" in events | App started but model not loaded | [`bad_config.md`](bad_config.md) |
| `MODEL_DIR path does not exist` in logs or `/readyz` body | Wrong `MODEL_DIR` env var | [`bad_config.md`](bad_config.md) |
| `Failed to load model from …` in logs | Model file corrupt or incompatible | Check model artefact |

### Pod Running + Ready but Service unreachable

```bash
kubectl get endpoints ai-lab -n ai-lab        # should list pod IPs
kubectl get svc ai-lab -n ai-lab -o yaml      # check selector + ports
kubectl exec -n ai-lab debug-pod -- nslookup ai-lab.ai-lab.svc.cluster.local
```

| Look for | Likely cause | Runbook |
|---|---|---|
| Endpoints shows `<none>` | Selector mismatch or all pods not Ready | [`dns_service_discovery.md`](dns_service_discovery.md) |
| `NXDOMAIN` from nslookup | Wrong service name or namespace in FQDN | [`dns_service_discovery.md`](dns_service_discovery.md) |
| nslookup times out | CoreDNS down or NetworkPolicy blocking port 53 | [`dns_service_discovery.md`](dns_service_discovery.md) |

### Pod OOMKilled, exit code 137, empty logs

```bash
kubectl describe pod -n ai-lab <pod>          # "Reason: OOMKilled" + memory limits
kubectl get events -n ai-lab --sort-by=.metadata.creationTimestamp
kubectl top pod -n ai-lab <pod>               # current usage (if pod is up)
```

| Look for | Likely cause | Runbook |
|---|---|---|
| `Limits: memory: 128Mi` (or similarly low) | Limit too low for TF runtime (~300–500 Mi) | [`oom_killed.md`](oom_killed.md) |
| OOM during inference, not startup | Batch too large or memory leak | [`oom_killed.md`](oom_killed.md) — Option D |

### Cannot pull image / ImagePullBackOff

```bash
kubectl describe pod -n ai-lab <pod>          # events: "Failed to pull image"
kubectl get pod <pod> -n ai-lab -o jsonpath='{.spec.containers[0].image}'
kind load docker-image <image> --name ai-lab  # reload into kind
```

| Look for | Likely cause | Runbook |
|---|---|---|
| "image not found" or "manifest unknown" | Image not loaded into kind cluster | Re-run `kind load docker-image` |
| "unauthorized" | Private registry, missing imagePullSecret | Add credentials |

---

## One-liner quick checks

```bash
# All pods at a glance
kubectl get pods -n ai-lab -o wide

# Recent events (newest last)
kubectl get events -n ai-lab --sort-by=.metadata.creationTimestamp

# Resource usage vs limits
kubectl top pods -n ai-lab
kubectl get pods -n ai-lab -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.containers[0].resources.limits}{"\n"}{end}'

# All endpoints (are pods receiving traffic?)
kubectl get endpoints -n ai-lab

# CoreDNS health
kubectl get pods -n kube-system -l k8s-app=kube-dns
```
