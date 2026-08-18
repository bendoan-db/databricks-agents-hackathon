# Agent Generation Harness

Generate production-shaped Databricks custom agents from a filled-in intake form,
grounded on a curated set of validated reference implementations.

## The problem

There is no shortage of templates for building custom agents on Databricks.
Between the official [Agents on Apps](https://docs.databricks.com/aws/en/agents/custom-agents/author-agent)
templates, solution accelerators, blog repos, and the dozens of one-off projects
that accumulate across an organization, an assistant asked to "build me a
document Q&A agent" has hundreds of plausible starting points.

That abundance is the problem. When an assistant is left to choose, it optimizes
for what looks reasonable in the moment: it blends patterns from several sources,
invents structure where it has no reference, and produces code that reads well
and has never run. The failure is quiet — you get a pipeline that executes
cleanly and extracts the wrong things, or an agent whose retriever points at an
index the pipeline never created. Nothing errors. It just doesn't work, and
finding out costs a day.

This harness removes the choice. It grounds assistants on a **small, curated
catalog of agents the SSA team has actually validated** — real projects that have
been deployed and run, not published examples. Generation is constrained to
porting logic from those repos into a fixed output shape, with mechanical checks
on the seams that quiet failures hide in.

It is built for **hackathon use**: get from an intake conversation to a
deployable, correctly-wired agent in an afternoon, and know which parts are
validated and which parts a human still has to fill in.

### What "grounded" means concretely

| Without the harness | With the harness |
|---|---|
| Assistant picks from hundreds of templates | 4 curated templates, each validated by the SSA team |
| Structure invented per run | Fixed output layout, enforced by a conventions skill |
| Requirements re-interpreted each time | One `generation_config.yaml` drives everything |
| Template choice undocumented | `selection.yaml` records what was chosen and why |
| Cross-artifact bugs found at deploy | Seam checks gate before you deploy |
| Unsupported requests silently improvised | Recorded under `unsupported:`, never passed off as validated |

## How to use

### Prerequisites

- [`uv`](https://docs.astral.sh/uv/) — the scripts declare their own dependencies inline
- `git`, and a Databricks CLI profile if you plan to deploy
- Claude Code, run from the project root

### 0. Link the skills into place (once per clone)

The harness skills are version-controlled in `skills/`, but Claude Code only
discovers skills under `.claude/skills/`, which is gitignored as machine-local
state. Link them across once after cloning:

```bash
mkdir -p .claude/skills
for s in skills/agent-gen-*; do
  ln -sfn "../../$s" ".claude/skills/$(basename "$s")"
done
```

Symlinks rather than copies, so `skills/` stays the single source of truth and
edits take effect without re-copying. Verify with `/agent-gen-build-agent`
tab-completing.

### 1. Fill in the intake

Answer the questions in `input/intake/INTAKE.md` directly in the file. Answer
what you know; leave the rest blank — the harness reports gaps rather than
guessing.

Drop any sample data you have into:

```
input/intake/example_documents/          # sample PDFs, DOCX, etc.
input/intake/example_structured_data/    # sample CSVs, table extracts
```

Samples are optional but change the output materially: with real documents the
harness can cross-check the intake's claims about file types and volume against
what is actually there.

### 2. Run the harness

```
/agent-gen-build-agent
```

That chains all four stages. To run them individually:

```
/agent-gen-intake-to-config              # INTAKE.md      -> generation_config.yaml
/agent-gen-select-templates              # config         -> selection.yaml + .template_cache/
/agent-gen-generate-ingestion-pipeline   # selection      -> output/document_ingestion_pipeline/
/agent-gen-generate-agent-app            # selection      -> output/agent_app/
/agent-gen-validate-output               # output/        -> pass/fail report
```

Two gates will stop the run rather than let it build on bad inputs: the config
must validate before template selection, and the output must pass seam checks
before you deploy. Both are scripts you can run yourself:

```
uv run scripts/validate_config.py
uv run scripts/check_output.py
```

### 3. Fill in the TODOs and deploy

Generated artifacts carry `# TODO:` markers wherever a value only you can
supply — catalog, schema, MLflow experiment id, warehouse id. The harness never
invents these. `check_output.py` prints the full list as your pre-deploy
checklist.

```
cd output/agent_app
databricks bundle validate -t dev
databricks bundle deploy   -t dev
databricks bundle run <app_resource> -t dev
```

`bundle deploy` alone leaves the app running the previous code — `bundle run` is
what restarts it.

### Re-running

Each stage is separately invocable. Prefer the narrowest one:

| Situation | Run |
|---|---|
| Intake answers changed | `/agent-gen-build-agent` (full chain) |
| Config hand-edited | from `/agent-gen-select-templates` |
| Re-tuning parsing or chunking | `/agent-gen-generate-ingestion-pipeline` then validate |
| Changing prompt, tools, or scorers | `/agent-gen-generate-agent-app` then validate |
| Just checking consistency | `/agent-gen-validate-output` |

## Key components

```
input/
  intake/INTAKE.md              18 discovery questions — the human-facing entry point
  intake/example_documents/     optional sample documents
  intake/example_structured_data/
  generation_config.yaml        the single source of truth for generation
  templates.yaml                the curated catalog of validated agents
  selection.yaml                which templates were chosen, and why

scripts/                        the deterministic parts of the harness
  detect_examples.py            filesystem -> example_provided booleans
  fetch_templates.py            sparse, code-only template fetch
  validate_config.py            GATE: config completeness and enum validity
  check_output.py               GATE: cross-artifact seams and template leakage

skills/                         the judgment parts (mirrored in .claude/skills/)
  agent-gen-intake-to-config/
  agent-gen-select-templates/
  agent-gen-generate-ingestion-pipeline/
  agent-gen-generate-agent-app/
  agent-gen-validate-output/
  agent-gen-build-agent/
  agent-gen-harness-conventions/

output/
  document_ingestion_pipeline/  numbered pipeline steps + config.yaml
  agent_app/                    Agents-on-Apps app + DAB deployment

.template_cache/                sparse clones of the selected templates (gitignored)
```

### The curated catalog

`input/templates.yaml` is deliberately small. Each entry is a project the SSA
team has validated, described by `template_description` and `key_features` — the
text an assistant matches against.

| Template | What it grounds |
|---|---|
| [`financebench-agent`](https://github.com/bendoan-db/databricks-financebench-agent) | Baseline document retrieval agent: parse, chunk, Delta Sync index, single-tool ResponsesAgent |
| [`complex-document-parsing`](https://github.com/qian-yu-db/ai-parse-document-adv-analysis-workflows) | `ai_parse_document` layout-aware parsing for figures, charts, tables; OCR path |
| [`multi-agent-supervisor-structured-unstructured`](https://github.com/bendoan-db/pricing_explainability_agent) | Vector search and Genie tools side by side, with cross-source synthesis |
| [`unstructured_to_structured_extraction`](https://github.com/bendoan-db/hil-doc-extraction) | `ai_extract` to JSON, flattened to Delta; batch execution |

Adding a template means adding four fields. Point `github_link` at a tag or
commit rather than a branch, so "validated" stays true as upstream moves.

### The generation config

`input/generation_config.yaml` is what everything downstream reads. Six sections:
`project`, `business_context`, `unstructured_data`, `structured_data`, `agent`,
`evaluation`. Every field carries an inline `(Qn)` comment naming the intake
question it came from, so the mapping is auditable in both directions.

Fields whose comments list `a | b | c` must hold exactly one of those tokens —
that is what template matching and the generators key off, and
`validate_config.py` fails the run on a free-text answer that was never
normalized.

### Why the fetch is sparse

Template repos are mostly not code. `financebench-agent` is a **1.2 GB** clone,
of which 673 MB is a `data/` directory of PDFs, wrapped around **131 KB** of
actual source. `fetch_templates.py` uses `--filter=blob:none` with sparse
checkout patterns to pull source files only:

```
all four templates:   ~1.2 GB naive  ->  1.9 MB cached
financebench-agent:      1.2 GB      ->  408 KB on disk
```

Always fetch through the script. A bare `git clone` of the catalog will download
a gigabyte of corpora to read a few hundred kilobytes of Python.

### Why there is a conventions skill

The four templates do not share a structure — different directory schemes,
different config strategies, different notebook conventions. Left alone, output
would take the shape of whichever template happened to be selected.

`agent-gen-harness-conventions` is the house style, reverse-engineered from
working artifacts, and it wins over any template's layout. Templates supply
*logic*; conventions supply *shape*. It covers the output layout, the
config-driven rule (no workspace-specific literal ever hardcoded in a `.py`
file), the pipeline notebook-source idiom, the three-layer
`databricks.yml > env > yaml` config precedence, the comment style that records
*why* and flags load-bearing values, and the `# TODO:` convention.

### The cross-artifact contract

The single hard dependency between the two output artifacts, and the reason the
ingestion pipeline is always generated first:

```
document_ingestion_pipeline/config.yaml : ingestion.vector_search.index_name
                                            |
                    +-----------------------+-----------------------+
                    v                                               v
agent_app/agent_config.yaml : retriever.index_name    agent_app/databricks.yml : variables.vs_index
```

All three must agree, and `catalog`/`schema` must match across both artifacts.
`check_output.py` checks this first, along with `manifest.yaml` mirroring the
bundle's resource grants, `app.yaml` staying in sync with `config.env`, contiguous
pipeline step numbering, hardcoded literals, and paths referenced in comments
that don't exist — the last of which is the usual signature of template leakage.

### What the harness will not do

- Invent a catalog, schema, warehouse id, experiment id, or secret scope. Those
  get `# TODO:` markers.
- Fill a field it cannot derive. Gaps are reported, not guessed.
- Present unvalidated code as validated. A requirement no template covers is
  recorded under `unsupported:` in `selection.yaml` and called out in the report.
- Skip a gate to keep a run moving.
