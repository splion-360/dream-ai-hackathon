from __future__ import annotations

import ast
import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from time import monotonic
from typing import Literal, Protocol

from math_tutor.domain import LessonStage
from math_tutor.generation import GenerationConfig, GenerationResult, ProviderError
from math_tutor.jobs import JobExecutionError, RenderOutcome, is_safe_job_id
from math_tutor.narration import NarrationStatus
from math_tutor.renderer import RenderError

_PYTHON_FENCE = re.compile(r"```(?:python|py)\s*\n(.*?)```", re.IGNORECASE | re.DOTALL)
_ALLOWED_IMPORTS = frozenset({"manim", "math", "numpy"})
_VOICEOVER_IMPORTS = {
    "manim_voiceover": frozenset({"VoiceoverScene"}),
    "manim_voiceover.services.elevenlabs": frozenset({"ElevenLabsService"}),
}
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


class PromptLessonRenderer(Protocol):
    def render(self, job_id: str, prompt: str | None = None) -> RenderOutcome: ...


InferencePath = Literal["base_model", "lora_adapter"]


class VoiceoverFallbackRenderer:
    def __init__(
        self,
        *,
        primary: PromptLessonRenderer,
        fallback: PromptLessonRenderer,
    ) -> None:
        self._primary = primary
        self._fallback = fallback

    def render(self, job_id: str, prompt: str | None = None) -> RenderOutcome:
        try:
            outcome = self._primary.render(job_id, prompt)
        except RenderError as error:
            fallback = self._fallback.render(f"{job_id}-silent", prompt)
            return replace(
                fallback,
                narration_status=NarrationStatus.UNAVAILABLE,
                narration_diagnostics={"voiceover_error": str(error)},
            )
        return replace(outcome, narration_status=NarrationStatus.READY)


class GenerationFallbackRenderer:
    def __init__(
        self,
        *,
        primary: PromptLessonRenderer,
        fallback: PromptLessonRenderer,
    ) -> None:
        self._primary = primary
        self._fallback = fallback

    def render(self, job_id: str, prompt: str | None = None) -> RenderOutcome:
        try:
            return self._primary.render(job_id, prompt)
        except (GeneratedLessonError, RenderError) as error:
            outcome = self._fallback.render(f"{job_id}-base", prompt)
            return replace(
                outcome,
                narration_diagnostics={
                    **dict(outcome.narration_diagnostics or {}),
                    "routing_fallback": "base_model",
                    "specialist_error": str(error),
                },
            )


def extract_and_validate_scene(
    response: str,
    *,
    voiceover: bool = False,
) -> ExtractedScene:
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
    expected_base = "VoiceoverScene" if voiceover else "Scene"
    if len(classes) != 1 or not (
        len(generated[0].bases) == 1
        and isinstance(generated[0].bases[0], ast.Name)
        and generated[0].bases[0].id == expected_base
    ):
        raise SceneValidationError(
            f"GeneratedLesson must be the only class and inherit directly from {expected_base}",
            diagnostics={"failure_stage": "validation"},
        )

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.partition(".")[0]
                if root not in _ALLOWED_IMPORTS:
                    raise _unsafe_import(root)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            root = module.partition(".")[0]
            permitted = node.level == 0 and root in _ALLOWED_IMPORTS
            if voiceover and module in _VOICEOVER_IMPORTS:
                permitted = node.level == 0 and all(
                    alias.name in _VOICEOVER_IMPORTS[module]
                    and alias.name != "*"
                    and alias.asname is None
                    for alias in node.names
                )
            if not permitted:
                raise _unsafe_import(module or root)
        elif isinstance(node, (ast.Name, ast.Attribute)):
            identifier = node.id if isinstance(node, ast.Name) else node.attr
            if _is_dunder_identifier(identifier):
                raise SceneValidationError(
                    "dunder identifiers are not allowed in generated scenes",
                    diagnostics={"failure_stage": "validation"},
                )
            if isinstance(node, ast.Name) and identifier in _FORBIDDEN_CALLS:
                raise SceneValidationError(
                    f"reference '{identifier}' is not allowed in generated scenes",
                    diagnostics={"failure_stage": "validation"},
                )
        elif isinstance(node, ast.Call):
            forbidden_call = _forbidden_call_name(node.func)
            if forbidden_call is not None:
                raise SceneValidationError(
                    f"call '{forbidden_call}' is not allowed in generated scenes",
                    diagnostics={"failure_stage": "validation"},
                )

    if voiceover:
        _validate_voiceover_contract(tree)

    return ExtractedScene(source=source, scene_class="GeneratedLesson")


