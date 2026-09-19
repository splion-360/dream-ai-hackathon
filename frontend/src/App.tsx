import { type FormEvent, useRef, useState } from "react";

import type { LessonJob, LessonStatus, LessonTransport, NarrationStatus } from "./contracts";
import { isTerminal } from "./contracts";
import { HttpLessonTransport } from "./transport";
import "./styles.css";

const defaultTransport = new HttpLessonTransport();
const DEFAULT_PROMPT = "Explain why a² + b² = c² using a visual proof.";

interface AppProps {
  transport?: LessonTransport;
  pollIntervalMs?: number;
}

const examples = [
  "Explain why √2 is irrational",
  "Visualize Euler’s identity",
  "Gradient descent intuition",
  "Fourier transform from heat diffusion",
];

const progressSteps = [
  "Parse prompt",
  "Generate Manim",
  "Render video",
  "Add narration/captions",
];

export function App({ transport = defaultTransport, pollIntervalMs = 700 }: AppProps) {
  const [prompt, setPrompt] = useState(DEFAULT_PROMPT);
  const [lesson, setLesson] = useState<LessonJob | null>(null);
  const [requestError, setRequestError] = useState<string | null>(null);
  const [polling, setPolling] = useState(false);
  const [artifactMode, setArtifactMode] = useState<"view" | "code">("view");
  const [captionsEnabled, setCaptionsEnabled] = useState(true);
  const mounted = useRef(true);
  const busy = polling;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!prompt.trim() || busy) return;
    mounted.current = true;
    setPolling(true);
    setRequestError(null);

    try {
      let next = await transport.submitLesson({ prompt: prompt.trim() });
      if (mounted.current) setLesson(next);
      while (!isTerminal(next.status)) {
        await delay(pollIntervalMs);
        next = await transport.getLesson(next.id);
        if (mounted.current) setLesson(next);
      }
    } catch (error) {
      if (mounted.current) {
        setRequestError(error instanceof Error ? error.message : "The lesson request failed");
      }
    } finally {
      if (mounted.current) setPolling(false);
    }
  }

  return (
    <main className="studio-shell">
      <header className="studio-header">
        <a className="brand" href="/" aria-label="Math Tutor home">
          <span className="brand-mark">∑</span>
          <span>
            <strong>Math Tutor</strong>
            <small>Visual math studio</small>
          </span>
        </a>
        <span className="engine-pill">Specialist LoRA + Manim + ElevenLabs</span>
      </header>

      <section className="workspace-grid">
        <form className="composer-panel" onSubmit={submit}>
          <div className="panel-copy">
            <p className="section-kicker">Create a visual lesson</p>
            <h1>What should we make visible?</h1>
            <p>Describe a concept or ask a question. The studio turns it into a visual lesson.</p>
          </div>

          <label htmlFor="lesson-prompt">Prompt or formula</label>
          <textarea
            id="lesson-prompt"
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            rows={5}
            spellCheck={false}
          />

          <div className="sample-row" aria-label="Example prompts">
            {examples.map((example) => (
              <button
                key={example}
                type="button"
                onClick={() => setPrompt(example)}
              >
                {example}
              </button>
            ))}
          </div>

          <button className="primary-action" type="submit" disabled={busy || !prompt.trim()}>
            {busy ? "Generating…" : "Generate lesson"}
            <span aria-hidden="true">→</span>
          </button>

          <div className="composer-meta">
            <span>1080p · 60 fps</span>
            <span>Typical render 18–24 sec</span>
          </div>
        </form>

        <section className="video-panel" aria-live="polite">
          <div className="video-panel-head">
            <div>
              <p className="section-kicker">Generated visual lesson</p>
              <h2>{lesson ? lessonTitle(lesson) : "Video output"}</h2>
            </div>
            <StatusBadge lesson={lesson} busy={busy} />
          </div>

          <div className="artifact-toolbar" aria-label="Lesson artifact controls">
            <div className="segmented-control" role="group" aria-label="Choose lesson artifact">
              <button
                type="button"
                className={artifactMode === "view" ? "active" : ""}
                onClick={() => setArtifactMode("view")}
              >
                View
              </button>
              <button
                type="button"
                className={artifactMode === "code" ? "active" : ""}
                onClick={() => setArtifactMode("code")}
              >
                {"</>"}
              </button>
            </div>
            <label className="caption-toggle">
              <input
                type="checkbox"
                checked={captionsEnabled}
                disabled={!lesson?.captions_url || artifactMode !== "view"}
                onChange={(event) => setCaptionsEnabled(event.target.checked)}
              />
              Captions
            </label>
          </div>

          <VideoStage
            lesson={lesson}
            busy={busy}
            mode={artifactMode}
            captionsEnabled={captionsEnabled}
          />

          <div className="video-controls-strip">
            <span>{artifactMode === "code" ? "Generated Manim source" : artifactStatus(lesson, captionsEnabled)}</span>
            <span>{lesson ? narrationLabel(lesson.narration_status) : "Narration pending"}</span>
          </div>

          {requestError && <p className="request-error" role="alert">{requestError}</p>}
        </section>
      </section>

      <SupportTabs lesson={lesson} />
    </main>
  );
}

