---
title: Agentic Data Workflows
subtitle: AI-ready, cloud-native data with rich metadata — from any legacy source
site:
  hide_outline: true
---

+++ {"class": "col-page text-center"}

# Agentic Data Workflows

### Turn disparate legacy and proprietary data into **AI-ready, cloud-native** data with rich **STAC** metadata.

An AI-driven pipeline that converts the formats science actually ships in — geodatabases, shapefiles, proprietary instrument exports, terabyte image stacks — into open, cloud-optimized serializations (Parquet, Zarr) described by machine-readable metadata, so that researchers *and their AI agents* can query data at scale without first downloading it or mastering a new toolchain.

The core conversion logic lives in our Python package, [**`cng-datasets`**](https://github.com/boettiger-lab/datasets); the heavy compute autoscales on **Kubernetes**. You describe the dataset; the pipeline produces the cloud-native artifacts and the catalog entry.

[**See how it works →**](how-it-works.md) &nbsp;·&nbsp; [Quickstart](quickstart.md) &nbsp;·&nbsp; [GitHub](https://github.com/boettiger-lab/data-workflows)

+++

## What it gives you

::::{grid} 1 1 2 2

:::{card} 🤖 An AI-driven pipeline
:link: features.md
Agents drive the workflow end to end — selecting the right cloud-native engine, generating the conversion jobs, and writing the metadata — instead of reaching for in-memory libraries that silently fail at scale.
:::

:::{card} 📦 `cng-datasets` at the core
:link: how-it-works.md
A single Python package embeds the conversion logic. One command turns a source dataset into Parquet/Zarr plus a catalog entry, and emits the Kubernetes jobs that do the work.
:::

:::{card} 🗂️ Rich STAC metadata
:link: features.md
Every output is described with the SpatioTemporal Asset Catalog standard: column schemas, asset roles, and provenance that let agents *find* and *correctly interpret* the data.
:::

:::{card} ☁️ Autoscaled on Kubernetes
:link: how-it-works.md
Compute runs on the cluster, not your laptop. Jobs fan out across hundreds of pods and stream larger-than-memory data, so terabyte datasets are routine.
:::

::::

+++

## General-purpose, proven at scale

The approach is **domain-agnostic** — any tabular or array data with a spatial, temporal, or otherwise indexable structure fits. We built and proved these methods at the largest **earth-observation** scales (working with NASA, The Nature Conservancy, and California Fish & Wildlife), and are extending them to the **life sciences**: spatial transcriptomics, whole-slide microscopy, and 3D-genome imaging at terabyte scale.

[**Browse the live catalog →**](catalog.md)
