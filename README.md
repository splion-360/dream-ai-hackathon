# Dream AI Math Tutor

The first vertical slice accepts a known lesson as an asynchronous job, renders it with Manim in a locked-down Docker container, and serves the resulting MP4. It does not call an LLM or train a model.

## Requirements

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/)
- Docker with at least 1 GB available to the render container

## Setup

```bash
uv sync --python 3.12
docker pull manimcommunity/manim@sha256:ab5ad56cf685d89da96e5d459e0cde3743fbdf2141be4dcff6c26566b5ca3191
```

The image is pinned by digest so development, evaluation, and demo renders use the same Manim environment.

## Run the API

```bash
.venv/bin/uvicorn math_tutor.main:app --reload
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

The status progresses through `queued` and `running` to a terminal `ready` or `failed` state. `partial` is reserved for later lessons that retain useful text or code when a downstream media step fails. A ready response contains a `video_url`; open that URL or download it with `curl`.

## Isolation and artifacts

Every render runs with:

- no network access;
- one CPU, 1 GB memory, and 256-process limits;
- a read-only container filesystem and restricted temporary filesystem;
- all Linux capabilities dropped and privilege escalation disabled;
- a configurable 90-second wall-clock timeout followed by forced cleanup.

Each job writes under `artifacts/<job-id>/`. The MP4 stays beneath `media/`, while `render.json` records the image, command, timestamps, timeout, exit code, and bounded stdout/stderr needed to reproduce or diagnose the attempt. Generated artifacts are intentionally ignored by Git.

Configuration can be supplied through the variables documented in [.env.example](.env.example). These variables are read from the process environment; the application does not automatically load the file.

## Verify

Run the fast suite, lint, and type checking:

```bash
.venv/bin/pytest -q
.venv/bin/ruff check src tests
PYTHONPATH=src .venv/bin/mypy src
```

Run the real API-to-container-to-MP4 check after pulling the image:

```bash
RUN_MANIM_DOCKER=1 .venv/bin/pytest tests/test_docker_renderer_integration.py -q
```
