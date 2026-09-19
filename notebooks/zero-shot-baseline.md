# Frozen zero-shot Manim baseline

This Runme notebook validates and executes the evaluation defined by
`data/evaluation/manim_eval_v1.jsonl`. Static cells never load `.env`. The live cells are
explicitly marked because they call Nebius, consume credits, and—once the exact model endpoint is
available—start Docker renders.

The frozen condition is `Qwen/Qwen3-4B` with temperature `0`, top-p `1`, maximum output `4096`, and
seed `42`. A run against another model is only a connectivity smoke test and is not baseline
evidence.

## Repository identity

Observed: this cell records the checkout and dirty-state summary without printing environment
variables or credentials.

```sh {"name":"baseline_setup"}
cd ..
pwd
git branch --show-current
git rev-parse HEAD
git status --short
```

## Validate the held-out slice

Observed: the dataset loader enforces unique stable IDs, the `evaluation` split, source metadata,
and at least five examples in each difficulty band.

```sh {"name":"validate_dataset"}
cd ..
.venv/bin/python -c 'from pathlib import Path; from collections import Counter; from math_tutor.evaluation import load_evaluation_slice; rows=load_evaluation_slice(Path("data/evaluation/manim_eval_v1.jsonl")); print({"examples": len(rows), "difficulty": dict(Counter(row.difficulty for row in rows)), "unique_ids": len({row.id for row in rows})})'
```

## Reproduce metric logic

Measured: this executes the tests that pin denominators, per-difficulty breakdowns, token totals,
and first-attempt versus repair accounting.

```sh {"name":"verify_metrics"}
cd ..
.venv/bin/pytest tests/test_evaluation.py -q
```

## Check exact model availability

Live, read-only: this loads `.env` only inside the child process, queries the model catalog, and
prints no credential. A healthy API with `model_available: false` means the Token Factory key works
but the exact checkpoint still needs a custom or dedicated endpoint.

```sh {"name":"check_nebius_model"}
cd ..
uv run --env-file .env python -c 'import os; from math_tutor.generation import GenerationConfig, NebiusTokenFactoryClient; client=NebiusTokenFactoryClient(api_key=os.environ["NEBIUS_API_KEY"], config=GenerationConfig()); print(client.health()); client.close()'
```

## Execute the frozen baseline

Live, credit-consuming: run this only after `check_nebius_model` reports
`model_available=True`. The command makes 15 model requests and starts up to 15 sequential isolated
Docker renders. It never repairs failed generations.

```sh {"name":"run_frozen_baseline"}
cd ..
test -n "${RUN_ID:-}" || { echo "Set RUN_ID to a stable run identifier"; exit 2; }
uv run --env-file .env python -m math_tutor.evaluation --run-id "$RUN_ID"
```

## Reproduce a completed run's aggregate metrics

Measured: aggregation reads immutable attempt records rather than calling the model again. Set
`RUN_ID` to the recorded run identifier.

```sh {"name":"reproduce_metrics"}
cd ..
test -n "${RUN_ID:-}" || { echo "Set RUN_ID to a completed run identifier"; exit 2; }
.venv/bin/python -c 'import json, os; from pathlib import Path; from math_tutor.evaluation import AttemptRecord, aggregate_metrics; path=Path("artifacts/evaluations")/os.environ["RUN_ID"] / "attempts.jsonl"; attempts=[AttemptRecord(**json.loads(line)) for line in path.read_text().splitlines() if line.strip()]; print(json.dumps(aggregate_metrics(attempts), indent=2, sort_keys=True))'
```

## Interpretation boundary

- Observed before a live run: dataset structure, frozen configuration, code paths, and tests.
- Measured after a live run: extraction success, parse success, render pass@1, timeout rate,
  generation/render latency, token usage, and per-difficulty results.
- Not measured here: mathematical correctness or visual similarity to a golden video. Those require a
  separate judge or reference-render metric and must not be inferred from render success.
