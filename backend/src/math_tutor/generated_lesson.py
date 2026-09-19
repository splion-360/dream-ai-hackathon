from __future__ import annotations

import ast
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from time import monotonic
from typing import Protocol

from math_tutor.generation import GenerationConfig, GenerationResult, ProviderError
from math_tutor.jobs import JobExecutionError, RenderOutcome, is_safe_job_id

_PYTHON_FENCE = re.compile(r"```(?:python|py)\s*\n(.*?)```", re.IGNORECASE | re.DOTALL)
_ALLOWED_IMPORTS = frozenset({"manim", "math", "numpy"})
_FORBIDDEN_CALLS = frozenset(
    {
        "open",
        "exec",
        "eval",
        "compile",
        "__import__",
        "input",
        "breakpoint",
        "getattr",
        "setattr",
        "globals",
        "locals",
        "vars",
    }
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
    except (SyntaxError, ValueError) as error:
        raise SceneValidationError(
            "generated scene is not valid Python",
            diagnostics={"failure_stage": "parse", "line": getattr(error, "lineno", None)},
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
        elif isinstance(node, (ast.Name, ast.Attribute)) and _is_dunder_identifier(
            node.id if isinstance(node, ast.Name) else node.attr
        ):
            raise SceneValidationError(
                "dunder identifiers are not allowed in generated scenes",
                diagnostics={"failure_stage": "validation"},
            )
        elif isinstance(node, ast.Call):
            forbidden_call = _forbidden_call_name(node.func)
            if forbidden_call is not None:
                raise SceneValidationError(
                    f"call '{forbidden_call}' is not allowed in generated scenes",
                    diagnostics={"failure_stage": "validation"},
                )

    return ExtractedScene(source=source, scene_class="GeneratedLesson")


def _unsafe_import(module: str) -> SceneValidationError:
    return SceneValidationError(
        f"import '{module}' is not allowed in generated scenes",
        diagnostics={"failure_stage": "validation"},
    )


def _is_dunder_identifier(value: str) -> bool:
    return value.startswith("__") and value.endswith("__")


def _forbidden_call_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id if node.id in _FORBIDDEN_CALLS else None
    if isinstance(node, ast.Attribute):
        return node.attr if node.attr in _FORBIDDEN_CALLS else None
    if isinstance(node, ast.Subscript):
        key = node.slice
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            return key.value if key.value in _FORBIDDEN_CALLS else None
    return None


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

    def render(self, job_id: str, prompt: str | None = None) -> RenderOutcome:
        if not is_safe_job_id(job_id):
            raise GeneratedLessonError(
                "job id is not safe for an artifact path",
                diagnostics={"failure_stage": "validation"},
            )
        job_dir = self._artifact_root / job_id
        job_dir.mkdir(parents=True, exist_ok=False)
        effective_prompt = prompt or self._prompt
        (job_dir / "prompt.txt").write_text(effective_prompt, encoding="utf-8")
        started = monotonic()
        try:
            result = self._generator.generate(effective_prompt)
        except ProviderError as error:
            self._write_metadata(
                job_dir,
                {
                    "status": "provider_failed",
                    "failure_stage": "provider",
                    "model": self._generator.config.model,
                    "elapsed_seconds": monotonic() - started,
                    "temperature": self._generator.config.temperature,
                    "top_p": self._generator.config.top_p,
                    "seed": self._generator.config.seed,
                },
            )
            raise GeneratedLessonError(
                str(error),
                diagnostics={"failure_stage": "provider"},
            ) from error
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
