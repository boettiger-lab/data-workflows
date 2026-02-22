---
name: nrp-k8s-batch
description: >
  Run batch processing jobs on the NRP (National Research Platform) Nautilus Kubernetes
  cluster. Covers the mandatory requirements for CPU jobs: opportunistic priority class,
  resource requests/limits, and GPU node avoidance. Use when creating or managing
  Kubernetes jobs on the NRP Nautilus cluster, or when the user mentions NRP, Nautilus,
  or needs to run batch workloads on a shared academic cluster.
license: Apache-2.0
compatibility: >
  Requires kubectl configured for the NRP Nautilus cluster (namespace: biodiversity).
  Works with any agent that can run shell commands.
metadata:
  author: boettiger-lab
  version: "1.0"
---

# NRP Kubernetes Batch Jobs

The NRP (National Research Platform) Nautilus cluster is a shared academic Kubernetes cluster primarily designed for GPU workloads. CPU-only batch jobs require specific configuration to coexist properly.

## Namespace

All our jobs run in the `biodiversity` namespace:

```bash
kubectl -n biodiversity get jobs
```

## Mandatory Requirements for CPU Jobs

### 1. Priority class (REQUIRED)

All CPU jobs **must** use the `opportunistic` priority class. This makes pods preemptible so they don't block GPU users. Without this, your job may be rejected or cause problems for other users.

```yaml
spec:
  template:
    spec:
      priorityClassName: opportunistic
```

### 2. Resource requests and limits (REQUIRED)

The NRP cluster **requires** both `requests` and `limits` on every container. Jobs without resource specifications will not be scheduled.

Set requests equal to limits for guaranteed QoS (Quality of Service). Be respectful — request only what you need:

```yaml
resources:
  requests:
    cpu: "4"
    memory: "8Gi"
  limits:
    cpu: "4"
    memory: "8Gi"
```

If you need ephemeral scratch disk (e.g., for large temporary files), request it explicitly:

```yaml
resources:
  requests:
    cpu: "4"
    memory: "32Gi"
    ephemeral-storage: "250Gi"
  limits:
    cpu: "4"
    memory: "32Gi"
```

### 3. GPU node avoidance (recommended)

To avoid wasting GPU node capacity on CPU-only work, add a node anti-affinity. This is strongly recommended but not strictly enforced:

```yaml
spec:
  template:
    spec:
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
              - matchExpressions:
                  - key: feature.node.kubernetes.io/pci-10de.present
                    operator: NotIn
                    values: ["true"]
```

## Minimal Job Example

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: my-job
spec:
  backoffLimit: 2
  ttlSecondsAfterFinished: 10800
  template:
    spec:
      priorityClassName: opportunistic
      restartPolicy: Never
      containers:
        - name: worker
          image: ghcr.io/boettiger-lab/datasets:latest
          command: ["bash", "-c", "echo hello"]
          resources:
            requests:
              cpu: "4"
              memory: "8Gi"
            limits:
              cpu: "4"
              memory: "8Gi"
```

## Secrets

Two secrets are available in the `biodiversity` namespace. See the [nrp-s3 skill](../nrp-s3/SKILL.md) for full details on S3 environment variables.

### `aws` — S3 credentials (environment variables)

```yaml
env:
  - name: AWS_ACCESS_KEY_ID
    valueFrom:
      secretKeyRef:
        name: aws
        key: AWS_ACCESS_KEY_ID
  - name: AWS_SECRET_ACCESS_KEY
    valueFrom:
      secretKeyRef:
        name: aws
        key: AWS_SECRET_ACCESS_KEY
```

### `rclone-config` — Rclone configuration (volume mount)

```yaml
volumeMounts:
  - name: rclone-config
    mountPath: /root/.config/rclone
    readOnly: true
volumes:
  - name: rclone-config
    secret:
      secretName: rclone-config
```

## Useful Fields

| Field | Purpose |
|-------|---------|
| `ttlSecondsAfterFinished: 10800` | Auto-deletes completed jobs after 3 hours to avoid resource leaks |
| `completionMode: Indexed` | For parallel workloads — each pod gets a unique `JOB_COMPLETION_INDEX` |
| `backoffLimitPerIndex` | Retries per index (instead of global `backoffLimit`) — useful for indexed jobs |
| `podFailurePolicy` with `DisruptionTarget: Ignore` | Don't count preemptions as failures (important with `opportunistic` priority) |

## Common Pitfalls

1. **Missing resource requests/limits** — Jobs will not schedule without them. Always specify both, and keep requests = limits.
2. **Forgetting `priorityClassName: opportunistic`** — Required for all CPU jobs on this cluster.
3. **Requesting too many resources** — Be respectful. Don't request 64 CPUs if you only need 4.
4. **Max 200 completions per indexed job** — Hard limit to avoid overwhelming the cluster's etcd.
