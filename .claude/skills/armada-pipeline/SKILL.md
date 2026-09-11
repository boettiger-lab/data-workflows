---
name: armada-pipeline
description: >-
  Set up and use the Armada batch queue on NRP: headless device-code authentication (the
  documented PKCE flow cannot work from a shell), armadactl install and config, queue-to-namespace
  mapping, Armada priority classes, when to microslice work into thousands of small jobs instead of
  hundreds of large ones, and how to close the retry loop with gap-fill since Armada retries
  nothing. Use when armadactl hangs or will not authenticate, when a k8s indexed job is hitting the
  completion cap, when a fan-out has come back short, or when deciding between the k8s and Armada
  pathways.
---

# Armada Pipeline (NRP)

## Why Armada: microslicing, not requeueing

Armada's value is **not** automatic retry — the
[NRP docs](https://nrp.ai/documentation/userdocs/running/scheduling/) state plainly that
*"preempted jobs will not be automatically rescheduled"*, and `armadactl get retry-policies`
returns `Unimplemented` on NRP. Reaching for Armada to survive preemption is the wrong reason.

Because nothing retries, **gap-fill is a pipeline stage rather than an exception** — measured 1-4
missing slices per 3,780 (~0.1%). See "Closing the retry loop" below; you no longer have to write
the gap-fill by hand for a raster hex build.

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

### Microslicing a raster hex is now generated, not hand-written

`cng-datasets raster-workflow` emits sub-h0 units directly, so the CHELSA-era pattern of a
bespoke `gen_armada_*.py` per dataset is no longer the only route for the **spatial** dimension:

```bash
cng-datasets raster-workflow --dataset <name> --source-url <url> --bucket <bucket> \
  --h3-resolution 10 --chunk-resolution 2 --backend auto
```

`--chunk-resolution N` makes one job a res-N descendant of an h0 rather than a whole h0, cutting
the largest chunk's cell count ~7x per level (measured: h1 4.6 GiB, h2 0.68 GiB, against ~32 GiB
for a whole h0 at res 10). `--max-hex-memory 8Gi` picks the *coarsest* level that fits a budget —
coarsest, because every extra level multiplies the pod count sevenfold and each pod schedules,
pulls the image and reads the source. `--backend auto` then routes to Armada once the chunk count
passes the ~200-pod k8s guideline, and to k8s below it.

⚠️ **The budget model covers the cell enumeration, not the reducer's working set.** It reports a
floor, not a guarantee. For a categorical layer under `mode`/`fractions` the binding term is the
per-cell class map inside exactextract — LANDFIRE EVC's is ~4x VCC's — so `--max-hex-memory`
under-predicts there. Chunking still fixes it (that map scales with cells too), but measure rather
than trusting the auto-selected request on categorical layers.

