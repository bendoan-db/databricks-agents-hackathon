---
name: agent-gen-select-templates
description: Match the filled generation_config.yaml against input/templates.yaml, fetch the selected template repos code-only, and write input/selection.yaml recording which template contributes what to each output artifact. Use after agent-gen-intake-to-config and before any agent-gen-generate-* skill.
---

# Template selection

Stage 2. Decides which pre-validated templates the generators read, and records
that decision durably so the generators do not each re-derive it.

**In:** `input/generation_config.yaml`, `input/templates.yaml`
**Out:** `input/selection.yaml`, populated `.template_cache/`

## Why the output is per-artifact, not per-template

Templates do not map one-to-one onto output directories:

- `financebench-agent` is a **whole project** — `00_document_ingestion/`,
  `01_research_agent/`, `setup/` — and feeds **both** output artifacts.
- `complex-document-parsing` feeds **ingestion only** (8 files).
- `multi-agent-supervisor-structured-unstructured` feeds mostly **the agent**.
- `unstructured_to_structured_extraction` feeds **ingestion/extraction**.

So a selection is not "use template X". It is a mapping of
*artifact -> [(template, files, what to take from them)]*, and a single artifact
routinely draws from two templates: one for overall skeleton, one for a specific
capability. Producing that mapping is this skill's whole job.

## Procedure

1. **Gate on a valid config.** Run `uv run scripts/validate_config.py`. If it
   fails, stop and route back to `agent-gen-intake-to-config`.

2. **Read the catalog.** `input/templates.yaml` — `template_description` and
   `key_features` are the matching signal.

3. **Match, per artifact.** For `document_ingestion_pipeline` and `agent_app`
   separately, pick a **primary** template (the skeleton) and any **contributing**
   templates (a specific capability). Anchor on these config values:

   | Config | Pulls in |
   |---|---|
   | `unstructured_data.enabled` | a document-ingestion template |
   | `unstructured_data.advanced_figures: true` | `complex-document-parsing` for the parse step |
   | `unstructured_data.source_quality: mixed`/`scanned_ocr_required` | `complex-document-parsing` (OCR path) |
   | `unstructured_data.custom_metadata_extraction: true` | `unstructured_to_structured_extraction` for `ai_extract` |
   | `structured_data.enabled` + `unstructured_data.enabled` | `multi-agent-supervisor-structured-unstructured` |
   | `agent.agent_pattern: single_agent` + docs only | `financebench-agent` |
   | `agent.agent_pattern: multi_agent_supervisor` | `multi-agent-supervisor-structured-unstructured` |
   | `agent.agent_pattern: deterministic_workflow`, batch task | `unstructured_to_structured_extraction` |
   | `evaluation.scorers.*` any true | whichever primary has an eval driver |

   Prefer the fewest templates that cover the requirements. Two is common, three
   is a smell.

4. **Fetch, code only.** For each selected template:
   ```
   uv run scripts/fetch_templates.py --template <template_name>
   ```
   Never `git clone` a template directly. `financebench-agent` is a 1.2 GB clone
   whose `data/` directory is 673 MB of PDFs; the script sparse-checks-out source
   files only and lands it at ~130 KB.

5. **Identify the files that matter.** List the cached tree
   (`uv run scripts/fetch_templates.py --manifest`) and name the specific files
   each artifact should read. All four templates' code together is only ~660 KB,
   so this is about precision, not survival — a generator pointed at 6 relevant
   files produces better output than one pointed at 80.

6. **Record unsupported combinations.** If a config value has no template behind
   it — `agent.framework: dspy` or `custom`, for instance, which no current
   template uses — write it into `selection.yaml` under `unsupported:` with the
   nearest template to adapt. Do **not** silently pick something and let the
   output imply it was validated.

7. **Write `input/selection.yaml`.** Shape:

   ```yaml
   generated_at:
   config_fingerprint:            # so a stale selection is detectable
   artifacts:
     document_ingestion_pipeline:
       primary_template:
       contributing_templates: []
       read_files:
         - template:
           paths: []
           take:                  # what to port from these files
       rationale:                 # which config values drove this
     agent_app:
       primary_template:
       contributing_templates: []
       read_files: []
       rationale:
   unsupported: []                # config values with no template behind them
   notes:
   ```

8. **Report** the selection and the reasoning in a few lines, and name anything
   under `unsupported:` explicitly.

## Do not

- Do not clone template repos with bare `git clone`.
- Do not read a whole template repo into context when `read_files` will do.
- Do not proceed to generation without writing `selection.yaml` — the generators
  read it, and without it they diverge from each other.
- Do not claim template backing for a capability no template implements.
