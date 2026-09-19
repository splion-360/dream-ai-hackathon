import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LessonResult } from "./App";
import {
  failedLesson,
  narratedLesson,
  partialLesson,
  queuedLesson,
  runningLesson,
  silentFallbackLesson,
} from "./fixtures";

describe("LessonResult", () => {
  it.each([
    [queuedLesson, "Queued"],
    [runningLesson, "Building your lesson"],
  ])("renders progress state", (lesson, text) => {
    render(<LessonResult lesson={lesson} />);
    expect(screen.getByText(text)).toBeInTheDocument();
  });

  it("plays the narrated result and exposes captions", () => {
    render(<LessonResult lesson={narratedLesson} />);
    expect(screen.getByText("Narrated lesson ready")).toBeInTheDocument();
    expect(screen.getByTestId("lesson-video")).toHaveAttribute(
      "src",
      "/lessons/demo/video",
    );
    expect(screen.getByTitle("English captions")).toHaveAttribute(
      "src",
      "/lessons/demo/captions",
    );
  });

  it("presents silent fallback as a successful lesson", () => {
    render(<LessonResult lesson={silentFallbackLesson} />);
    expect(screen.getByText("Video ready · narration unavailable")).toBeInTheDocument();
    expect(screen.getByTestId("lesson-video")).toHaveAttribute(
      "src",
      "/lessons/demo/video/silent",
    );
    expect(screen.queryByText(/lesson failed/i)).not.toBeInTheDocument();
  });

  it("keeps useful partial output visible", () => {
    render(<LessonResult lesson={partialLesson} />);
    expect(screen.getByText("Partial lesson available")).toBeInTheDocument();
    expect(screen.getByText("The explanation is ready, but video rendering failed.")).toBeInTheDocument();
  });

  it("shows terminal failure without a video player", () => {
    render(<LessonResult lesson={failedLesson} />);
    expect(screen.getByText("Lesson failed")).toBeInTheDocument();
    expect(screen.queryByTestId("lesson-video")).not.toBeInTheDocument();
  });
});
