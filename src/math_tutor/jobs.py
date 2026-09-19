from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Lock
from typing import Protocol
from uuid import uuid4

from math_tutor.domain import LessonJob, LessonStatus, utc_now


@dataclass(frozen=True)
class RenderOutcome:
    video_path: Path
    renderer: str
    elapsed_seconds: float
    logs: str


class Renderer(Protocol):
    def render(self, job_id: str) -> RenderOutcome: ...


class JobNotFoundError(KeyError):
    pass


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, LessonJob] = {}
        self._lock = Lock()

    def create(self, lesson: str) -> LessonJob:
        job = LessonJob(
            id=uuid4().hex,
            lesson=lesson,
            status=LessonStatus.QUEUED,
            created_at=utc_now(),
        )
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> LessonJob:
        with self._lock:
            try:
                return self._jobs[job_id]
            except KeyError as error:
                raise JobNotFoundError(job_id) from error

    def mark_running(self, job_id: str) -> LessonJob:
        return self._mutate(
            job_id,
            lambda job: replace(
                job,
                status=LessonStatus.RUNNING,
                started_at=utc_now(),
            ),
        )

    def mark_ready(self, job_id: str, outcome: RenderOutcome) -> LessonJob:
        return self._mutate(
            job_id,
            lambda job: replace(
                job,
                status=LessonStatus.READY,
                completed_at=utc_now(),
                video_path=str(outcome.video_path),
                diagnostics={
                    "renderer": outcome.renderer,
                    "elapsed_seconds": outcome.elapsed_seconds,
                    "logs": outcome.logs,
                },
            ),
        )

    def mark_failed(self, job_id: str, error: Exception) -> LessonJob:
        return self._mutate(
            job_id,
            lambda job: replace(
                job,
                status=LessonStatus.FAILED,
                completed_at=utc_now(),
                error=str(error),
            ),
        )

    def _mutate(
        self,
        job_id: str,
        update: Callable[[LessonJob], LessonJob],
    ) -> LessonJob:
        with self._lock:
            try:
                updated = update(self._jobs[job_id])
            except KeyError as error:
                raise JobNotFoundError(job_id) from error
            self._jobs[job_id] = updated
            return updated


class LessonService:
    def __init__(
        self,
        renderer: Renderer,
        store: JobStore | None = None,
        executor: ThreadPoolExecutor | None = None,
    ) -> None:
        self._renderer = renderer
        self._store = store or JobStore()
        self._executor = executor or ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="lesson-render",
        )

    def submit(self, lesson: str) -> LessonJob:
        job = self._store.create(lesson)
        self._executor.submit(self._run, job.id)
        return job

    def get(self, job_id: str) -> LessonJob:
        return self._store.get(job_id)

    def close(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=True)

    def _run(self, job_id: str) -> None:
        self._store.mark_running(job_id)
        try:
            outcome = self._renderer.render(job_id)
        except Exception as error:
            self._store.mark_failed(job_id, error)
        else:
            self._store.mark_ready(job_id, outcome)
