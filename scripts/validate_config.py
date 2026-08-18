# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml"]
# ///
"""Validate a filled-in generation_config.yaml before generation runs.

Catches the two failure modes that produce plausible-looking but wrong output:
unfilled fields that a generator would silently default, and free-text answers
that never got normalized to the enum values the templates key off.

Exits non-zero on ERROR so it can gate the pipeline. WARNINGs are advisory.

Usage:
    uv run scripts/validate_config.py
    uv run scripts/validate_config.py --quiet   # errors only
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ruamel.yaml import YAML

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "input" / "generation_config.yaml"

ENUMS = {
    "unstructured_data.source_quality": ["clean_digital", "mixed", "scanned_ocr_required"],
    "agent.task_type": ["conversational_chat", "workflow_automation", "batch_extraction", "research_assistant"],
    "agent.agent_pattern": ["single_agent", "multi_agent_supervisor", "deterministic_workflow"],
    "agent.framework": ["openai_agents_sdk", "langgraph", "dspy", "custom"],
    "agent.memory.scope": ["none", "thread", "user"],
    "agent.memory.state_backend": ["none", "lakebase"],
}
FIELD_TYPES = ["string", "number", "date", "boolean", "array"]

ALWAYS_REQUIRED = [
    "project.name",
    "project.description",
    "agent.task_type",
    "agent.agent_pattern",
    "agent.framework",
    "agent.llm_endpoint",
]

# (condition path, required-when-true paths)
CONDITIONAL = [
    ("unstructured_data.enabled", [
        "unstructured_data.source.location",
        "unstructured_data.document_file_type",
        "unstructured_data.document_description",
        "unstructured_data.source_quality",
        "unstructured_data.advanced_figures",
    ]),
    ("unstructured_data.custom_metadata_extraction", ["unstructured_data.metadata_fields"]),
    ("structured_data.enabled", ["structured_data.table_description", "structured_data.schema"]),
    ("agent.memory.enabled", ["agent.memory.scope", "agent.memory.state_backend"]),
]

errors: list[str] = []
warnings: list[str] = []


def get(cfg, path: str, missing=KeyError):
    cur = cfg
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return missing
        cur = cur[part]
    return cur


def is_empty(v) -> bool:
    return v is None or v == "" or v == [] or v == {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    if not CONFIG.exists():
        print(f"ERROR  {CONFIG} not found", file=sys.stderr)
        return 1

    yaml = YAML(typ="safe")
    with open(CONFIG) as f:
        cfg = yaml.load(f) or {}

    for path in ALWAYS_REQUIRED:
        v = get(cfg, path)
        if v is KeyError:
            errors.append(f"{path}: field absent from config")
        elif is_empty(v):
            errors.append(f"{path}: required but empty")

    for cond, required in CONDITIONAL:
        if get(cfg, cond) is True:
            for path in required:
                v = get(cfg, path)
                if v is KeyError or is_empty(v):
                    errors.append(f"{path}: required because {cond} is true")

    for path, allowed in ENUMS.items():
        v = get(cfg, path)
        if v is KeyError or is_empty(v):
            continue
        if v not in allowed:
            errors.append(f"{path}: {v!r} is not one of {allowed} — normalize the intake answer")

    for section in ("unstructured_data.metadata_fields", "structured_data.schema"):
        fields = get(cfg, section)
        if fields is KeyError or is_empty(fields):
            continue
        if not isinstance(fields, list):
            errors.append(f"{section}: expected a list, got {type(fields).__name__}")
            continue
        for i, f in enumerate(fields):
            if not isinstance(f, dict):
                errors.append(f"{section}[{i}]: expected a mapping with name/type/description")
                continue
            if is_empty(f.get("name")):
                errors.append(f"{section}[{i}].name: required")
            t = f.get("type")
            if not is_empty(t) and t not in FIELD_TYPES:
                errors.append(f"{section}[{i}].type: {t!r} is not one of {FIELD_TYPES}")
            if is_empty(f.get("description")):
                warnings.append(f"{section}[{i}].description: empty — the LLM uses this to extract the field")

    # neither data source enabled means there is nothing to build
    uns, st = get(cfg, "unstructured_data.enabled"), get(cfg, "structured_data.enabled")
    if uns is not True and st is not True:
        errors.append("unstructured_data.enabled and structured_data.enabled are both false/unset — no data source to build against")

    # advisory-only fields that materially improve the system prompt
    for path in ("business_context.business_outcome", "business_context.current_process", "agent.system_prompt_guidance"):
        v = get(cfg, path)
        if v is KeyError or is_empty(v):
            warnings.append(f"{path}: empty — the generated system prompt will be generic")

    if get(cfg, "agent.framework") in ("dspy", "custom"):
        warnings.append(f"agent.framework={get(cfg,'agent.framework')!r}: no template in templates.yaml uses this framework; the generator will have to adapt one")

    if not args.quiet and warnings:
        print(f"WARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"  ~ {w}")
        print()

    if errors:
        print(f"ERRORS ({len(errors)}):")
        for e in errors:
            print(f"  x {e}")
        print("\nFAIL — fix the errors above before running generation.")
        return 1

    print(f"PASS — generation_config.yaml is complete and consistent" + (f" ({len(warnings)} warnings)" if warnings else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
