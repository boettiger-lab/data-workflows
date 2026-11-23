#!/usr/bin/env python3
"""Flag catalog files that upload a STAC collection without stac-publish-guard.py.

A job that uploads a collection built from JSON it carries (a ConfigMap, a gen_stac.py run)
replaces whatever is live, and undoes every catalog-wide change made since that JSON was
written: default styles (#881), the column dictionary and rel pmtiles links (#890), asset-key
renames. scripts/stac-publish-guard.py keeps what can be kept and refuses the rest.

The rule: a catalog file that writes `stac-collection.json` to NRP must either

  * run the guard (mention `stac-publish-guard`), or
  * say why it does not need to:

        # STAC-PUBLISH-GUARD: not needed: <reason>

    The usual reason is that the job reads the live collection and edits it in place, so
    nothing added since is lost (the audit fix jobs, the coral-reef-watch extent updates).

A file counts as a writer when it mentions `stac-collection.json` and uploads a local file with
`rclone copyto`/`copy` (source not `nrp:`) or `rclone rcat`, in shell or as a Python argument
list. That is deliberately broad; a false positive costs one declaration line.

Ratchets like check-generated-manifests.py: with --base, only the catalog files the PR
changes are checked. --all lists every undeclared writer. Exit 0 clean, 1 otherwise.
"""
import pathlib
import re
import subprocess
import sys

UPLOAD = re.compile(
    r"""rclone\s+(?:copyto|copy)\s+(?:--?\S+\s+)*(?!["']?nrp:)["']?[^\s"'-]"""   # local source
    r"""|rclone\s+rcat\s"""
    r"""|\[\s*['"]rclone['"]\s*,\s*['"](?:copyto|copy)['"]\s*,\s*(?!f?['"]nrp:)"""
    r"""|\[\s*['"]rclone['"]\s*,\s*['"]rcat['"]""")
COLLECTION = "stac-collection.json"
GUARDED = re.compile(r"stac-publish-guard")
DECLARED = re.compile(r"#\s*STAC-PUBLISH-GUARD:\s*not needed:\s*\S")
SUFFIXES = {".yaml", ".yml", ".sh", ".py"}


def is_unguarded_writer(text: str) -> bool:
    return (COLLECTION in text and bool(UPLOAD.search(text))
            and not GUARDED.search(text) and not DECLARED.search(text))


def changed(base: str) -> list[pathlib.Path]:
    out = subprocess.run(["git", "diff", "--name-only", "--diff-filter=AMR", f"{base}...HEAD"],
                         capture_output=True, text=True, check=True).stdout
    return [pathlib.Path(p) for p in out.split() if p.startswith("catalog/")]


def main(argv: list[str]) -> int:
    if argv[1:3] and argv[1] == "--base":
        paths = changed(argv[2])
    elif argv[1:] == ["--all"]:
        paths = sorted(pathlib.Path("catalog").rglob("*"))
    else:
        print(__doc__, file=sys.stderr)
        return 2
    bad = [p for p in paths if p.suffix in SUFFIXES and p.is_file()
           and is_unguarded_writer(p.read_text(errors="replace"))]
    for p in bad:
        print(f"{p}: uploads a stac-collection.json without stac-publish-guard.py. Guard it "
              f"(see the script's docstring), or add `# STAC-PUBLISH-GUARD: not needed: "
              f"<reason>` if it reads the live collection and edits it in place.")
    if not bad:
        print(f"ok: {len(paths)} catalog file(s) checked")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
