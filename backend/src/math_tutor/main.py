from __future__ import annotations

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
from math_tutor.settings import Settings, get_settings

GENERATED_DEMO_PROMPT = """Create a concise visual lesson explaining why the Taylor
series of e^x equals the function. Show the polynomial approximations building from
orders zero through five, label the equation, and keep all objects inside the frame."""


def build_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    package_root = Path(__file__).parent
    renderer = DockerManimRenderer(
        artifact_root=resolved.artifact_root,
        scene_path=package_root / "scenes" / "pythagorean_theorem.py",
        image=DEFAULT_MANIM_IMAGE,
        timeout_seconds=resolved.render_timeout_seconds,
    )
    config = GenerationConfig()
    api_key = (
        resolved.nebius_api_key.get_secret_value() if resolved.nebius_api_key is not None else ""
    )
    model = (
        NebiusTokenFactoryClient(
            api_key=api_key,
            config=config,
            base_url=resolved.nebius_base_url,
        )
        if api_key
        else UnavailableModelClient(config, "Nebius API key is not configured")
    )
    generated = GeneratedLessonPipeline(
        artifact_root=resolved.artifact_root,
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
        LessonService(renderer=dispatcher, max_pending_jobs=resolved.max_pending_jobs),
        model_health=model.health,
        close_model=model.close,
    )


app = build_app()
