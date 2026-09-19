from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TrainingConfig:
    train_path: Path
    holdout_path: Path
    output_dir: Path
    metadata_path: Path
    seed: int = 42
    max_steps: int = 1
    per_device_train_batch_size: int = 1
    gradient_accumulation_steps: int = 4
    learning_rate: float = 2e-4
    max_seq_length: int = 2048
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    target_modules: tuple[str, ...] = field(
        default=("q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj")
    )
    load_in_4bit: bool = True


class ConfigError(ValueError):
    pass


def load_config(path: Path) -> TrainingConfig:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ConfigError("config root must be a JSON object")
    base_dir = Path.cwd()
    return parse_config(raw, base_dir=base_dir)


def parse_config(raw: dict[str, Any], *, base_dir: Path) -> TrainingConfig:
    forbidden = {
        "model_id",
        "condition",
        "adapter_id",
        "dynamic_adapter_spawning",
        "learned_router",
    }
    present_forbidden = sorted(forbidden & raw.keys())
    if present_forbidden:
        joined = ", ".join(present_forbidden)
        raise ConfigError(f"frozen baseline fields are not configurable: {joined}")

    def path_field(name: str) -> Path:
        value = raw.get(name)
        if not isinstance(value, str) or not value:
            raise ConfigError(f"{name} must be a non-empty string")
        path = Path(value)
        return path if path.is_absolute() else base_dir / path

    def int_field(name: str, default: int) -> int:
        value = raw.get(name, default)
        if not isinstance(value, int) or value <= 0:
            raise ConfigError(f"{name} must be a positive integer")
        return value

    def float_field(name: str, default: float) -> float:
        value = raw.get(name, default)
        if not isinstance(value, int | float) or value <= 0:
            raise ConfigError(f"{name} must be a positive number")
        return float(value)

    target_modules_raw = raw.get(
        "target_modules",
        ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    )
    if (
        not isinstance(target_modules_raw, list)
        or not target_modules_raw
        or not all(isinstance(item, str) and item for item in target_modules_raw)
    ):
        raise ConfigError("target_modules must be a non-empty list of strings")

    load_in_4bit = raw.get("load_in_4bit", True)
    if not isinstance(load_in_4bit, bool):
        raise ConfigError("load_in_4bit must be a boolean")

    lora_dropout = raw.get("lora_dropout", 0.05)
    if not isinstance(lora_dropout, int | float) or not 0 <= lora_dropout < 1:
        raise ConfigError("lora_dropout must be in [0, 1)")

    return TrainingConfig(
        train_path=path_field("train_path"),
        holdout_path=path_field("holdout_path"),
        output_dir=path_field("output_dir"),
        metadata_path=path_field("metadata_path"),
        seed=int_field("seed", 42),
        max_steps=int_field("max_steps", 1),
        per_device_train_batch_size=int_field("per_device_train_batch_size", 1),
        gradient_accumulation_steps=int_field("gradient_accumulation_steps", 4),
        learning_rate=float_field("learning_rate", 2e-4),
        max_seq_length=int_field("max_seq_length", 2048),
        lora_r=int_field("lora_r", 16),
        lora_alpha=int_field("lora_alpha", 32),
        lora_dropout=float(lora_dropout),
        target_modules=tuple(target_modules_raw),
        load_in_4bit=load_in_4bit,
    )
