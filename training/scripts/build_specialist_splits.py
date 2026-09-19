from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

DIFFICULTIES = ("foundational", "intermediate", "advanced")
SYSTEM_PROMPT = (
    "You generate concise, runnable Manim Community Edition Python scenes for math tutoring. "
    "Return only Python code."
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build deterministic Token Factory train/validation files per difficulty."
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--validation-ratio", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    manifest = build_specialist_splits(
        args.source,
        args.output_dir,
        validation_ratio=args.validation_ratio,
        seed=args.seed,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


def build_specialist_splits(
    source: Path,
    output_dir: Path,
    *,
    validation_ratio: float,
    seed: int,
) -> dict[str, Any]:
    if not 0 < validation_ratio < 1:
        raise ValueError("validation_ratio must be between 0 and 1")

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    with source.open(encoding="utf-8") as input_file:
        for line_number, line in enumerate(input_file, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            difficulty = record.get("difficulty")
            if difficulty not in DIFFICULTIES:
                raise ValueError(f"line {line_number}: unsupported difficulty {difficulty!r}")
            grouped[difficulty].append(record)

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "source": source.name,
        "source_sha256": _sha256(source),
        "seed": seed,
        "validation_ratio": validation_ratio,
        "specialists": {},
    }
    for difficulty in DIFFICULTIES:
        records = grouped[difficulty]
        if len(records) < 2:
            raise ValueError(f"{difficulty} requires at least two records")
        ordered = sorted(records, key=lambda record: _split_key(str(record["id"]), seed))
        validation_count = max(1, round(len(ordered) * validation_ratio))
        validation_records = ordered[:validation_count]
        train_records = ordered[validation_count:]

        train_path = output_dir / f"{difficulty}_train.jsonl"
        validation_path = output_dir / f"{difficulty}_validation.jsonl"
        _write_token_factory_jsonl(train_path, train_records)
        _write_token_factory_jsonl(validation_path, validation_records)
        manifest["specialists"][difficulty] = {
            "source_records": len(records),
            "train_records": len(train_records),
            "validation_records": len(validation_records),
            "train_file": train_path.name,
            "train_sha256": _sha256(train_path),
            "validation_file": validation_path.name,
            "validation_sha256": _sha256(validation_path),
        }

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def _split_key(record_id: str, seed: int) -> str:
    return hashlib.sha256(f"{seed}:{record_id}".encode()).hexdigest()


def _write_token_factory_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as output_file:
        for record in records:
            payload = {
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"Topic: {record['topic']}\nTask: {record['prompt']}",
                    },
                    {"role": "assistant", "content": str(record["manim_code"]).strip()},
                ]
            }
            output_file.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
