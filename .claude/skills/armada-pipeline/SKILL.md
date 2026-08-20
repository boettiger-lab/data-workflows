---
name: armada-pipeline
description: >-
  Set up and use the Armada batch queue on NRP: headless device-code authentication (the
  documented PKCE flow cannot work from a shell), armadactl install and config, queue-to-namespace
  mapping, Armada priority classes, and when to microslice work into thousands of small jobs
  instead of hundreds of large ones. Use when armadactl hangs or will not authenticate, when a k8s
  indexed job is hitting the completion cap, or when deciding between the k8s and Armada pathways.
---

# Armada Pipeline (NRP)

## Why Armada: microslicing, not requeueing

Armada's value is **not** automatic retry — the
[NRP docs](https://nrp.ai/documentation/userdocs/running/scheduling/) state plainly that
*"preempted jobs will not be automatically rescheduled"*. Reaching for Armada to survive
preemption is the wrong reason.

The real reason is that Armada is not bound by the k8s indexed-Job completion cap (~200, an etcd
pressure limit). Millions of completions are fine. That makes **microslicing** practical, and
microslicing improves four things at once:

| | few large jobs | many small slices |
|---|---|---|
| unit of loss on preemption | hours | minutes |
| RAM requested | sized for the worst step in the chain | what each step actually needs |
| scheduling | needs large contiguous free slots; pods sit `Pending` | fits in scraps almost anywhere |
| stragglers | one holds up the batch and can leave stale output | retries invisibly |

The scheduling point is the one most easily missed: 20 pods at 64Gi need ~1.3 TB free **in large
contiguous chunks**, so realized parallelism is far below requested. Thousands of 8-16Gi slices
pack into whatever is free and start immediately. Placing 10,000 small slices is often faster
than placing 100 big ones — more so under preemption.

Big jobs also make you *conservative*: a 35-step chain must request the peak requirement of its
worst step, so every step pays that cost. One unit per job asks for what it needs.

## ⛔ Authentication: use the device-code flow, not the documented PKCE flow

The config NRP publishes at `https://nrp.ai/.armadactl.yaml` uses **PKCE** (`openIdAuth`), which
binds `127.0.0.1:50000` and waits for a browser redirect. **This cannot complete in a headless
shell.** It hangs silently, prints no URL, and — critically — **keeps holding port 50000**, so
every later attempt dies with:

```
panic: listen tcp 127.0.0.1:50000: bind: address already in use
```

That panic is a symptom of the first hung process, not a separate fault. Kill the original before
retrying.

**Working headless config** — swap `openIdAuth` for `openIdDeviceAuth`:

```yaml
currentContext: main
contexts:
  main:
    cacheRefreshToken: true
    armadaUrl: armada.nrp-nautilus.io:50051    # port 50051, NOT 443
    openIdDeviceAuth:
      providerUrl: "https://authentik.nrp-nautilus.io/application/o/armada/"
      clientId: "8AeUAhsM1rA8WRJoX586BhJk8t5Icfrm169ESz8Y"
      scopes:
        - "openid"
        - "profile_prefixed"
        - "offline_access"
```

armadactl then prints a URL to approve on any device, with no local callback port:

```
Complete your login in the browser:
    https://authentik.nrp-nautilus.io/device?code=960348666
```

### ⛔ The code expires in 60 SECONDS, and the token cannot be cached here

Two hard constraints, both measured rather than documented.

**1. A 60-second window.** Authentik grants `expires_in: 60` (poll `interval: 5`) — not the 5-10
minutes most providers give. Verify any time with:

```bash
curl -s -X POST "https://authentik.nrp-nautilus.io/application/o/device/" \
  -d "client_id=8AeUAhsM1rA8WRJoX586BhJk8t5Icfrm169ESz8Y&scope=openid profile_prefixed offline_access" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['expires_in'], d['interval'])"
```

**Operational rule: fire the code and hand the URL over in a message containing nothing else.**
Writing a paragraph of explanation first burns the entire window. Explain afterwards. Firing a
second code does not extend the first — it only makes it ambiguous which link is live, so the
person approves a stale one.

Run it with `nohup ... &` so it keeps polling while the URL is handed over.

**2. `cacheRefreshToken: true` silently does nothing in a container.** armadactl caches through
`go-keyring`, which on Linux needs a D-Bus Secret Service:

```
Failed to save token to cache
error="failed to save refresh token to keyring: exec: \"dbus-launch\": executable file not found in $PATH"
```

So **every invocation re-authenticates**. Tolerable for a submit — one `armadactl submit` can
carry thousands of jobs, so one approval covers a whole job set — but it rules out unattended
use, since nothing can approve a device code on a cron.

Three ways out, in increasing order of robustness:

- install **`dbus-launch`** plus a session keyring in the image, so caching works as intended;
- **`execAuth`** — run the device flow once with `curl`, store the refresh token in a file, and
  point `execAuth.cmd` at a script that exchanges refresh for access on demand. No keyring
  needed, fully headless;
- **`OpenIdClientCredentialsAuth`** — a service-account client, if NRP will issue one. The right
  answer for a cron or an always-on agent.

Monitoring needs auth per command too, so prefer <https://armada-lookout.nrp-nautilus.io> or
check the output on S3 directly rather than re-authenticating for every status query.

Device auth is supported by the provider but **undocumented on the NRP page** — authentik
advertises `device_authorization_endpoint` and `urn:ietf:params:oauth:grant-type:device_code` in
its OIDC discovery. Verify with:

```bash
curl -s https://authentik.nrp-nautilus.io/application/o/armada/.well-known/openid-configuration \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('device_authorization_endpoint')); print(d.get('grant_types_supported'))"
```

The binary also supports `OpenIdClientCredentialsAuth` (fully unattended, needs a service-account
client), `OpenIdPasswordAuth`, `basicAuth` and `execAuth` — none documented by NRP. Client
credentials is the right answer for a cron or an always-on agent, if NRP will issue one.

`cacheRefreshToken: true` persists a refresh token, which is **not machine-bound** — authenticating
elsewhere and copying the cache is a valid fallback.

## Install

`armadactl` is **not** in the standard image. From the
[releases page](https://github.com/armadaproject/armada/releases):

```bash
curl -sL -o /tmp/armadactl.tgz \
  https://github.com/armadaproject/armada/releases/download/v0.22.7/armadactl_0.22.7_linux_amd64.tar.gz
tar xzf /tmp/armadactl.tgz -C /tmp && install -m 0755 /tmp/armadactl ~/.local/bin/armadactl
```

## Queues map to namespaces

Per the NRP docs, `armadactl get queues` *"will list all queues matching the list of all namespaces
in the cluster. You can submit to the ones you normally access."* So a queue already exists for
each namespace you can use — **you do not create one**. Submit to the queue matching the namespace
the job should land in.

Verified 2026-08-19: **1,875 queues**, one per namespace, including `geo-workflows`,
`biodiversity`, `biodiversity-llm` and `boettiger-lab`. Data-workflow jobs belong in
**`geo-workflows`**.

`cng_datasets/k8s/armada.py` defaults to `queue="biodiversity"`, which predates the
`geo-workflows` migration — pass the right queue explicitly.

## Priority classes

| Armada class | preemptible | value |
|---|---|---|
| `armada-default` | no | 100 |
| `armada-preemptible` | yes | 50 |
| `armada-high-priority` | no | 1000 |

`cng_datasets/k8s/armada.py` **defaults to `armada-preemptible`** and maps k8s `opportunistic`
onto it. Preemptible is the right default *when microsliced*; pass `armada-default` when a unit is
long enough that losing it hurts.

Armada preemption acts only within Armada — its pods neither preempt nor are preempted by normal
cluster pods.

## ⛔ Job specs are world-readable

The NRP docs warn that *"job specs (the YAML you submit) are visible to every user of the
cluster"*, with no namespace restriction. Reference secrets via `secretKeyRef` — never inline a
credential into a submitted spec.

## Converting an existing k8s job

```python
from cng_datasets.k8s.armada import k8s_indexed_job_to_armada, save_armada_yaml
import yaml
with open('<name>-hex.yaml') as f:
    job_spec = yaml.safe_load(f)
armada_spec = k8s_indexed_job_to_armada(job_spec, queue='<namespace>', job_set_id='<name>-hex')
save_armada_yaml(armada_spec, 'armada-<name>-hex.yaml')
```

Submit with `armadactl submit <file>`; monitor at <https://armada-lookout.nrp-nautilus.io>.

## Choosing a pathway

- **k8s** — the standard route here. Right when the work is naturally a few hundred units and each
  is short. Pair with default priority (not `opportunistic`) for anything over ~1 hour; see the
  `pod-preemption` skill.
- **Armada** — right when the work microslices into thousands of small units, or when the ~200
  completion cap forces artificial batching that inflates per-pod RAM and runtime.
