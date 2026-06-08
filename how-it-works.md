---
title: How it works
subtitle: From a legacy source file to AI-ready data and a catalog entry
---

The pipeline has one job: take data in whatever format it arrives in and produce
**cloud-native, AI-ready artifacts plus the metadata that describes them** — with
the actual compute running on autoscaling infrastructure rather than a workstation.

## The pipeline

```{mermaid}
flowchart LR
    A[Legacy / proprietary source<br/>GDB · Shapefile · GeoTIFF<br/>instrument exports · image stacks] --> B
    B[cng-datasets<br/>embeds the core logic] --> C[Kubernetes jobs<br/>autoscale the compute]
    C --> D[Cloud-native outputs<br/>Parquet · Zarr · derived indexes]
    C --> E[STAC metadata<br/>schemas · assets · provenance]
    D --> F[Object store<br/>streamed by range-request]
    E --> F
    F --> G[Agents & researchers<br/>query at scale, no download]
```

### 1. Describe the dataset

You point the [`cng-datasets`](https://github.com/boettiger-lab/datasets) CLI at a
source and describe how it should be indexed. The package **embeds the core
conversion logic** — the format readers, the chunking and indexing strategy, the
memory model — so a single command captures the whole recipe. It does not process
data locally; it *generates* the Kubernetes job manifests that will.

### 2. Autoscale the compute

You apply those manifests to a **Kubernetes** cluster. The work fans out across
many pods, each handling a slice of the data, and streams larger-than-memory
inputs by spilling to disk instead of loading everything into RAM. A dataset that
would never fit on a laptop is processed in parallel on cluster metal. Memory and
parallelism are tuned per job; failed slices are reprocessed in isolation.

### 3. Produce cloud-native, AI-ready outputs

Outputs land on an **object store** in open, cloud-optimized formats — columnar
**Parquet** for tables, chunked **Zarr** for arrays, plus derived spatial indexes.
These are read by **range-request**: a query streams only the bytes it needs
rather than downloading the whole file, which is what makes terabyte data tractable
from a notebook.

### 4. Describe it with STAC

Alongside the data, the pipeline records **STAC** (SpatioTemporal Asset Catalog)
metadata: the column schema of each asset, its role and format, units, coded-value
definitions, and provenance. This is the layer that lets an AI agent **find** the
right dataset and **interpret it correctly** — without it, a model has to guess at
column meanings and silently returns wrong answers.

## Why "agentic"

As coding assistants become the everyday interface for analysis, they reach by
default for the in-memory libraries they know best (e.g. `pandas`) — which fail at
scale and, lacking metadata, misread the data. This pipeline closes that gap from
both ends:

- It **produces** the cloud-native artifacts and the STAC metadata an agent needs.
- Companion tooling (see [the ecosystem](ecosystem.md)) then **points agents at that
  metadata** and confines them to validated cloud-native engines, so the agent a
  scientist already uses makes the move from in-memory tools to the streaming stack
  on the user's behalf.

The result is an AI-driven path from a raw legacy file to data that researchers and
their agents can query at scale — with no new toolchain to learn.
