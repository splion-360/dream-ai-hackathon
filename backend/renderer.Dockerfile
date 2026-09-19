# syntax=docker/dockerfile:1

FROM manimcommunity/manim@sha256:ab5ad56cf685d89da96e5d459e0cde3743fbdf2141be4dcff6c26566b5ca3191

USER root
RUN pip install --no-cache-dir "manim-voiceover[elevenlabs]==0.3.7"
USER manimuser
