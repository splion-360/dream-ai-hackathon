# Three fixed LoRA specialists on Token Factory

This Runme notebook records the hackathon approximation to Dynamic LoRA: three predetermined
difficulty specialists with explicit routing. It does **not** claim dynamic adapter spawning or a
learned inference router. All three jobs use the same model and hyperparameters; only their
difficulty-specific datasets differ.

## Repository identity

Observed: capture the checkout without loading credentials.

```sh {"name":"specialist_setup"}
cd ../..
pwd
git branch --show-current
git rev-parse HEAD
git status --short
```

## Rebuild deterministic specialist splits

Measured on 2026-09-19: 995 valid Bespoke-Manim examples produced 895 training examples and 100
validation examples. Difficulty is a proxy derived from target-code line-count tertiles, not an
independently validated measure of mathematical difficulty.

```sh {"name":"build_specialist_splits"}
cd ../..
backend/.venv/bin/python training/scripts/build_specialist_splits.py \
  training/data/bespoke_manim_train.jsonl \
  training/data/specialists \
  --validation-ratio 0.1 \
  --seed 42
```

## Validate generated files

Measured: verify that all six upload files are valid JSONL and reproduce their record counts and
content hashes.

```sh {"name":"validate_specialist_files"}
cd ../..
for file in training/data/specialists/*.jsonl; do
  jq -e -c . "$file" >/dev/null
  wc -l "$file"
  shasum -a 256 "$file"
done
```

## Submitted jobs

Observed on 2026-09-19: all jobs were accepted with status `running` on `Qwen/Qwen3-4B`.

| Specialist | Training | Validation | Token Factory job |
| --- | ---: | ---: | --- |
| Foundational | 302 | 34 | `ftjob-7a0245e25f344c49a03c9f99b423902b` |
| Intermediate | 299 | 33 | `ftjob-264c7413e60546f888cc63e23cafb663` |
| Advanced | 294 | 33 | `ftjob-eadca09a5f91458084f28ad68fa639b1` |

Every job uses two epochs, batch size 8, learning rate `2×10⁻⁴`, LoRA rank 16, alpha 32,
dropout 0.05, packing enabled, context length 8192, and seed 42.

## Check live job status

Live, read-only: loads the API key only inside the shell and prints bounded job metadata without
credentials. This does not start, cancel, or modify a job.

```sh {"name":"check_specialist_jobs"}
cd ../..
set -a
source backend/.env
set +a
for job_id in \
  ftjob-7a0245e25f344c49a03c9f99b423902b \
  ftjob-264c7413e60546f888cc63e23cafb663 \
  ftjob-eadca09a5f91458084f28ad68fa639b1
do
  curl --fail --silent "https://api.tokenfactory.nebius.com/v1/fine_tuning/jobs/$job_id" \
    --header "Authorization: Bearer $NEBIUS_API_KEY" \
    | jq '{id, suffix, model, status, estimated_finish, trained_steps, total_steps, trained_tokens, error}'
done
```

## Retrieve measured checkpoint metrics

Live, read-only: run after jobs succeed. Token Factory reports training and validation loss and
mean token accuracy per checkpoint. These are training metrics, not proof of mathematical
correctness or Manim render success.

```sh {"name":"read_specialist_metrics"}
cd ../..
set -a
source backend/.env
set +a
for job_id in \
  ftjob-7a0245e25f344c49a03c9f99b423902b \
  ftjob-264c7413e60546f888cc63e23cafb663 \
  ftjob-eadca09a5f91458084f28ad68fa639b1
do
  curl --fail --silent \
    "https://api.tokenfactory.nebius.com/v1/fine_tuning/jobs/$job_id/checkpoints" \
    --header "Authorization: Bearer $NEBIUS_API_KEY" \
    | jq --arg job_id "$job_id" '{job_id: $job_id, checkpoints: [.data[] | {id, step_number, metrics}]}'
done
```

## Interpretation boundary

- Measured: dataset counts and hashes, provider job state, provider checkpoint loss, and mean token
  accuracy.
- To measure after deployment: extraction success, Python parse success, Manim render pass@1,
  generation latency, token use, and results by known difficulty.
- Not measured yet: mathematical correctness, visual quality, automatic-router accuracy, or an
  advantage over a shared LoRA control.
- This experiment is fixed specialization with explicit/oracle routing. It is not evidence of
  dynamic adapter spawning.
