import { type FormEvent, useEffect, useRef, useState } from "react";

import type { LessonJob, LessonTransport } from "./contracts";
import { isTerminal } from "./contracts";
import { HttpLessonTransport } from "./transport";
import "./styles.css";

const defaultTransport = new HttpLessonTransport();
const DEFAULT_PROMPT = "Explain why a² + b² = c² using a visual proof.";

interface AppProps {
  transport?: LessonTransport;
  pollIntervalMs?: number;
}

export function App({ transport = defaultTransport, pollIntervalMs = 700 }: AppProps) {
  const [prompt, setPrompt] = useState(DEFAULT_PROMPT);
  const [lesson, setLesson] = useState<LessonJob | null>(null);
  const [requestError, setRequestError] = useState<string | null>(null);
  const [polling, setPolling] = useState(false);
  const mounted = useRef(true);
  const busy = polling;

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!prompt.trim() || busy) return;
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
    <main className="app-shell">
      <header className="masthead">
        <a className="brand" href="/" aria-label="Proof Play home">
          <span className="brand-mark">∴</span>
          <span>Proof Play</span>
        </a>
        <span className="engine-badge"><i /> Dynamic LoRA engine</span>
      </header>

      <section className="hero">
        <p className="eyebrow">A math tutor that shows its work</p>
        <h1>Turn hard ideas into <em>clear motion.</em></h1>
        <p className="hero-copy">
          Ask for a concept—from algebra to analysis—and get a visual lesson with
          explanation, code, captions, and optional narration.
        </p>

        <form className="prompt-card" onSubmit={submit}>
          <label htmlFor="lesson-prompt">What should we make intuitive?</label>
          <textarea
            id="lesson-prompt"
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            rows={3}
          />
          <div className="prompt-footer">
            <span>Fixture mode · Pythagorean theorem</span>
            <button type="submit" disabled={busy || !prompt.trim()}>
              {busy ? "Building lesson…" : "Create visual lesson"}
              <span aria-hidden="true">→</span>
            </button>
          </div>
        </form>
      </section>

      {requestError && <p className="request-error" role="alert">{requestError}</p>}
      {lesson && <LessonResult lesson={lesson} />}

      <footer>
        <span>Manim visuals</span><span>ElevenLabs voice</span><span>Dynamic adapters</span>
      </footer>
    </main>
  );
}

export function LessonResult({ lesson }: { lesson: LessonJob }) {
  if (lesson.status === "queued" || lesson.status === "running") {
    return (
      <section className="result-card progress-card" aria-live="polite">
        <div className="orbital-loader"><span>Σ</span></div>
        <div>
          <p className="result-kicker">{lesson.status === "queued" ? "Queued" : "Building your lesson"}</p>
          <h2>{lesson.status === "queued" ? "Waiting for a render slot" : "Sketching the proof, frame by frame"}</h2>
          <p>The video and narration are assembled independently, so a voice outage never loses the lesson.</p>
        </div>
      </section>
    );
  }

  if (lesson.status === "failed") {
    return (
      <section className="result-card error-card" role="alert">
        <p className="result-kicker">Lesson failed</p>
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
    <section className="result-card lesson-card" aria-live="polite">
      <div className="result-heading">
        <div>
          <p className="result-kicker">Your visual explanation</p>
          <h2>{heading}</h2>
        </div>
        <span className={`status-dot status-${lesson.narration_status}`}>
          {lesson.narration_status === "ready" ? "Voice + captions" : "Silent playback"}
        </span>
      </div>

      {playableVideo && (
        <div className="video-frame">
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
          <span className="equation-stamp">a² + b² = c²</span>
        </div>
      )}

      {!playableVideo && lesson.status === "partial" && (
        <div className="partial-placeholder">Visual render unavailable—your written lesson is preserved below.</div>
      )}

      {lesson.narration_status === "unavailable" && playableVideo && (
        <p className="fallback-note">Narration could not be attached. The complete silent video is ready to watch.</p>
      )}

      <div className="lesson-details">
        <article>
          <span className="detail-number">01</span>
          <h3>Explanation</h3>
          <p>{lesson.explanation ?? "The visual lesson is ready. A written explanation will appear when the model pipeline is connected."}</p>
        </article>
        <article>
          <span className="detail-number">02</span>
          <h3>Generated scene</h3>
          <pre><code>{lesson.generated_code ?? "# Manim source will appear here"}</code></pre>
        </article>
      </div>
    </section>
  );
}

const delay = (milliseconds: number) =>
  new Promise<void>((resolve) => window.setTimeout(resolve, milliseconds));
