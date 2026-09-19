from __future__ import annotations

import ast
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from math_tutor.generation import GenerationConfig, GenerationResult
from math_tutor.jobs import JobExecutionError, RenderOutcome

_PYTHON_FENCE = re.compile(r"```(?:python|py)\s*\n(.*?)```", re.IGNORECASE | re.DOTALL)
_ALLOWED_IMPORTS = frozenset({"manim", "math", "numpy"})
_FORBIDDEN_CALLS = frozenset(
    {"open", "exec", "eval", "compile", "__import__", "input", "breakpoint"}
)


class GeneratedLessonError(JobExecutionError):
    pass


class ExtractionError(GeneratedLessonError):
    pass


class SceneValidationError(GeneratedLessonError):
    pass


@dataclass(frozen=True)
class ExtractedScene:
    source: str
    scene_class: str


class Generator(Protocol):
    config: GenerationConfig

    def generate(self, prompt: str) -> GenerationResult: ...


class SourceRenderer(Protocol):
    def render_source(self, job_id: str, source: str, scene_class: str) -> RenderOutcome: ...


def extract_and_validate_scene(response: str) -> ExtractedScene:
    matches = _PYTHON_FENCE.findall(response)
    if len(matches) != 1:
        raise ExtractionError(
            "model response must contain exactly one Python code fence",
            diagnostics={"failure_stage": "extraction"},
        )
    source = matches[0].strip()
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        raise SceneValidationError(
            "generated scene is not valid Python",
            diagnostics={"failure_stage": "parse", "line": error.lineno},
        ) from error

    classes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
    generated = [node for node in classes if node.name == "GeneratedLesson"]
    if len(generated) != 1:
        raise SceneValidationError(
            "generated code must define exactly one class named GeneratedLesson",
            diagnostics={"failure_stage": "validation"},
        )
    if len(classes) != 1 or not any(
        isinstance(base, ast.Name) and base.id == "Scene" for base in generated[0].bases
    ):
        raise SceneValidationError(
            "GeneratedLesson must be the only class and inherit directly from Scene",
            diagnostics={"failure_stage": "validation"},
        )

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.partition(".")[0]
                if root not in _ALLOWED_IMPORTS:
                    raise _unsafe_import(root)
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").partition(".")[0]
            if root not in _ALLOWED_IMPORTS:
                raise _unsafe_import(root)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in _FORBIDDEN_CALLS
        ):
            raise SceneValidationError(
                f"call '{node.func.id}' is not allowed in generated scenes",
                diagnostics={"failure_stage": "validation"},
            )

    return ExtractedScene(source=source, scene_class="GeneratedLesson")


def _unsafe_import(module: str) -> SceneValidationError:
    return SceneValidationError(
        f"import '{module}' is not allowed in generated scenes",
        diagnostics={"failure_stage": "validation"},
    )


class GeneratedLessonPipeline:
    def __init__(
        self,
        *,
        artifact_root: Path,
        prompt: str,
        generator: Generator,
        renderer: SourceRenderer,
    ) -> None:
        self._artifact_root = artifact_root.resolve()
        self._prompt = prompt
        self._generator = generator
        self._renderer = renderer

    def render(self, job_id: str) -> RenderOutcome:
        job_dir = self._artifact_root / job_id
        job_dir.mkdir(parents=True, exist_ok=False)
        (job_dir / "prompt.txt").write_text(self._prompt, encoding="utf-8")
        result = self._generator.generate(self._prompt)
        (job_dir / "raw_response.txt").write_text(result.content, encoding="utf-8")
        (job_dir / "provider_response.json").write_text(
            result.provider_response,
            encoding="utf-8",
        )
        metadata: dict[str, object] = {
            "status": "generated",
            "model": result.model,
            "request_id": result.request_id,
            "finish_reason": result.finish_reason,
            "elapsed_seconds": result.elapsed_seconds,
            "temperature": self._generator.config.temperature,
            "top_p": self._generator.config.top_p,
            "seed": self._generator.config.seed,
            **asdict(result.usage),
        }
        self._write_metadata(job_dir, metadata)
        try:
            extracted = extract_and_validate_scene(result.content)
        except GeneratedLessonError as error:
            metadata["status"] = f"{error.diagnostics.get('failure_stage', 'validation')}_failed"
            self._write_metadata(job_dir, metadata)
            raise
        (job_dir / "extracted_scene.py").write_text(extracted.source, encoding="utf-8")
        return self._renderer.render_source(
            job_id,
            extracted.source,
            extracted.scene_class,
        )

    @staticmethod
    def _write_metadata(job_dir: Path, metadata: dict[str, object]) -> None:
        (job_dir / "generation.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True),
            encoding="utf-8",
        )
