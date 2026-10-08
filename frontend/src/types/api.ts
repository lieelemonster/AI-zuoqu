export interface PresetOption {
  id: string;
  name: string;
}

export interface Presets {
  themes: PresetOption[];
  emotions: PresetOption[];
  styles: PresetOption[];
}

export interface CreativeInput {
  themeId: string;
  emotionId: string;
  styleId: string;
  story: string;
}

export type LyricApproach = 'story' | 'emotion' | 'imagery';

export interface LyricVariant {
  id: string;
  approach: LyricApproach;
  title: string;
  text: string;
}

export interface LyricsResponse {
  variants: LyricVariant[];
  modelId: string;
  promptVersion: string;
}

export interface MusicJobCreate {
  requestId: string;
  sourceRevision: number;
  input: CreativeInput;
  lyrics: string;
  selectedVariantId: string | null;
}

export type JobStatus = 'queued' | 'running' | 'succeeded' | 'failed';
export type JobStage = 'queued' | 'planning' | 'composing' | 'rendering' | 'encoding' | 'checking' | 'done';

export interface MusicJobView {
  id: string;
  status: JobStatus;
  stage: JobStage;
  errorCode: string | null;
  errorMessage: string | null;
  durationSeconds: number | null;
  audioUrl: string | null;
  downloadUrl: string | null;
}

export interface ApiErrorBody {
  code: string;
  message: string;
  retryable: boolean;
  fields: string[];
}
