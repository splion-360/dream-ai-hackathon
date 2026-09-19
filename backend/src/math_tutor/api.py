from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator
from starlette.concurrency import run_in_threadpool

from math_tutor.domain import LessonJob, LessonStatus
from math_tutor.generation import FROZEN_MODEL, ModelHealth
from math_tutor.jobs import JobNotFoundError, LessonService, RenderQueueFullError
from math_tutor.narration import NarrationStatus


class CreateLessonRequest(BaseModel):
    lesson: Literal["pythagorean-theorem", "generated-demo"] | None = None
    prompt: str | None = Field(default=None, min_length=1, max_length=2_000)

    @model_validator(mode="after")
    def require_one_input(self) -> CreateLessonRequest:
        if (self.lesson is None) == (self.prompt is None):
            raise ValueError("provide exactly one of lesson or prompt")
        if self.prompt is not None:
            self.prompt = self.prompt.strip()
            if not self.prompt:
                raise ValueError("prompt must not be blank")
        return self


class ModelHealthResponse(BaseModel):
    reachable: bool
    model: str
    model_available: bool
    error: str | None


class LessonResponse(BaseModel):
    id: str
    lesson: str
    status: LessonStatus
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    video_url: str | None
    silent_video_url: str | None
    captions_url: str | None
    narration_status: NarrationStatus
    explanation: str | None
    generated_code: str | None
    diagnostics: dict[str, object]
    error: str | None


def to_response(job: LessonJob) -> LessonResponse:
    video_url = f"/lessons/{job.id}/video" if job.video_path else None
    silent_video_url = (
        f"/lessons/{job.id}/video/silent" if job.silent_video_path else None
    )
    captions_url = f"/lessons/{job.id}/captions" if job.captions_path else None
    return LessonResponse(
        id=job.id,
        lesson=job.lesson,
        status=job.status,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        video_url=video_url,
        silent_video_url=silent_video_url,
        captions_url=captions_url,
        narration_status=job.narration_status,
        explanation=job.explanation,
        generated_code=job.generated_code,
        diagnostics=dict(job.diagnostics),
        error=job.error,
    )


def create_app(
    service: LessonService,
    *,
    model_health: Callable[[], ModelHealth] | None = None,
    close_model: Callable[[], None] | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await run_in_threadpool(service.close)
        if close_model is not None:
            await run_in_threadpool(close_model)

    app = FastAPI(title="Math Tutor API", version="0.1.0", lifespan=lifespan)

    @app.get("/model/health", response_model=ModelHealthResponse)
    def get_model_health() -> ModelHealthResponse:
        health = (
            model_health()
            if model_health is not None
            else ModelHealth(
                reachable=False,
                model=FROZEN_MODEL,
                model_available=False,
                error="model provider is not configured",
            )
        )
        return ModelHealthResponse(
            reachable=health.reachable,
            model=health.model,
            model_available=health.model_available,
            error=health.error,
        )

    @app.post(
        "/lessons",
        response_model=LessonResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    def submit_lesson(request: CreateLessonRequest) -> LessonResponse:
        try:
            return to_response(service.submit(request.prompt or request.lesson or ""))
        except RenderQueueFullError as error:
            raise HTTPException(
                status_code=503,
                detail="render queue is full",
                headers={"Retry-After": "1"},
            ) from error

    @app.get("/lessons/{job_id}", response_model=LessonResponse)
    def get_lesson(job_id: str) -> LessonResponse:
        try:
            return to_response(service.get(job_id))
        except JobNotFoundError as error:
            raise HTTPException(status_code=404, detail="lesson job not found") from error

    @app.get("/lessons/{job_id}/video", response_class=FileResponse)
    def get_video(job_id: str) -> FileResponse:
        try:
            job = service.get(job_id)
        except JobNotFoundError as error:
            raise HTTPException(status_code=404, detail="lesson job not found") from error
        if job.status is not LessonStatus.READY or job.video_path is None:
            raise HTTPException(status_code=409, detail="lesson video is not ready")
        video_path = Path(job.video_path)
        if not video_path.is_file():
            raise HTTPException(status_code=410, detail="lesson video is unavailable")
        return FileResponse(video_path, media_type="video/mp4", filename="lesson.mp4")

    @app.get("/lessons/{job_id}/video/silent", response_class=FileResponse)
    def get_silent_video(job_id: str) -> FileResponse:
        job = _ready_job(service, job_id)
        if job.silent_video_path is None:
            raise HTTPException(status_code=409, detail="silent lesson video is not ready")
        video_path = Path(job.silent_video_path)
        if not video_path.is_file():
            raise HTTPException(status_code=410, detail="silent lesson video is unavailable")
        return FileResponse(video_path, media_type="video/mp4", filename="lesson-silent.mp4")

    @app.get("/lessons/{job_id}/captions", response_class=FileResponse)
    def get_captions(job_id: str) -> FileResponse:
        job = _ready_job(service, job_id)
        if job.captions_path is None:
            raise HTTPException(status_code=409, detail="lesson captions are not ready")
        captions_path = Path(job.captions_path)
        if not captions_path.is_file():
            raise HTTPException(status_code=410, detail="lesson captions are unavailable")
        return FileResponse(captions_path, media_type="text/vtt", filename="lesson.vtt")

    return app


def _ready_job(service: LessonService, job_id: str) -> LessonJob:
    try:
        job = service.get(job_id)
    except JobNotFoundError as error:
        raise HTTPException(status_code=404, detail="lesson job not found") from error
    if job.status is not LessonStatus.READY:
        raise HTTPException(status_code=409, detail="lesson is not ready")
    return job
