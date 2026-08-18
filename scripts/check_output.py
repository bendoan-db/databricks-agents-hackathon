# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml"]
# ///
"""Mechanical checks on generated output/. Exits non-zero on any ERROR.

Checks the seams that nothing else looks at: the vector index name has to agree
across three files, catalog/schema have to agree across both artifacts, app.yaml
and the bundle's config.env have to stay in sync, and manifest.yaml has to mirror
the bundle's resource grants.

Usage:
    uv run scripts/check_output.py
    uv run scripts/check_output.py --quiet     # errors only
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

from ruamel.yaml import YAML

ROOT = Path(__file__).resolve().parent.parent
ING = ROOT / "output" / "document_ingestion_pipeline"
APP = ROOT / "output" / "agent_app"

errors: list[str] = []
warnings: list[str] = []
notes: list[str] = []


def load(p: Path):
    if not p.exists():
        return None
    yaml = YAML(typ="safe")
    with open(p) as f:
        return yaml.load(f) or {}


def get(d, path, default=None):
    cur = d
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def check_cross_artifact(ing_cfg, agent_cfg, bundle):
    """The one hard dependency between the two artifacts."""
    if ing_cfg is None or agent_cfg is None:
        return
    ing_index = get(ing_cfg, "ingestion.vector_search.index_name")
    app_index = get(agent_cfg, "retriever.index_name")
    if ing_index and app_index and ing_index != app_index:
        errors.append(
            f"vector index mismatch: pipeline creates {ing_index!r} but the agent "
            f"retriever points at {app_index!r}"
        )
    elif ing_index and not app_index:
        errors.append("agent_config.yaml retriever.index_name is empty; pipeline creates "
                      f"{ing_index!r}")
    elif ing_index:
        notes.append(f"index name agrees across artifacts: {ing_index}")

    if bundle:
        var_index = get(bundle, "variables.vs_index.default")
        if var_index and ing_index and var_index != ing_index:
            errors.append(f"databricks.yml variables.vs_index.default={var_index!r} does not "
                          f"match the pipeline's index {ing_index!r}")

    for key, ing_path, app_path in (
        ("catalog", "global.catalog", "databricks_config.catalog"),
        ("schema", "global.schema", "databricks_config.schema"),
    ):
        a, b = get(ing_cfg, ing_path), get(agent_cfg, app_path)
        if a and b and a != b:
            errors.append(f"{key} mismatch: pipeline {a!r} vs agent app {b!r}")


def check_env_sync(app_yaml, bundle):
    """app.yaml is local dev; databricks.yml config.env wins on deploy. They must agree."""
    if not app_yaml or not bundle:
        return
    apps = get(bundle, "resources.apps") or {}
    if not apps:
        warnings.append("databricks.yml declares no resources.apps entry")
        return
    app_key = next(iter(apps))
    bundle_env = {e["name"]: e.get("value", e.get("value_from")) for e in
                  (get(apps[app_key], "config.env") or []) if isinstance(e, dict) and "name" in e}
    local_env = {e["name"]: e.get("value", e.get("valueFrom")) for e in
                 (app_yaml.get("env") or []) if isinstance(e, dict) and "name" in e}

    for name in sorted(set(local_env) & set(bundle_env)):
        if local_env[name] != bundle_env[name] and "${" not in str(bundle_env[name]):
            warnings.append(f"env {name} differs: app.yaml={local_env[name]!r} vs "
                            f"databricks.yml={bundle_env[name]!r}")
    only_local = sorted(set(local_env) - set(bundle_env))
    if only_local:
        warnings.append(f"env vars in app.yaml but not databricks.yml config.env: {only_local}")


def check_manifest_mirror(manifest, bundle):
    if not manifest or not bundle:
        return
    spec_names = {s["name"] for s in (manifest.get("resource_specs") or []) if "name" in s}
    apps = get(bundle, "resources.apps") or {}
    if not apps:
        return
    grant_names = {r["name"] for r in (get(apps[next(iter(apps))], "resources") or [])
                   if isinstance(r, dict) and "name" in r}
    if spec_names != grant_names:
        missing = grant_names - spec_names
        extra = spec_names - grant_names
        msg = "manifest.yaml resource_specs do not mirror databricks.yml resources:"
        if missing:
            msg += f" granted but not declared {sorted(missing)};"
        if extra:
            msg += f" declared but not granted {sorted(extra)};"
        errors.append(msg.rstrip(";"))


def check_hardcoded(ing_cfg, agent_cfg):
    """A literal catalog or schema in a .py file is a generation bug."""
    literals = {v for v in (get(ing_cfg or {}, "global.catalog"), get(ing_cfg or {}, "global.schema"),
                            get(agent_cfg or {}, "databricks_config.catalog"),
                            get(agent_cfg or {}, "databricks_config.schema")) if v}
    if not literals:
        return
    for py in sorted(list(ING.rglob("*.py")) + list(APP.rglob("*.py"))):
        if "__pycache__" in py.parts:
            continue
        text = py.read_text(errors="replace")
        for lit in literals:
            for i, line in enumerate(text.splitlines(), 1):
                if lit in line and not line.lstrip().startswith("#"):
                    errors.append(f"{py.relative_to(ROOT)}:{i} hardcodes {lit!r} — read it from config")


def check_syntax():
    for py in sorted(list(ING.rglob("*.py")) + list(APP.rglob("*.py"))):
        if "__pycache__" in py.parts:
            continue
        src = py.read_text(errors="replace")
        # notebook-source files use %md / %sql magics that are comments already
        try:
            ast.parse(src)
        except SyntaxError as e:
            errors.append(f"{py.relative_to(ROOT)}:{e.lineno} syntax error: {e.msg}")


def check_step_numbering():
    steps = sorted(p.name for p in ING.glob("[0-9][0-9]_*.py"))
    if not steps:
        return
    nums = [int(s[:2]) for s in steps]
    expected = list(range(1, len(nums) + 1))
    if nums != expected:
        errors.append(f"pipeline step numbering is not contiguous from 01: {steps}")
    else:
        notes.append(f"{len(steps)} pipeline steps, numbered contiguously")


def check_config_keys_used(ing_cfg):
    """Every leaf under ingestion: should be read by some step."""
    if not ing_cfg:
        return
    src = "\n".join(p.read_text(errors="replace") for p in ING.rglob("*.py")
                    if "__pycache__" not in p.parts)

    def leaves(node, pre=""):
        if isinstance(node, dict):
            for k, v in node.items():
                yield from leaves(v, f"{pre}.{k}" if pre else k)
        else:
            yield pre

    for path in leaves(get(ing_cfg, "ingestion") or {}):
        key = path.split(".")[-1]
        if f'"{key}"' not in src and f"'{key}'" not in src:
            warnings.append(f"config.yaml ingestion.{path} is never read by any pipeline step")


def check_dead_paths():
    """A path named in a comment must exist."""
    # quoted OR bare — the existing output references a template path unquoted:
    #   "# Index built by 00b_document_ingestion_v2/03_create_vector_search_index.py"
    pat = re.compile(r"[`'\"\s(]([\w][\w./-]*\.(?:py|yaml|yml|md))[`'\"\s,.)]|[`'\"\s(]([\w][\w./-]*\.(?:py|yaml|yml|md))$")
    for f in sorted(list(ING.rglob("*")) + list(APP.rglob("*"))):
        if not f.is_file() or "__pycache__" in f.parts or f.suffix not in {".py", ".yaml", ".yml", ".md"}:
            continue
        for i, line in enumerate(f.read_text(errors="replace").splitlines(), 1):
            if not (line.lstrip().startswith(("#", "//")) or "MAGIC" in line):
                continue
            for m in pat.finditer(line):
                ref = m.group(1) or m.group(2)
                if "/" not in ref and ref != f.name:
                    if not (f.parent / ref).exists():
                        warnings.append(f"{f.relative_to(ROOT)}:{i} references {ref!r}, which does not exist")
                elif "/" in ref and not any((base / ref).exists() for base in (f.parent, ING, APP, ROOT)):
                    warnings.append(f"{f.relative_to(ROOT)}:{i} references {ref!r}, which does not exist")


def check_hygiene():
    caches = [p for p in (ROOT / "output").rglob("__pycache__") if p.is_dir()]
    if caches:
        warnings.append(f"{len(caches)} __pycache__ directories in output/ — compiled artifacts "
                        "should not ship with generated code")
    todos = []
    for f in sorted((ROOT / "output").rglob("*")):
        if not f.is_file() or "__pycache__" in f.parts or f.suffix not in {".py", ".yaml", ".yml", ".md", ".toml"}:
            continue
        for i, line in enumerate(f.read_text(errors="replace").splitlines(), 1):
            if "TODO" in line:
                todos.append(f"{f.relative_to(ROOT)}:{i} {line.strip()[:88]}")
    if todos:
        notes.append(f"{len(todos)} TODO markers a human must fill:")
        notes.extend("    " + t for t in todos)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    if not ING.exists() and not APP.exists():
        print("ERROR  nothing generated under output/ yet", file=sys.stderr)
        return 1

    ing_cfg = load(ING / "config.yaml")
    agent_cfg = load(APP / "agent_config.yaml")
    bundle = load(APP / "databricks.yml")
    app_yaml = load(APP / "app.yaml")
    manifest = load(APP / "manifest.yaml")

    if ING.exists() and ing_cfg is None:
        errors.append("output/document_ingestion_pipeline/config.yaml is missing")
    if APP.exists() and agent_cfg is None:
        errors.append("output/agent_app/agent_config.yaml is missing")

    check_cross_artifact(ing_cfg, agent_cfg, bundle)
    check_env_sync(app_yaml, bundle)
    check_manifest_mirror(manifest, bundle)
    check_hardcoded(ing_cfg, agent_cfg)
    check_syntax()
    check_step_numbering()
    check_config_keys_used(ing_cfg)
    check_dead_paths()
    check_hygiene()

    if not args.quiet:
        if notes:
            print("NOTES:")
            for n in notes:
                print(f"  . {n}")
            print()
        if warnings:
            print(f"WARNINGS ({len(warnings)}):")
            for w in warnings:
                print(f"  ~ {w}")
            print()

    if errors:
        print(f"ERRORS ({len(errors)}):")
        for e in errors:
            print(f"  x {e}")
        print("\nFAIL")
        return 1
    print(f"PASS" + (f" ({len(warnings)} warnings)" if warnings else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
