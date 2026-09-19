from __future__ import annotations

import json
import subprocess
from hashlib import sha256
from pathlib import Path

import pytest

from math_tutor.renderer import (
    DEFAULT_MANIM_IMAGE,
    DockerManimRenderer,
    RenderFailed,
    RenderTimedOut,
)


def test_renderer_runs_known_scene_with_resource_and_network_limits(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    scene = tmp_path / "known_scene.py"
    scene.write_text("# known-good scene", encoding="utf-8")
    commands: list[list[str]] = []

    def successful_run(
        command: list[str], timeout_seconds: float
    ) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        assert timeout_seconds == 30
        video = artifacts / "job-123" / "output" / "media" / "videos" / "scene" / "480p15"
        video.mkdir(parents=True)
        (video / "PythagoreanTheorem.mp4").write_bytes(b"mp4")
        return subprocess.CompletedProcess(command, 0, stdout="rendered", stderr="")

    renderer = DockerManimRenderer(
        artifact_root=artifacts,
        scene_path=scene,
        image=DEFAULT_MANIM_IMAGE,
        timeout_seconds=30,
        command_runner=successful_run,
    )

    outcome = renderer.render("job-123")

    assert outcome.video_path.read_bytes() == b"mp4"
    assert outcome.renderer == f"docker:{DEFAULT_MANIM_IMAGE}"
    command = commands[0]
    assert command[:3] == ["docker", "run", "--rm"]
    assert _option(command, "--network") == "none"
    assert _option(command, "--cpus") == "1.0"
    assert _option(command, "--memory") == "1g"
    assert _option(command, "--memory-swap") == "1g"
    assert _option(command, "--pids-limit") == "256"
    assert "--read-only" in command
    assert command[command.index("--cap-drop") :][:2] == ["--cap-drop", "ALL"]
    assert _option(command, "--security-opt") == "no-new-privileges"

    metadata = json.loads((artifacts / "job-123" / "render.json").read_text())
    assert metadata["status"] == "ready"
    assert metadata["image"] == DEFAULT_MANIM_IMAGE
    assert metadata["exit_code"] == 0
    assert metadata["stdout"] == "rendered"
    assert metadata["scene_sha256"] == sha256(b"# known-good scene").hexdigest()
    assert len(metadata["validator_sha256"]) == 64
    assert (artifacts / "job-123" / "scene.py").read_text() == "# known-good scene"
    assert (artifacts / "job-123" / "render_known.py").is_file()


def test_renderer_force_removes_container_after_timeout(tmp_path: Path) -> None:
    commands: list[list[str]] = []

    def timeout_run(command: list[str], timeout_seconds: float) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        if command[:2] == ["docker", "run"]:
            raise subprocess.TimeoutExpired(command, timeout_seconds, output="still rendering")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    renderer = DockerManimRenderer(
        artifact_root=tmp_path / "artifacts",
        scene_path=_scene_file(tmp_path),
        timeout_seconds=0.1,
        command_runner=timeout_run,
    )

    with pytest.raises(RenderTimedOut, match="0.1 seconds"):
        renderer.render("slow-job")

    assert commands[1] == ["docker", "rm", "-f", "math-tutor-render-slow-job"]
    metadata = json.loads(
        (tmp_path / "artifacts" / "slow-job" / "render.json").read_text()
    )
    assert metadata["status"] == "timed_out"
    assert metadata["stdout"] == "still rendering"
    assert metadata["cleanup_succeeded"] is True


def test_renderer_reports_when_timeout_cleanup_fails(tmp_path: Path) -> None:
    def timeout_and_failed_cleanup(
        command: list[str], timeout_seconds: float
    ) -> subprocess.CompletedProcess[str]:
        if command[:2] == ["docker", "run"]:
            raise subprocess.TimeoutExpired(command, timeout_seconds)
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="daemon unavailable")

    renderer = DockerManimRenderer(
        artifact_root=tmp_path / "artifacts",
        scene_path=_scene_file(tmp_path),
        timeout_seconds=0.1,
        command_runner=timeout_and_failed_cleanup,
    )

    with pytest.raises(RenderTimedOut, match="container cleanup failed"):
        renderer.render("cleanup-failed-job")

    metadata = json.loads(
        (tmp_path / "artifacts" / "cleanup-failed-job" / "render.json").read_text()
    )
    assert metadata["cleanup_succeeded"] is False
    assert metadata["cleanup_stderr"] == "daemon unavailable"


def test_renderer_preserves_diagnostics_for_terminal_failure(tmp_path: Path) -> None:
    def failed_run(command: list[str], timeout_seconds: float) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command,
            42,
            stdout="render started",
            stderr="render exploded",
        )

    renderer = DockerManimRenderer(
        artifact_root=tmp_path / "artifacts",
        scene_path=_scene_file(tmp_path),
        command_runner=failed_run,
    )

    with pytest.raises(RenderFailed, match="render exploded"):
        renderer.render("failed-job")

    metadata = json.loads(
        (tmp_path / "artifacts" / "failed-job" / "render.json").read_text()
    )
    assert metadata["status"] == "failed"
    assert metadata["exit_code"] == 42
    assert metadata["stderr"] == "render exploded"


def test_renderer_preserves_diagnostics_when_docker_cannot_start(tmp_path: Path) -> None:
    def missing_docker(
        command: list[str], timeout_seconds: float
    ) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("docker executable missing")

    renderer = DockerManimRenderer(
        artifact_root=tmp_path / "artifacts",
        scene_path=_scene_file(tmp_path),
        command_runner=missing_docker,
    )

    with pytest.raises(RenderFailed, match="docker executable missing") as caught:
        renderer.render("missing-docker-job")

    metadata = json.loads(
        (tmp_path / "artifacts" / "missing-docker-job" / "render.json").read_text()
    )
    assert metadata["status"] == "failed"
    assert metadata["stderr"] == "docker executable missing"
    assert caught.value.diagnostics["logs"] == "docker executable missing"
    assert caught.value.diagnostics["metadata_file"] == "render.json"


def test_renderer_rejects_video_symlink_that_escapes_job_directory(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    secret = tmp_path / "secret.txt"
    secret.write_text("not a video", encoding="utf-8")

    def symlink_run(command: list[str], timeout_seconds: float) -> subprocess.CompletedProcess[str]:
        video = (
            artifacts
            / "symlink-job"
            / "output"
            / "media"
            / "videos"
            / "scene"
            / "480p15"
        )
        video.mkdir(parents=True)
        (video / "PythagoreanTheorem.mp4").symlink_to(secret)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    renderer = DockerManimRenderer(
        artifact_root=artifacts,
        scene_path=_scene_file(tmp_path),
        command_runner=symlink_run,
    )

    with pytest.raises(RenderFailed, match="unsafe rendered video path"):
        renderer.render("symlink-job")


def test_renderer_rejects_mutable_image_tag(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="digest-pinned"):
        DockerManimRenderer(
            artifact_root=tmp_path / "artifacts",
            scene_path=_scene_file(tmp_path),
            image="manimcommunity/manim:v0.19.0",
        )


def _option(command: list[str], name: str) -> str:
    return command[command.index(name) + 1]


def _scene_file(tmp_path: Path) -> Path:
    scene = tmp_path / "known_scene.py"
    scene.write_text("# known-good scene", encoding="utf-8")
    return scene
