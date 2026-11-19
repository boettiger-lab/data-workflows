---
name: pod-preemption
description: >-
  Diagnose and prevent preemption of long-running Kubernetes jobs: reading the succeeded-vs-failed
  gap that reveals pod mortality, why generated jobs (podFailurePolicy Ignore on DisruptionTarget)
  never count preemption in failed, how to tell it apart from by-design OOM-and-reroute which
  produces the same shape, why priorityClassName opportunistic (-2000000000) is unsafe for
  multi-hour pods, choosing a priority class and parallelism against NRP's pod usage policy
  (default-priority pods must be sized to measured use or the whole account is blocked; short
  pods belong at opportunistic), keeping failed pods inspectable
  when backoffLimitPerIndex deletes them, and why failedIndexes is the wrong input to a remap
  list. Use when indexed job pods die and retry for no apparent reason, when an index exhausts
  its retry budget, when reconciling which indexes actually need re-running, or before
  submitting a job whose pods run over an hour.
---

# Pod Preemption

## The tell: `failed` far exceeds the number of failed indexes

An indexed Job reports both counts. Read them together:

```bash
kubectl -n geo-workflows get job <name> \
  -o jsonpath='succeeded={.status.succeeded} failed={.status.failed} failedIndexes={.status.failedIndexes}{"\n"}'
```

