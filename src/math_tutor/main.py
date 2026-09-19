from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI

from math_tutor.api import create_app
from math_tutor.jobs import LessonService
from math_tutor.renderer import DEFAULT_MANIM_IMAGE, DockerManimRenderer


def build_app() -> FastAPI:
    package_root = Path(__file__).parent
    artifact_root = Path(os.getenv("MATH_TUTOR_ARTIFACT_ROOT", "artifacts"))
    image = os.getenv("MATH_TUTOR_MANIM_IMAGE", DEFAULT_MANIM_IMAGE)
    timeout_seconds = float(os.getenv("MATH_TUTOR_RENDER_TIMEOUT_SECONDS", "90"))
    renderer = DockerManimRenderer(
        artifact_root=artifact_root,
        scene_path=package_root / "scenes" / "pythagorean_theorem.py",
        image=image,
        timeout_seconds=timeout_seconds,
    )
    return create_app(LessonService(renderer=renderer))


app = build_app()
