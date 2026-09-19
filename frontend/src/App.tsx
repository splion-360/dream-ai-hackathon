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
        <span className="engine-pill">Dynamic LoRA + Manim + ElevenLabs</span>
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

          <VideoStage lesson={lesson} busy={busy} />

          <div className="video-controls-strip">
            <span>Captions enabled</span>
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
  return (
    <section className="standalone-result">
      <div className="video-panel-head">
        <div>
          <p className="section-kicker">Generated visual lesson</p>
          <h2>{lessonTitle(lesson)}</h2>
        </div>
        <StatusBadge lesson={lesson} busy={false} />
      </div>
      <VideoStage lesson={lesson} busy={lesson.status === "queued" || lesson.status === "running"} />
      {lesson.status !== "queued" && lesson.status !== "running" && <SupportTabs lesson={lesson} />}
    </section>
  );
}

function VideoStage({ lesson, busy }: { lesson: LessonJob | null; busy: boolean }) {
  if (!lesson) return <EmptyVideo />;
  if (lesson.status === "queued" || lesson.status === "running") {
    return <GeneratingVideo lesson={lesson} busy={busy} />;
  }
  if (lesson.status === "failed") return <FailedVideo lesson={lesson} />;
  if (lesson.status === "partial") return <PartialVideo lesson={lesson} />;
  return <ReadyVideo lesson={lesson} />;
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
  const progress = lesson.status === "queued" ? 18 : 68;
  const heading = lesson.status === "queued"
    ? "Queued for a render worker"
    : "Rendering your visual lesson";

  return (
    <div className="video-stage video-generating">
      <div className="generation-topline">
        <span>{lesson.lesson}</span>
        <span>{progress}%</span>
      </div>
      <div className="generation-center">
        <span className="spinner-mark">∑</span>
        <h3>{heading}</h3>
        <div className="progress-track">
          <span style={{ width: `${progress}%` }} />
        </div>
      </div>
      <div className="inline-steps">
        {progressSteps.map((step, index) => {
          const threshold = [10, 32, 68, 90][index] ?? 100;
          return (
            <div key={step} className={progress >= threshold ? "is-complete" : ""}>
              <span />
              <p>{index + 1}. {step}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ReadyVideo({ lesson }: { lesson: LessonJob }) {
  const playableVideo = lesson.video_url ?? lesson.silent_video_url;

  return (
    <div className="video-stage video-ready">
      {playableVideo ? (
        <video data-testid="lesson-video" src={playableVideo} controls preload="metadata">
          {lesson.captions_url && (
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
      <span className="scene-label">Scene 03 · visual proof</span>
      {lesson.captions_url && <span className="caption-preview">Synchronized captions</span>}
      <span className={`video-state-pill video-state-${lesson.narration_status}`}>
        {narrationLabel(lesson.narration_status)}
      </span>
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
      <div className="support-tabs" role="tablist" aria-label="Lesson details">
        <button type="button" className="active">Explanation</button>
        <button type="button">Generated Manim Code</button>
        <button type="button">Diagnostics / Adapter Routing</button>
      </div>
      <div className="support-content">
        {lesson ? (
          <article className="explanation-layout">
            <div>
              <p className="section-kicker">Mathematical intuition</p>
              <h2>Explanation</h2>
              <p>
                {lesson.explanation ?? `Generated visual lesson for: ${lesson.lesson}`}
              </p>
            </div>
            <div className="proof-list">
              <ProofStep number="01" title="Reasoning target" formula={lesson.lesson}>
                Convert the prompt into a concise mathematical objective that can be explained visually.
              </ProofStep>
              <ProofStep number="02" title="Scene construction" formula="Scene → Shapes → Transformations">
                Use Manim code to build the animation as composable visual steps.
              </ProofStep>
              <ProofStep number="03" title="Narration package" formula="Video + Captions + Voice">
                Attach synchronized captions and narration when ElevenLabs output is available.
              </ProofStep>
              <details className="code-panel">
                <summary>Generated Manim · Python</summary>
                <pre><code>{lesson.generated_code ?? "# Manim source will appear here"}</code></pre>
              </details>
            </div>
          </article>
        ) : (
          <div className="awaiting-content">
            Generate a visual lesson to unlock its explanation, code, and adapter diagnostics.
          </div>
        )}
      </div>
    </section>
  );
}

function ProofStep({
  number,
  title,
  formula,
  children,
}: {
  number: string;
  title: string;
  formula: string;
  children: React.ReactNode;
}) {
  return (
    <section className="proof-step">
      <span>{number}</span>
      <div>
        <h3>{title}</h3>
        <p>{children}</p>
        <code>{formula}</code>
      </div>
    </section>
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

const delay = (milliseconds: number) =>
  new Promise<void>((resolve) => window.setTimeout(resolve, milliseconds));

export { LessonResult };
