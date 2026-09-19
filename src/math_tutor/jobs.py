from __future__ import annotations

from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from threading import BoundedSemaphore, Lock
from typing import Protocol
from uuid import uuid4

from math_tutor.domain import LessonJob, LessonStatus, utc_now


@dataclass(frozen=True)
class RenderOutcome:
    video_path: Path
    renderer: str
    elapsed_seconds: float
    logs: str


class JobExecutionError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        diagnostics: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.diagnostics = dict(diagnostics or {})


@dataclass(frozen=True)
class PartialOutcome:
    renderer: str
    elapsed_seconds: float
    logs: str
    error: str


class JobRenderer(Protocol):
    def render(self, job_id: str) -> RenderOutcome | PartialOutcome: ...


class Renderer(Protocol):
    def render(self, job_id: str, lesson: str) -> RenderOutcome | PartialOutcome: ...


class DispatchingRenderer:
    def __init__(self, renderers: Mapping[str, JobRenderer]) -> None:
        self._renderers = dict(renderers)

    def render(self, job_id: str, lesson: str) -> RenderOutcome | PartialOutcome:
        try:
            renderer = self._renderers[lesson]
        except KeyError as error:
            raise JobExecutionError(f"no renderer configured for lesson '{lesson}'") from error
        return renderer.render(job_id)


class JobNotFoundError(KeyError):
    pass


class RenderQueueFullError(RuntimeError):
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
        diagnostics = error.diagnostics if isinstance(error, JobExecutionError) else {}
        return self._mutate(
            job_id,
            lambda job: replace(
                job,
                status=LessonStatus.FAILED,
                completed_at=utc_now(),
                error=str(error),
                diagnostics=diagnostics,
            ),
        )

    def mark_partial(self, job_id: str, outcome: PartialOutcome) -> LessonJob:
        return self._mutate(
            job_id,
            lambda job: replace(
                job,
                status=LessonStatus.PARTIAL,
                completed_at=utc_now(),
                error=outcome.error,
                diagnostics={
                    "renderer": outcome.renderer,
                    "elapsed_seconds": outcome.elapsed_seconds,
                    "logs": outcome.logs,
                },
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
        max_pending_jobs: int = 8,
    ) -> None:
        if max_pending_jobs <= 0:
            raise ValueError("max_pending_jobs must be positive")
        self._renderer = renderer
        self._store = store or JobStore()
        self._executor = executor or ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="lesson-render",
        )
        self._capacity = BoundedSemaphore(max_pending_jobs)

    def submit(self, lesson: str) -> LessonJob:
        if not self._capacity.acquire(blocking=False):
            raise RenderQueueFullError("render queue is full")
        job = self._store.create(lesson)
        try:
            self._executor.submit(self._run, job.id)
        except RuntimeError:
            self._capacity.release()
            raise
        return job

    def get(self, job_id: str) -> LessonJob:
        return self._store.get(job_id)

    def close(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=True)

    def _run(self, job_id: str) -> None:
        try:
            job = self._store.mark_running(job_id)
            try:
                outcome = self._renderer.render(job_id, job.lesson)
            except Exception as error:
                self._store.mark_failed(job_id, error)
            else:
                if isinstance(outcome, PartialOutcome):
                    self._store.mark_partial(job_id, outcome)
                else:
                    self._store.mark_ready(job_id, outcome)
        finally:
            self._capacity.release()
