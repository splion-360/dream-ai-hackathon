from __future__ import annotations

import argparse
from pathlib import Path

from shared_lora_baseline.config import load_config
from shared_lora_baseline.dry_run import build_run_plan, write_run_metadata
from shared_lora_baseline.trainer import train_shared_lora


def main() -> None:
    parser = argparse.ArgumentParser(description="Static shared-LoRA baseline for Manim SFT")
    subparsers = parser.add_subparsers(dest="command", required=True)

    dry_run = subparsers.add_parser("dry-run", help="validate inputs and print a redacted run plan")
    dry_run.add_argument("--config", required=True, type=Path)

    train = subparsers.add_parser("train", help="run supervised fine-tuning for one shared LoRA")
    train.add_argument("--config", required=True, type=Path)

    args = parser.parse_args()
    config = load_config(args.config)

    if args.command == "dry-run":
        plan = build_run_plan(config)
        write_run_metadata(plan, config.metadata_path)
        print(plan.redacted_text)
        return

    if args.command == "train":
        plan = train_shared_lora(config)
        print(plan.redacted_text)
        return

    raise SystemExit(f"unknown command: {args.command}")


if __name__ == "__main__":
    main()
