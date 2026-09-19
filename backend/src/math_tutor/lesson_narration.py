from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Protocol

from math_tutor.jobs import JobRenderer, PartialOutcome, PromptRenderer, RenderOutcome
from math_tutor.narration import (
    MediaBundle,
    NarrationPlan,
    NarrationProvider,
    NarrationStatus,
    SynthesizedNarration,
)


class MediaAssembler(Protocol):
    def assemble(
        self,
        *,
        silent_video: Path,
        narration: SynthesizedNarration,
        output_dir: Path,
    ) -> MediaBundle: ...


class NarratingRenderer:
    def __init__(
        self,
        *,
        renderer: JobRenderer,
        provider: NarrationProvider,
        assembler: MediaAssembler,
        plan_factory: Callable[[], NarrationPlan],
        artifact_root: Path,
    ) -> None:
        self._renderer = renderer
        self._provider = provider
        self._assembler = assembler
        self._plan_factory = plan_factory
        self._artifact_root = artifact_root

    def render(self, job_id: str) -> RenderOutcome | PartialOutcome:
        outcome = self._renderer.render(job_id)
        if isinstance(outcome, PartialOutcome):
            return outcome
        return _attach_narration(
            job_id=job_id,
            outcome=outcome,
            plan=self._plan_factory(),
            provider=self._provider,
            assembler=self._assembler,
            artifact_root=self._artifact_root,
        )


class PromptNarratingRenderer:
    def __init__(
        self,
        *,
        renderer: PromptRenderer,
        provider: NarrationProvider,
        assembler: MediaAssembler,
        plan_factory: Callable[[str], NarrationPlan],
        artifact_root: Path,
    ) -> None:
        self._renderer = renderer
        self._provider = provider
        self._assembler = assembler
        self._plan_factory = plan_factory
        self._artifact_root = artifact_root

    def render(self, job_id: str, prompt: str) -> RenderOutcome | PartialOutcome:
        outcome = self._renderer.render(job_id, prompt)
        if isinstance(outcome, PartialOutcome):
            return outcome
        return _attach_narration(
            job_id=job_id,
            outcome=outcome,
            plan=self._plan_factory(prompt),
            provider=self._provider,
            assembler=self._assembler,
            artifact_root=self._artifact_root,
        )


def _attach_narration(
    *,
    job_id: str,
    outcome: RenderOutcome,
    plan: NarrationPlan,
    provider: NarrationProvider,
    assembler: MediaAssembler,
    artifact_root: Path,
) -> RenderOutcome:
    try:
        job_dir = artifact_root / job_id
        narration = provider.synthesize(plan, job_dir / "audio")
        bundle = assembler.assemble(
            silent_video=outcome.video_path,
            narration=narration,
            output_dir=job_dir / "narration",
        )
    except Exception as error:
        return replace(
            outcome,
            silent_video_path=outcome.video_path,
            narration_status=NarrationStatus.UNAVAILABLE,
            narration_diagnostics={
                "narration_error": type(error).__name__,
                "narration_error_cause": (
                    type(error.__cause__).__name__ if error.__cause__ is not None else None
                ),
            },
        )
    return replace(
        outcome,
        video_path=bundle.video_path,
        silent_video_path=bundle.silent_video_path,
        captions_path=bundle.captions_path,
        narration_status=bundle.narration_status,
        narration_diagnostics=bundle.diagnostics,
    )
