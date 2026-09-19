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
    [queuedLesson, "Queued for a render worker"],
    [runningLesson, "Rendering your visual lesson"],
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
    expect(screen.queryByText("Scene 03 · visual proof")).not.toBeInTheDocument();
    expect(screen.queryByText("Synchronized captions")).not.toBeInTheDocument();
  });

  it("lets the user toggle captions off", () => {
    render(<LessonResult lesson={narratedLesson} />);

    fireEvent.click(screen.getByLabelText("Captions"));

    expect(screen.queryByTitle("English captions")).not.toBeInTheDocument();
  });

  it("shows generated Manim code inside the main artifact panel", () => {
    render(<LessonResult lesson={narratedLesson} />);

    fireEvent.click(screen.getByRole("button", { name: "</>" }));

    expect(screen.getByText("Generated Manim · Python")).toBeInTheDocument();
    expect(screen.getByText(/MathTex/)).toBeInTheDocument();
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

  it("shows the submitted prompt instead of a hard-coded theorem", () => {
    render(
      <LessonResult
        lesson={{
          ...silentFallbackLesson,
          lesson: "Explain why √2 is irrational",
          explanation: null,
        }}
      />,
    );

    expect(screen.getByText("Generated visual lesson for: Explain why √2 is irrational")).toBeInTheDocument();
    expect(screen.queryByText("a² + b² = c²")).not.toBeInTheDocument();
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

    expect(screen.getByText("Create a visual lesson")).toBeInTheDocument();
    expect(screen.getByText("Your generated visual lesson will appear here.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /generate lesson/i }));

    expect(await screen.findByText("Narrated lesson ready")).toBeInTheDocument();
    expect(screen.getByText("Generated visual lesson")).toBeInTheDocument();
    expect(screen.getByText("Captions on")).toBeInTheDocument();
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
