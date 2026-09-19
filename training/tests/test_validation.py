from __future__ import annotations

import json
from pathlib import Path

import pytest

from shared_lora_baseline.validation import DatasetValidationError, validate_training_dataset


def write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")


def valid_record(record_id: str, difficulty: str) -> dict[str, object]:
    manim_code = (
        "from manim import *\n\n"
        "class Lesson(Scene):\n"
        "    def construct(self):\n"
        "        self.add(Text('d/dx x^2 = 2x'))\n"
    )
    return {
        "id": record_id,
        "difficulty": difficulty,
        "topic": "calculus",
        "prompt": "Create a Manim lesson for the derivative of x squared.",
        "manim_code": manim_code,
        "split": "train",
        "source": {"name": "unit-fixture", "reference": record_id},
    }


def test_training_records_must_cover_allowed_difficulties_and_avoid_holdout(tmp_path: Path) -> None:
    train_path = tmp_path / "train.jsonl"
    holdout_path = tmp_path / "holdout.jsonl"
    write_jsonl(
        train_path,
        [
            valid_record("train-foundational-001", "foundational"),
            valid_record("train-intermediate-001", "intermediate"),
            valid_record("train-advanced-001", "advanced"),
        ],
    )
    write_jsonl(
        holdout_path,
        [
            {
                "id": "eval-foundational-001",
                "difficulty": "foundational",
                "topic": "fractions",
                "prompt": "Holdout prompt.",
                "split": "evaluation",
                "source": {"name": "holdout", "reference": "eval-foundational-001"},
            }
        ],
    )

    report = validate_training_dataset(train_path, holdout_path)

    assert report.record_count == 3
    assert report.difficulty_counts == {"foundational": 1, "intermediate": 1, "advanced": 1}
    assert (
        report.training_ids_sha256
        == "00ad1476d0252cea523a104372073a97bf291704b98e14942b2bb76cc23c5485"
    )


def test_validation_rejects_duplicate_unstable_and_holdout_ids(tmp_path: Path) -> None:
    train_path = tmp_path / "train.jsonl"
    holdout_path = tmp_path / "holdout.jsonl"
    overlapping = valid_record("eval-foundational-001", "foundational")
    write_jsonl(
        train_path,
        [
            valid_record("bad id", "foundational"),
            valid_record("train-advanced-001", "expert"),
            overlapping,
            overlapping,
        ],
    )
    write_jsonl(
        holdout_path,
        [
            {
                "id": "eval-foundational-001",
                "difficulty": "foundational",
                "topic": "fractions",
                "prompt": "Holdout prompt.",
                "split": "evaluation",
                "source": {"name": "holdout", "reference": "eval-foundational-001"},
            }
        ],
    )

    with pytest.raises(DatasetValidationError) as exc_info:
        validate_training_dataset(train_path, holdout_path)

    message = str(exc_info.value)
    assert "duplicate training id: eval-foundational-001" in message
    assert "invalid id format: bad id" in message
    assert "invalid difficulty for train-advanced-001: expert" in message
    assert "training IDs overlap holdout IDs: eval-foundational-001" in message
