from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from math_tutor.domain import LessonJob, LessonStatus
from math_tutor.jobs import JobNotFoundError, LessonService, RenderQueueFullError


class CreateLessonRequest(BaseModel):
    lesson: Literal["pythagorean-theorem"]


class LessonResponse(BaseModel):
    id: str
    lesson: str
    status: LessonStatus
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    video_url: str | None
    diagnostics: dict[str, object]
    error: str | None


def to_response(job: LessonJob) -> LessonResponse:
    video_url = f"/lessons/{job.id}/video" if job.video_path else None
    return LessonResponse(
        id=job.id,
        lesson=job.lesson,
        status=job.status,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        video_url=video_url,
        diagnostics=dict(job.diagnostics),
        error=job.error,
    )


def create_app(service: LessonService) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await run_in_threadpool(service.close)

    app = FastAPI(title="Math Tutor API", version="0.1.0", lifespan=lifespan)

    @app.post(
        "/lessons",
        response_model=LessonResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    def submit_lesson(request: CreateLessonRequest) -> LessonResponse:
        try:
            return to_response(service.submit(request.lesson))
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

    return app
