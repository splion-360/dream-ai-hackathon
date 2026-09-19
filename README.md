# Dream AI Math Tutor

The first vertical slice accepts a known lesson as an asynchronous job, renders it with Manim in a locked-down Docker container, and serves the resulting MP4. It does not call an LLM or train a model.

## Requirements

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/)
- Docker with at least 1 GB available to the render container
- `ffmpeg` and `ffprobe` when narration is enabled
- Node.js 20 or newer for the React frontend

## Setup

```bash
uv sync --python 3.12
docker pull manimcommunity/manim@sha256:ab5ad56cf685d89da96e5d459e0cde3743fbdf2141be4dcff6c26566b5ca3191
```

The image must be pinned by digest so development, evaluation, and demo renders use the same Manim environment. Startup rejects mutable image tags.

Install the frontend separately:

```bash
cd frontend
npm ci
```

## Secrets

Copy `.env.example` to `.env` and populate credentials as integrations are enabled. Environment files are reserved for secrets such as Nebius and ElevenLabs API keys; ordinary application configuration remains version-controlled in code.

`ELEVENLABS_API_KEY` enables narration. When it is absent, the same API and frontend operate in silent-video mode. The ElevenLabs voice, model, output format, timeouts, and other non-secret choices live in Python code.

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

The status progresses through `queued` and `running` to a terminal `ready`, `partial`, or `failed` state. `partial` represents an incomplete lesson that still retains useful artifacts or diagnostics. A ready response contains a `video_url`; open that URL or download it with `curl`. When all render capacity is occupied, new submissions receive `503 Service Unavailable` with `Retry-After: 1` instead of accumulating an unbounded queue.

With narration enabled, `narration_status` progresses from `pending` to `ready` or `unavailable`. The response is additive and exposes:

- `video_url`: the best playable result, narrated when available and silent otherwise;
- `silent_video_url`: the original Manim render;
- `captions_url`: measured-timing WebVTT captions when narration succeeds;
- `explanation` and `generated_code`: nullable handoff fields for the Nebius generation pipeline.

Narration is intentionally all-or-nothing for the MVP. ElevenLabs, duration-probe, caption, or mux failures are sanitized and recorded in diagnostics while the lesson remains `ready` with its silent video. Segment durations come from `ffprobe`, not text-length estimates, and drive the audio timeline and captions. Visual cue names are retained for a future cue-aware Manim renderer; this branch preserves the full silent render, pads shorter narration with silence, and does not retime individual visual events. Word-, phoneme-, and cue-level visual alignment are outside this hackathon slice.

## Run the frontend

Start FastAPI on port 8000, then run:

```bash
cd frontend
npm run dev
```

Vite proxies `/lessons` to FastAPI. The browser talks only to the lesson API; it never receives Nebius or ElevenLabs credentials. The current submission transport deliberately targets the bundled Pythagorean fixture until the generation ticket supplies arbitrary prompts. Typed fixtures cover queued, running, narrated success, silent fallback, partial, and failed states.

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
cd frontend && npm test && npm run typecheck && npm run build
```

Run the real API-to-container-to-MP4 check after pulling the image:

```bash
.venv/bin/pytest --run-manim-docker tests/test_docker_renderer_integration.py -q
```