function LessonResult({ lesson }: { lesson: LessonJob }) {
  const [artifactMode, setArtifactMode] = useState<"view" | "code">("view");
  const [captionsEnabled, setCaptionsEnabled] = useState(true);

  return (
    <section className="standalone-result">
      <div className="video-panel-head">
        <div>
          <p className="section-kicker">Generated visual lesson</p>
          <h2>{lessonTitle(lesson)}</h2>
        </div>
        <StatusBadge lesson={lesson} busy={false} />
      </div>
      <div className="artifact-toolbar" aria-label="Lesson artifact controls">
        <div className="segmented-control" role="group" aria-label="Choose lesson artifact">
          <button
            type="button"
            className={artifactMode === "view" ? "active" : ""}
            onClick={() => setArtifactMode("view")}
          >
            View
          </button>
          <button
            type="button"
            className={artifactMode === "code" ? "active" : ""}
            onClick={() => setArtifactMode("code")}
          >
            {"</>"}
          </button>
        </div>
        <label className="caption-toggle">
          <input
            type="checkbox"
            checked={captionsEnabled}
            disabled={!lesson.captions_url || artifactMode !== "view"}
            onChange={(event) => setCaptionsEnabled(event.target.checked)}
          />
          Captions
        </label>
      </div>
      <VideoStage
        lesson={lesson}
        busy={lesson.status === "queued" || lesson.status === "running"}
        mode={artifactMode}
        captionsEnabled={captionsEnabled}
      />
      {lesson.status !== "queued" && lesson.status !== "running" && <SupportTabs lesson={lesson} />}
    </section>
  );
}

function VideoStage({
  lesson,
  busy,
  mode,
  captionsEnabled,
}: {
  lesson: LessonJob | null;
  busy: boolean;
  mode: "view" | "code";
  captionsEnabled: boolean;
}) {
  if (!lesson) return <EmptyVideo />;
  if (lesson.status === "queued" || lesson.status === "running") {
    return <GeneratingVideo lesson={lesson} busy={busy} />;
  }
  if (mode === "code") return <CodeStage lesson={lesson} />;
  if (lesson.status === "failed") return <FailedVideo lesson={lesson} />;
  if (lesson.status === "partial") return <PartialVideo lesson={lesson} />;
  return <ReadyVideo lesson={lesson} captionsEnabled={captionsEnabled} />;
}

function EmptyVideo() {
  return (
    <div className="video-stage video-empty">
      <div className="chalk-orbit" />
      <div className="empty-video-copy">
        <span className="play-glyph">▶</span>
        <h3>Your generated visual lesson will appear here.</h3>
        <p>Enter a concept or equation, then generate a Manim-powered explanation.</p>
      </div>
    </div>
  );
}

