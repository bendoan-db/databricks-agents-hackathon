---
name: agent-gen-generate-agent-app
description: Generate output/agent_app/ from input/selection.yaml, the generation config, and cached template code. Use after agent-gen-generate-ingestion-pipeline, since the app's retriever config must match the index the pipeline creates.
---

# Generate the agent app

Stage 3b. A Databricks App on the Agents-on-Apps framework: MLflow
`agent_server` handlers behind the built-in chat UI, deployed via DAB.

**In:** `input/selection.yaml`, `input/generation_config.yaml`,
`output/document_ingestion_pipeline/config.yaml`, `.template_cache/`
**Out:** `output/agent_app/`

## Before writing anything

1. Load the `agent-gen-harness-conventions` skill.
2. Read `input/selection.yaml` -> `artifacts.agent_app`; read only its
   `read_files`.
3. Read `output/document_ingestion_pipeline/config.yaml` — specifically
   `global.catalog`, `global.schema`, and `ingestion.vector_search.index_name`.
   These are inputs, not choices. If that file does not exist, stop: run
   `agent-gen-generate-ingestion-pipeline` first.
4. Read the existing `output/agent_app/` as a worked example of the target shape.

## File-by-file

**`agent_config.yaml`** — `databricks_config` / `llm` / `retriever` sections.
`retriever.index_name` must equal the pipeline's
`ingestion.vector_search.index_name`. `llm.endpoint_name` from
`agent.llm_endpoint`. `retriever.columns` must be columns the pipeline actually
syncs. `tool_name` should be domain-specific and verb-like
(`search_sec_filings`), never `search_documents`.

**`agent_server/config.py`** — YAML plus env-var overrides into frozen
dataclasses, `@lru_cache(maxsize=1)` on the loader, and a load-time raise for
every constrained value (3-part index names, `ANN`/`HYBRID`, numeric coercion).
One override env var per value that a deployed app might need repointed.

**`agent_server/agent.py`** — shape follows `agent.framework` and
`agent.agent_pattern`:

| Config | Structure |
|---|---|
| `single_agent` | one model, one `create_agent`, tool list built once |
| `multi_agent_supervisor` | supervisor plus sub-agents, tools scoped per sub-agent from `agent.workflow_steps[]` |
| `deterministic_workflow` | explicit ordered steps, no autonomous routing; per-step prompts and output schemas |

Always: `@invoke()` and `@stream()` handlers, module-level `CONFIG = load_config()`
logged via `CONFIG.describe()`, `mlflow.langchain.autolog()` (or the framework's
equivalent), and session-id propagation into
`mlflow.update_current_trace(metadata={"mlflow.trace.session": ...})` so
multi-turn traces group.

When `agent.memory.enabled` is false, conversation history arrives in
`request.input` each call and there is **no** server-side checkpointer. Say that
in the module docstring — it is the kind of thing a later reader will otherwise
try to "fix".

**`agent_server/retriever.py`** — one builder per retrieval surface. Accept an
optional `workspace_client` so on-behalf-of-user auth can be switched on without
restructuring; default to the service principal.

**`agent_server/prompts.py`** — build the system prompt from
`agent.system_prompt_guidance`, `business_context.*`, and
`unstructured_data.document_description` / `structured_data.table_description`.
Render per call so injected temporal context stays current. State the corpus's
scope and limits — a prompt that does not say what the agent cannot answer
produces confident wrong answers.

**`agent_server/evaluate_agent.py`** — wire only the scorers set true under
`evaluation.scorers`. Include `guidelines` strings and one custom `@scorer` per
`evaluation.scorers.custom[]` entry. When `benchmark_dataset_provided` is false,
synthesize from the chunk table and label the dataset as synthetic.

**`agent_server/utils.py`**, **`agent_server/start_server.py`**,
**`output/agent_app/scripts/start_app.py`**,
**`pyproject.toml`**, **`.env.example`** — port from the primary template,
adjusting names only.

**`app.yaml`** and **`databricks.yml`** — `app.yaml` is local dev; the bundle's
`config.env` wins on deploy. Both carry the comment saying so. `databricks.yml`
needs: a `variables:` block for `catalog` / `schema` / `vs_index` /
`llm_endpoint`; `resources.apps.<snake_case_key>` with an `agent-`-prefixed
kebab-case `name`; `config.env` overrides composing
`${var.catalog}.${var.schema}.${var.vs_index}`; a `resources:` grant list; `dev`
and `prod` targets; and the three-step deploy sequence in the header comment.

**`manifest.yaml`** — `resource_specs` mirroring the `databricks.yml` grants:
same names, same permissions. Typically `experiment` (CAN_EDIT), the index as a
`uc_securable_spec` TABLE/SELECT, and `llm_endpoint` CAN_QUERY. No grant is
needed for a managed-embedding model endpoint — the index service does the
embedding, not the app. Say that in a comment so nobody adds one.

**`README.md`** — what the agent does, the deploy sequence, the config
precedence rule, and the TODOs a human must fill before first deploy.

## Optional capabilities

Emit these only when the config asks for them: Lakebase state
(`memory.state_backend: lakebase`), image inputs
(`multimodal.image_inputs`), tool-confirmation gating
(`human_in_the_loop: true`, gating the tools behind
`workflow_steps[].automated: false`), and a structured-data tool
(`structured_data.enabled`).

## Report

The framework and pattern used, the tools wired, the index the retriever points
at, the scorers enabled, and every remaining `# TODO:` a human must fill.

## Do not

- Do not point the retriever at an index name the pipeline does not create.
- Do not hardcode catalog or schema in `.py` files — `config.py` composes them.
- Do not let `app.yaml` and `databricks.yml` `config.env` drift.
- Do not add a serving-endpoint grant for a managed-embedding model.
- Do not carry over the template's domain prompts, entity lists, or eval fixtures.
- Do not invent experiment ids, warehouse ids, or workspace URLs.
