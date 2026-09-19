# ElevenLabs Boundary and React Contracts

## Goal

Add a provider-neutral narration boundary and a frontend contract that can be developed and tested without Nebius. A known lesson fixture must be able to produce measured narration segments, captions, and a narrated media result. Narration failures must preserve the existing silent-video result.

## Ticket mapping

- Primary: #6, segment-synchronized ElevenLabs narration.
- Enabling slice: #4, typed React lesson-job and media contracts plus mocked UI states.
- Enabling slice: #5, narration failure degrades to the silent video.
- Existing prerequisite only: #1, known asynchronous lesson and silent render.
- Downstream only: #12, final narrated demo.
- Out of scope: #2, #3, and #7-#11.

This branch must not close #4 or #5. It implements only the contracts and behavior needed by #6.

## Scope

### Backend

Introduce immutable provider-neutral types for:

- `NarrationPlan`: ordered narration segments for a lesson.
- `NarrationSegment`: stable ID, spoken text, and visual cue.
- `SynthesizedSegment`: audio artifact, measured duration, and content hash.
- `SynthesizedNarration`: ordered synthesized segment results and provider metadata.
- `MediaBundle`: silent video, optional narrated video, optional captions, narration status, and diagnostics.

Introduce a `NarrationProvider` protocol. Its first production adapter calls ElevenLabs; tests use a deterministic fake. Provider configuration is application-owned. The API key is loaded only from `ELEVENLABS_API_KEY` and never enters a serialized contract.

For the MVP, narration is all-or-nothing. If synthesis, duration inspection, caption creation, or muxing fails, the lesson retains its silent video and records sanitized narration diagnostics.

### Frontend

Create a React TypeScript frontend package with:

- TypeScript definitions matching the additive lesson API contract.
- A transport interface with mock and HTTP implementations.
- UI states for queued, running, narrated success, silent fallback, partial, and failed lessons.
- A result view capable of showing explanation, generated code, the best available video, captions, and narration availability.

The frontend never calls ElevenLabs or Nebius directly and never receives provider credentials.

## Data contracts

### Narration plan

```json
{
  "schema_version": "narration-plan.v1",
  "lesson_id": "pythagorean-theorem",
  "segments": [
    {
      "id": "introduce-triangle",
      "text": "Consider a right triangle with side lengths a, b, and c.",
      "cue": "triangle-visible"
    }
  ]
}
```

Segment IDs must be unique and non-empty. Text and cue values must be non-empty. Segment order is authoritative. No provider-specific voice or model setting appears in this contract.

### Audio timeline

```json
{
  "schema_version": "audio-timeline.v1",
  "lesson_id": "pythagorean-theorem",
  "provider": "elevenlabs",
  "model_id": "eleven_multilingual_v2",
  "segments": [
    {
      "id": "introduce-triangle",
      "cue": "triangle-visible",
      "text": "Consider a right triangle with side lengths a, b, and c.",
      "audio_file": "audio/introduce-triangle.mp3",
      "duration_seconds": 4.82,
      "sha256": "..."
    }
  ]
}
```

Durations come from inspecting returned audio, never from text-length estimates.

### Lesson API additions

The existing response remains backward compatible. The frontend types allow these additive fields:

```json
{
  "explanation": null,
  "generated_code": null,
  "video_url": "/lessons/id/video",
  "silent_video_url": "/lessons/id/video/silent",
  "captions_url": "/lessons/id/captions",
  "narration_status": "ready"
}
```

`narration_status` is `not_requested`, `pending`, `ready`, or `unavailable`. `video_url` always identifies the best playable result: narrated when available, otherwise silent.

## Processing sequence

1. A fixture or future model adapter produces a `NarrationPlan`.
2. The narration provider synthesizes each segment into a job-scoped artifact directory.
3. Audio duration is measured and persisted in the audio timeline.
4. Captions are generated from ordered segment text and measured timing.
5. The timed renderer and muxer produce the final narrated video.
6. On any narration-stage failure, the silent render remains the successful lesson artifact.

Segment-level synchronization is in scope. Word- and phoneme-level synchronization are not.

## Ownership boundaries

- The Nebius work owns prompt execution and eventual production of a compatible lesson/narration plan.
- This branch owns narration synthesis, measured timing, captions, media assembly contracts, and narration-aware frontend states.
- The existing renderer remains the authority for isolated Manim execution.
- Lovable may supply visual component ideas, but exported code is reviewed and integrated manually. This repository remains the source of truth.

## Verification

- Backend unit tests prove validation, ordering, measured-duration propagation, caption timing, sanitized failures, and silent fallback.
- Provider contract tests use a fake transport; live ElevenLabs smoke tests are opt-in and never part of the default suite.
- Frontend tests prove all six mocked lesson states and verify that silent fallback is presented as a successful lesson rather than a total failure.
- Existing Python tests and Ruff checks remain green.
- Frontend type checking and tests run independently of FastAPI and external providers.

## Commit boundaries

1. Backend narration contracts and tests.
2. ElevenLabs adapter and failure behavior.
3. Media timeline/caption assembly.
4. React lesson contracts, mocked transport, and state components.
5. Narrow job/API integration after the isolated boundaries are verified.
