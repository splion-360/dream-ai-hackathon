from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Any

import httpx

FROZEN_MODEL = "Qwen/Qwen3-4B"
SYSTEM_PROMPT = """You generate one self-contained Manim Community Python scene.
Return exactly one Python code fence and no prose.
The code must import only from manim, math, or numpy.
Define exactly one renderable class named GeneratedLesson that inherits from Scene.
Do not access files, the network, subprocesses, environment variables, or dynamic execution.
Keep the animation under 45 seconds and use only APIs available in Manim Community v0.19.
"""


class ProviderError(RuntimeError):
    """A credential-safe model provider failure."""


@dataclass(frozen=True)
class GenerationConfig:
    model: str = FROZEN_MODEL
    temperature: float = 0.0
    top_p: float = 1.0
    max_tokens: int = 4096
    seed: int = 42
    system_prompt: str = SYSTEM_PROMPT


@dataclass(frozen=True)
class TokenUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class GenerationResult:
    content: str
    model: str
    request_id: str
    finish_reason: str | None
    usage: TokenUsage
    elapsed_seconds: float
    provider_response: str


@dataclass(frozen=True)
class ModelHealth:
    reachable: bool
    model: str
    model_available: bool
    error: str | None = None


class NebiusTokenFactoryClient:
    def __init__(
        self,
        *,
        api_key: str,
        config: GenerationConfig,
        base_url: str,
        timeout_seconds: float = 60,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("Nebius API key is required")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.config = config
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout_seconds,
            transport=transport,
        )

    def generate(self, prompt: str) -> GenerationResult:
        started = monotonic()
        try:
            response = self._client.post(
                "/chat/completions",
                json={
                    "model": self.config.model,
                    "messages": [
                        {"role": "system", "content": self.config.system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": self.config.temperature,
                    "top_p": self.config.top_p,
                    "max_tokens": self.config.max_tokens,
                    "seed": self.config.seed,
                },
            )
        except httpx.HTTPError as error:
            raise ProviderError("Nebius generation request could not be completed") from error
        elapsed = monotonic() - started
        if response.status_code != 200:
            raise ProviderError(
                f"Nebius generation request failed with HTTP {response.status_code}"
            )
        try:
            payload: Any = response.json()
            choice = payload["choices"][0]
            content = choice["message"]["content"]
            usage = payload.get("usage", {})
            if not isinstance(content, str) or not content:
                raise TypeError
            return GenerationResult(
                content=content,
                model=str(payload.get("model") or self.config.model),
                request_id=str(payload.get("id") or ""),
                finish_reason=(
                    str(choice["finish_reason"])
                    if choice.get("finish_reason") is not None
                    else None
                ),
                usage=TokenUsage(
                    prompt_tokens=int(usage.get("prompt_tokens", 0)),
                    completion_tokens=int(usage.get("completion_tokens", 0)),
                    total_tokens=int(usage.get("total_tokens", 0)),
                ),
                elapsed_seconds=elapsed,
                provider_response=response.text,
            )
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise ProviderError("Nebius generation returned a malformed response") from error

    def health(self) -> ModelHealth:
        try:
            response = self._client.get("/models")
        except httpx.HTTPError:
            return ModelHealth(
                reachable=False,
                model=self.config.model,
                model_available=False,
                error="Nebius model catalog request could not be completed",
            )
        if response.status_code != 200:
            return ModelHealth(
                reachable=False,
                model=self.config.model,
                model_available=False,
                error=f"Nebius model catalog returned HTTP {response.status_code}",
            )
        try:
            payload: Any = response.json()
            model_ids = {
                str(item["id"])
                for item in payload["data"]
                if isinstance(item, dict) and "id" in item
            }
        except (KeyError, TypeError, ValueError):
            return ModelHealth(
                reachable=True,
                model=self.config.model,
                model_available=False,
                error="Nebius model catalog returned a malformed response",
            )
        return ModelHealth(
            reachable=True,
            model=self.config.model,
            model_available=self.config.model in model_ids,
        )

    def close(self) -> None:
        self._client.close()


class UnavailableModelClient:
    def __init__(self, config: GenerationConfig, reason: str) -> None:
        self.config = config
        self._reason = reason

    def generate(self, prompt: str) -> GenerationResult:
        raise ProviderError(self._reason)

    def health(self) -> ModelHealth:
        return ModelHealth(
            reachable=False,
            model=self.config.model,
            model_available=False,
            error=self._reason,
        )

    def close(self) -> None:
        return None
