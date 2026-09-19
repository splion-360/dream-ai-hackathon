from __future__ import annotations

from pathlib import Path
from threading import Event
from time import monotonic, sleep

from fastapi.testclient import TestClient

from math_tutor.api import create_app
from math_tutor.jobs import JobExecutionError, LessonService, PartialOutcome, RenderOutcome
from math_tutor.narration import NarrationStatus


class ControlledRenderer:
    def __init__(self, video_path: Path) -> None:
        self.started = Event()
        self.release = Event()
        self.video_path = video_path

    def render(self, job_id: str) -> RenderOutcome:
        self.started.set()
        if not self.release.wait(timeout=2):
            raise RuntimeError("test renderer was never released")
        return RenderOutcome(
            video_path=self.video_path,
            renderer="controlled-test-renderer",
            elapsed_seconds=0.01,
            logs="render complete",
        )


class FailedRenderer:
    def render(self, job_id: str) -> RenderOutcome:
        raise RuntimeError(f"render failed for {job_id}")


class PartialRenderer:
    def render(self, job_id: str) -> PartialOutcome:
        return PartialOutcome(
            renderer="partial-test-renderer",
            elapsed_seconds=0.01,
            logs="video unavailable",
            error=f"partial result for {job_id}",
        )


class DiagnosticFailedRenderer:
    def render(self, job_id: str) -> RenderOutcome:
        raise JobExecutionError(
            f"render failed for {job_id}",
            diagnostics={
                "renderer": "diagnostic-test-renderer",
                "logs": "container exited 42",
                "metadata_file": "render.json",
            },
        )


class NarratedRenderer:
    def __init__(self, narrated: Path, silent: Path, captions: Path) -> None:
        self.narrated = narrated
        self.silent = silent
        self.captions = captions

    def render(self, job_id: str) -> RenderOutcome:
        return RenderOutcome(
            video_path=self.narrated,
            silent_video_path=self.silent,
            captions_path=self.captions,
            narration_status=NarrationStatus.READY,
            narration_diagnostics={"narration_provider": "fake"},
            renderer="narrated-test-renderer",
            elapsed_seconds=0.02,
            logs="narrated",
        )


def wait_for_status(client: TestClient, job_id: str, expected: str) -> dict[str, object]:
    deadline = monotonic() + 2
    while monotonic() < deadline:
        response = client.get(f"/lessons/{job_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] == expected:
            return payload
        sleep(0.01)
    raise AssertionError(f"job {job_id} did not reach {expected}")


def test_submit_known_lesson_returns_before_render_and_can_be_polled(tmp_path: Path) -> None:
    video = tmp_path / "lesson.mp4"
    video.write_bytes(b"video")
    renderer = ControlledRenderer(video)
    service = LessonService(renderer=renderer)

    with TestClient(create_app(service)) as client:
        submitted = client.post("/lessons", json={"lesson": "pythagorean-theorem"})

        assert submitted.status_code == 202
        queued = submitted.json()
        assert queued["id"]
        assert queued["lesson"] == "pythagorean-theorem"
        assert queued["status"] == "queued"
        assert queued["video_url"] is None
        assert queued["silent_video_url"] is None
        assert queued["captions_url"] is None
        assert queued["narration_status"] == "not_requested"
        assert queued["explanation"] is None
        assert queued["generated_code"] is None
        assert renderer.started.wait(timeout=1)

        running = wait_for_status(client, queued["id"], "running")
        assert running["started_at"] is not None

        renderer.release.set()
        ready = wait_for_status(client, queued["id"], "ready")

    assert ready["video_url"] == f"/lessons/{queued['id']}/video"
    assert ready["silent_video_url"] == f"/lessons/{queued['id']}/video/silent"
    assert ready["completed_at"] is not None
    assert ready["diagnostics"]["renderer"] == "controlled-test-renderer"


def test_unknown_job_returns_not_found(tmp_path: Path) -> None:
    renderer = ControlledRenderer(tmp_path / "unused.mp4")
    service = LessonService(renderer=renderer)

    with TestClient(create_app(service)) as client:
        response = client.get("/lessons/not-a-job")

    assert response.status_code == 404
    assert response.json() == {"detail": "lesson job not found"}


def test_render_failure_reaches_terminal_failed_state() -> None:
    service = LessonService(renderer=FailedRenderer())

    with TestClient(create_app(service)) as client:
        submitted = client.post("/lessons", json={"lesson": "pythagorean-theorem"})
        failed = wait_for_status(client, submitted.json()["id"], "failed")

    assert failed["completed_at"] is not None
    assert failed["video_url"] is None
    assert "render failed" in failed["error"]


def test_render_failure_exposes_bounded_diagnostics() -> None:
    service = LessonService(renderer=DiagnosticFailedRenderer())

    with TestClient(create_app(service)) as client:
        submitted = client.post("/lessons", json={"lesson": "pythagorean-theorem"})
        failed = wait_for_status(client, submitted.json()["id"], "failed")

    assert failed["diagnostics"] == {
        "renderer": "diagnostic-test-renderer",
        "logs": "container exited 42",
        "metadata_file": "render.json",
    }


def test_useful_incomplete_result_reaches_terminal_partial_state() -> None:
    service = LessonService(renderer=PartialRenderer())

    with TestClient(create_app(service)) as client:
        submitted = client.post("/lessons", json={"lesson": "pythagorean-theorem"})
        partial = wait_for_status(client, submitted.json()["id"], "partial")

    assert partial["completed_at"] is not None
    assert partial["video_url"] is None
    assert partial["error"].startswith("partial result")
    assert partial["diagnostics"]["renderer"] == "partial-test-renderer"


def test_submission_is_rejected_when_render_capacity_is_full(tmp_path: Path) -> None:
    renderer = ControlledRenderer(tmp_path / "lesson.mp4")
    service = LessonService(renderer=renderer, max_pending_jobs=1)

    with TestClient(create_app(service)) as client:
        first = client.post("/lessons", json={"lesson": "pythagorean-theorem"})
        assert renderer.started.wait(timeout=1)

        second = client.post("/lessons", json={"lesson": "pythagorean-theorem"})

        assert first.status_code == 202
        assert second.status_code == 503
        assert second.headers["retry-after"] == "1"
        assert second.json() == {"detail": "render queue is full"}
        renderer.video_path.write_bytes(b"video")
        renderer.release.set()
        wait_for_status(client, first.json()["id"], "ready")


def test_narrated_lesson_exposes_best_silent_and_caption_artifacts(tmp_path: Path) -> None:
    narrated = tmp_path / "narrated.mp4"
    silent = tmp_path / "silent.mp4"
    captions = tmp_path / "captions.vtt"
    narrated.write_bytes(b"narrated")
    silent.write_bytes(b"silent")
    captions.write_text("WEBVTT\n", encoding="utf-8")
    service = LessonService(
        renderer=NarratedRenderer(narrated, silent, captions),
        narration_requested=True,
    )

    with TestClient(create_app(service)) as client:
        submitted = client.post("/lessons", json={"lesson": "pythagorean-theorem"})
        assert submitted.json()["narration_status"] == "pending"
        job_id = submitted.json()["id"]
        ready = wait_for_status(client, job_id, "ready")

        best_response = client.get(ready["video_url"])
        silent_response = client.get(ready["silent_video_url"])
        captions_response = client.get(ready["captions_url"])

    assert ready["narration_status"] == "ready"
    assert ready["diagnostics"]["narration_provider"] == "fake"
    assert best_response.content == b"narrated"
    assert silent_response.content == b"silent"
    assert captions_response.text == "WEBVTT\n"
