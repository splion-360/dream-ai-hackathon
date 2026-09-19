# ElevenLabs Narration and React Contracts Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use mattpocock-skills:implement and mattpocock-skills:tdd to execute this plan task-by-task.

**Goal:** Add independently testable ElevenLabs narration, measured audio/caption timing, silent-video fallback, and a typed React demo surface without depending on Nebius. Visual cue retiming is explicitly deferred.

**Architecture:** Keep provider-neutral narration types and orchestration in Python, isolate ElevenLabs behind an injected HTTP transport, and isolate `ffprobe`/`ffmpeg` behind a media assembler. Extend the existing asynchronous lesson job additively. Put the browser behind a typed transport so the same UI can run against deterministic fixtures or FastAPI.

**Tech Stack:** Python 3.11+, dataclasses/protocols, FastAPI, httpx, pytest, React 19, TypeScript, Vite, Vitest, Testing Library.

---

### Task 1: Provider-neutral narration contracts

**Files:**
- Create: `src/math_tutor/narration.py`
- Create: `tests/test_narration.py`

1. Write a failing public-contract test for ordered, validated `NarrationPlan` values.
2. Run `uv run pytest tests/test_narration.py -q` and confirm the import/behavior fails.
3. Implement immutable narration plan, synthesized segment, narration result, media bundle, status, and provider protocol types.
4. Rerun the focused test and `uv run mypy src/math_tutor/narration.py`.
5. Commit as `feat(narration): add provider-neutral contracts`.

### Task 2: ElevenLabs provider adapter

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `src/math_tutor/elevenlabs.py`
- Create: `tests/test_elevenlabs.py`

1. Write a failing test at the provider boundary using an injected fake HTTP transport.
2. Verify the request uses the official text-to-speech endpoint, `xi-api-key`, configured voice/model, and writes one audio artifact per segment without serializing secrets.
3. Implement the smallest adapter and stable provider error.
4. Add `httpx` as an application dependency and rerun focused tests, Ruff, and mypy.
5. Commit as `feat(narration): add ElevenLabs adapter`.

### Task 3: Measured media timeline and captions

**Files:**
- Create: `src/math_tutor/media.py`
- Create: `tests/test_media.py`

1. Write a failing test for propagating injected `ffprobe` durations into WebVTT captions and an audio timeline.
2. Implement duration inspection, WebVTT generation, ordered audio concatenation, and `ffmpeg` muxing behind an injected command runner.
3. Test failed probe/mux operations as stable media errors. Do not require host binaries in the default suite.
4. Run focused tests, Ruff, and mypy.
5. Commit as `feat(media): assemble timed narration artifacts`.

### Task 4: Silent fallback and API integration

**Files:**
- Modify: `src/math_tutor/domain.py`
- Modify: `src/math_tutor/jobs.py`
- Modify: `src/math_tutor/api.py`
- Modify: `src/math_tutor/main.py`
- Create: `src/math_tutor/lesson_narration.py`
- Modify: `tests/test_lesson_api.py`
- Create: `tests/test_lesson_narration.py`

1. Write failing tests showing successful narration selects the narrated video and failed narration preserves a ready silent lesson with sanitized diagnostics.
2. Add narration-aware artifacts/status to `LessonJob` and additive response fields.
3. Decorate the existing renderer with optional narration orchestration; keep the base render successful on any narration-stage failure.
4. Add silent-video and captions download routes with the same readiness/path checks as the existing video route.
5. Configure ElevenLabs only when `ELEVENLABS_API_KEY` is present; keep ordinary settings in code.
6. Run focused and existing backend tests, Ruff, and mypy.
7. Commit as `feat(api): add narrated lesson fallback flow`.

### Task 5: React contracts and demo states

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/index.html`
- Create: `frontend/src/contracts.ts`
- Create: `frontend/src/transport.ts`
- Create: `frontend/src/fixtures.ts`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/styles.css`
- Create: `frontend/src/App.test.tsx`
- Create: `frontend/src/test-setup.ts`

1. Write failing UI tests for queued/running, narrated-ready, silent-fallback, partial, and failed states through the public React component.
2. Implement matching lesson contracts, mock and HTTP transports, polling, form submission, result selection, caption availability, code/explanation panels, and explicit fallback messaging.
3. Keep provider credentials and provider calls out of the browser.
4. Run `npm test`, `npm run typecheck`, and `npm run build` from `frontend/`.
5. Commit as `feat(frontend): add narration-aware lesson UI`.

### Task 6: Documentation and final verification

**Files:**
- Modify: `README.md`

1. Document the backend/frontend commands, ElevenLabs secret, `ffmpeg` prerequisite, fallback semantics, and mock demo.
2. Run the full Python suite, Ruff, mypy, frontend tests, frontend typecheck, and frontend production build.
3. Commit as `docs: explain narrated lesson workflow`.
4. Request a read-only Claude Opus 4.8 review against base commit `5b72079`, fix findings test-first, and repeat verification.
5. Move GitHub ticket #6 from **In progress** to **In review** only after the review and checks pass. Do not push.
