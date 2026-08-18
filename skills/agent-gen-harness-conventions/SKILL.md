---
name: agent-gen-harness-conventions
description: The house style for generated artifacts in this harness — output layout, config-driven rules, comment conventions, and the cross-artifact contract between the ingestion pipeline and the agent app. Load this before generating or validating anything under output/. Not a stage skill; it is reference material the agent-gen-generate-* and agent-gen-validate-output skills read.
---

# Harness output conventions

The four template repos in `input/templates.yaml` do **not** share a structure. This
document is what makes `output/` look the same regardless of which template was
selected. When a template's shape conflicts with what is written here, this
document wins — port the template's *logic*, not its layout.

Everything below was extracted from the existing generated artifacts in `output/`.
Read those files directly for worked examples before generating new ones.

## Output layout

```
output/document_ingestion_pipeline/
  config.yaml                        # all tunables; the .py files read this and nothing else
  01_parse_documents.py              # numbered, one materialized stage each
  02_prep_search_chunks.py
  03_create_vector_search_index.py

output/agent_app/
  agent_config.yaml                  # agent tunables, env-overridable
  app.yaml                           # LOCAL dev config
  databricks.yml                     # DAB: variables, app resource, config.env, targets
  manifest.yaml                      # resource_specs the app declares
  pyproject.toml
  .env.example
  README.md
  agent_server/
    agent.py                         # @invoke() / @stream() handlers
    config.py                        # YAML + env-var overrides -> frozen dataclasses
    retriever.py                     # tool construction
    prompts.py                       # system prompt builder
    evaluate_agent.py                # MLflow eval driver
    utils.py                         # session id, temporal context, stream adapters
    start_server.py
  scripts/start_app.py
```

Numbered pipeline steps exist so each expensive stage materializes on its own.
Parsing is the costly step; iterating on chunking must never re-parse the corpus.
Preserve that boundary even if a template runs everything in one notebook.

## Rule 1: nothing workspace-specific is hardcoded in Python

Every catalog, schema, table, volume, index, endpoint, and warehouse id lives in
`config.yaml` or `agent_config.yaml`. Python reads config and composes names:

```python
volume_path = f"/Volumes/{catalog}/{schema}/{volume_name}"
parsed_table_path = f"{catalog}.{schema}.{parsed_table}"
```

A literal catalog name in a `.py` file is a generation bug. `agent-gen-validate-output`
greps for this.

## Rule 2: the pipeline config-load idiom

Pipeline steps are Databricks notebook-source `.py` files. Reproduce this header
and load block exactly — the runtime check is what lets the same file run both as
a job task and locally:

```python
# Databricks notebook source
# MAGIC %md
# MAGIC # <What this step does>
# MAGIC
# MAGIC **Input:** `/Volumes/{catalog}/{schema}/{document_volume}`
# MAGIC **Output:**
# MAGIC - `<table>` — one row per <grain>
# MAGIC - `<errors_table>` — rows that failed
# MAGIC
# MAGIC <Why this step is separate, and what it deliberately does not do.>

# COMMAND ----------

import os
import yaml

# COMMAND ----------

if "DATABRICKS_RUNTIME_VERSION" in os.environ:
    config_path = "config.yaml"
else:
    notebook_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(notebook_dir, "config.yaml")

with open(config_path, "r") as f:
    config = yaml.safe_load(f)
```

Then unpack config into named locals, and print a resolved-configuration summary
before doing work. Every step ends by printing what it wrote and where.

Pipeline configs carry guardrails, not just names — e.g. `max_error_rate: 0.05`
fails the step when too large a fraction of documents error, instead of quietly
producing a thin table.

## Rule 3: three-layer config precedence in the app

`databricks.yml` `config.env` **>** environment variables **>** `agent_config.yaml`
defaults. The point is that a deployed app can be repointed at a different index
or LLM endpoint by editing `databricks.yml` and redeploying, with no code change.

`config.py` implements this with `_env_str` / `_env_int` / `_env_float` helpers,
frozen dataclasses, and `@lru_cache(maxsize=1)` on the loader. It **validates and
raises** rather than defaulting silently:

```python
if index_full_name.count(".") != 2:
    raise ValueError(f"Vector search index must be a 3-part name 'catalog.schema.index', got {index_full_name!r}.")
if query_type not in {"ANN", "HYBRID"}:
    raise ValueError(f"query_type must be 'ANN' or 'HYBRID', got {query_type!r}.")
```

Carry this forward: every enum-valued and structurally-constrained config value
gets a load-time check with an actionable message.

## Rule 4: comments state *why*, and flag what is load-bearing

This is the most distinctive thing about the house style. Comments record
rationale and warn against plausible-looking edits:

```yaml
  # Must be "HYBRID" or "ANN" (uppercase — the tool validates against those exact strings).
  # HYBRID is load-bearing here: its keyword leg is what matches "NETFLIX" and "2017" as
  # literal tokens now that there are no metadata filters.
  query_type: HYBRID
```

When a value came from the config rather than the template default, say so. When
a template's value was deliberately changed, say what it was and why. When
something was removed, say what and why. Do not write comments that restate the
code.

## Rule 5: `# TODO:` marks values a human must supply

Workspace-specific values that the harness cannot know get a real value where one
is inferable and a TODO marker either way:

```yaml
  catalog: ssa_team_sandbox_classic_catalog # TODO: add catalog
  experiment_id: "" # TODO: set the MLflow experiment id
```

Never invent a warehouse id, experiment id, secret scope, or workspace URL.
Leave it empty with a TODO.

## Rule 6: the cross-artifact contract

The one hard dependency between the two output directories:

```
document_ingestion_pipeline/config.yaml : ingestion.vector_search.index_name
                    |
                    v
agent_app/agent_config.yaml             : retriever.index_name
agent_app/databricks.yml                : variables.vs_index.default
```

All three must agree, and `catalog`/`schema` must match across both artifacts.
This is what `agent-gen-validate-output` checks first. It is also why the ingestion pipeline
is generated before the agent app.

Related seams that must stay in sync:

- `app.yaml` `env` **↔** `databricks.yml` `config.env` — app.yaml is local dev only,
  the bundle block wins on deploy. Both files carry a comment saying so.
- `manifest.yaml` `resource_specs` **↔** `databricks.yml` `resources` — same
  resource names, same permissions, one declares and one grants.
- Any path referenced in a comment must exist. The current output has a stale
  reference to `00b_document_ingestion_v2/03_create_vector_search_index.py`;
  generated comments must point at real files in `output/`.

## Rule 7: deploy sequence and naming

`databricks.yml` documents the full three-step sequence in its header, including
the trap that `deploy` alone leaves the app on old code:

```
databricks bundle validate -t dev
databricks bundle deploy   -t dev
databricks bundle run <app_resource_name> -t dev
```

Databricks apps for agents are named with an `agent-` prefix
(`name: "agent-sec-research"`). Bundle name and resource key use snake_case;
the app `name` uses kebab-case.

Targets are `dev` (mode: development, default: true) and `prod` (mode: production).

## Rule 8: what not to carry over from templates

- Template-specific corpora, sample data, and `mlflow.db` files.
- Setup notebooks that upload a template's own demo data.
- Hardcoded entity lists, company names, or eval fixtures from the template's domain.
- Numbered-directory schemes from the template (`00_document_ingestion/`,
  `01_research_agent/`) — the output layout above is flat per artifact.
- Anything in the template's `MIGRATE.md` / changelog framing. If the generated
  code deliberately differs from the template, explain it in a comment at the
  point of difference, not in a separate migration doc.
