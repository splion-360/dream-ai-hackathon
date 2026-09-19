from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI

from math_tutor.api import create_app
from math_tutor.generated_lesson import GeneratedLessonPipeline
from math_tutor.generation import (
    GenerationConfig,
    NebiusTokenFactoryClient,
    UnavailableModelClient,
)
from math_tutor.jobs import DispatchingRenderer, LessonService
from math_tutor.renderer import DEFAULT_MANIM_IMAGE, DockerManimRenderer

ARTIFACT_ROOT = Path("artifacts")
RENDER_TIMEOUT_SECONDS = 90
MAX_PENDING_JOBS = 8
GENERATED_DEMO_PROMPT = """Create a concise visual lesson explaining why the Taylor
series of e^x equals the function. Show the polynomial approximations building from
orders zero through five, label the equation, and keep all objects inside the frame."""


def build_app() -> FastAPI:
    package_root = Path(__file__).parent
    renderer = DockerManimRenderer(
        artifact_root=ARTIFACT_ROOT,
        scene_path=package_root / "scenes" / "pythagorean_theorem.py",
        image=DEFAULT_MANIM_IMAGE,
        timeout_seconds=RENDER_TIMEOUT_SECONDS,
    )
    config = GenerationConfig()
    api_key = os.environ.get("NEBIUS_API_KEY", "")
    model = (
        NebiusTokenFactoryClient(api_key=api_key, config=config)
        if api_key
        else UnavailableModelClient(config, "Nebius API key is not configured")
    )
    generated = GeneratedLessonPipeline(
        artifact_root=ARTIFACT_ROOT,
        prompt=GENERATED_DEMO_PROMPT,
        generator=model,
        renderer=renderer,
    )
    dispatcher = DispatchingRenderer(
        {
            "pythagorean-theorem": renderer,
            "generated-demo": generated,
        }
    )
    return create_app(
        LessonService(renderer=dispatcher, max_pending_jobs=MAX_PENDING_JOBS),
        model_health=model.health,
        close_model=model.close,
    )


app = build_app()
