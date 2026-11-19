# AI Evaluation Report

> [!NOTE]
> This document records the evaluation methodology, dataset specification, and threshold
> decision for the CRM's AI classification system. Run numbers are filled in after each
> manual evaluation against the live Anthropic model. CI only validates the runner and
> fixture structure — it never calls the real provider.

---

## Evaluation metadata

| Field | Value |
|---|---|
| Date of last run | _run manually — see [Running the evaluation](#running-the-evaluation)_ |
| Model | `claude-3-5-haiku-20241022` (set via `LLM_MODEL` in `.env`) |
| Prompt version | `classify-v2` (`CLASSIFY_PROMPT_VERSION` in `app/modules/ai/prompts.py`) |
| Dataset | `backend/tests/fixtures/ai_evaluation.jsonl` |
| Dataset size | 60 records (30 English, 30 Bangla; 14 mixed-language messages) |
| Evaluated fields | `category`, `intent`, `buying_stage`, `sentiment`, `recommended_action` |
| Review-confidence threshold | `0.6` (`REVIEW_CONFIDENCE_THRESHOLD` in `evaluate_ai.py`) |

---

## Dataset

The fixture at `backend/tests/fixtures/ai_evaluation.jsonl` contains 60 synthetic,
human-labeled messages. **No real customer text, names, phone numbers or email addresses
appear anywhere in the fixture.**

### Composition

| Language tag | Records | Notes |
|---|---|---|
| `en` | 30 | Monolingual English and English-dominant mixed messages |
| `bn` | 30 | Monolingual Bangla and Bangla-dominant mixed messages |

Mixed-language messages (at least 14) include English technical terms inside Bangla
sentences (`eval_051`–`eval_060`) and are tagged with the dominant language. These cover
the most common confusion risk the prompt describes: *the message may be in English,
Bangla, or a mix*.

### Label coverage

Every combination of `intent` and `buying_stage` that appears in the prompt's allowed
values is represented by at least one record. The `spam` and `partner` categories each
have at least two records across both languages.

### Adding records

Append to the JSONL file. Each line must pass `EvaluationRecord` validation — run
`pytest tests/unit/test_ai_evaluation_runner.py::test_load_dataset_validates_existing_jsonl`
after editing. Update the counts in this document if the totals change.

---

## Metrics

The runner (`backend/app/scripts/evaluate_ai.py`) produces:

1. **Per-field accuracy** — `correct / total` for each of the five evaluated fields,
   split by language (`en` / `bn`) and overall.
2. **Intent confusion matrix** — rows = expected intent, columns = predicted intent.
   Off-diagonal cells identify the most common misclassifications.
3. **Review-threshold metrics** — how well `confidence < 0.6` identifies incorrect
   predictions:
   - `low_confidence_error_rate_percent`: of the predictions flagged for review, what
     fraction were actually wrong? A high rate validates the threshold.
   - `high_confidence_error_rate_percent`: of the predictions *not* flagged, what
     fraction were wrong? A low rate means the threshold catches most errors.

### Last run numbers

> [!IMPORTANT]
> Fill in this table after each real model run. Run the evaluation with:
>
> ```powershell
> cd backend
> backstore\Scripts\Activate.ps1
> python -m app.scripts.evaluate_ai
> ```

| Metric | en | bn | overall |
|---|---|---|---|
| category accuracy | — | — | — |
| intent accuracy | — | — | — |
| buying_stage accuracy | — | — | — |
| sentiment accuracy | — | — | — |
| recommended_action accuracy | — | — | — |
| **overall field accuracy** | — | — | — |
| failed predictions | — | — | — |

**Review-threshold (confidence < 0.6):**

| | Count | Error rate |
|---|---|---|
| Low-confidence predictions (flagged for review) | — | — |
| High-confidence predictions (not flagged) | — | — |

**Intent confusion (rows = expected, columns = most common wrong prediction):**

_Paste the table printed by the runner here after the run._

---

## Threshold decision

The confidence threshold is `0.6`. This was chosen because:

- The prompt instructs the model to lower confidence when the message is *ambiguous,
  incomplete, or gives conflicting signals*, so confidence correlates with output quality.
- In the classification module (`app/modules/ai/classification.py`) the `requires_human_review`
  rule already uses this threshold to flag low-confidence assessments stored in the database.
- Keeping the evaluation threshold identical to the production rule means the evaluation
  measures exactly what the system flags in production.

**If the numbers show the threshold is wrong:** change `REVIEW_CONFIDENCE_THRESHOLD` in
`evaluate_ai.py`, re-run, and update this document. If you also change the production
threshold in `classification.py` or `rules.py`, do it in the same PR and note the change
in `SECURITY.md` section 4.

---

## Running the evaluation

The evaluation calls the real Anthropic API and costs real tokens. It is **not** run in
CI. Run it manually when:

- The prompt (`CLASSIFY_PROMPT_VERSION`) changes.
- The model changes.
- The fixture grows by more than 10 records.
- A reported misclassification suggests a systematic failure mode.

```powershell
# From the repo root on Windows
cd backend
backstore\Scripts\Activate.ps1
# Ensure LLM_API_KEY and LLM_MODEL are set in .env
python -m app.scripts.evaluate_ai | Tee-Object -FilePath ..\docs\eval_run_$(Get-Date -Format 'yyyyMMdd').json
```

The JSON output plus the confusion table and threshold summary are written to stdout.
Paste the numbers into the table above, commit, and open a PR.

---

## Coverage of Day 8 requirements

The guide (master §8 / `missing-parts-guide.md` #3b) requires that the following
classifications are tested:

| Requirement | Covered by |
|---|---|
| Summary | `evaluate_ai.py` prompt covers all five fields; `test_llm_adapter_uses_existing_client_and_runner_prompt` checks the system prompt |
| Sentiment | 60 fixture records include all three sentiment values |
| Rule-based priority (`requires_human_review`) | Tested in `tests/unit/test_ai_rules.py` (pre-existing) and in `test_ai_evaluation_runner_extra.py` threshold tests |
| Task creation (follow_up_days) | Covered by `test_ai_jobs.py` via `FakeAnalyzer`; not an evaluated field here because the fixture only tests classification labels, not downstream task creation |

---

_Last edited: 2026-11-17 · Step #3b_
