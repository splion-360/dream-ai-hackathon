export type LessonStatus = "queued" | "running" | "ready" | "partial" | "failed";

export type NarrationStatus =
  | "not_requested"
  | "pending"
  | "ready"
  | "unavailable";

export interface LessonJob {
  id: string;
  lesson: string;
  status: LessonStatus;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  explanation: string | null;
  generated_code: string | null;
  video_url: string | null;
  silent_video_url: string | null;
  captions_url: string | null;
  narration_status: NarrationStatus;
  diagnostics: Record<string, unknown>;
  error: string | null;
}

export interface CreateLessonInput {
  prompt: string;
}

export interface LessonTransport {
  submitLesson(input: CreateLessonInput): Promise<LessonJob>;
  getLesson(id: string): Promise<LessonJob>;
}

export const isTerminal = (status: LessonStatus): boolean =>
  status === "ready" || status === "partial" || status === "failed";
