---
name: agent-gen-build-agent
description: Run the full agent harness end to end — intake to config, template selection, both generated artifacts, then validation. Use when asked to build or regenerate a Databricks agent from the intake, or to run the whole pipeline in one go.
---

# Build a custom Databricks agent

Orchestrator. Runs the four harness stages in order, stopping at the first gate
that fails rather than generating on top of bad inputs.

```
input/intake/INTAKE.md
        |  agent-gen-intake-to-config              + scripts/detect_examples.py
        v                                  scripts/validate_config.py  (GATE)
input/generation_config.yaml
        |  agent-gen-select-templates              + scripts/fetch_templates.py
        v
input/selection.yaml  +  .template_cache/
        |
        +-- agent-gen-generate-ingestion-pipeline -> output/document_ingestion_pipeline/
        |          (writes config.yaml: index_name, catalog, schema)
        |                    |
        |                    v  must run first
        +-- agent-gen-generate-agent-app         -> output/agent_app/
        |
        v  agent-gen-validate-output              + scripts/check_output.py  (GATE)
```

## Procedure

1. **`agent-gen-intake-to-config`** — stop if the intake is unanswered. Report derived
   values, gaps, and sample-vs-claim discrepancies.

2. **Gate:** `uv run scripts/validate_config.py`. Errors stop the run. Ask the
   user for what only they can supply rather than guessing.

3. **`agent-gen-select-templates`** — writes `input/selection.yaml` and fetches code-only
   into `.template_cache/`. Surface anything under `unsupported:` before
   continuing.

4. **`agent-gen-generate-ingestion-pipeline`** — must precede the app. Report the
   `index_name` it settled on.

5. **`agent-gen-generate-agent-app`** — consumes that index name plus catalog/schema from
   the pipeline's `config.yaml`.

6. **Gate:** `agent-gen-validate-output`. Fix generation errors, then re-run.

7. **Hand off.** Report: what was built, which templates it came from, the
   remaining `# TODO:` list, and the deploy sequence:
   ```
   databricks bundle validate -t dev
   databricks bundle deploy   -t dev
   databricks bundle run <app_resource> -t dev
   ```

## Partial and repeat runs

Each stage is separately invocable — prefer the narrowest one.

| Situation | Run |
|---|---|
| Intake answers changed | the full chain from stage 1 |
| Config hand-edited | from stage 2 (selection may change) |
| Chunking or parsing needs re-tuning | `agent-gen-generate-ingestion-pipeline` + `agent-gen-validate-output` |
| Prompt, tools, or scorers need changing | `agent-gen-generate-agent-app` + `agent-gen-validate-output` |
| Just checking consistency | `agent-gen-validate-output` |

If `input/selection.yaml` is older than `input/generation_config.yaml`, the
selection is stale — re-run stage 3 rather than generating against it.

## Do not

- Do not skip a gate to keep the run moving. A generated artifact built on an
  invalid config looks finished and is not.
- Do not run the two generators in parallel; the app depends on the pipeline's
  config output.
- Do not overwrite `output/` when a previous run's artifacts are still being
  reviewed without saying what will be replaced.
