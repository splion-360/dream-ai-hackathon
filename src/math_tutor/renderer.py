from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Any

from math_tutor.jobs import RenderOutcome

CommandRunner = Callable[[list[str], float], subprocess.CompletedProcess[str]]
DEFAULT_MANIM_IMAGE = (
    "manimcommunity/manim@sha256:"
    "ab5ad56cf685d89da96e5d459e0cde3743fbdf2141be4dcff6c26566b5ca3191"
)
_SAFE_JOB_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_LOG_LIMIT = 32_000


class RenderError(RuntimeError):
    pass


class RenderTimedOut(RenderError):
    pass


class RenderFailed(RenderError):
    pass


def run_command(command: list[str], timeout_seconds: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )


class DockerManimRenderer:
    def __init__(
        self,
        artifact_root: Path,
        scene_path: Path,
        image: str = DEFAULT_MANIM_IMAGE,
        timeout_seconds: float = 90,
        command_runner: CommandRunner = run_command,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._artifact_root = artifact_root.resolve()
        self._scene_path = scene_path.resolve()
        self._image = image
        self._timeout_seconds = timeout_seconds
        self._run_command = command_runner

    def render(self, job_id: str) -> RenderOutcome:
        if not _SAFE_JOB_ID.fullmatch(job_id):
            raise RenderFailed("job id is not safe for an artifact path or container name")
        if not self._scene_path.is_file():
            raise RenderFailed(f"known scene is missing: {self._scene_path}")

        job_dir = self._artifact_root / job_id
        job_dir.mkdir(parents=True, exist_ok=False)
        container_name = f"math-tutor-render-{job_id}"
        command = self._render_command(job_dir, container_name)
        started_at = datetime.now(UTC)
        started = monotonic()

        try:
            result = self._run_command(command, self._timeout_seconds)
        except subprocess.TimeoutExpired as error:
            elapsed = monotonic() - started
            self._force_remove(container_name)
            stdout = _as_text(error.output)
            stderr = _as_text(error.stderr)
            self._write_metadata(
                job_dir,
                status="timed_out",
                command=command,
                started_at=started_at,
                elapsed_seconds=elapsed,
                exit_code=None,
                stdout=stdout,
                stderr=stderr,
            )
            raise RenderTimedOut(
                f"Manim render exceeded {self._timeout_seconds} seconds"
            ) from error

        elapsed = monotonic() - started
        stdout = _trim(result.stdout)
        stderr = _trim(result.stderr)
        if result.returncode != 0:
            self._write_metadata(
                job_dir,
                status="failed",
                command=command,
                started_at=started_at,
                elapsed_seconds=elapsed,
                exit_code=result.returncode,
                stdout=stdout,
                stderr=stderr,
            )
            detail = stderr or stdout or "no renderer output"
            raise RenderFailed(f"Manim exited with code {result.returncode}: {detail}")

        videos = list((job_dir / "media").rglob("PythagoreanTheorem.mp4"))
        if len(videos) != 1:
            self._write_metadata(
                job_dir,
                status="failed",
                command=command,
                started_at=started_at,
                elapsed_seconds=elapsed,
                exit_code=result.returncode,
                stdout=stdout,
                stderr=stderr,
            )
            raise RenderFailed(f"expected one rendered video, found {len(videos)}")

        self._write_metadata(
            job_dir,
            status="ready",
            command=command,
            started_at=started_at,
            elapsed_seconds=elapsed,
            exit_code=result.returncode,
            stdout=stdout,
            stderr=stderr,
        )
        return RenderOutcome(
            video_path=videos[0],
            renderer=f"docker:{self._image}",
            elapsed_seconds=elapsed,
            logs="\n".join(part for part in (stdout, stderr) if part),
        )

    def _render_command(self, job_dir: Path, container_name: str) -> list[str]:
        return [
            "docker",
            "run",
            "--rm",
            "--name",
            container_name,
            "--network",
            "none",
            "--cpus",
            "1.0",
            "--memory",
            "1g",
            "--memory-swap",
            "1g",
            "--pids-limit",
            "256",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=256m",
            "--env",
            "HOME=/tmp",
            "--volume",
            f"{self._scene_path}:/work/scene.py:ro",
            "--volume",
            f"{job_dir.resolve()}:/work/output:rw",
            "--workdir",
            "/work/output",
            self._image,
            "manim",
            "-ql",
            "--disable_caching",
            "--media_dir",
            "/work/output/media",
            "/work/scene.py",
            "PythagoreanTheorem",
        ]

    def _force_remove(self, container_name: str) -> None:
        with suppress(OSError, subprocess.SubprocessError):
            self._run_command(["docker", "rm", "-f", container_name], 10)

    def _write_metadata(
        self,
        job_dir: Path,
        *,
        status: str,
        command: list[str],
        started_at: datetime,
        elapsed_seconds: float,
        exit_code: int | None,
        stdout: str,
        stderr: str,
    ) -> None:
        metadata: dict[str, Any] = {
            "status": status,
            "image": self._image,
            "scene": self._scene_path.name,
            "command": command,
            "started_at": started_at.isoformat(),
            "completed_at": datetime.now(UTC).isoformat(),
            "elapsed_seconds": elapsed_seconds,
            "timeout_seconds": self._timeout_seconds,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
        }
        (job_dir / "render.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True),
            encoding="utf-8",
        )


def _trim(value: str | None) -> str:
    return (value or "")[-_LOG_LIMIT:]


def _as_text(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return _trim(value.decode(errors="replace"))
    return _trim(value)
