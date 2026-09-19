from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType

from math_tutor.narration import NarrationStatus


def utc_now() -> datetime:
    return datetime.now(UTC)


class LessonStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    READY = "ready"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass(frozen=True)
class LessonJob:
    id: str
    lesson: str
    status: LessonStatus
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    video_path: str | None = None
    silent_video_path: str | None = None
    captions_path: str | None = None
    narration_status: NarrationStatus = NarrationStatus.NOT_REQUESTED
    explanation: str | None = None
    generated_code: str | None = None
    diagnostics: Mapping[str, object] = MappingProxyType({})
    error: str | None = None
