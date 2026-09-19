# Nebius Generated-Lesson Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect a frozen Nebius model request to validated Manim rendering, then evaluate that unchanged path over a reproducible difficulty-stratified prompt slice.

**Architecture:** A small provider boundary owns OpenAI-compatible Nebius requests and returns typed generation provenance. A generated-lesson pipeline persists the prompt and raw response, extracts and statically validates one `GeneratedLesson` scene, and delegates execution to the existing isolated Docker renderer. The evaluation runner calls that same pipeline and derives aggregate metrics solely from immutable attempt records.

**Tech Stack:** Python 3.11+, FastAPI, httpx, pytest, Manim Docker image, Runme Markdown.

**Spec:** GitHub issues #2 and #3; `docs/math-tutor-dynamic-lora-prd-system-design.html`

## Global Constraints

- Only secrets such as `NEBIUS_API_KEY` are environment variables; model and decoding configuration live in version-controlled Python.
- The frozen target checkpoint is `Qwen/Qwen3-4B`; a different smoke-test model must be disclosed and never reported as the frozen baseline.
- Generated code never executes on the host and uses the existing digest-pinned, network-disabled Docker renderer.
- First-attempt outputs are immutable and are never manually repaired.
- Live generated artifacts and credentials are not committed.

## Review Focus

- Missing or rejected Nebius credentials must produce a terminal job failure without exposing the key.
- Prose around a Python fence must extract exactly one scene; ambiguous multiple code fences must fail.
- Syntactically valid but unsafe imports or calls must be rejected before Docker execution.
- Provider and render failures must still preserve prompt, response, timing, and failure-stage evidence.
- Aggregate metrics must use all attempts as the denominator and retain per-difficulty denominators.

---

### Task 1: Typed Nebius generation boundary

**Files:**
- Create: `src/math_tutor/generation.py`
- Create: `tests/test_generation.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: `GenerationConfig`, `GenerationResult`, `ModelHealth`, `NebiusTokenFactoryClient.generate()`, and `NebiusTokenFactoryClient.health()`.

- [ ] Write tests proving the exact OpenAI-compatible payload, safe response parsing, unavailable-model health, and sanitized provider errors.
- [ ] Run `pytest tests/test_generation.py -q` and observe failure because the module is absent.
- [ ] Implement the minimal httpx client with dependency-injected transport.
- [ ] Run the focused tests, Ruff, and mypy.
- [ ] Commit the provider boundary.

### Task 2: Generated-code extraction and isolated rendering

**Files:**
- Create: `src/math_tutor/generated_lesson.py`
- Create: `tests/test_generated_lesson.py`
- Modify: `src/math_tutor/renderer.py`
- Modify: `src/math_tutor/jobs.py`
- Modify: `tests/test_docker_renderer.py`
- Modify: `tests/test_lesson_api.py`

**Interfaces:**
- Consumes: `GenerationResult` and the existing `DockerManimRenderer`.
- Produces: `extract_and_validate_scene()`, `GeneratedLessonPipeline.render(job_id)`, and persisted `generation.json`, `prompt.txt`, `raw_response.txt`, and `extracted_scene.py` artifacts.

- [ ] Write failing tests for fenced extraction, ambiguity, parse failure, forbidden imports/calls, provenance persistence, and dynamic scene-class rendering.
- [ ] Run the focused tests and confirm expected failures.
- [ ] Generalize the Docker renderer to accept an in-memory scene and class name while preserving the known-scene path.
- [ ] Implement extraction, AST safety validation, persistence, and pipeline orchestration.
- [ ] Run focused tests and commit the generated-render slice.

### Task 3: API demo path and health contract

**Files:**
- Modify: `src/math_tutor/api.py`
- Modify: `src/math_tutor/main.py`
- Modify: `src/math_tutor/jobs.py`
- Modify: `tests/test_lesson_api.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: known and generated renderers.
- Produces: `POST /lessons` with `generated-demo` and `GET /model/health` without exposing credentials.

- [ ] Write failing API tests for generated-demo dispatch, missing credentials, health output, and secret omission.
- [ ] Run the focused tests and confirm expected failures.
- [ ] Implement lesson-aware renderer dispatch and the safe health response.
- [ ] Run focused tests and commit the end-to-end API seam.

### Task 4: Frozen evaluation slice, metrics, and Runme notebook

**Files:**
- Create: `data/evaluation/manim_eval_v1.jsonl`
- Create: `src/math_tutor/evaluation.py`
- Create: `tests/test_evaluation.py`
- Create: `notebooks/zero-shot-baseline.md`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: the same `GeneratedLessonPipeline` used by the API.
- Produces: immutable JSONL attempt records and `metrics.json` with overall and per-difficulty extraction, parse, render, timeout, latency, and token metrics.

- [ ] Write failing tests for dataset validation, training-ID overlap rejection, denominators, per-difficulty metrics, and first-attempt-only accounting.
- [ ] Run focused tests and confirm expected failures.
- [ ] Add five original held-out prompts per difficulty with stable IDs and source metadata.
- [ ] Implement the runner and pure metric aggregation from recorded attempt JSONL.
- [ ] Add named Runme cells for setup, dry validation, live opt-in execution, and metric reproduction.
- [ ] Run focused tests, Runme-safe cells, the full test suite, Ruff, and mypy; commit the evaluation slice.

### Task 5: Independent review and tracking

**Files:**
- Modify only files required by accepted review findings.

**Interfaces:**
- Consumes: the complete local commit range for Tickets #2 and #3.
- Produces: a read-only Claude review, verified fixes, and GitHub project status `In review`.

- [ ] Ask a dedicated Claude reviewer to inspect the exact base-to-head diff with read-only permissions.
- [ ] Reproduce and address actionable findings using test-first fixes.
- [ ] Run the full verification suite again.
- [ ] Move Tickets #2 and #3 to `In review`; do not push.
