# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml"]
# ///
"""Derive the `example_provided` booleans from the filesystem.

These two config fields are the only ones whose value comes from what is on disk
rather than from a human's intake answer, so they are computed here rather than
left to judgment. Also reports observed file types and counts, which the
agent-gen-intake-to-config skill uses as a cross-check against what the intake claims.

Usage:
    uv run scripts/detect_examples.py             # report only
    uv run scripts/detect_examples.py --write     # patch generation_config.yaml
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from ruamel.yaml import YAML

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "input" / "generation_config.yaml"
DOC_DIR = ROOT / "input" / "intake" / "example_documents"
TAB_DIR = ROOT / "input" / "intake" / "example_structured_data"

IGNORE = {".DS_Store", ".gitkeep", "README.md"}


def scan(d: Path) -> dict:
    if not d.exists():
        return {"exists": False, "count": 0, "types": {}, "bytes": 0, "files": []}
    files = [p for p in d.rglob("*") if p.is_file() and p.name not in IGNORE]
    return {
        "exists": True,
        "count": len(files),
        "types": dict(Counter(p.suffix.lower().lstrip(".") or "(no ext)" for p in files)),
        "bytes": sum(p.stat().st_size for p in files),
        "files": [str(p.relative_to(d)) for p in sorted(files)[:10]],
    }


def report(label: str, path: Path, s: dict) -> None:
    print(f"\n{label}")
    print(f"  path:     {path.relative_to(ROOT)}")
    if not s["exists"]:
        print("  MISSING directory")
    print(f"  files:    {s['count']}")
    if s["count"]:
        print(f"  types:    {', '.join(f'{k} x{v}' for k, v in sorted(s['types'].items()))}")
        print(f"  size:     {s['bytes'] / 1024:.1f}K")
        for f in s["files"]:
            print(f"    - {f}")
        if s["count"] > len(s["files"]):
            print(f"    ... and {s['count'] - len(s['files'])} more")
    print(f"  -> example_provided: {str(s['count'] > 0).lower()}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="patch generation_config.yaml in place")
    args = ap.parse_args()

    docs, tabs = scan(DOC_DIR), scan(TAB_DIR)
    report("unstructured_data.example_provided", DOC_DIR, docs)
    report("structured_data.example_provided", TAB_DIR, tabs)

    if docs["count"]:
        exts = sorted(docs["types"], key=lambda k: -docs["types"][k])
        print(f"\nObserved document_file_type: {exts[0]}" + (f" (also {', '.join(exts[1:])})" if len(exts) > 1 else ""))
        print(f"Observed document_count:     {docs['count']}")
        print("  Cross-check these against the intake answers; a mismatch means the")
        print("  sample is not representative of the real corpus. Do not silently")
        print("  overwrite the intake's numbers with the sample's.")

    if not args.write:
        print("\n(report only — pass --write to patch generation_config.yaml)")
        return 0

    yaml = YAML()  # round-trip: preserves comments and ordering
    yaml.preserve_quotes = True
    with open(CONFIG) as f:
        cfg = yaml.load(f)

    changed = []
    for section, value in (("unstructured_data", docs["count"] > 0), ("structured_data", tabs["count"] > 0)):
        if section not in cfg:
            print(f"WARNING: no `{section}:` section in {CONFIG.name}, skipping", file=sys.stderr)
            continue
        if cfg[section].get("example_provided") != value:
            cfg[section]["example_provided"] = value
            changed.append(f"{section}.example_provided = {str(value).lower()}")

    if not changed:
        print("\nNo change — config already matches the filesystem.")
        return 0

    with open(CONFIG, "w") as f:
        yaml.dump(cfg, f)
    print("\nPatched " + str(CONFIG.relative_to(ROOT)) + ":")
    for c in changed:
        print(f"  {c}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
