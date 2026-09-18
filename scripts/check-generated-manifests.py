#!/usr/bin/env python3
"""Flag catalog recipes that invoke cng-datasets from a HAND-WRITTEN manifest.

Why this exists
---------------
`cng-datasets` is tested and has a deploy pipeline; a manifest typed by hand is
neither. Hand-rolled recipes drift from the tool in ways that are invisible in
review -- a missing --nodata, a stale reducer, a namespace that silently resolves
to `default`. The catalog is currently 90 generated raster recipes to 26
hand-rolled, and the hand-rolled ones are disproportionately the large, hard,
expensive builds.

The failure mode this guards against is social, not technical: an agent copies a
neighbouring hand-rolled recipe because that is what the catalog shows it, and a
reviewer who is not sure whether the deviation was deliberate does not push back.
Making the deviation *explicit* moves that conversation from "should I challenge
this?" to "this file says why".

The rule
--------
A recipe directory that runs `cng-datasets` must either

  * carry the generator banner (`# Generation command: cng-datasets ...`), or
  * declare, in the manifest that deviates, why it does not:

        # HAND-ROLLED: <reason> (<tracking issue>)

Deviating is legitimate -- some shapes the generator genuinely cannot emit yet
(boettiger-lab/datasets#190, #191, #172, #39). The requirement is a stated reason
and, where the gap is in the tool, an issue to close so the deviation is
temporary rather than permanent.

Exit 0 clean, 1 if any recipe is undeclared.
"""
import pathlib, re, subprocess, sys

CNG_CALL = re.compile(r"\bcng-datasets\s+(raster|convert|hex|workflow|raster-workflow)\b")
BANNER = re.compile(r"Generation command:\s*cng-datasets")
DECLARED = re.compile(r"#\s*HAND-ROLLED:\s*(\S.*)")


def changed_paths(base):
    try:
        out = subprocess.run(["git", "diff", "--name-only", f"{base}...HEAD"],
                             capture_output=True, text=True, check=True).stdout
        return [pathlib.Path(p) for p in out.split() if p.startswith("catalog/")]
    except subprocess.CalledProcessError:
        return None


def main():
    args = sys.argv[1:]
    base = None
    if args and args[0] == "--base":
        base = args[1]; args = args[2:]

    root = pathlib.Path("catalog")
    if base:
        paths = changed_paths(base)
        dirs = sorted({p.parent for p in (paths or []) if p.suffix in (".yaml", ".yml")})
        if not dirs:
            print("no changed catalog manifests -- nothing to check")
            return 0
    else:
        dirs = sorted({p.parent for p in root.rglob("*.y*ml")})

    offenders = []
    for d in dirs:
        if not d.exists():
            continue
        files = list(d.glob("*.y*ml"))
        text = {f: f.read_text(errors="ignore") for f in files}
        invoking = [f for f, t in text.items() if CNG_CALL.search(t)]
        if not invoking:
            continue
        if any(BANNER.search(t) for t in text.values()):
            continue                                   # generated -- fine
        declared = [DECLARED.search(t) for t in text.values()]
        if any(declared):
            reason = next(m for m in declared if m).group(1).strip()
            print(f"  declared  {d}  -- {reason}")
            continue
        offenders.append((d, invoking))

    if offenders:
        print("\nUNDECLARED hand-rolled recipes (invoke cng-datasets, no generator "
              "banner, no HAND-ROLLED declaration):\n")
        for d, files in offenders:
            print(f"  {d}")
            for f in files:
                print(f"      {f.name}")
        print("\nEither regenerate with `cng-datasets ... --output-dir <dir>`, or add to the\n"
              "manifest that deviates:\n\n"
              "    # HAND-ROLLED: <why the generator cannot emit this> (<tracking issue>)\n")
        return 1

    print("OK: every catalog recipe invoking cng-datasets is generated or declares why not.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
