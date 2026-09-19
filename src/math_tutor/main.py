from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from math_tutor.api import create_app
from math_tutor.jobs import LessonService
from math_tutor.renderer import DEFAULT_MANIM_IMAGE, DockerManimRenderer

ARTIFACT_ROOT = Path("artifacts")
RENDER_TIMEOUT_SECONDS = 90
MAX_PENDING_JOBS = 8


def build_app() -> FastAPI:
    package_root = Path(__file__).parent
    renderer = DockerManimRenderer(
        artifact_root=ARTIFACT_ROOT,
        scene_path=package_root / "scenes" / "pythagorean_theorem.py",
        image=DEFAULT_MANIM_IMAGE,
        timeout_seconds=RENDER_TIMEOUT_SECONDS,
    )
    return create_app(
        LessonService(renderer=renderer, max_pending_jobs=MAX_PENDING_JOBS)
    )


app = build_app()