A real example from the CHELSA build (data-workflows #564):

```
succeeded=120 failed=47 failedIndexes=39,43
```

122 indices, only **two** ultimately failed — so roughly **45 pods died and were retried
successfully**. That ~28% pod mortality is the signal. `failed` counts *pod* deaths, not indices;
when it is many times larger than `len(failedIndexes)`, the work is fine and the pods are being
killed underneath it.

**A job can even report `Complete=True` while this is happening.** Retries hide it. Check the gap
on every long job, not just failing ones.

## ⛔ Generated jobs do not count preemption in `failed`

`cng-datasets` writes this into every indexed Job it generates:

```yaml
podFailurePolicy:
  rules:
  - action: Ignore
    onPodConditions:
    - type: DisruptionTarget
```

A pod killed by preemption or a node drain carries `DisruptionTarget`. Under this rule it is
replaced without being counted in `.status.failed` or against `backoffLimitPerIndex`. The gap above
therefore only works on jobs without the rule. CHELSA (#564) had none. On a generated job,
`failed=0` says nothing about preemption, and neither does a sibling stage's `failed=0`.

In #792, `tidal-marsh-2020-staging-2020-hex` (opportunistic, 122 indexes) showed no `failed` key at
all while four indexes were running on replacement pods. Check for the rule first:

```bash
kubectl -n geo-workflows get job <name> -o jsonpath='{.spec.podFailurePolicy}{"\n"}'
```

Where it is set, read deaths from the pods and events instead, while the job is still running:

```bash
# a replacement pod starts later than its index's first wave
kubectl -n geo-workflows get pods -l job-name=<name> --sort-by=.metadata.creationTimestamp \
  -o custom-columns='POD:.metadata.name,INDEX:.metadata.annotations.batch\.kubernetes\.io/job-completion-index,CREATED:.metadata.creationTimestamp'
# kills without OOMKilled or Evicted; events expire after about an hour
kubectl -n geo-workflows get events --field-selector involvedObject.kind=Pod | grep <name> | grep -E 'Killing|Preempt'
```

The rule's upside: a preempted pod does not use up its index's retries, so preemption alone does
not exhaust an index. A long pod still loses its work each time it is killed.

## ⛔ The gap is necessary, not sufficient — OOM-and-reroute looks identical

A wide `failed` vs `failedIndexes` gap says *pods died and retried*. It does **not** say why. A
pipeline with an expected-OOM tier — dense partitions that fail at the normal memory limit and are
rerouted to a bigger companion job — produces exactly the same shape, which is also why such jobs
carry a deliberately loose `maxFailedIndexes`.

The GBIF 2026-09 consolidate (data-workflows [#662](https://github.com/boettiger-lab/data-workflows/issues/662#issuecomment-5753332199))
read `succeeded=114 failed=47 failedIndexes=4,12,15,19-21,34` — near-identical to the #564
signature below, **same `failed=47`**. It was not preemption. Do not let that number pattern-match
you into the wrong answer; it cost a session here exactly that.

Two checks settle it before you touch the data:

- **A clean earlier stage is weak evidence.** Stage 1 of that job ran `succeeded=200 failed=0` at
  default priority in the same window as Stage 2's 47 deaths. That rules preemption out only on a
  job without the `DisruptionTarget` Ignore rule (section above); with it, a preempted stage also
  reads `failed=0`.
- **Size correlation is the positive tell for OOM.** Every failed index was among the largest
  partitions — the seven held 2.6B of 3.57B rows. Preemption hits indexes without regard to size;
  OOM hits the big ones and only the big ones.

So: check the priority class *and* a sibling stage *and* whether the failures track partition size.
Read the pipeline's own README first — an expected-OOM tier is usually documented, and it was here.

## Why it happens

`priorityClassName: opportunistic` on NRP carries priority **-2000000000** — the lowest value
available. Verify what a pod actually got:

```bash
kubectl -n geo-workflows get pods -l <selector> \
  -o custom-columns='NAME:.metadata.name,PRIOCLASS:.spec.priorityClassName,PRIO:.spec.priority'
```

Preemption risk scales with **how long a pod runs**. A 5-minute opportunistic pod is nearly always
fine; a **multi-hour** one is a large target and will be evicted repeatedly. Pod runtime is the
variable that matters, far more than pod count.

## Choosing a priority class: preemption against NRP's usage policy (#804)

There are two costs to weigh when choosing a priority class, and avoiding one exposes a job to the other:

- **At `opportunistic`**, a long pod is preempted. That is the rest of this skill.
- **At default priority**, the pod is subject to NRP's usage policy. An oversized request there blocks the whole account.

Weigh both every time.

**NRP usage policy**, as stated by NRP to Carl (#804):

- A running pod is outside the policy when its use falls outside these ranges of its request: memory 20–150%, CPU 20–200%, GPU above 40%.
- Memory is checked only on pods requesting more than 2 GiB. CPU is checked only on pods requesting more than 1 core.
- **Exempt:** opportunistic (negative-priority) pods, JupyterHub pods, and pods younger than 30 minutes. The portal checks every 10 minutes.
- **Our rule is zero pods outside the ranges, at all times.** NRP tolerates up to 4 across the account as a grace, not an allowance: over 4, its admission webhook `deployment.nrp-nautilus.io` denies every Deployment change on the account with `Your pods resources utilization is too low for account …`, and violating regularly, even within the grace, can get the account banned. Any out-of-range pod is an incident to fix at once.
- A separate admission policy, `container-must-meet-memory-and-cpu-ratio`, caps limit/request at **1.2** for CPU and for memory. A memory limit of 1.5× the request was rejected, and 1.2× passed.

**What it cost.** On 2026-10-26, `crw-5km-daily-backfill` (#802) ran 10 default-priority pods requesting 16Gi each and using 0.9–2.5Gi, which is 6–16% of the request. That blocked a global-30x30 rollout until the job was suspended. The 16Gi came straight from the generator's default.

**The rule:**

1. **Pods expected to run under about an hour use `priorityClassName: opportunistic`.** This covers setup-bucket jobs, daily CronJob runs, and fan-outs whose units are short. These pods are exempt from the usage check, and their preemption exposure is small.
2. **Split long work into short units where that is practical**, so it can run at `opportunistic`. Preemption exposure is roughly proportional to runtime, so pods of ~30–60 min instead of 3+ hours cut losses proportionally; weigh that against the merge step splitting usually reintroduces.
3. **Pods that must run long use default priority, sized to measured use.** Default priority is `0`, two billion points above `opportunistic`, and generated manifests already omit `priorityClassName` unless `--priority-class` is passed (datasets#201).
   - Default priority means **leaving `priorityClassName` out**. Writing `priorityClassName: default` is refused at submission (`exceeded quota: high-priority-ban`, checked 2026-11-17 by server-side dry-run in `geo-workflows`), and NRP's ban quotas list other classes too (`kubectl -n geo-workflows get resourcequota high-priority-ban low-priority-ban -o yaml`).
   - Keep use within the ranges above, with the limit no more than 1.2× the request.
   - Measure first: run one unit, or watch `kubectl top pod` on the first pods.
   - Check again about 30 minutes after launch, before the portal's first check.
   - No pod may fall outside the ranges. Other sessions on the same account count too, so check the whole account, not only your job.
   - Lower parallelism as priority rises, so the total claim on shared nodes does not grow. Halving parallelism is a fair trade: per-pod runtime *improved* from 3h32m to 117 min for identical work, because there was less contention.
   - `backoffLimitPerIndex` is a supplement, not the fix: each retry re-runs the whole pod, so a preempted 3-hour pod costs 3 hours again.
4. **Do not trust a generated memory request.** `cng-datasets` defaults are sized for the worst case, not measured. If the peak is a short spike far above the average, as in #802 where DuckDB peaked above 4.5 GiB while the pod averaged 2 GiB, shrink the peak rather than the request. In #802 that meant splitting the step into `--h0-subset` batches, which brought it to a 3Gi request with a 3.5Gi limit.

## Do not misread it as a data problem

The failing indices are usually **not special**. In #564 the two that failed looked meaningful —
both were sparse-land ocean cells — and that coincidence cost two diagnostic cycles. The same
h0 then:

| run | retries per index | outcome |
|---|---|---|
| parallelism 40 | 3 attempts | failed |
| parallelism 2 | 2 attempts | failed |
| single pod | 1 attempt | **succeeded, unchanged** |

The variable was the retry budget against a background death rate — not the cell, not the code,
not parallelism. **Before investigating the data, re-run one failing index on its own.** If it
succeeds unchanged, it was environmental.

**The converse case is real too**, so run the discriminator above before concluding this: in the
GBIF #662 job the failing indexes *were* special — they were the densest cells on Earth, and the
single-pod re-run would have OOMed again. "Usually not special" is a prior, not a finding.

**On Armada**, priority classes and preemption work differently: a preempted Armada job is not
rescheduled, and Armada preemption acts only within Armada. See the `armada-pipeline` skill.

## ⛔ Keep failed pods inspectable

Setting `backoffLimitPerIndex` implies `podReplacementPolicy: Failed`: the controller **deletes a
failed pod before creating its replacement**. You get a clean gate signal and lose the forensics —
by the time you look, there is nothing to read, and `kubectl describe job` shows only
`Warning FailedIndexes`.

To diagnose, re-run the single failing index as a **non-indexed** Job with **`backoffLimit: 0`**.
The failed pod then persists as `Error` and can be read:

```bash
kubectl -n geo-workflows logs <pod>
kubectl -n geo-workflows describe pod <pod> | grep -iE "Reason:|Exit Code|OOMKilled|Evicted|ephemeral"
```

Write such a diagnostic to a **throwaway S3 prefix**, never the published path, and log resource
state (`df -h /tmp`, `du -sh` on scratch dirs) just before the step you suspect — a deleted pod
takes that evidence with it.

## ⛔ A retry-exhausted index leaves STALE data, not missing data

This is the real damage, and it is easy to miss. If the partition already existed from an earlier
build, a failed index leaves the **old** file in place. Then:

- the partition **count** still matches the expected set, so a coverage check passes;
- a glob read spans **two schemas** (in #564: two bio1-only partitions of 0.7 MB and 10 MB beside
  106 seven-variable partitions of up to 1.99 GB).

Never treat partition count as proof. Compare **timestamps and sizes** against the run that should
have written them:

```bash
curl -s "https://s3-west.nrp-nautilus.io/<bucket>?list-type=2&prefix=<path>/hex/h0=<cell>/" \
  | grep -o '<LastModified>[^<]*</LastModified>\|<Size>[0-9]*</Size>' | sed 's/<[^>]*>//g'
```

Do not publish or update STAC until every index is genuinely current.

## ⛔ `failedIndexes` is the wrong input to a remap list

An index that was **in flight when the job was suspended or deleted** appears in *neither*
`completedIndexes` nor `failedIndexes`. Build a re-run list from `failedIndexes` and you silently
skip it.

Take the set difference against `completions` instead:

```bash
kubectl -n geo-workflows get job <name> \
  -o jsonpath='{.spec.completions}{"\n"}{.status.completedIndexes}{"\n"}{.status.failedIndexes}{"\n"}'
```

Verified on the GBIF #662 job: `completions=122`, `completedIndexes` covering 114, `failedIndexes`
7 — and index **95** in neither list, because it was running when someone suspended the job.
114 + 7 = 121, not 122. The arithmetic is the check.

## ⛔ Do not put a short TTL on a remediation job

`ttlSecondsAfterFinished` garbage-collects the Job object, and with it the only in-cluster record
that the remediation ever ran. For the job that *rescues* an expected-OOM tier this is actively
harmful: the rescued parent is typically left `suspended` or `Failed` by design, so once the
rescuer has aged out, the cluster shows a stalled build and nothing else.

That is exactly what happened on GBIF #662 — the rechunk carried `ttlSecondsAfterFinished: 10800`,
so three hours after it succeeded the only surviving evidence was **object timestamps on S3**
(two write waves: 114 partitions ≤1.65 GB from 19:56–20:22, then eight of 8.4–26.8 GB from 21:15
to 00:56, six of them written *after* the parent's 21:15:52 suspension). A healthy, complete build
looked broken for eleven days.

Give a remediation job a long TTL, **or** write one line to the issue when you apply it. Either
makes the audit unnecessary.

## Checklist before submitting a long job

- [ ] Estimate pod runtime. Under ~1 hour → `opportunistic`. Over ~1 hour → default priority,
      or split the work so it fits under an hour.
- [ ] At default priority: size requests to measured use under the usage policy above, and
      check `kubectl top pod` ~30 min after launch.
- [ ] Set parallelism to keep the total node claim reasonable as priority rises.
- [ ] `backoffLimitPerIndex` + `maxFailedIndexes` so a partial run surfaces as `Failed`
      (AGENTS.md #409) — never `backoffLimit: 0` on a fan-out.
- [ ] After it finishes, check the `succeeded` vs `failed` gap, not just the condition. If the job
      ignores `DisruptionTarget` (every generated job does), read replacement pods and `Killing`
      events while it runs instead; `failed` will not show preemption.
- [ ] Before calling a gap preemption, check a sibling stage and whether failures track partition
      size — an expected-OOM tier produces the same signature.
- [ ] Build any re-run list from `completions` minus `completedIndexes` minus `failedIndexes`,
      never from `failedIndexes` alone.
- [ ] If the job has a remediation companion, give it a long TTL or record the run on the issue.
- [ ] If any index failed, verify its output is current by timestamp before publishing.
