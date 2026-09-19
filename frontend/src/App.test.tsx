import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { App, LessonResult } from "./App";
import type { CreateLessonInput, LessonTransport } from "./contracts";
import {
  failedLesson,
  narratedLesson,
  partialLesson,
  queuedLesson,
  runningLesson,
  silentFallbackLesson,
} from "./fixtures";
import { MockLessonTransport } from "./transport";

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

describe("App lesson flow", () => {
  it("submits, polls, and renders a terminal lesson", async () => {
    const transport = new MockLessonTransport([
      queuedLesson,
      runningLesson,
      narratedLesson,
    ]);
    render(<App transport={transport} pollIntervalMs={0} />);

    expect(screen.getByText("Lesson composer / 01")).toBeInTheDocument();
    expect(screen.getByText("Formalized expression")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /generate lesson/i }));

    expect(await screen.findByText("Narrated lesson ready")).toBeInTheDocument();
    expect(screen.getByText("Synchronized captions")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /generate lesson/i })).toBeEnabled();
  });

  it("re-enables submission when polling fails", async () => {
    const transport: LessonTransport = {
      async submitLesson(_input: CreateLessonInput) {
        return runningLesson;
      },
      async getLesson(_id: string) {
        throw new Error("polling unavailable");
      },
    };
    render(<App transport={transport} pollIntervalMs={0} />);

    fireEvent.click(screen.getByRole("button", { name: /generate lesson/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("polling unavailable");
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /generate lesson/i })).toBeEnabled(),
    );
  });
});
