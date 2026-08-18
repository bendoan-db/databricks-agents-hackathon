---
name: agent-gen-validate-output
description: Check generated output/ for cross-artifact seam breaks, template leakage, hardcoded workspace values, and unfilled TODOs. Use after either agent-gen-generate-* skill, before deploying, or when asked whether generated artifacts are consistent.
---

# Validate generated output

Stage 4. Catches the failure class where generated code is individually plausible
but collectively broken — the pipeline builds `index_a` while the app queries
`index_b`, or a comment points at a file that only exists in the template repo.

**In:** `output/`
**Out:** a pass/fail report

## Run the mechanical checks first

```
uv run scripts/check_output.py
```

Exits non-zero on any ERROR. What it covers:

| Check | Severity | Why |
|---|---|---|
| Vector index name agrees across pipeline config, `agent_config.yaml`, `databricks.yml` | ERROR | The one hard cross-artifact dependency |
| `catalog` / `schema` agree across both artifacts | ERROR | Silent mismatch produces a working app pointed at nothing |
| `manifest.yaml` `resource_specs` mirror `databricks.yml` `resources` | ERROR | Declared-but-not-granted fails at runtime, not deploy |
| Hardcoded catalog/schema literals in `.py` | ERROR | Breaks the config-driven rule |
| Python syntax | ERROR | — |
| Pipeline steps numbered contiguously from `01` | ERROR | Renumbering was missed when a step was added or dropped |
| `app.yaml` `env` vs `databricks.yml` `config.env` drift | WARNING | app.yaml is local dev; bundle wins on deploy |
| Config keys never read by any step | WARNING | Dead config, or a step that forgot to honor it |
| Paths named in comments that do not exist | WARNING | Template leakage |
| `__pycache__` in `output/` | WARNING | Compiled artifacts should not ship |
| `# TODO:` inventory | NOTE | The human's pre-deploy checklist |

## Then check what a script cannot

The script compares files to each other. It cannot tell whether the code does what
the config asked for. Verify by reading:

1. **Did every enabled capability actually get built?** Walk the config's booleans
   and confirm each one produced code: `custom_metadata_extraction` -> an
   `ai_extract` step whose schema matches `metadata_fields[]`;
   `human_in_the_loop` -> confirmation gating on the right tools;
   `memory.enabled` -> a state backend; each true `evaluation.scorers.*` -> a
   scorer in `evaluate_agent.py`. A silently dropped capability is the most
   common generation failure and no seam check catches it.

2. **Do the retriever's columns exist?** `agent_config.yaml`
   `retriever.columns` must be a subset of the pipeline's
   `vector_search.columns_to_sync` plus the auto-appended primary key and
   embedding source column.

3. **Is the prompt domain-specific?** `prompts.py` should reflect
   `document_description`, `business_context`, and the corpus's limits. A generic
   "you are a helpful assistant" prompt means step 7 of `agent-gen-intake-to-config` was
   skipped.

4. **Is anything left over from the template's domain?** Company names, entity
   lists, eval fixtures, or table names from the template's subject matter rather
   than this project's.

5. **Optionally, does the bundle validate?**
   ```
   databricks bundle validate -t dev
   ```
   Requires workspace auth and will fail on unfilled TODOs — a TODO-driven failure
   here is expected, not a generation bug.

## Report

Errors first with the file and line, then warnings worth acting on, then the TODO
checklist. Distinguish clearly between "generation is wrong" and "a human still
has to fill this in" — they are different asks.

## Do not

- Do not fix errors silently as part of validating. Report, then fix in a
  separate pass so the user sees what was wrong.
- Do not treat unfilled TODOs as failures; they are the designed handoff.
