from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from shared_lora_baseline.config import TrainingConfig
from shared_lora_baseline.trainer import _format_record, train_shared_lora


def training_record(record_id: str, difficulty: str) -> dict[str, object]:
    return {
        "id": record_id,
        "difficulty": difficulty,
        "topic": "geometry",
        "prompt": "Explain triangle area.",
        "manim_code": "from manim import *\nclass Lesson(Scene):\n    pass\n",
        "split": "train",
        "source": {"name": "unit-fixture", "reference": record_id},
    }


def write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")


class FakeTokenizer:
    eos_token = "<|im_end|>"
    pad_token: str | None = None

    def apply_chat_template(
        self,
        messages: list[dict[str, str]],
        *,
        tokenize: bool,
        add_generation_prompt: bool,
    ) -> str:
        assert tokenize is False
        assert add_generation_prompt is False
        return "".join(
            f"<|im_start|>{message['role']}\n{message['content']}<|im_end|>\n"
            for message in messages
        )

    def __call__(self, *_args: object, **_kwargs: object) -> dict[str, list[int]]:
        return {"input_ids": [1, 2, 3]}

    def save_pretrained(self, _path: Path) -> None:
        return None


def test_format_record_uses_chat_template_and_ends_with_eos() -> None:
    tokenizer = FakeTokenizer()

    formatted = _format_record(training_record("train-foundational-001", "foundational"), tokenizer)

    assert formatted["text"].startswith("<|im_start|>system\n")
    assert "<|im_start|>user\nDifficulty: foundational" in formatted["text"]
    assert "<|im_start|>assistant\nfrom manim import *" in formatted["text"]
    assert formatted["text"].rstrip().endswith("<|im_end|>")
    assert "<|system|>" not in formatted["text"]


def test_seed_is_set_before_model_and_adapter_initialization(
    tmp_path: Path, monkeypatch: Any
) -> None:
    events: list[str] = []
    tokenizer = FakeTokenizer()

    class FakeModel:
        def save_pretrained(self, _path: Path) -> None:
            return None

    class FakeDataset:
        @classmethod
        def from_list(cls, _records: list[dict[str, str]]) -> FakeDataset:
            return cls()

        def map(self, *_args: object, **_kwargs: object) -> FakeDataset:
            return self

    class FakeTrainer:
        def __init__(self, **_kwargs: object) -> None:
            return None

        def train(self) -> None:
            return None

    transformers = SimpleNamespace(
        __version__="4.51.0",
        set_seed=lambda _seed: events.append("seed"),
        AutoTokenizer=SimpleNamespace(from_pretrained=lambda *_args, **_kwargs: tokenizer),
        AutoModelForCausalLM=SimpleNamespace(
            from_pretrained=lambda *_args, **_kwargs: events.append("model") or FakeModel()
        ),
        TrainingArguments=lambda **_kwargs: object(),
        DataCollatorForLanguageModeling=lambda **_kwargs: object(),
        Trainer=FakeTrainer,
    )
    peft = SimpleNamespace(
        __version__="0.12.0",
        LoraConfig=lambda **_kwargs: object(),
        TaskType=SimpleNamespace(CAUSAL_LM="CAUSAL_LM"),
        get_peft_model=lambda model, _config: events.append("adapter") or model,
    )
    modules = {
        "datasets": SimpleNamespace(__version__="2.21.0", Dataset=FakeDataset),
        "peft": peft,
        "torch": SimpleNamespace(__version__="2.4.0"),
        "transformers": transformers,
    }
    monkeypatch.setattr(
        "shared_lora_baseline.trainer.import_module", lambda name: modules[name]
    )

    train_path = tmp_path / "train.jsonl"
    holdout_path = tmp_path / "holdout.jsonl"
    write_jsonl(
        train_path,
        [
            training_record("train-foundational-001", "foundational"),
            training_record("train-intermediate-001", "intermediate"),
            training_record("train-advanced-001", "advanced"),
        ],
    )
    write_jsonl(holdout_path, [{"id": "eval-001"}])
    config = TrainingConfig(
        train_path=train_path,
        holdout_path=holdout_path,
        output_dir=tmp_path / "adapter",
        metadata_path=tmp_path / "run.json",
        load_in_4bit=False,
    )

    plan = train_shared_lora(config)

    assert events.index("seed") < events.index("model") < events.index("adapter")
    assert plan.metadata["runtime_versions"]["transformers"] == "4.51.0"
    assert set(plan.metadata["runtime_versions"]) == {
        "accelerate",
        "bitsandbytes",
        "datasets",
        "peft",
        "safetensors",
        "torch",
        "transformers",
    }
