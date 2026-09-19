# Live math-tutor demo smoke test

This Runme notebook records the judge-facing product path separately from the frozen research
baseline. The live demo uses `Qwen/Qwen3-30B-A3B-Instruct-2507`, because that model is available
from the current Nebius Token Factory endpoint. These results must not be presented as the
`Qwen/Qwen3-4B` baseline or as evidence about LoRA performance.

## Repository identity

Observed: record the checkout without loading credentials or printing environment variables.

```sh {"name":"demo_setup"}
cd ..
pwd
git branch --show-current
git rev-parse HEAD
git status --short
```

## Check the running services

Live, read-only: verify the local applications and selected demo model. This cell does not make an
inference request.

```sh {"name":"check_demo_services"}
cd ..
curl --fail --silent http://127.0.0.1:8000/model/health | jq
curl --fail --silent http://127.0.0.1:5173/ >/dev/null
```

## Reproduce the recorded typed-prompt result

Measured on 2026-09-19: job `c4671423e73b44fa873c1abf7b39cb04` submitted the prompt
`Explain visually why the square root of 2 is irrational.` through the frontend origin. Nebius
returned 1,604 completion tokens from 1,768 total tokens in 26.248 seconds. The first-attempt Manim
render completed in 10.186 seconds. The successful result followed earlier failed attempts caused
by invalid model-generated Manim APIs; those failures remain in `backend/artifacts/` and are not
counted as successes.

```sh {"name":"inspect_recorded_demo"}
cd ..
JOB_ID="${JOB_ID:-c4671423e73b44fa873c1abf7b39cb04}"
test -f "artifacts/$JOB_ID/generation.json"
test -f "artifacts/$JOB_ID/render.json"
jq '{status, model, request_id, finish_reason, elapsed_seconds, prompt_tokens, completion_tokens, total_tokens}' "artifacts/$JOB_ID/generation.json"
jq '{status, exit_code, elapsed_seconds, scene_class}' "artifacts/$JOB_ID/render.json"
find "artifacts/$JOB_ID/output/media" -name 'GeneratedLesson.mp4' -type f -exec stat -f '%z bytes %N' {} \;
```

## Reproduce the recorded ElevenLabs result

Measured on 2026-09-19: the available ElevenLabs `Alice` educator voice synthesized one 7.340-second
segment. FFmpeg produced a 654,268-byte narrated MP4 and WebVTT captions. This smoke artifact was
muxed onto the recorded successful render without another Nebius request. Generated lessons now
use the same narration wrapper, with silent-video fallback when synthesis or muxing fails.

```sh {"name":"inspect_recorded_audio"}
cd ..
JOB_ID="${JOB_ID:-c4671423e73b44fa873c1abf7b39cb04}"
test -s "artifacts/$JOB_ID/narration-smoke/narrated.mp4"
test -s "artifacts/$JOB_ID/narration-smoke/captions.vtt"
docker compose -f ../compose.yaml exec --no-TTY backend \
  ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 \
  "artifacts/$JOB_ID/narration-smoke/narrated.mp4"
stat -f '%z bytes %N' "artifacts/$JOB_ID/narration-smoke/narrated.mp4"
sed -n '1,8p' "artifacts/$JOB_ID/narration-smoke/captions.vtt"
```

## Submit another live lesson

Live, credit-consuming: this cell calls both Nebius and ElevenLabs. It is gated to prevent an
accidental paid run. Poll the returned job ID through `GET /lessons/<job-id>`.

```sh {"name":"submit_live_demo"}
cd ..
test "${RUN_LIVE:-0}" = "1" || { echo "Set RUN_LIVE=1 to spend provider credits"; exit 2; }
curl --fail --silent --request POST http://127.0.0.1:5173/lessons \
  --header 'content-type: application/json' \
  --data '{"prompt":"Explain visually why the square root of 2 is irrational."}' | jq
```

## Verify the implementation

Measured: execute the deterministic backend and frontend gates without provider calls.

```sh {"name":"verify_demo_code"}
cd ..
.venv/bin/ruff check src tests
PYTHONPATH=src .venv/bin/mypy src
.venv/bin/pytest -q
cd ../frontend
npm test
npm run typecheck
npm run build
```

## Interpretation boundary

- Measured: provider reachability, saved token counts, generation latency, render outcome and
  latency, synthesized-audio duration, caption creation, and muxed-video size.
- Observed limitation: render success is sensitive to model-generated Manim API correctness.
- Not measured: mathematical correctness, visual quality, semantic audio/animation alignment, the
  frozen 4B baseline, shared LoRA, or Dynamic LoRA performance.