def _validate_voiceover_contract(tree: ast.Module) -> None:
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    service_calls = [
        node
        for node in calls
        if isinstance(node.func, ast.Attribute) and node.func.attr == "set_speech_service"
    ]
    if len(service_calls) != 1:
        raise SceneValidationError(
            "generated voiceover scene must configure speech service exactly once",
            diagnostics={"failure_stage": "validation"},
        )
    service_argument = service_calls[0].args[0] if service_calls[0].args else None
    disables_transcription = (
        isinstance(service_argument, ast.Call)
        and isinstance(service_argument.func, ast.Name)
        and service_argument.func.id == "ElevenLabsService"
        and any(
            keyword.arg == "transcription_model"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value is None
            for keyword in service_argument.keywords
        )
    )
    if not disables_transcription:
        raise SceneValidationError(
            "ElevenLabsService must set transcription_model=None",
            diagnostics={"failure_stage": "validation"},
        )
    uses_supported_model = isinstance(service_argument, ast.Call) and any(
        keyword.arg == "model"
        and isinstance(keyword.value, ast.Constant)
        and keyword.value.value == "eleven_multilingual_v2"
        for keyword in service_argument.keywords
    )
    if not uses_supported_model:
        raise SceneValidationError(
            "ElevenLabsService must use model eleven_multilingual_v2",
            diagnostics={"failure_stage": "validation"},
        )
    voiceover_calls = [
        node
        for node in calls
        if isinstance(node.func, ast.Attribute) and node.func.attr == "voiceover"
    ]
    if not 3 <= len(voiceover_calls) <= 6:
        raise SceneValidationError(
            "generated voiceover scene must contain 3 to 6 voiceover blocks",
            diagnostics={"failure_stage": "validation"},
        )
    uses_tracker_duration = any(
        isinstance(node, ast.Attribute)
        and node.attr == "duration"
        and isinstance(node.value, ast.Name)
        and node.value.id == "tracker"
        for node in ast.walk(tree)
    )
    if not uses_tracker_duration:
        raise SceneValidationError(
            "generated voiceover scene must pace animation with tracker.duration",
            diagnostics={"failure_stage": "validation"},
        )


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
        voiceover: bool = False,
        inference_path: InferencePath = "base_model",
        stage_reporter: Callable[[str, LessonStage], None] | None = None,
    ) -> None:
        self._artifact_root = artifact_root.resolve()
        self._prompt = prompt
        self._generator = generator
        self._renderer = renderer
        self._voiceover = voiceover
        self._inference_path = inference_path
        self._stage_reporter = stage_reporter

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
        self._report_stage(job_id, LessonStage.GENERATING_CODE)
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
        self._report_stage(job_id, LessonStage.VALIDATING_CODE)
        try:
            extracted = extract_and_validate_scene(
                result.content,
                voiceover=self._voiceover,
            )
        except GeneratedLessonError as error:
            metadata["status"] = f"{error.diagnostics.get('failure_stage', 'validation')}_failed"
            self._write_metadata(job_dir, metadata)
            raise
        (job_dir / "extracted_scene.py").write_text(extracted.source, encoding="utf-8")
        self._report_stage(job_id, LessonStage.RENDERING)
        outcome = self._renderer.render_source(
            job_id,
            extracted.source,
            extracted.scene_class,
        )
        return replace(
            outcome,
            narration_status=(
                NarrationStatus.READY if self._voiceover else outcome.narration_status
            ),
            narration_diagnostics={
                **dict(outcome.narration_diagnostics or {}),
                "inference_path": self._inference_path,
                "inference_model": result.model,
            },
        )

    def _report_stage(self, job_id: str, stage: LessonStage) -> None:
        if self._stage_reporter is not None:
            self._stage_reporter(job_id, stage)

    @staticmethod
    def _write_metadata(job_dir: Path, metadata: dict[str, object]) -> None:
        (job_dir / "generation.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True),
            encoding="utf-8",
        )
