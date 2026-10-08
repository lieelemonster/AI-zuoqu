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

export interface ApiErrorBody {
  code: string;
  message: string;
  retryable: boolean;
  fields: string[];
}
