---
name: agent-gen-intake-to-config
description: Read the filled-in input/intake/INTAKE.md and populate input/generation_config.yaml. Use when starting a new agent build, when intake answers have changed, or when asked to map intake responses to generation parameters. Normalizes prose answers into the config's enum values and reports gaps rather than guessing.
---

# Intake -> generation config

Stage 1 of the harness. Turns a human's prose answers into the machine-readable
config that drives everything downstream.

**In:** `input/intake/INTAKE.md` (answered), `input/intake/example_documents/`,
`input/intake/example_structured_data/`
**Out:** `input/generation_config.yaml` (filled), plus a gaps report to the user

This is the only stage where freeform human text becomes structured data, so it is
where every downstream error originates. A wrong `advanced_figures` silently
selects the wrong parser and produces a pipeline that runs cleanly and extracts
the wrong things. Prefer reporting a gap over making a plausible guess.

## Procedure

1. **Read the intake.** `input/intake/INTAKE.md`. If answers are absent or the file
   is still just the question list, stop and tell the user — do not invent answers.

2. **Compute the filesystem-derived fields.** Run:
   ```
   uv run scripts/detect_examples.py --write
   ```
   This sets `unstructured_data.example_provided` and
   `structured_data.example_provided`, and reports observed file types and counts.
   Never set these two by hand.

3. **Cross-check samples against claims.** The script reports observed extensions
   and file counts. If the intake says "about 40,000 PDFs" and the sample dir has
   3 `.docx` files, that is a real discrepancy: the sample is not representative.
   Keep the intake's numbers for `document_count` (they describe the corpus) and
   flag the mismatch to the user. Do not overwrite corpus figures with sample
   figures.

4. **Map answers to fields.** The config's inline `(Qn)` comments name the source
   question for each field. Work through them in file order.

5. **Normalize to enums, don't paraphrase.** Any field whose comment lists
   `a | b | c` must end up as exactly one of those tokens:

   | Field | Allowed |
   |---|---|
   | `unstructured_data.source_quality` | `clean_digital` `mixed` `scanned_ocr_required` |
   | `agent.task_type` | `conversational_chat` `workflow_automation` `batch_extraction` `research_assistant` |
   | `agent.agent_pattern` | `single_agent` `multi_agent_supervisor` `deterministic_workflow` |
   | `agent.framework` | `openai_agents_sdk` `langgraph` `dspy` `custom` |
   | `agent.memory.scope` | `none` `thread` `user` |
   | `agent.memory.state_backend` | `none` `lakebase` |
   | `*.type` in field lists | `string` `number` `date` `boolean` `array` |

   "Some are scanned, most are clean exports" -> `mixed`, not `"mostly clean"`.

6. **Apply the Q17 rule.** INTAKE.md says explicitly: if the user does not know
   what agent memory or multimodal I/O are, the answer is **no**. Set
   `agent.memory.enabled: false` and both `multimodal.*: false` unless the intake
   affirmatively asks for them.

7. **Derive the fields no question asks directly.** These are judgment calls —
   state each one to the user rather than burying it:
   - `agent.agent_pattern` — from Q5+Q6. One retrieval surface and a
     conversational task is `single_agent`. Distinct stages needing different
     tools is `multi_agent_supervisor`. A fixed sequence where reproducibility
     matters more than flexibility is `deterministic_workflow`.
   - `agent.framework` — default `langgraph`; it is what the existing output and
     the primary template use. Only diverge if the intake names a framework.
   - `agent.human_in_the_loop` — true when Q2's cost-of-error is high or Q15's
     action is hard to reverse.
   - `agent.system_prompt_guidance` — distilled from Q1, Q2, Q5, Q6. Write the
     substance here; the generator turns it into `prompts.py`.
   - `agent.llm_endpoint` — default `databricks-claude-sonnet-4-5`.

8. **Leave unknowns empty.** An empty field that `validate_config.py` flags is
   strictly better than a confident wrong value. Do not fill `metadata_fields`
   with guesses; that schema determines what `ai_extract` pulls out.

9. **Validate.** Run:
   ```
   uv run scripts/validate_config.py
   ```
   Fix real errors. For errors that need information only the user has, report
   them as gaps.

10. **Report.** Give the user three lists, briefly:
    - **Derived** — judgment calls from step 7, with the reasoning in a clause each.
    - **Gaps** — unanswered questions and answers too vague to map. Say what each
      one blocks.
    - **Discrepancies** — sample-vs-claim mismatches from step 3.

## Do not

- Do not fill `example_provided` by hand.
- Do not write values into a field whose comment lists enums unless the value is
  one of those tokens exactly.
- Do not proceed to template selection with `validate_config.py` failing.
- Do not add or rename config fields. If the intake surfaces something the config
  cannot express, say so — changing the schema is the user's call, and
  `templates.yaml` matching and the generators both key off these paths.
