---
name: agent-gen-generate-ingestion-pipeline
description: Generate output/document_ingestion_pipeline/ from input/selection.yaml, the generation config, and the cached template code. Use after agent-gen-select-templates. Produces the numbered pipeline steps plus the config.yaml that the agent app depends on.
---

# Generate the ingestion pipeline

Stage 3a. Runs **before** `agent-gen-generate-agent-app`, because its `config.yaml` defines
the vector index name the app consumes.

**In:** `input/selection.yaml`, `input/generation_config.yaml`, `.template_cache/`
**Out:** `output/document_ingestion_pipeline/`

## Before writing anything

1. Load the `agent-gen-harness-conventions` skill. It is the house style and it wins over
   any template's layout.
2. Read `input/selection.yaml` -> `artifacts.document_ingestion_pipeline`. Read
   only the files under `read_files`.
3. Read the existing `output/document_ingestion_pipeline/` as a worked example of
   the target shape. Do not assume it matches the current config — it is a prior
   run's output for a different project.

## Step sequence is config-driven

Decide the numbered steps from the config, then number them contiguously with no
gaps. Each step is one materialized stage.

| Step | Emitted when | Template source |
|---|---|---|
| `01_parse_documents.py` | `unstructured_data.enabled` | primary; use `complex-document-parsing` when `advanced_figures` or non-`clean_digital` quality |
| `02_extract_metadata.py` | `custom_metadata_extraction: true` | `unstructured_to_structured_extraction` |
| `0N_prep_search_chunks.py` | `unstructured_data.enabled` | primary |
| `0N_create_vector_search_index.py` | `unstructured_data.enabled` | primary |
| `0N_load_structured_tables.py` | `structured_data.enabled` | primary or `multi-agent-supervisor-*` |

Renumber the whole sequence when a step is added or dropped — with metadata
extraction the chunk step becomes `03_` and the index step `04_`. Never leave a
number unused, and never keep a template's own numbering.

## Write config.yaml first

It is the contract. Follow the existing file's two-section shape (`global:` then
`ingestion:` with a subsection per step). Fill from the config:

- `global.catalog` / `global.schema` — from the config if present, else a
  `# TODO: add catalog` marker. Never invent a real catalog name.
- `ingestion.document_volume` — bare volume name from
  `unstructured_data.source.location`.
- `ingestion.parse.*` — `description_element_types` from
  `advanced_element_types` (`"*"` for all, `"figure"` for figures only, `""` for
  none). Set `image_output_path` non-empty only when
  `agent.multimodal.image_inputs` is true.
- `ingestion.extract.*` — the `ai_extract` field schema straight from
  `unstructured_data.metadata_fields[]`, names and types preserved exactly.
- `ingestion.vector_search.*` — `index_name`, `primary_key`,
  `embedding_source_column`, `embedding_model_endpoint`. Add every
  `metadata_fields[].name` to `columns_to_sync` so the app can filter on them.
- A `max_error_rate` guardrail on the parse step.

Table names should read from the domain, not the template: `document_description`
and `project.name` are the source, not `sec_docs_*`.

## Then the steps

Each `.py` file follows the notebook-source header and config-load idiom in
`agent-gen-harness-conventions` exactly. Per step:

- Markdown header block naming **Input:** and **Output:** with each table and its
  grain, plus a sentence on why the step is separate and what it deliberately
  does not do.
- Unpack config into named locals at the top; compose three-part names with
  f-strings; print the resolved configuration before doing work.
- Print what was written and where at the end.
- An errors table plus the `max_error_rate` check wherever a per-document
  operation can fail.

## Scale the compute story to the corpus

`document_count`, `total_pages`, and `avg_pages_per_document` are in the config
for a reason. A 40,000-document corpus and a 40-document corpus want different
batching. When these values imply something material — batch sizes, whether
parsing needs partitioning — write it in a comment stating the number it was
derived from.

## Report

Name the steps emitted and why, the tables produced, and — explicitly — the
`ingestion.vector_search.index_name` value, since that is what
`agent-gen-generate-agent-app` consumes next.

## Do not

- Do not hardcode a catalog, schema, table, volume, or endpoint in a `.py` file.
- Do not carry over template sample data, setup notebooks that upload demo
  corpora, or domain fixtures (company lists, eval sets).
- Do not keep the template's directory nesting.
- Do not merge parse and chunk into one step; the boundary is deliberate.
- Do not invent a warehouse id, experiment id, or secret scope. TODO marker only.
