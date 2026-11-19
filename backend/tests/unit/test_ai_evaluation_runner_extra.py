"""Additional tests for the intent confusion matrix and review-threshold metrics
added in step #3b. Uses the same injected fake predictor — no real LLM calls.
"""

from app.scripts import evaluate_ai


def good_prediction(**overrides):
    values = {
        "category": "unknown",
        "intent": "request_demo",
        "buying_stage": "consideration",
        "sentiment": "positive",
        "recommended_action": "schedule_demo",
    }
    values.update(overrides)
    return evaluate_ai.EvaluationLabels.model_validate(values)


def good_prediction_with_confidence(confidence: float, **overrides):
    """Return a dict (not a model) so the confidence key is visible to evaluate_records."""
    base = good_prediction(**overrides)
    return {**base.model_dump(), "confidence": confidence}


def records_with_prediction(expected=None, language="en", count=1):
    expected = expected or {
        "category": "unknown",
        "intent": "request_demo",
        "buying_stage": "consideration",
        "sentiment": "positive",
        "recommended_action": "schedule_demo",
    }
    return [
        evaluate_ai.EvaluationRecord(
            id=f"test_{i}",
            language=language,
            message=f"Sample message {i}.",
            expected=expected,
        )
        for i in range(count)
    ]


def run(records, predictor):
    return evaluate_ai.evaluate_records(records, predictor=predictor)


# ── Fixture: mixed-language records were added ────────────────────────────────


def test_fixture_now_has_sixty_records_with_mixed_language_examples():
    from pathlib import Path

    path = Path(__file__).parents[1] / "fixtures" / "ai_evaluation.jsonl"
    records = evaluate_ai.load_dataset(path)
    assert len(records) == 60
    assert sum(r.language == "en" for r in records) == 30
    assert sum(r.language == "bn" for r in records) == 30
    # Mixed-language messages: a Bangla-tagged record containing ASCII alpha chars
    mixed = [
        r
        for r in records
        if r.language == "bn" and any(c.isalpha() and c < "\x80" for c in r.message)
    ]
    assert len(mixed) >= 5, "expected at least 5 mixed-language (bn) records"


# ── Intent confusion matrix ───────────────────────────────────────────────────


def test_correct_prediction_produces_diagonal_confusion_entry():
    records = records_with_prediction()  # expected intent = request_demo
    report = run(records, lambda _msg: good_prediction())

    # Find the row for request_demo
    rows = {row.expected: row for row in report.intent_confusion}
    assert "request_demo" in rows
    assert rows["request_demo"].predicted_counts["request_demo"] == 1


def test_wrong_intent_prediction_shows_off_diagonal_entry():
    records = records_with_prediction()  # expected = request_demo
    report = run(records, lambda _msg: good_prediction(intent="pricing"))

    rows = {row.expected: row for row in report.intent_confusion}
    assert "request_demo" in rows
    assert rows["request_demo"].predicted_counts["pricing"] == 1
    assert rows["request_demo"].predicted_counts["request_demo"] == 0


def test_confusion_table_counts_multiple_records():
    records = (
        records_with_prediction(count=3)  # all expected request_demo
        + records_with_prediction(
            expected={
                "category": "unknown",
                "intent": "pricing",
                "buying_stage": "consideration",
                "sentiment": "neutral",
                "recommended_action": "email",
            },
            count=2,
        )
    )
    preds = iter(
        [good_prediction()] * 3  # request_demo → request_demo (correct)
        + [good_prediction(intent="info")] * 2  # pricing → info (wrong)
    )
    report = run(records, lambda _msg: next(preds))

    rows = {row.expected: row for row in report.intent_confusion}
    assert rows["request_demo"].predicted_counts["request_demo"] == 3
    assert rows["pricing"].predicted_counts["info"] == 2
    assert rows["pricing"].predicted_counts["pricing"] == 0


def test_intent_confusion_rows_only_include_intents_that_appeared():
    records = records_with_prediction()  # only request_demo appears
    report = run(records, lambda _msg: good_prediction())

    expected_intents = {row.expected for row in report.intent_confusion}
    # Only request_demo appeared in expected
    assert "request_demo" in expected_intents
    # 'complaint' never appeared, so its row is absent
    assert "complaint" not in expected_intents


