from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import av

scene_class = sys.argv[1] if len(sys.argv) == 2 else "PythagoreanTheorem"
command = [
    "manim",
    "-ql",
    "--disable_caching",
    "--media_dir",
    "/work/output/media",
    "/work/scene.py",
    scene_class,
]
subprocess.run(command, check=True)

videos = list(Path("/work/output/media").rglob(f"{scene_class}.mp4"))
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
