# Dream AI Math Tutor Backend

The first vertical slice accepts a known lesson as an asynchronous job, renders it with Manim in a locked-down Docker container, and serves the resulting MP4. It does not call an LLM or train a model.

## Requirements

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/)
- Docker with at least 1 GB available to the render container

## Setup

Run backend commands from this directory:

```bash
cd backend
```

```bash
uv sync --python 3.12
docker pull manimcommunity/manim@sha256:ab5ad56cf685d89da96e5d459e0cde3743fbdf2141be4dcff6c26566b5ca3191
```

The image must be pinned by digest so development, evaluation, and demo renders use the same Manim environment. Startup rejects mutable image tags.

## Secrets

Copy `.env.example` to `.env` and populate credentials as integrations are enabled. Environment files are reserved for secrets such as Nebius and ElevenLabs API keys; ordinary application configuration remains version-controlled in code.

## Run the API

```bash
.venv/bin/uvicorn --env-file .env math_tutor.main:app --reload
```

Submit the bundled Pythagorean theorem lesson:

```bash
curl -i \
  -X POST http://127.0.0.1:8000/lessons \
  -H 'content-type: application/json' \
  -d '{"lesson":"pythagorean-theorem"}'
```

The `202 Accepted` response contains a stable job `id` and begins in `queued`. Poll it without holding the submission request open:

```bash
curl http://127.0.0.1:8000/lessons/JOB_ID
```

Submit the fixed generated-lesson smoke test with the same job contract:

```bash
curl -i \
  -X POST http://127.0.0.1:8000/lessons \
  -H 'content-type: application/json' \
  -d '{"lesson":"generated-demo"}'
```

The generated path reads `NEBIUS_API_KEY` only on the server, records the frozen model and decoding configuration, preserves the raw provider response, validates exactly one `GeneratedLesson` scene, and renders it in the same isolated container. Check provider reachability and exact-checkpoint availability separately:

```bash
curl http://127.0.0.1:8000/model/health
```

The frozen target is `Qwen/Qwen3-4B`. At the time of implementation it was supported for Nebius post-training but absent from this account's shared serverless inference catalog, so a live matching run requires a custom or dedicated endpoint. A smoke test against another model proves connectivity only and must not be reported as the frozen baseline.

The status progresses through `queued` and `running` to a terminal `ready`, `partial`, or `failed` state. `partial` represents an incomplete lesson that still retains useful artifacts or diagnostics. A ready response contains a `video_url`; open that URL or download it with `curl`. When all render capacity is occupied, new submissions receive `503 Service Unavailable` with `Retry-After: 1` instead of accumulating an unbounded queue.

## Isolation and artifacts

Every render runs with:

- no network access;
- one CPU, 1 GB memory, and 256-process limits;
- a read-only container filesystem and restricted temporary filesystem;
- all Linux capabilities dropped and privilege escalation disabled;
- a configurable 90-second wall-clock timeout followed by forced cleanup.

Each job writes under `artifacts/<job-id>/`. Snapshots and SHA-256 hashes preserve the exact scene and validation source. The MP4 stays beneath `output/media/`, while `render.json` records the image, command, timestamps, timeout, cleanup result, exit code, and bounded stdout/stderr needed to reproduce or diagnose the attempt. Failed job responses also include bounded renderer diagnostics. Before a job becomes ready, PyAV decodes a video frame inside the pinned container and the host rejects symlinks or paths escaping the job output directory. Generated artifacts are intentionally ignored by Git.

## Verify

Run the fast suite, lint, and type checking:

```bash
.venv/bin/pytest -q
.venv/bin/ruff check src tests
PYTHONPATH=src .venv/bin/mypy src
```

Run the real API-to-container-to-MP4 check after pulling the image:

```bash
.venv/bin/pytest --run-manim-docker tests/test_docker_renderer_integration.py -q
```
