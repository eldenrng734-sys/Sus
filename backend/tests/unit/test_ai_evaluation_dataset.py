import json
from pathlib import Path

from app.modules.ai.service import AssessmentOutput

DATASET_PATH = Path(__file__).parents[1] / "fixtures" / "ai_evaluation.jsonl"
EXPECTED_FIELDS = {"category", "intent", "buying_stage", "sentiment", "recommended_action"}


def load_dataset() -> list[dict]:
    with DATASET_PATH.open(encoding="utf-8") as dataset_file:
        return [json.loads(line) for line in dataset_file if line.strip()]


def test_ai_evaluation_dataset_shape_and_labels():
    records = load_dataset()

    assert len(records) == 50
    assert sum(record["language"] == "en" for record in records) == 25
    assert sum(record["language"] == "bn" for record in records) == 25
    assert len({record["id"] for record in records}) == 50

    messages = [" ".join(record["message"].split()).casefold() for record in records]
    assert all(messages)
    assert len(set(messages)) == len(messages)
    assert {record["expected"]["intent"] for record in records} == {
        "request_demo",
        "pricing",
        "support",
        "info",
        "complaint",
        "other",
        "unknown",
    }
    assert {record["expected"]["sentiment"] for record in records} == {
        "positive",
        "neutral",
        "negative",
    }
    assert {record["expected"]["buying_stage"] for record in records} == {
        "awareness",
        "consideration",
        "decision",
        "unknown",
    }

    for record in records:
        assert set(record) == {"id", "language", "message", "expected"}
        assert record["language"] in {"en", "bn"}
        assert set(record["expected"]) == EXPECTED_FIELDS
        AssessmentOutput.model_validate(record["expected"])


def test_every_dataset_line_is_valid_json():
    with DATASET_PATH.open(encoding="utf-8") as dataset_file:
        lines = dataset_file.readlines()

    assert len(lines) == 50
    assert all(json.loads(line) for line in lines)
