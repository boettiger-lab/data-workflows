---
title: Features
subtitle: What makes the pipeline AI-native and scalable
---

## An AI-driven pipeline

The workflow is built to be **driven by agents**, not just usable by experts. Each
step — selecting a cloud-native engine, generating conversion jobs, writing the
catalog entry — is something a coding assistant can do on a researcher's behalf.
The point is not to add a chatbot, but to make the underlying stack *legible* to the
models scientists already use, so they reach for streaming engines instead of the
in-memory libraries that silently break at scale.

## `cng-datasets` as the embedded core

All of the conversion logic lives in one open-source Python package,
[`cng-datasets`](https://github.com/boettiger-lab/datasets): format readers, the
chunking and indexing strategy, the memory model, and the job-generation. Because the
logic is packaged rather than scattered across scripts, the same recipe runs
identically on a laptop, a private cloud, or a public cluster — and a single command
expresses the whole transformation.

## Cloud-native, AI-ready outputs

Outputs are open, cloud-optimized serializations that stream by range-request:

- **Parquet** — columnar tables for out-of-core query engines (DuckDB, Polars).
- **Zarr** — chunked, compressed arrays for imaging and gridded data.
- **Derived indexes** — spatial and hierarchical indexes for fast joins and aggregation.

Nothing is downloaded to be read; a query pulls only the bytes it needs. This is what
makes terabyte datasets usable from an ordinary notebook.

## Rich STAC metadata

Every dataset ships with [STAC](https://stacspec.org) metadata — the
SpatioTemporal Asset Catalog standard — describing each asset's schema, role, units,
coded-value definitions, and provenance. This metadata is the difference between an
agent that *finds and correctly reads* a dataset and one that guesses. It also makes
collections discoverable and composable across the whole catalog.

## Autoscaling on Kubernetes

Heavy compute runs on the cluster. Jobs fan out across many pods, each processing a
slice of the data in parallel, with memory and parallelism tuned per job. Larger-than-
memory inputs spill to disk rather than exhausting RAM, and individual failed slices
are reprocessed in isolation. The same workflow scales from one small file to a
catalog of terabyte-scale datasets.

## General-purpose, beyond geo

The architecture is **domain-agnostic**. Any data with a tabular or array structure —
and some indexable dimension to partition on — fits the same pipeline. We proved it
first at earth-observation scale; the identical machinery extends to the life sciences:

- **Spatial transcriptomics** and image-based assays
- **Whole-slide microscopy** and other large image stacks
- **3D-genome imaging** and other terabyte array data

The cloud-native foundation it builds on — Parquet, Zarr, DuckDB, Polars, STAC — is
already mature and widely adopted across domains. What this project adds is the
**AI-native layer** that lets researchers and their agents drive it together, at scale.
