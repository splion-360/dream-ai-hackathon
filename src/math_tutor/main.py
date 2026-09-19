from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI

from math_tutor.api import create_app
from math_tutor.elevenlabs import ElevenLabsNarrationProvider
from math_tutor.jobs import LessonService, Renderer
from math_tutor.lesson_narration import NarratingRenderer
from math_tutor.media import MediaAssembler, probe_audio_duration
from math_tutor.narration import NarrationPlan, NarrationSegment
from math_tutor.renderer import DEFAULT_MANIM_IMAGE, DockerManimRenderer

ARTIFACT_ROOT = Path("artifacts")
RENDER_TIMEOUT_SECONDS = 90
MAX_PENDING_JOBS = 8
ELEVENLABS_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"


def pythagorean_narration_plan() -> NarrationPlan:
    return NarrationPlan(
        lesson_id="pythagorean-theorem",
        segments=(
            NarrationSegment(
                id="theorem",
                text="For a right triangle, a squared plus b squared equals c squared.",
                cue="equation-visible",
            ),
        ),
    )


def build_app() -> FastAPI:
    package_root = Path(__file__).parent
    renderer: Renderer = DockerManimRenderer(
        artifact_root=ARTIFACT_ROOT,
        scene_path=package_root / "scenes" / "pythagorean_theorem.py",
        image=DEFAULT_MANIM_IMAGE,
        timeout_seconds=RENDER_TIMEOUT_SECONDS,
    )
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if api_key:
        renderer = NarratingRenderer(
            renderer=renderer,
            provider=ElevenLabsNarrationProvider(
                api_key=api_key,
                voice_id=ELEVENLABS_VOICE_ID,
                duration_probe=probe_audio_duration,
            ),
            assembler=MediaAssembler(),
            plan_factory=pythagorean_narration_plan,
            artifact_root=ARTIFACT_ROOT,
        )
    return create_app(
        LessonService(
            renderer=renderer,
            max_pending_jobs=MAX_PENDING_JOBS,
            narration_requested=bool(api_key),
        )
    )


app = build_app()
