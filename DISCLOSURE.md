# Disclosure: use of software tools

Portions of the material in this repository were drafted with the aid of large language model coding tools: Anthropic Claude models, most recently Claude Opus 5.5 (model ID `claude-opus-5-5`), accessed through the Claude Code command-line tool, beginning February 2026. This includes the Kubernetes job manifests and scripts under `catalog/` and `scripts/`, the agent guidance in `AGENTS.md` and `.claude/skills/`, and the STAC metadata and README files that this repository's workflows publish to object storage.

The authors directed this work and reviewed, tested, and validated the results, including generating manifests with the tested `cng-datasets` tool, checking published metadata with `scripts/verify-stac.py`, and checking hand-written manifests with `scripts/check-generated-manifests.py` in continuous integration. The authors take full responsibility for the code, metadata and text, and any errors they contain.