def test_failed_predictions_are_excluded_from_confusion_table():
    from app.modules.ai.llm_client import LLMUnavailable

    records = records_with_prediction(count=3)

    def _fail(_msg):
        raise LLMUnavailable("down")

    report = run(records, _fail)
    assert report.failed_predictions == 3
    # No successful predictions → confusion table is empty
    assert len(report.intent_confusion) == 0


# ── Review-threshold metrics ──────────────────────────────────────────────────


def test_all_high_confidence_correct_predictions_give_zero_low_conf_count():
    records = records_with_prediction(count=3)
    report = run(records, lambda _msg: good_prediction_with_confidence(0.9))

    m = report.review_threshold
    assert m.threshold == evaluate_ai.REVIEW_CONFIDENCE_THRESHOLD
    assert m.total_predictions == 3
    assert m.low_confidence_count == 0
    assert m.high_confidence_count == 3
    assert m.low_confidence_error_rate_percent is None  # no low-conf samples
    assert m.high_confidence_error_rate_percent == 0.0


def test_low_confidence_wrong_prediction_is_counted_as_low_conf_wrong():
    records = records_with_prediction()  # expected intent = request_demo
    # Predict pricing (wrong) with low confidence
    report = run(
        records,
        lambda _msg: good_prediction_with_confidence(0.3, intent="pricing"),
    )

    m = report.review_threshold
    assert m.low_confidence_count == 1
    assert m.low_confidence_wrong_count == 1
    assert m.low_confidence_error_rate_percent == 100.0


def test_low_confidence_correct_prediction_is_not_counted_as_wrong():
    records = records_with_prediction()  # expected intent = request_demo
    # Predict correctly but with low confidence
    report = run(
        records,
        lambda _msg: good_prediction_with_confidence(0.4),
    )

    m = report.review_threshold
    assert m.low_confidence_count == 1
    assert m.low_confidence_wrong_count == 0
    assert m.low_confidence_error_rate_percent == 0.0


def test_high_confidence_wrong_prediction_is_counted_separately():
    records = records_with_prediction()  # expected intent = request_demo
    # Predict pricing (wrong) with high confidence (overconfident model)
    report = run(
        records,
        lambda _msg: good_prediction_with_confidence(0.95, intent="pricing"),
    )

    m = report.review_threshold
    assert m.high_confidence_count == 1
    assert m.high_confidence_wrong_count == 1
    assert m.high_confidence_error_rate_percent == 100.0
    assert m.low_confidence_count == 0


def test_threshold_metrics_missing_confidence_key_defaults_to_high_confidence():
    """When the predictor returns a prediction with no 'confidence' key, the
    runner assumes confidence=1.0 (i.e. the prediction is treated as high-conf)."""
    records = records_with_prediction()
    # Return a plain model with no 'confidence' key
    report = run(records, lambda _msg: good_prediction(intent="pricing"))

    m = report.review_threshold
    # No confidence key → defaults to 1.0 → high-confidence bucket
    assert m.high_confidence_count == 1
    assert m.low_confidence_count == 0


def test_mixed_confidence_batch_produces_correct_split():
    records = records_with_prediction(count=4)
    preds = iter(
        [
            good_prediction_with_confidence(0.2, intent="pricing"),  # low, wrong
            good_prediction_with_confidence(0.5),  # low, correct (0.5 < 0.6)
            good_prediction_with_confidence(0.8),  # high, correct
            good_prediction_with_confidence(0.9, intent="pricing"),  # high, wrong
        ]
    )
    report = run(records, lambda _msg: next(preds))

    m = report.review_threshold
    assert m.total_predictions == 4
    assert m.low_confidence_count == 2
    assert m.high_confidence_count == 2
    assert m.low_confidence_wrong_count == 1
    assert m.high_confidence_wrong_count == 1
    assert m.low_confidence_error_rate_percent == 50.0
    assert m.high_confidence_error_rate_percent == 50.0
