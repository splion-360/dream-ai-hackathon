import { type FormEvent, useMemo, useRef, useState } from "react";

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
  "Geometric intuition of Euler's identity",
  "How gradient descent minimizes loss",
  "Derive the Fourier transform from heat diffusion",
];

export function App({ transport = defaultTransport, pollIntervalMs = 700 }: AppProps) {
  const [prompt, setPrompt] = useState(DEFAULT_PROMPT);
  const [lesson, setLesson] = useState<LessonJob | null>(null);
  const [requestError, setRequestError] = useState<string | null>(null);
  const [polling, setPolling] = useState(false);
  const mounted = useRef(true);
  const busy = polling;
  const formalizedExpression = useMemo(() => inferFormula(prompt), [prompt]);

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
        <div className="header-status">
          <span className="live-dot" />
          <span>Local demo environment</span>
        </div>
      </header>

      <section className="intro-band">
        <p className="section-kicker">Lesson composer / 01</p>
        <div className="intro-copy">
          <h1>From symbolic notation to visual intuition.</h1>
          <p>
            Enter a mathematical idea. The tutor packages the derivation,
            animation, captions, and narration as separate lesson assets.
          </p>
        </div>
      </section>

      <section className="composer-grid" aria-label="Lesson composer">
        <form className="composer-panel" onSubmit={submit}>
          <div className="mode-tabs" aria-label="Input mode">
            <button type="button" className="mode-tab active">Natural language</button>
            <button type="button" className="mode-tab" aria-disabled="true">LaTeX / formula</button>
          </div>

          <div className="field-head">
            <label htmlFor="lesson-prompt">Mathematical question</label>
            <span>{prompt.length} chars</span>
          </div>
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

          <div className="composer-actions">
            <span>Visual proof · Manim · ElevenLabs-ready</span>
            <button type="submit" disabled={busy || !prompt.trim()}>
              {busy ? "Generating…" : "Generate lesson"}
              <span aria-hidden="true">→</span>
            </button>
          </div>
        </form>

        <aside className="formula-panel">
          <div className="formula-panel-top">
            <p>Natural language → Formalized LaTeX</p>
            <span>Extracted</span>
          </div>
          <div className="formula-workspace">
            <blockquote>“{prompt}”</blockquote>
            <div>
              <p className="formula-label">Formalized expression</p>
              <code>{formalizedExpression}</code>
            </div>
          </div>
          <div className="formula-panel-bottom">
            <span>Input valid</span>
            <span>Display mode</span>
          </div>
        </aside>
      </section>

      <StatusPanel status={lesson?.status ?? (busy ? "running" : "queued")} lesson={lesson} busy={busy} />

      {requestError && <p className="request-error" role="alert">{requestError}</p>}
      {lesson && <LessonResult lesson={lesson} />}
    </main>
  );
}

function StatusPanel({
  status,
  lesson,
  busy,
}: {
  status: LessonStatus;
  lesson: LessonJob | null;
  busy: boolean;
}) {
  const progress = lessonProgress(status, busy);
  const label = busy
    ? status === "queued" ? "Queued" : "Generating lesson"
    : lesson ? status : "Ready for prompt";
  const detail = busy
    ? "Structuring the proof, rendering the scene, and packaging lesson assets."
    : lesson ? resultDetail(lesson) : "No job has been submitted yet.";

  return (
    <section className="status-panel" aria-live="polite">
      <div className="status-summary">
        <StatusIcon status={status} active={busy} />
        <div>
          <p>{label}</p>
          <span>{detail}</span>
        </div>
      </div>
      <div className="status-track" aria-label="Lesson progress">
        <span className={`status-progress status-progress-${status}`} style={{ width: `${progress}%` }} />
      </div>
      <div className="pipeline-steps">
        <PipelineStep done={progress > 25} active={progress <= 25} label="Parse & reason" meta="Symbolic graph" />
        <PipelineStep done={progress > 70} active={progress > 25 && progress <= 70} label="Build animation" meta="Manim render" />
        <PipelineStep done={progress > 95} active={progress > 70} label="Package lesson" meta="Audio + captions" />
      </div>
    </section>
  );
}

