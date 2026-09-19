from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from math_tutor.api import create_app
from math_tutor.domain import Difficulty
from math_tutor.elevenlabs import ElevenLabsNarrationProvider
from math_tutor.generated_lesson import (
    GeneratedLessonPipeline,
    PromptLessonRenderer,
    VoiceoverFallbackRenderer,
)
from math_tutor.generation import (
    VOICEOVER_SYSTEM_PROMPT,
    GenerationConfig,
    ModalVllmClient,
    NebiusTokenFactoryClient,
    UnavailableModelClient,
)
from math_tutor.jobs import DispatchingRenderer, JobRenderer, LessonService
from math_tutor.lesson_narration import NarratingRenderer
from math_tutor.media import MediaAssembler, probe_audio_duration
from math_tutor.narration import NarrationPlan, NarrationSegment
from math_tutor.renderer import (
    DEFAULT_MANIM_IMAGE,
    VOICEOVER_MANIM_IMAGE,
    DockerManimRenderer,
)
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
        resolved.nebius_api_key.get_secret_value() if resolved.nebius_api_key is not None else ""
    )
    silent_model = (
        NebiusTokenFactoryClient(
            api_key=nebius_api_key,
            config=generation_config,
            base_url=resolved.nebius_base_url,
        )
        if nebius_api_key
        else UnavailableModelClient(generation_config, "Nebius API key is not configured")
    )
    silent_generated_renderer = GeneratedLessonPipeline(
        artifact_root=resolved.artifact_root,
        prompt=GENERATED_DEMO_PROMPT,
        generator=silent_model,
        renderer=base_renderer,
    )
    generated_renderer: PromptLessonRenderer = silent_generated_renderer
    health_model = silent_model
    models_to_close = [silent_model]
    voiceover_renderer: DockerManimRenderer | None = None
    if elevenlabs_api_key:
        voiceover_config = GenerationConfig(
            model=resolved.nebius_model,
            system_prompt=VOICEOVER_SYSTEM_PROMPT.replace(
                "__VOICE_ID__",
                resolved.elevenlabs_voice_id,
            ),
        )
        voiceover_model = (
            NebiusTokenFactoryClient(
                api_key=nebius_api_key,
                config=voiceover_config,
                base_url=resolved.nebius_base_url,
            )
            if nebius_api_key
            else UnavailableModelClient(
                voiceover_config,
                "Nebius API key is not configured",
            )
        )
        models_to_close.append(voiceover_model)
        health_model = voiceover_model
        voiceover_renderer = DockerManimRenderer(
            artifact_root=resolved.artifact_root,
            scene_path=package_root / "scenes" / "pythagorean_theorem.py",
            image=VOICEOVER_MANIM_IMAGE,
            timeout_seconds=resolved.render_timeout_seconds,
            network="bridge",
            environment={"ELEVEN_API_KEY": elevenlabs_api_key},
            require_audio=True,
        )
        voiceover_generated_renderer = GeneratedLessonPipeline(
            artifact_root=resolved.artifact_root,
            prompt=GENERATED_DEMO_PROMPT,
            generator=voiceover_model,
            renderer=voiceover_renderer,
            voiceover=True,
        )
        generated_renderer = VoiceoverFallbackRenderer(
            primary=voiceover_generated_renderer,
            fallback=silent_generated_renderer,
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
            modal_config = GenerationConfig(
                model=difficulty.value,
                system_prompt=(
                    VOICEOVER_SYSTEM_PROMPT.replace(
                        "__VOICE_ID__",
                        resolved.elevenlabs_voice_id,
                    )
                    if elevenlabs_api_key
                    else generation_config.system_prompt
                ),
            )
            modal_client = ModalVllmClient(
                api_key=modal_api_key,
                config=modal_config,
                base_url=resolved.modal_vllm_base_url,
                timeout_seconds=resolved.modal_vllm_timeout_seconds,
            )
            modal_clients[difficulty] = modal_client
            modal_renderer = base_renderer
            if elevenlabs_api_key:
                assert voiceover_renderer is not None
                modal_renderer = voiceover_renderer
            modal_pipeline = GeneratedLessonPipeline(
                artifact_root=resolved.artifact_root,
                prompt=GENERATED_DEMO_PROMPT,
                generator=modal_client,
                renderer=modal_renderer,
                voiceover=bool(elevenlabs_api_key),
            )
            routed_renderers[difficulty] = (
                VoiceoverFallbackRenderer(
                    primary=modal_pipeline,
                    fallback=silent_generated_renderer,
                )
                if elevenlabs_api_key
                else modal_pipeline
            )
    dispatcher = DispatchingRenderer(
        {
            "pythagorean-theorem": pythagorean_renderer,
            "generated-demo": generated_renderer,
        },
        fallback=generated_renderer,
    )
    def close_models() -> None:
        for configured_model in models_to_close:
            configured_model.close()
        for modal_client in modal_clients.values():
            modal_client.close()

    model_health = (
        modal_clients[Difficulty.FOUNDATIONAL].health
        if modal_clients
        else health_model.health
    )
    return create_app(
        LessonService(
            renderer=dispatcher,
            max_pending_jobs=resolved.max_pending_jobs,
            routed_renderers=routed_renderers,
            narration_requested=bool(elevenlabs_api_key),
        ),
        model_health=model_health,
        close_model=close_models,
    )


app = build_app()
