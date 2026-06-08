---
title: The ecosystem
subtitle: Teaching agents to drive data at scale
---

`data-workflows` is one of three open-source components that together let
researchers and their AI agents work with terabyte-scale data through the tools they
already use. Each is independently useful; together they form an **AI-native bridge**
to the mature cloud-native stack the sciences are converging on.

::::{grid} 1 1 3 3

:::{card} data-workflows
:link: https://github.com/boettiger-lab/data-workflows
**Prepares the data.** The pipeline on this site — transforms legacy and proprietary
sources into AI-ready Parquet/Zarr with rich STAC metadata, run locally, on private
clouds, or on public object stores.
:::

:::{card} mcp-data-server
:link: https://boettiger-lab.github.io/mcp-data-server/
**Connects the agents.** An open [Model Context Protocol](https://modelcontextprotocol.io)
server that points coding agents at a collection's STAC metadata and exposes
cloud-native engines (DuckDB, hardware-accelerated Polars) — so the model uses them
instead of in-memory libraries. Runs locally for sensitive data or on autoscaling
Kubernetes for scale.
:::

:::{card} jupyter-geoagent
:link: https://jupyter-geoagent.readthedocs.io/
**Meets researchers where they work.** A JupyterLab extension integrating with
Jupyter-AI — a data persona users drive with commercial *or* fully open models run
locally, keeping data on the researcher's own hardware.
:::

::::

## Why a bridge, not a fork

The components this connects — [Zarr](https://zarr.dev), xarray,
[Parquet](https://parquet.apache.org), [DuckDB](https://duckdb.org), Polars,
[STAC](https://stacspec.org), [Jupyter](https://jupyter.org), and the
[Model Context Protocol](https://modelcontextprotocol.io) — are individually mature
open-source projects with wide adoption. What is new is the **AI-native layer** that
lets researchers and their agents drive them *together*, at scale.

The leverage is that Jupyter and agentic coding assistants are already the field's
everyday tools. The bridge meets that existing base without asking anyone to learn a
new toolchain: the agent a scientist already uses makes the move from in-memory
libraries to the cloud-native stack on the user's behalf. And because the MCP layer
works with small, locally-run open models, it reduces dependence on closed models and
keeps sensitive data — clinical, patient, controlled-access — on local hardware.

## From earth observation to the life sciences

These methods were built and proven at the largest earth-observation scales. The same
architecture extends to the life sciences, where spatially-resolved data — 3D-genome
imaging, spatial transcriptomics, whole-slide microscopy — now arrives at terabyte
scale, well beyond the in-memory tools most researchers rely on. The cloud-native
foundation to handle it is mature; the missing piece is the agentic layer that makes
it reachable. That is what this ecosystem provides.
