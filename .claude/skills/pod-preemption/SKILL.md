---
name: pod-preemption
description: >-
  Diagnose and prevent preemption of long-running Kubernetes jobs: reading the succeeded-vs-failed
  gap that reveals pod mortality, why priorityClassName opportunistic (-2000000000) is unsafe for
  multi-hour pods, choosing a priority class and parallelism, and keeping failed pods inspectable
  when backoffLimitPerIndex deletes them. Use when indexed job pods die and retry for no apparent
  reason, when an index exhausts its retry budget, or before submitting a job whose pods run over
  an hour.
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

## Fixes, in order of preference

1. **Do not run long pods at `opportunistic`.** Omitting `priorityClassName` gives default
   priority `0` — two billion points higher — and is admitted in `geo-workflows` (verified). Pair
   it with **lower parallelism** so the total claim on shared nodes does not grow; halving
   parallelism while raising priority is a fair trade, and observed runtime per pod *improved*
   (117 min vs 3h32m for identical work) because there is less contention.
2. **Shorten the pods.** Preemption exposure is roughly proportional to runtime. Splitting work so
   pods run ~30-60 min instead of 3+ hours cuts losses proportionally — but weigh it against the
   merge step that splitting usually reintroduces.
3. **Raise `backoffLimitPerIndex`.** Cheap insurance, but each retry re-runs the whole pod, so a
   preempted 3-hour pod costs 3 hours again. Treat this as a supplement, never the fix.

**Armada offers non-preemptible classes** — `cng_datasets/k8s/armada.py` lists
`armada-default` (non-preemptible, priority 100), `armada-preemptible` (preemptible, 50) and
`armada-high-priority` (non-preemptible, 1000). The catch is that the helper **defaults to
`armada-preemptible`** and maps k8s `opportunistic` onto it, so a job converted without an
explicit `priority_class` stays preemptible. Pass `armada-default` deliberately. Armada also
requeues automatically, which changes the cost of a death as well as its likelihood.

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

## Checklist before submitting a long job

- [ ] Estimate pod runtime. Over ~1 hour → do not use `opportunistic`.
- [ ] Set parallelism to keep the total node claim reasonable as priority rises.
- [ ] `backoffLimitPerIndex` + `maxFailedIndexes` so a partial run surfaces as `Failed`
      (AGENTS.md #409) — never `backoffLimit: 0` on a fan-out.
- [ ] After it finishes, check the `succeeded` vs `failed` gap, not just the condition.
- [ ] If any index failed, verify its output is current by timestamp before publishing.
