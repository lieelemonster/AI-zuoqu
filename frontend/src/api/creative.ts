import type { CreativeInput, LyricsResponse, Presets } from '../types/api';
import { requestJson } from './client';

export function getPresets(signal?: AbortSignal): Promise<Presets> {
  return requestJson<Presets>('/api/presets', { signal });
}

/** 歌词生成需等待文本模型，后端最多重试一次，超时设得较长。 */
export function generateLyrics(input: CreativeInput, signal?: AbortSignal): Promise<LyricsResponse> {
  return requestJson<LyricsResponse>('/api/lyrics', { method: 'POST', body: input, signal, timeoutMs: 150000 });
}
