from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from math_tutor.generation import GenerationConfig, GenerationResult, ModelHealth
from math_tutor.renderer import VOICEOVER_MANIM_IMAGE
from math_tutor.settings import Settings


def test_build_app_uses_injected_settings_for_nebius(
    tmp_path: Path,
    monkeypatch,
) -> None:
    observed: dict[str, object] = {}

    class RecordingModelClient:
        def __init__(
            self,
            *,
            api_key: str,
            config: GenerationConfig,
            base_url: str,
        ) -> None:
            observed.update(api_key=api_key, model=config.model, base_url=base_url)
            self.config = config

        def generate(self, prompt: str) -> GenerationResult:
            raise AssertionError("generation is not part of this test")

        def health(self) -> ModelHealth:
            return ModelHealth(True, self.config.model, True)

        def close(self) -> None:
            observed["closed"] = True

    import math_tutor.main as main

    monkeypatch.setattr(main, "NebiusTokenFactoryClient", RecordingModelClient)
    settings = Settings(
        _env_file=None,
        nebius_api_key="injected-secret",
        nebius_base_url="https://nebius.example/v1",
        artifact_root=tmp_path / "artifacts",
    )

    with TestClient(main.build_app(settings)) as client:
        response = client.get("/model/health")

    assert response.json()["model_available"] is True
    assert observed == {
        "api_key": "injected-secret",
        "model": "Qwen/Qwen3-30B-A3B-Instruct-2507",
        "base_url": "https://nebius.example/v1",
        "closed": True,
    }


def test_build_app_without_secret_keeps_provider_unavailable(tmp_path: Path) -> None:
    import math_tutor.main as main

    settings = Settings(
        _env_file=None,
        nebius_api_key=None,
        artifact_root=tmp_path / "artifacts",
    )

    with TestClient(main.build_app(settings)) as client:
        response = client.get("/model/health")

    assert response.json() == {
        "reachable": False,
        "model": "Qwen/Qwen3-30B-A3B-Instruct-2507",
        "model_available": False,
        "error": "Nebius API key is not configured",
    }


def test_build_app_configures_voiceover_generation_when_elevenlabs_is_available(
    tmp_path: Path,
    monkeypatch,
) -> None:
    observed_clients: list[GenerationConfig] = []
    observed_renderers: list[dict[str, object]] = []

    class RecordingModelClient:
        def __init__(self, *, api_key: str, config: GenerationConfig, base_url: str) -> None:
            observed_clients.append(config)
            self.config = config

        def generate(self, prompt: str) -> GenerationResult:
            raise AssertionError("generation is not part of this test")

        def health(self) -> ModelHealth:
            return ModelHealth(True, self.config.model, True)

        def close(self) -> None:
            return None

    class RecordingDockerRenderer:
        def __init__(self, **kwargs: object) -> None:
            observed_renderers.append(kwargs)

        def render(self, job_id: str):
            raise AssertionError("rendering is not part of this test")

        def render_source(self, job_id: str, source: str, scene_class: str):
            raise AssertionError("rendering is not part of this test")

    import math_tutor.main as main

    monkeypatch.setattr(main, "NebiusTokenFactoryClient", RecordingModelClient)
    monkeypatch.setattr(main, "DockerManimRenderer", RecordingDockerRenderer)
    settings = Settings(
        _env_file=None,
        nebius_api_key="nebius-secret",
        elevenlabs_api_key="eleven-secret",
        elevenlabs_voice_id="voice-123",
        artifact_root=tmp_path / "artifacts",
    )

    with TestClient(main.build_app(settings)) as client:
        assert client.get("/model/health").status_code == 200

    assert len(observed_clients) == 2
    voiceover_config = next(
        config for config in observed_clients if "VoiceoverScene" in config.system_prompt
    )
    silent_config = next(
        config for config in observed_clients if "VoiceoverScene" not in config.system_prompt
    )
    assert 'voice_id="voice-123"' in voiceover_config.system_prompt
    assert silent_config.model == voiceover_config.model
    voiceover_renderer = next(
        item for item in observed_renderers if item.get("image") == VOICEOVER_MANIM_IMAGE
    )
    assert voiceover_renderer["network"] == "bridge"
    assert voiceover_renderer["environment"] == {"ELEVEN_API_KEY": "eleven-secret"}
    assert voiceover_renderer["require_audio"] is True
