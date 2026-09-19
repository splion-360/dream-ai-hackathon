from __future__ import annotations

import json
from pathlib import Path

from shared_lora_baseline.config import load_config


def test_relative_paths_resolve_from_config_directory(tmp_path: Path, monkeypatch: object) -> None:
    config_dir = tmp_path / "config-dir"
    config_dir.mkdir()
    config_path = config_dir / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "train_path": "../data/train.jsonl",
                "holdout_path": "../data/holdout.jsonl",
                "output_dir": "../artifacts/adapter",
                "metadata_path": "../artifacts/run.json",
            }
        ),
        encoding="utf-8",
    )
    unrelated_cwd = tmp_path / "elsewhere"
    unrelated_cwd.mkdir()
    monkeypatch.chdir(unrelated_cwd)  # type: ignore[attr-defined]

    config = load_config(config_path)

    assert config.train_path == config_dir / "../data/train.jsonl"
    assert config.holdout_path == config_dir / "../data/holdout.jsonl"
    assert config.output_dir == config_dir / "../artifacts/adapter"
    assert config.metadata_path == config_dir / "../artifacts/run.json"
