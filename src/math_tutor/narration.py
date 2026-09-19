from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Protocol


class NarrationStatus(StrEnum):
    NOT_REQUESTED = "not_requested"
    PENDING = "pending"
    READY = "ready"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class NarrationSegment:
    id: str
    text: str
    cue: str

    def __post_init__(self) -> None:
        for name, value in (("id", self.id), ("text", self.text), ("cue", self.cue)):
            if not value.strip():
                raise ValueError(f"narration segment {name} must not be blank")


@dataclass(frozen=True)
class NarrationPlan:
    lesson_id: str
    segments: tuple[NarrationSegment, ...]
    schema_version: str = field(default="narration-plan.v1", init=False)

    def __post_init__(self) -> None:
        if not self.lesson_id.strip():
            raise ValueError("lesson_id must not be blank")
        if not self.segments:
            raise ValueError("narration plan needs at least one segment")
        segment_ids = [segment.id for segment in self.segments]
        if len(segment_ids) != len(set(segment_ids)):
            raise ValueError("narration segment ids must be unique")


@dataclass(frozen=True)
class SynthesizedSegment:
    id: str
    cue: str
    text: str
    audio_path: Path
    duration_seconds: float
    sha256: str

    def __post_init__(self) -> None:
        if self.duration_seconds <= 0:
            raise ValueError("duration_seconds must be positive")
        if len(self.sha256) != 64:
            raise ValueError("sha256 must be a 64-character hexadecimal digest")
        try:
            int(self.sha256, 16)
        except ValueError as error:
            raise ValueError("sha256 must be a 64-character hexadecimal digest") from error


@dataclass(frozen=True)
class SynthesizedNarration:
    lesson_id: str
    provider: str
    model_id: str
    segments: tuple[SynthesizedSegment, ...]
    plan: NarrationPlan = field(repr=False, compare=False)
    schema_version: str = field(default="audio-timeline.v1", init=False)

    def __post_init__(self) -> None:
        if self.lesson_id != self.plan.lesson_id:
            raise ValueError("synthesized narration lesson must match its plan")
        expected = [segment.id for segment in self.plan.segments]
        actual = [segment.id for segment in self.segments]
        if actual != expected:
            raise ValueError("synthesized segments must match plan order")


@dataclass(frozen=True)
class MediaBundle:
    silent_video_path: Path
    video_path: Path
    narration_status: NarrationStatus
    captions_path: Path | None = None
    timeline_path: Path | None = None
    diagnostics: Mapping[str, object] = field(
        default_factory=lambda: MappingProxyType({})
    )


class NarrationProvider(Protocol):
    def synthesize(
        self,
        plan: NarrationPlan,
        output_dir: Path,
    ) -> SynthesizedNarration: ...
