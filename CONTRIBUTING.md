# Contributing to Agentic Data Workflows

Thanks for your interest in contributing! This repository holds the dataset
processing workflows that turn disparate legacy and proprietary data into
AI-ready, cloud-native data with rich STAC metadata, autoscaled on NRP
Kubernetes. Contributions of all kinds are welcome — new datasets, workflow and
STAC improvements, and documentation.

By participating in this project you agree to abide by our
[Code of Conduct](CODE_OF_CONDUCT.md).

## Ways to contribute

- **Request a dataset** — the lowest-friction way to contribute. See
  [`dataset-requests/`](dataset-requests/) for how requests are filed and
  processed.
- **Add or improve a dataset workflow** — the per-dataset pipelines under
  [`catalog/`](catalog/).
- **Improve STAC metadata** — schema, categorical encodings, and asset fields.
- **Documentation** — the site under [`docs/`](docs/) and the top-level guides.

Browse [open issues](https://github.com/boettiger-lab/data-workflows/issues) for
concrete tasks, or open a
[Discussion](https://github.com/boettiger-lab/data-workflows/discussions) to
propose an idea or ask a question first.

## Development setup

Workflows are generated with [`cng-datasets`](https://github.com/boettiger-lab/cng-datasets),
which requires the Python GDAL binding matched to the system `libgdal`. A
bootstrap script sets up a local [`uv`](https://docs.astral.sh/uv/) venv:

```bash
scripts/setup-venv.sh
source .venv/bin/activate
```

This installs the `gdal` binding pinned to your system `gdal-config --version`.
The pure-templating `workflow` subcommands generate Kubernetes YAML locally; no
geospatial compute runs on your machine — that all happens on the cluster.

## Making changes

1. Fork the repo and create a topic branch off `main`.
2. Keep changes focused; follow the patterns of the surrounding datasets and
   scripts.
3. For dataset changes, verify STAC output — CI runs STAC validation on every
   pull request (`.github/workflows/verify-stac.yml`), and the linters under
   [`scripts/`](scripts/) (`lint-stac-*.py`, `check-hex-*.sh`) catch common
   encoding and coverage issues.
4. Update documentation as appropriate.
5. Open a pull request with a clear description and link any related issue.

Maintainers will review and may request changes before merging.

## Reporting bugs and asking questions

- **Bugs / feature requests:** open a
  [GitHub Issue](https://github.com/boettiger-lab/data-workflows/issues).
- **Questions / ideas:** start a
  [GitHub Discussion](https://github.com/boettiger-lab/data-workflows/discussions).

## License

This project is dual-licensed: **content** (data, documentation, STAC metadata)
under [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/) and **code**
under the [BSD 3-Clause License](LICENSE). By contributing, you agree that your
contributions will be licensed under the same terms.
