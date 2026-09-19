from __future__ import annotations

import subprocess
from pathlib import Path

import av

command = [
    "manim",
    "-ql",
    "--disable_caching",
    "--media_dir",
    "/work/output/media",
    "/work/scene.py",
    "PythagoreanTheorem",
]
subprocess.run(command, check=True)

videos = list(Path("/work/output/media").rglob("PythagoreanTheorem.mp4"))
if len(videos) != 1:
    raise RuntimeError(f"expected one rendered video, found {len(videos)}")

with av.open(str(videos[0])) as container:
    video_streams = list(container.streams.video)
    if len(video_streams) != 1:
        raise RuntimeError(f"expected one video stream, found {len(video_streams)}")
    try:
        next(container.decode(video_streams[0]))
    except StopIteration as error:
        raise RuntimeError("rendered video has no decodable frames") from error