function LessonResult({ lesson }: { lesson: LessonJob }) {
  if (lesson.status === "queued" || lesson.status === "running") {
    return (
      <section className="result-frame progress-card" aria-live="polite">
        <div className="spinner-mark">Σ</div>
        <div>
          <p className="section-kicker">{lesson.status === "queued" ? "Queued" : "Building your lesson"}</p>
          <h2>{lesson.status === "queued" ? "Waiting for a render slot" : "Sketching the proof, frame by frame"}</h2>
          <p>The video and narration are assembled independently, so a voice outage never loses the lesson.</p>
        </div>
      </section>
    );
  }

  if (lesson.status === "failed") {
    return (
      <section className="result-frame error-card" role="alert">
        <p className="section-kicker">Lesson failed</p>
        <h2>That proof needs another approach.</h2>
        <p>{lesson.error ?? "The lesson could not be generated."}</p>
      </section>
    );
  }

  const playableVideo = lesson.video_url ?? lesson.silent_video_url;
  const heading = lesson.status === "partial"
    ? "Partial lesson available"
    : lesson.narration_status === "ready"
      ? "Narrated lesson ready"
      : "Video ready · narration unavailable";

  return (
    <section className="lesson-result-grid" aria-live="polite">
      <article className="lesson-copy">
        <div className="lesson-heading">
          <div>
            <p className="section-kicker">Lesson 01 · from prompt</p>
            <h2>{heading}</h2>
          </div>
          <NarrationBadge status={lesson.narration_status} />
        </div>

        <p className="lesson-summary">
          {lesson.explanation ?? "The visual lesson is ready. A written explanation will appear when the model pipeline is connected."}
        </p>

        <div className="proof-steps">
          <ProofStep number="01" title="Reasoning target" formula="a² + b² = c²">
            Convert the prompt into a concise mathematical objective that can be explained visually.
          </ProofStep>
          <ProofStep number="02" title="Scene construction" formula="Scene → Shapes → Transformations">
            Use Manim code to build the animation as composable visual steps.
          </ProofStep>
          <ProofStep number="03" title="Narration package" formula="Video + Captions + Voice">
            Attach synchronized captions and narration when ElevenLabs output is available.
          </ProofStep>
        </div>

        <details className="code-panel" open>
          <summary>Generated Manim · Python</summary>
          <pre><code>{lesson.generated_code ?? "# Manim source will appear here"}</code></pre>
        </details>
      </article>

      <aside className="playback-panel">
        {playableVideo ? (
          <div className="video-shell">
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
            <span className="scene-label">Scene 03 · visual proof</span>
            {lesson.captions_url && <span className="caption-preview">Synchronized captions</span>}
          </div>
        ) : (
          <div className="partial-placeholder">
            <strong>Video render timed out</strong>
            <span>{lesson.error ?? "The explanation and source code are preserved."}</span>
          </div>
        )}

        <div className="playback-meta">
          <span className={`audio-state audio-state-${lesson.narration_status}`}>
            {narrationLabel(lesson.narration_status)}
          </span>
          {lesson.narration_status === "unavailable" && playableVideo && (
            <p>Narration could not be attached. Silent playback is ready with the generated lesson assets.</p>
          )}
        </div>
      </aside>
    </section>
  );
}

function PipelineStep({
  done,
  active,
  label,
  meta,
}: {
  done: boolean;
  active: boolean;
  label: string;
  meta: string;
}) {
  return (
    <div className="pipeline-step">
      <span className={done ? "done" : active ? "active" : ""}>{done ? "✓" : active ? "•" : "·"}</span>
      <div>
        <p>{label}</p>
        <small>{meta}</small>
      </div>
    </div>
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

function StatusIcon({ status, active }: { status: LessonStatus; active: boolean }) {
  const symbol = status === "failed" ? "!" : status === "ready" ? "✓" : status === "partial" ? "△" : "↻";
  return <span className={`status-icon status-icon-${status} ${active ? "is-active" : ""}`}>{symbol}</span>;
}

function NarrationBadge({ status }: { status: NarrationStatus }) {
  return <span className={`narration-badge narration-${status}`}>{narrationLabel(status)}</span>;
}

function narrationLabel(status: NarrationStatus) {
  if (status === "ready") return "Voice + captions";
  if (status === "pending") return "Narration pending";
  if (status === "unavailable") return "Silent fallback active";
  return "Narration not requested";
}

function resultDetail(lesson: LessonJob) {
  if (lesson.status === "failed") return lesson.error ?? "Generation stopped.";
  if (lesson.status === "partial") return "Useful partial output is available.";
  if (lesson.narration_status === "ready") return "Video, narration, and captions are ready.";
  if (lesson.narration_status === "unavailable") return "Video is ready without narration.";
  return "Lesson assets are available.";
}

function lessonProgress(status: LessonStatus, busy: boolean) {
  if (status === "failed") return 41;
  if (status === "partial") return 76;
  if (status === "ready") return 100;
  if (status === "running") return 67;
  return busy ? 18 : 0;
}

function inferFormula(prompt: string) {
  const value = prompt.toLowerCase();
  if (value.includes("sqrt") || value.includes("√2") || value.includes("irrational")) {
    return "√2 ∉ ℚ";
  }
  if (value.includes("euler")) {
    return "e^(iπ) + 1 = 0";
  }
  if (value.includes("gradient")) {
    return "θₜ₊₁ = θₜ − η∇J(θₜ)";
  }
  if (value.includes("fourier") || value.includes("heat")) {
    return "F{f}(ξ) = ∫ f(x)e^(-2πixξ) dx";
  }
  return "a² + b² = c²";
}

const delay = (milliseconds: number) =>
  new Promise<void>((resolve) => window.setTimeout(resolve, milliseconds));

export { LessonResult };
