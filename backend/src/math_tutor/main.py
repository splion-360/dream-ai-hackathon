from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from math_tutor.api import create_app
from math_tutor.domain import Difficulty
from math_tutor.elevenlabs import ElevenLabsNarrationProvider
from math_tutor.generated_lesson import GeneratedLessonPipeline
from math_tutor.generation import (
    GenerationConfig,
    ModalVllmClient,
    NebiusTokenFactoryClient,
    UnavailableModelClient,
)
from math_tutor.jobs import DispatchingRenderer, JobRenderer, LessonService, PromptRenderer
from math_tutor.lesson_narration import NarratingRenderer, PromptNarratingRenderer
from math_tutor.media import MediaAssembler, probe_audio_duration
from math_tutor.narration import NarrationPlan, NarrationSegment
from math_tutor.renderer import DEFAULT_MANIM_IMAGE, DockerManimRenderer
from math_tutor.settings import Settings, get_settings

GENERATED_DEMO_PROMPT = """Create a concise visual lesson explaining why the Taylor
series of e^x equals the function. Show the polynomial approximations building from
orders zero through five, label the equation, and keep all objects inside the frame."""


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


def generated_narration_plan(prompt: str) -> NarrationPlan:
    return NarrationPlan(
        lesson_id="generated-lesson",
        segments=(
            NarrationSegment(
                id="lesson",
                text=f"In this lesson, we explore this question: {prompt}",
                cue="lesson-visible",
            ),
        ),
    )


def build_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    package_root = Path(__file__).parent
    base_renderer = DockerManimRenderer(
        artifact_root=resolved.artifact_root,
        scene_path=package_root / "scenes" / "pythagorean_theorem.py",
        image=DEFAULT_MANIM_IMAGE,
        timeout_seconds=resolved.render_timeout_seconds,
    )

    elevenlabs_api_key = (
        resolved.elevenlabs_api_key.get_secret_value()
        if resolved.elevenlabs_api_key is not None
        else ""
    )
    pythagorean_renderer: JobRenderer = base_renderer
    narration_provider: ElevenLabsNarrationProvider | None = None
    media_assembler: MediaAssembler | None = None
    if elevenlabs_api_key:
        narration_provider = ElevenLabsNarrationProvider(
            api_key=elevenlabs_api_key,
            voice_id=resolved.elevenlabs_voice_id,
            duration_probe=probe_audio_duration,
        )
        media_assembler = MediaAssembler()
        pythagorean_renderer = NarratingRenderer(
            renderer=base_renderer,
            provider=narration_provider,
            assembler=media_assembler,
            plan_factory=pythagorean_narration_plan,
            artifact_root=resolved.artifact_root,
        )

    generation_config = GenerationConfig(model=resolved.nebius_model)
    nebius_api_key = (
        resolved.nebius_api_key.get_secret_value()
        if resolved.nebius_api_key is not None
        else ""
    )
    model = (
        NebiusTokenFactoryClient(
            api_key=nebius_api_key,
            config=generation_config,
            base_url=resolved.nebius_base_url,
        )
        if nebius_api_key
        else UnavailableModelClient(generation_config, "Nebius API key is not configured")
    )
    generated_renderer = GeneratedLessonPipeline(
        artifact_root=resolved.artifact_root,
        prompt=GENERATED_DEMO_PROMPT,
        generator=model,
        renderer=base_renderer,
    )
    generated_fallback: PromptRenderer = generated_renderer
    if narration_provider is not None and media_assembler is not None:
        generated_fallback = PromptNarratingRenderer(
            renderer=generated_renderer,
            provider=narration_provider,
            assembler=media_assembler,
            plan_factory=generated_narration_plan,
            artifact_root=resolved.artifact_root,
        )
    routed_renderers = {}
    modal_clients: dict[Difficulty, ModalVllmClient] = {}
    if resolved.modal_vllm_base_url:
        modal_api_key = (
            resolved.modal_vllm_api_key.get_secret_value()
            if resolved.modal_vllm_api_key is not None
            else ""
        )
        for difficulty in Difficulty:
            modal_client = ModalVllmClient(
                api_key=modal_api_key,
                config=GenerationConfig(model=difficulty.value),
                base_url=resolved.modal_vllm_base_url,
                timeout_seconds=resolved.modal_vllm_timeout_seconds,
            )
            modal_clients[difficulty] = modal_client
            routed_renderers[difficulty] = GeneratedLessonPipeline(
                artifact_root=resolved.artifact_root,
                prompt=GENERATED_DEMO_PROMPT,
                generator=modal_client,
                renderer=base_renderer,
            )
    dispatcher = DispatchingRenderer(
        {
            "pythagorean-theorem": pythagorean_renderer,
            "generated-demo": generated_renderer,
        },
        fallback=generated_fallback,
    )
    def close_models() -> None:
        model.close()
        for modal_client in modal_clients.values():
            modal_client.close()

    model_health = (
        modal_clients[Difficulty.FOUNDATIONAL].health if modal_clients else model.health
    )
    return create_app(
        LessonService(
            renderer=dispatcher,
            max_pending_jobs=resolved.max_pending_jobs,
            narration_requested=lambda lesson: bool(elevenlabs_api_key)
            and lesson != "generated-demo",
            routed_renderers=routed_renderers,
        ),
        model_health=model_health,
        close_model=close_models,
    )


app = build_app()