⚠️ **Still hand-written: the non-spatial dimensions.** CHELSA microsliced by
`(h0, variable, GCM member)`; `--chunk-resolution` only splits space. A multi-variable or
multi-member build still needs its own generator for the other axes, or `year=`-style partitioning
(cng-datasets #172).

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

### Queue and namespace are two fields, not one

A submitted job set carries `queue` at the top and `namespace` on **each job**:

```yaml
queue: geo-workflows          # Armada's scheduling / accounting entity
jobSetId: chelsa-hex
jobs:
  - namespace: geo-workflows  # the k8s namespace the pod is actually created in
    priorityClassName: armada-default
    podSpec: {...}
```

They are 1:1 *by NRP convention*, not by the format — nothing stops you submitting to one queue
with pods in another namespace, though your access to the namespace still has to hold. The CHELSA
run set both explicitly and identically (`gen_armada_hex.py` takes separate `--queue` and
`--namespace`, each defaulting to `geo-workflows`), and the pods executed in `geo-workflows`,
visible there as `armada-<jobid>-0`.

⚠️ **`cng-datasets` derives the queue from `--namespace`**, passing `queue=namespace` for every
converted step. So the queue follows whatever namespace you generated with — and
`raster-workflow`/`workflow` still default `--namespace` to **`biodiversity`**. A generated Armada
workflow with no `--namespace` therefore submits to the **`biodiversity`** queue, not
`geo-workflows`, regardless of `convert_workflow_to_armada`'s own `geo-workflows` default, which
the generators override. **Pass `--namespace geo-workflows` for data-workflows builds.**

`cng_datasets/k8s/armada.py` now defaults to `queue="geo-workflows"` (it used to default to
`biodiversity`, predating the migration), and the workflow generators pass the namespace
explicitly in any case. Verified against cng-datasets `main`, 2026-09-11.

## Priority classes

| Armada class | preemptible | value |
|---|---|---|
| `armada-default` | no | 100 |
| `armada-preemptible` | yes | 50 |
| `armada-high-priority` | no | 1000 |

`cng_datasets/k8s/armada.py` **defaults to `armada-default`** (non-preemptible), and the
`opportunistic` → `armada-preemptible` mapping has been **removed**. It used to do both, which was
the trap: an opportunistic k8s pod is preempted and then *recreated by its Job controller*, while a
preempted Armada job simply stops, so the mapping preserved the preemption and dropped the
recovery. Verified against cng-datasets `main`, 2026-09-11.

Preemptible is still the right choice *when microsliced* — pass `--armada-priority-class
preemptible` once a unit is short enough that losing it is cheap. The default is conservative
because the converter reproduces whatever shape it is given, and that is not always small.

Armada preemption acts only within Armada — its pods neither preempt nor are preempted by normal
cluster pods.

## ⛔ Job specs are world-readable

The NRP docs warn that *"job specs (the YAML you submit) are visible to every user of the
cluster"*, with no namespace restriction. Reference secrets via `secretKeyRef` — never inline a
credential into a submitted spec.

## Getting work onto Armada

**Preferred: generate it.** `--backend armada` (or `--backend auto`) on `workflow` /
`raster-workflow` converts every step as it generates, emitting `armada-<name>-<step>.yaml`
alongside the k8s manifests. Submit each in order with `armadactl submit`.

**Converting a manifest you already have:**

```python
from cng_datasets.k8s.armada import k8s_indexed_job_to_armada, save_armada_yaml
import yaml
with open('<name>-hex.yaml') as f:
    job_spec = yaml.safe_load(f)
armada_spec = k8s_indexed_job_to_armada(job_spec, queue='geo-workflows', job_set_id='<name>-hex')
save_armada_yaml(armada_spec, 'armada-<name>-hex.yaml')
```

Pass `indices=[...]` to expand only some completions — that is what gap-fill uses.

Monitor at <https://armada-lookout.nrp-nautilus.io>.

## Closing the retry loop: gap-fill

Nothing retries, so **every fan-out needs a completeness gate and a way to re-run what is
missing.** For a sub-h0 raster hex build that is now built in:

```bash
# 1. The merge refuses to publish a partial build, and names what is absent.
cng-datasets merge-chunks --chunks-dir s3://<bucket>/<ds>/hex-chunks \
  --output-dir s3://<bucket>/<ds>/hex --expect-chunks 294
#    Incomplete fan-out: 2 of 294 chunks never recorded completion.
#      Missing chunk indices: 41,77

# 2. Emit a job set for exactly those, and submit it.
cng-datasets gapfill --chunks-dir s3://<bucket>/<ds>/hex-chunks --expect-chunks 294 \
  --hex-manifest <ds>-hex.yaml --output armada-<ds>-gapfill.yaml
armadactl submit armada-<ds>-gapfill.yaml

# 3. Merge again. Re-running a chunk is idempotent, so a partial rerun is safe.
```

`gapfill` exits 0 when nothing is missing and 1 when it wrote a job set, so a pipeline branches on
it the way it would on `diff`.

⛔ **Find gaps by ENUMERATING the expected set, never by counting.** 3,779 of 3,780 reads as
complete at a glance, and a count cannot tell you *which* slice is absent. Every chunk writes a
completion marker under `_manifest/` **whether or not it produced data** — a chunk that does not
overlap the raster legitimately writes no output, so counting output files cannot distinguish
"nothing here" from "never ran".

**Gap detection needs only S3 — no Armada and no Kubernetes access.** It reads the markers as an
ordinary S3 client after a job set finishes, whatever submitted it. Only re-submitting needs
`armadactl`. That is what lets the retry loop close without touching Armada's authentication,
which (see above) is the real blocker for anything unattended.

`catalog/bioclimate/scripts/armada_gapfill.py` remains the pattern for builds whose units are not
plain h3 chunks — it enumerates the expected `(variable, member, h0)` set from S3 the same way.

**The k8s backend needs none of this.** `backoffLimitPerIndex` + `maxFailedIndexes` retry a failed
index in place and surface a partial run as `Failed`; that Job-level budget is precisely what
conversion to Armada cannot carry across.

## ⛔ Concurrency is set by your RESOURCE REQUEST, not by a quota

Armada queues carry no concurrency limit — `armadactl get queue <q>` shows only
`priorityFactor: 1` and no resource caps, identical across queues. What limits how many jobs run
is **how many pods of your shape the cluster can hold**, against every other tenant. So an
over-sized request throttles your own queue.

Measured on one workload, requesting 32Gi / 8 cores per job:

```
Number of jobs scheduled:                   2
Number of jobs that could not be scheduled: 4231
Unschedulable jobs:
 4231: job does not fit on any node
```

Actual usage was **peak 5.2 Gi** and a **mean of 3.3 cores**. Right-size both dimensions — see
the `hex-tuning` skill for the measurement recipe and the bimodal-profile caveat.

**Treat memory as the resource to be most conservative about.** Cores are comparatively elastic:
a node with spare CPU can usually take another pod, and a slice that wants fewer cores simply runs
a little longer. Memory is not elastic — a node either has the gigabytes free or it cannot host
the pod at all, so the memory request is what decides how many placement slots exist for your work
at all. Size cpu honestly too, but if you have to be wrong in one direction, be tight on memory.

Two forward-looking reasons this matters beyond today's cluster:

- **Federation.** Armada can schedule across clusters, and another cluster may have no large-RAM
  nodes even if its Armada limits are configured differently. A slice that needs 8 Gi is portable
  to anywhere; one that needs 64 Gi is placeable only where big nodes exist, which forfeits the
  main thing Armada offers.
- **The controller-less cap.** NRP already refuses anything over 32 GB (above), so memory is the
  dimension with a hard wall, not merely a soft contention cost.

⚠️ Do **not** conclude "cpu binds, not memory" from a small change in concurrency after
right-sizing memory. We briefly drew that inference from concurrency moving 28 → 31 pods, then
found both figures had been sampled during Armada's lease ramp, which later reached 128. Ramp
noise is not a ceiling — see the next section.

## ⛔ You cannot measure Armada concurrency with `kubectl`

Two ways a point-in-time pod count misleads:

- **Armada reaps completed pods quickly**, so a snapshot catches only a fraction of what is
  cycling through.
- **Armada leases gradually.** An hour of sampling read "steady at 22-27 running" while the
  scheduler was still ramping; it later reached **128 running** with `cpu=1312` allocated. What
  looked like a ceiling was the climb, and a throughput estimate taken during it was ~2x
  pessimistic.

Use the scheduler's own view, and divide by the per-job request to get real concurrency:

```bash
armadactl get queue-report <queue>
#   Total allocated resources after scheduling: (memory=..., cpu=1312, ...)
```

Or count completed outputs over a fixed interval — the only measure that is independent of both
effects. When counting S3 objects, `grep -c '<Key>'` counts *lines* and the listing is one line:
use `grep -o '<Key>' | wc -l`, and follow `NextContinuationToken` past 1,000 keys.

## Armada keeps failed pods, which k8s does not

A failed Armada pod stays in the namespace as `armada-<jobid>-0` in `Error`, so its logs are
readable straight away:

```bash
kubectl -n <namespace> get pods | grep '^armada-.*Error'
kubectl -n <namespace> logs <pod>
```

On the k8s path, setting `backoffLimitPerIndex` implies `podReplacementPolicy: Failed`, which
**deletes a failed pod before creating its replacement** — the gate signal survives, the
forensics do not. Diagnosing there means re-running the failing index as a non-indexed job at
`backoffLimit: 0` just to keep a pod around (see the `pod-preemption` skill).

Combined with small units, this makes Armada markedly easier to debug: a failure is minutes of
lost work and its evidence is still sitting there.

## ⛔ Do not inline SQL in a job spec

A pod spec's command passes through shell, YAML and (if it embeds Python) a third quoting layer.
Inline SQL escaping collapses in ways that only appear at runtime — a path can reach DuckDB as
`'''/tmp/...` and fail with `No files found that match the pattern`, *after* the expensive step
has already run.

Put the step in a script in a ConfigMap, mount it, and pass paths as arguments — ideally as
query parameters so there is nothing to escape at all.

## Choosing a pathway

- **k8s** — the standard route here. Right when the work is naturally a few hundred units and each
  is short. Pair with default priority (not `opportunistic`) for anything over ~1 hour; see the
  `pod-preemption` skill. `cng-datasets` now omits `priorityClassName` by default and gives hex
  fan-outs `backoffLimitPerIndex`, so a generated k8s job already has both.
- **Armada** — right when the work microslices into thousands of small units, or when the ~200
  completion cap forces artificial batching that inflates per-pod RAM and runtime. Budget for a
  gap-fill pass: nothing retries, so a fan-out of a few thousand will lose one or two units.

`--backend auto` makes that choice on chunk count alone (~200), which is a reasonable proxy but
only a proxy — it does not know how long a unit runs or how expensive losing one is. Override it
when you do.
