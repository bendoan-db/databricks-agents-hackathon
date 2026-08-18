# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml"]
# ///
"""Sparse-clone template repos, code only, into .template_cache/.

Why this exists: a plain `git clone` of the template catalog is pathological. The
financebench template is a 1.2 GB clone of which 673 MB is `data/` PDFs, wrapped
around 131 KB of actual code. This fetches blobs lazily and checks out only
source files, so the cache holds what a generator can actually read.

Usage:
    uv run scripts/fetch_templates.py                    # all templates
    uv run scripts/fetch_templates.py --template NAME    # just one
    uv run scripts/fetch_templates.py --manifest         # list what's cached
    uv run scripts/fetch_templates.py --force            # re-clone
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from ruamel.yaml import YAML

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_YAML = ROOT / "input" / "templates.yaml"
CACHE = ROOT / ".template_cache"

# Checked out. gitignore-style, matched at any depth.
CODE_PATTERNS = ["*.py", "*.ipynb", "*.yaml", "*.yml", "*.toml", "*.md", "*.txt", "*.sql", "*.json"]

# Never checked out even when a pattern would match — these are corpora, not code.
EXCLUDE_DIRS = ["data", "datasets", "sample_data", "notebooks/data", ".github"]

MAX_FILE_BYTES = 512_000  # a "code" file bigger than this is almost certainly data


def load_templates() -> list[dict]:
    yaml = YAML(typ="safe")
    with open(TEMPLATES_YAML) as f:
        return yaml.load(f).get("templates") or []


def parse_link(link: str) -> tuple[str, str | None]:
    """Split a GitHub URL into (clone_url, ref). Supports /tree/<ref> pins."""
    link = link.split("#")[0].strip().rstrip("/")
    if "/tree/" in link:
        base, ref = link.split("/tree/", 1)
        return base + ".git", ref.split("/")[0]
    return link + ".git", None


def run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def fetch(name: str, link: str, force: bool) -> dict:
    dest = CACHE / name
    clone_url, ref = parse_link(link)

    if dest.exists():
        if not force:
            return {"name": name, "status": "cached", "path": dest}
        shutil.rmtree(dest)

    dest.parent.mkdir(parents=True, exist_ok=True)

    # blob:none defers file contents; no-checkout keeps the working tree empty until
    # sparse patterns are set, so excluded blobs are never downloaded at all.
    cmd = ["git", "clone", "--filter=blob:none", "--no-checkout", "--depth", "1", clone_url, str(dest)]
    if ref:
        cmd[-2:-2] = ["--branch", ref]
    r = run(cmd)
    if r.returncode != 0:
        return {"name": name, "status": "FAILED", "error": r.stderr.strip().splitlines()[-1:] or ["clone failed"]}

    patterns = list(CODE_PATTERNS) + [f"!/{d}/" for d in EXCLUDE_DIRS]
    run(["git", "sparse-checkout", "set", "--no-cone", *patterns], cwd=dest)
    r = run(["git", "checkout"], cwd=dest)
    if r.returncode != 0:
        return {"name": name, "status": "FAILED", "error": [r.stderr.strip()]}

    # Drop oversized "code" files that slipped through (giant JSON fixtures, etc.)
    dropped = 0
    for p in dest.rglob("*"):
        if p.is_file() and ".git" not in p.parts and p.stat().st_size > MAX_FILE_BYTES:
            p.unlink()
            dropped += 1

    return {"name": name, "status": "fetched", "path": dest, "dropped": dropped, "ref": ref or "default"}


def summarize(dest: Path) -> tuple[int, int]:
    files = [p for p in dest.rglob("*") if p.is_file() and ".git" not in p.parts]
    return len(files), sum(p.stat().st_size for p in files)


def human(n: int) -> str:
    for unit in ("B", "K", "M", "G"):
        if n < 1024 or unit == "G":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n/1:.0f}{unit}" if False else f"{n:.1f}{unit}"
        n /= 1024.0
    return f"{n:.1f}G"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", help="fetch only this template_name")
    ap.add_argument("--force", action="store_true", help="re-clone even if cached")
    ap.add_argument("--manifest", action="store_true", help="list cached files and exit")
    args = ap.parse_args()

    templates = load_templates()
    if args.template:
        templates = [t for t in templates if t.get("template_name") == args.template]
        if not templates:
            print(f"No template named {args.template!r} in {TEMPLATES_YAML}", file=sys.stderr)
            return 1

    if args.manifest:
        for t in templates:
            d = CACHE / t["template_name"]
            if not d.exists():
                print(f"{t['template_name']}: NOT CACHED")
                continue
            print(f"\n{t['template_name']}:")
            for p in sorted(d.rglob("*")):
                if p.is_file() and ".git" not in p.parts:
                    print(f"  {p.stat().st_size:>8}  {p.relative_to(d)}")
        return 0

    failed = 0
    for t in templates:
        name, link = t.get("template_name"), t.get("github_link", "")
        if not link or "<org>" in link:
            print(f"SKIP    {name}: github_link not filled in")
            continue
        res = fetch(name, link, args.force)
        if res["status"] == "FAILED":
            failed += 1
            print(f"FAILED  {name}: {'; '.join(res['error'])}")
            continue
        n, size = summarize(res["path"])
        extra = f"  (dropped {res['dropped']} oversized)" if res.get("dropped") else ""
        print(f"{res['status'].upper():7s} {name}: {n} files, {human(size)}{extra}")

    print(f"\nCache: {CACHE}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
