from __future__ import annotations

import json
from pathlib import Path

import pytest

from math_tutor.generated_lesson import (
    ExtractionError,
    GeneratedLessonPipeline,
    SceneValidationError,
    extract_and_validate_scene,
)
from math_tutor.generation import (
    GenerationConfig,
    GenerationResult,
    ModelHealth,
    TokenUsage,
)
from math_tutor.jobs import RenderOutcome

VALID_SCENE = """from manim import *

class GeneratedLesson(Scene):
    def construct(self):
        self.play(Write(MathTex(r"x^2")))
"""


class FixedGenerator:
    def __init__(self, result: GenerationResult) -> None:
        self.config = GenerationConfig()
        self._result = result

    def generate(self, prompt: str) -> GenerationResult:
        return self._result

    def health(self) -> ModelHealth:
        return ModelHealth(True, self.config.model, True)


class RecordingSourceRenderer:
    def __init__(self, video_path: Path) -> None:
        self.video_path = video_path
        self.received: tuple[str, str, str] | None = None

    def render_source(self, job_id: str, source: str, scene_class: str) -> RenderOutcome:
        self.received = (job_id, source, scene_class)
        self.video_path.write_bytes(b"video")
        return RenderOutcome(
            video_path=self.video_path,
            renderer="docker:test-image@sha256:abc",
            elapsed_seconds=1.25,
            logs="rendered",
        )


def _generation(content: str) -> GenerationResult:
    return GenerationResult(
        content=content,
        model="Qwen/Qwen3-4B",
        request_id="chatcmpl-123",
        finish_reason="stop",
        usage=TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
        elapsed_seconds=0.5,
        provider_response=json.dumps({"id": "chatcmpl-123", "choices": []}),
    )


def test_extracts_one_python_fence_and_validates_generated_scene() -> None:
    extracted = extract_and_validate_scene(f"```python\n{VALID_SCENE}```")

    assert extracted.source == VALID_SCENE.rstrip()
    assert extracted.scene_class == "GeneratedLesson"


def test_rejects_ambiguous_multiple_code_fences() -> None:
    response = f"```python\n{VALID_SCENE}```\n```python\n{VALID_SCENE}```"

    with pytest.raises(ExtractionError, match="exactly one Python code fence"):
        extract_and_validate_scene(response)


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("import os\n" + VALID_SCENE, "import 'os' is not allowed"),
        (VALID_SCENE + "\nopen('/tmp/file', 'w')", "call 'open' is not allowed"),
        ("class GeneratedLesson(Scene)\n    pass", "not valid Python"),
        (
            "from manim import *\nclass WrongName(Scene):\n    pass",
            "class named GeneratedLesson",
        ),
    ],
)
def test_rejects_invalid_or_unsafe_generated_code(source: str, message: str) -> None:
    with pytest.raises(SceneValidationError, match=message):
        extract_and_validate_scene(f"```python\n{source}\n```")


def test_pipeline_persists_generation_evidence_before_isolated_render(tmp_path: Path) -> None:
    response = _generation(f"Here is the scene:\n```python\n{VALID_SCENE}```")
    source_renderer = RecordingSourceRenderer(tmp_path / "lesson.mp4")
    pipeline = GeneratedLessonPipeline(
        artifact_root=tmp_path / "artifacts",
        prompt="Explain the derivative of x squared visually.",
        generator=FixedGenerator(response),
        renderer=source_renderer,
    )

    outcome = pipeline.render("generated-123")

    assert outcome.video_path.read_bytes() == b"video"
    assert source_renderer.received == (
        "generated-123",
        VALID_SCENE.rstrip(),
        "GeneratedLesson",
    )
    job_dir = tmp_path / "artifacts" / "generated-123"
    assert (job_dir / "prompt.txt").read_text() == (
        "Explain the derivative of x squared visually."
    )
    assert (job_dir / "raw_response.txt").read_text() == response.content
    assert (job_dir / "provider_response.json").read_text() == response.provider_response
    assert (job_dir / "extracted_scene.py").read_text() == VALID_SCENE.rstrip()
    metadata = json.loads((job_dir / "generation.json").read_text())
    assert metadata == {
        "completion_tokens": 20,
        "elapsed_seconds": 0.5,
        "finish_reason": "stop",
        "model": "Qwen/Qwen3-4B",
        "prompt_tokens": 10,
        "request_id": "chatcmpl-123",
        "seed": 42,
        "status": "generated",
        "temperature": 0.0,
        "top_p": 1.0,
        "total_tokens": 30,
    }


def test_pipeline_preserves_raw_response_when_extraction_fails(tmp_path: Path) -> None:
    response = _generation("I cannot provide code.")
    pipeline = GeneratedLessonPipeline(
        artifact_root=tmp_path / "artifacts",
        prompt="Prompt",
        generator=FixedGenerator(response),
        renderer=RecordingSourceRenderer(tmp_path / "unused.mp4"),
    )

    with pytest.raises(ExtractionError):
        pipeline.render("failed-123")

    job_dir = tmp_path / "artifacts" / "failed-123"
    assert (job_dir / "raw_response.txt").read_text() == "I cannot provide code."
    metadata = json.loads((job_dir / "generation.json").read_text())
    assert metadata["status"] == "extraction_failed"
    assert metadata["model"] == "Qwen/Qwen3-4B"
