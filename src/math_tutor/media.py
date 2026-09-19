from __future__ import annotations

import json
import math
import subprocess
from collections.abc import Callable
from pathlib import Path

from math_tutor.narration import MediaBundle, NarrationStatus, SynthesizedNarration

CommandRunner = Callable[[list[str], float], subprocess.CompletedProcess[str]]


class MediaAssemblyError(RuntimeError):
    """A sanitized media-stage failure safe for job diagnostics."""


def run_command(command: list[str], timeout_seconds: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )


def probe_audio_duration(
    audio_path: Path,
    *,
    command_runner: CommandRunner = run_command,
    timeout_seconds: float = 10.0,
) -> float:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
    ]
    try:
        result = command_runner(command, timeout_seconds)
        duration = float(result.stdout.strip())
    except (OSError, subprocess.SubprocessError, ValueError):
        raise MediaAssemblyError("could not measure synthesized audio duration") from None
    if result.returncode != 0 or not math.isfinite(duration) or duration <= 0:
        raise MediaAssemblyError("could not measure synthesized audio duration")
    return duration


class MediaAssembler:
    def __init__(
        self,
        *,
        command_runner: CommandRunner = run_command,
        timeout_seconds: float = 60.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._run_command = command_runner
        self._timeout_seconds = timeout_seconds

    def assemble(
        self,
        *,
        silent_video: Path,
        narration: SynthesizedNarration,
        output_dir: Path,
    ) -> MediaBundle:
        if not silent_video.is_file():
            raise MediaAssemblyError("silent video is unavailable")
        output_dir.mkdir(parents=True, exist_ok=True)
        timeline_path = output_dir / "audio-timeline.json"
        captions_path = output_dir / "captions.vtt"
        concatenated_audio = output_dir / "narration.mp3"
        narrated_video = output_dir / "narrated.mp4"

        timeline_path.write_text(
            json.dumps(_timeline_payload(narration), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        captions_path.write_text(_webvtt(narration), encoding="utf-8")

        concat_command = ["ffmpeg", "-y"]
        for segment in narration.segments:
            concat_command.extend(("-i", str(segment.audio_path)))
        concat_command.extend(
            (
                "-filter_complex",
                f"concat=n={len(narration.segments)}:v=0:a=1",
                "-c:a",
                "libmp3lame",
                str(concatenated_audio),
            )
        )
        self._execute(concat_command, "audio concatenation failed")

        mux_command = [
            "ffmpeg",
            "-y",
            "-i",
            str(silent_video),
            "-i",
            str(concatenated_audio),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            str(narrated_video),
        ]
        self._execute(mux_command, "video muxing failed")

        return MediaBundle(
            silent_video_path=silent_video,
            video_path=narrated_video,
            narration_status=NarrationStatus.READY,
            captions_path=captions_path,
            timeline_path=timeline_path,
            diagnostics={
                "narration_provider": narration.provider,
                "narration_model": narration.model_id,
                "narration_segments": len(narration.segments),
                "narration_duration_seconds": sum(
                    segment.duration_seconds for segment in narration.segments
                ),
            },
        )

    def _execute(self, command: list[str], message: str) -> None:
        try:
            result = self._run_command(command, self._timeout_seconds)
        except (OSError, subprocess.SubprocessError):
            raise MediaAssemblyError(message) from None
        if result.returncode != 0:
            raise MediaAssemblyError(message)
        output_path = Path(command[-1])
        if not output_path.is_file():
            raise MediaAssemblyError(message)


def _timeline_payload(narration: SynthesizedNarration) -> dict[str, object]:
    return {
        "schema_version": narration.schema_version,
        "lesson_id": narration.lesson_id,
        "provider": narration.provider,
        "model_id": narration.model_id,
        "segments": [
            {
                "id": segment.id,
                "cue": segment.cue,
                "text": segment.text,
                "audio_file": f"audio/{segment.audio_path.name}",
                "duration_seconds": segment.duration_seconds,
                "sha256": segment.sha256,
            }
            for segment in narration.segments
        ],
        "total_duration_seconds": sum(
            segment.duration_seconds for segment in narration.segments
        ),
    }


def _webvtt(narration: SynthesizedNarration) -> str:
    lines = ["WEBVTT", ""]
    start = 0.0
    for segment in narration.segments:
        end = start + segment.duration_seconds
        lines.extend(
            (
                f"{_timestamp(start)} --> {_timestamp(end)}",
                segment.text,
                "",
            )
        )
        start = end
    return "\n".join(lines).rstrip() + "\n"


def _timestamp(seconds: float) -> str:
    total_milliseconds = round(seconds * 1000)
    hours, remainder = divmod(total_milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}.{milliseconds:03d}"
