import type { LessonJob } from "./contracts";

const base: LessonJob = {
  id: "demo",
  lesson: "pythagorean-theorem",
  status: "queued",
  created_at: "2026-09-19T18:00:00Z",
  started_at: null,
  completed_at: null,
  explanation: null,
  generated_code: null,
  video_url: null,
  silent_video_url: null,
  captions_url: null,
  narration_status: "pending",
  diagnostics: {},
  error: null,
};

export const queuedLesson: LessonJob = { ...base };

export const runningLesson: LessonJob = {
  ...base,
  status: "running",
  started_at: "2026-09-19T18:00:01Z",
};

export const narratedLesson: LessonJob = {
  ...base,
  status: "ready",
  started_at: "2026-09-19T18:00:01Z",
  completed_at: "2026-09-19T18:00:09Z",
  explanation: "A right triangle relates its two legs to its hypotenuse.",
  generated_code: "equation = MathTex(r\"a^2 + b^2 = c^2\")",
  video_url: "/lessons/demo/video",
  silent_video_url: "/lessons/demo/video/silent",
  captions_url: "/lessons/demo/captions",
  narration_status: "ready",
};

export const silentFallbackLesson: LessonJob = {
  ...narratedLesson,
  video_url: "/lessons/demo/video/silent",
  captions_url: null,
  narration_status: "unavailable",
  diagnostics: { narration_error: "ElevenLabsError" },
};

export const partialLesson: LessonJob = {
  ...base,
  status: "partial",
  completed_at: "2026-09-19T18:00:09Z",
  explanation: "The explanation is ready, but video rendering failed.",
  narration_status: "unavailable",
  error: "Manim render unavailable",
};

export const failedLesson: LessonJob = {
  ...base,
  status: "failed",
  completed_at: "2026-09-19T18:00:04Z",
  narration_status: "unavailable",
  error: "The lesson could not be generated.",
};
