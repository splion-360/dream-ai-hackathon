from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from math_tutor.generation import GenerationConfig, GenerationResult, ModelHealth
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
        "model": "Qwen/Qwen3-4B",
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
        "model": "Qwen/Qwen3-4B",
        "model_available": False,
        "error": "Nebius API key is not configured",
    }