function GeneratingVideo({ lesson }: { lesson: LessonJob; busy: boolean }) {
  const progress = truthfulProgress(lesson);
  const heading = lesson.status === "queued"
    ? "Queued for a render worker"
    : "Rendering your visual lesson";
  const phase = lesson.status === "queued" ? "Queued" : "Rendering";

  return (
    <div className="video-stage video-generating">
      <div className="generation-topline">
        <span>{lesson.lesson}</span>
        <span>{progress === null ? phase : `${progress}%`}</span>
      </div>
      <div className="generation-center">
        <span className="spinner-mark">∑</span>
        <h3>{heading}</h3>
        <div className={progress === null ? "progress-track is-indeterminate" : "progress-track"}>
          <span style={progress === null ? undefined : { width: `${progress}%` }} />
        </div>
      </div>
      <div className="inline-steps">
        {progressSteps.map((step, index) => {
          const threshold = [10, 32, 68, 90][index] ?? 100;
          return (
            <div
              key={step}
              className={progress !== null && progress >= threshold ? "is-complete" : ""}
            >
              <span />
              <p>{index + 1}. {step}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ReadyVideo({
  lesson,
  captionsEnabled,
}: {
  lesson: LessonJob;
  captionsEnabled: boolean;
}) {
  const playableVideo = lesson.video_url ?? lesson.silent_video_url;

  return (
    <div className="video-stage video-ready">
      {playableVideo ? (
        <video data-testid="lesson-video" src={playableVideo} controls preload="metadata">
          {captionsEnabled && lesson.captions_url && (
            <track
              title="English captions"
              kind="captions"
              src={lesson.captions_url}
              srcLang="en"
              label="English"
              default
            />
          )}
        </video>
      ) : (
        <div className="video-placeholder">Video asset unavailable</div>
      )}
    </div>
  );
}

function CodeStage({ lesson }: { lesson: LessonJob }) {
  return (
    <div className="video-stage code-stage">
      <div className="code-stage-head">
        <span>Generated Manim · Python</span>
        <span>{lesson.generated_code ? "Ready" : "Waiting for source"}</span>
      </div>
      <pre><code>{lesson.generated_code ?? "# Manim source will appear here"}</code></pre>
    </div>
  );
}

function PartialVideo({ lesson }: { lesson: LessonJob }) {
  return (
    <div className="video-stage video-partial">
      <h3>Video render timed out</h3>
      <p>{lesson.error ?? "The render timed out, but useful lesson assets are preserved."}</p>
    </div>
  );
}

function FailedVideo({ lesson }: { lesson: LessonJob }) {
  return (
    <div className="video-stage video-failed">
      <h3>Generation stopped</h3>
      <p>{lesson.error ?? "The lesson could not be generated."}</p>
    </div>
  );
}

function SupportTabs({ lesson }: { lesson: LessonJob | null }) {
  return (
    <section className="support-panel">
      <div className="support-content">
        {lesson ? (
          <article className="lesson-details-grid">
            <section className="detail-card">
              <p className="section-kicker">Mathematical intuition</p>
              <h2>Explanation</h2>
              <p>
                {lesson.explanation ?? `Generated visual lesson for: ${lesson.lesson}`}
              </p>
            </section>
            <section className="detail-card adapter-card">
              <p className="section-kicker">Adapter routing</p>
              <h2>Dynamic LoRA trace</h2>
              <AdapterRouting diagnostics={lesson.diagnostics} />
            </section>
          </article>
        ) : (
          <div className="awaiting-content">
            Generate a visual lesson to unlock its explanation and adapter diagnostics.
          </div>
        )}
      </div>
    </section>
  );
}

function AdapterRouting({ diagnostics }: { diagnostics: Record<string, unknown> }) {
  const adapter = readText(diagnostics, ["adapter", "adapter_id", "selected_adapter"]) ?? "Pending";
  const route = readText(diagnostics, ["route", "router_path", "topic"]) ?? "No route reported yet";
  const confidence = readPercent(diagnostics, ["confidence", "router_confidence"]);

  return (
    <div className="adapter-routing">
      <div>
        <span>Selected adapter</span>
        <strong>{adapter}</strong>
      </div>
      <div>
        <span>Route</span>
        <strong>{route}</strong>
      </div>
      <div>
        <span>Confidence</span>
        <strong>{confidence === null ? "Pending" : `${confidence}%`}</strong>
      </div>
    </div>
  );
}

function StatusBadge({ lesson, busy }: { lesson: LessonJob | null; busy: boolean }) {
  const status = lesson?.status ?? (busy ? "running" : "idle");
  const text = !lesson
    ? busy ? "Rendering" : "Awaiting prompt"
    : status === "ready" ? "Ready"
      : status === "partial" ? "Partial output"
        : status === "failed" ? "Failed"
          : status === "queued" ? "Queued"
            : "Rendering";

  return <span className={`status-badge status-${status}`}>{text}</span>;
}

function lessonTitle(lesson: LessonJob) {
  if (lesson.status === "failed") return "Lesson failed";
  if (lesson.status === "partial") return "Partial lesson available";
  if (lesson.status === "queued") return "Queued";
  if (lesson.status === "running") return "Rendering";
  if (lesson.narration_status === "ready") return "Narrated lesson ready";
  if (lesson.narration_status === "unavailable") return "Video ready · narration unavailable";
  return "Video ready";
}

function narrationLabel(status: NarrationStatus) {
  if (status === "ready") return "Voice + captions";
  if (status === "pending") return "Narration pending";
  if (status === "unavailable") return "Silent fallback active";
  return "Narration not requested";
}

function artifactStatus(lesson: LessonJob | null, captionsEnabled: boolean) {
  if (!lesson) return "Video appears here";
  if (!lesson.captions_url) return "Captions unavailable";
  return captionsEnabled ? "Captions on" : "Captions off";
}

function truthfulProgress(lesson: LessonJob) {
  return readPercent(lesson.diagnostics, ["progress_percent", "progress"]);
}

function readText(record: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  return null;
}

function readPercent(record: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const value = record[key];
    if (typeof value !== "number" || Number.isNaN(value)) continue;
    const normalized = value > 0 && value <= 1 ? value * 100 : value;
    if (normalized >= 0 && normalized <= 100) return Math.round(normalized);
  }
  return null;
}

const delay = (milliseconds: number) =>
  new Promise<void>((resolve) => window.setTimeout(resolve, milliseconds));

export { LessonResult };
