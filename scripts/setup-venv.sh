#!/usr/bin/env bash
# Bootstrap the local YAML-generation venv for cng-datasets.
#
# Why this exists: cng-datasets does `from osgeo import gdal` at import time, so the CLI
# won't load without the Python GDAL binding — even for the pure-templating `workflow`
# subcommands that generate k8s YAML (no geospatial compute runs locally; that's all on
# the cluster). libgdal ships on the standard image; we just install the *matching*
# Python binding, pinned dynamically to `gdal-config --version` so it works on any clone.
#
# Usage:
#   scripts/setup-venv.sh          # create/refresh ./.venv
#   source .venv/bin/activate
set -euo pipefail

if ! command -v gdal-config >/dev/null 2>&1; then
  echo "ERROR: gdal-config not found. Install system GDAL (libgdal-dev) first." >&2
  echo "       The Python 'gdal' package builds against the system libgdal via gdal-config." >&2
  exit 1
fi
GDAL_VERSION="$(gdal-config --version)"
echo "System libgdal: ${GDAL_VERSION}"

if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: uv not found. Install from https://docs.astral.sh/uv/ ." >&2
  exit 1
fi

uv venv
# shellcheck disable=SC1091
source .venv/bin/activate

# GDAL binding must match the system libgdal exactly; setup.py auto-detects headers via gdal-config.
uv pip install "gdal==${GDAL_VERSION}"
uv pip install git+https://github.com/boettiger-lab/datasets.git

python -c 'from osgeo import gdal; print("osgeo GDAL OK:", gdal.__version__)'
echo "Done. Activate with:  source .venv/bin/activate"
