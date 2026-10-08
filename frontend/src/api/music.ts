import type { MusicJobCreate, MusicJobView } from '../types/api';
import { requestJson } from './client';

export function newRequestId(): string {
  return `req_${crypto.randomUUID().replaceAll('-', '')}`;
}

export function createMusicJob(payload: MusicJobCreate, signal?: AbortSignal): Promise<MusicJobView> {
  return requestJson<MusicJobView>('/api/music-jobs', { method: 'POST', body: payload, signal });
}

export function getMusicJob(id: string, signal?: AbortSignal): Promise<MusicJobView> {
  return requestJson<MusicJobView>(`/api/music-jobs/${encodeURIComponent(id)}`, { signal });
}
