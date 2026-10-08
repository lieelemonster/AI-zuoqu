import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError } from '../api/client';
import { createMusicJob, getMusicJob } from '../api/music';
import type { MusicJobCreate, MusicJobView } from '../types/api';

/** snapshot 记录提交时的创作信息与歌词，用来判断结果是否与当前内容一致。 */
export interface TrackedJob {
  view: MusicJobView;
  snapshot: string;
}

const POLL_MS = 1000;
const SLOW_MS = 90_000;
const MAX_POLL_FAILURES = 5;

function jobFailure(view: MusicJobView): ApiError {
  return new ApiError({
    code: view.errorCode ?? 'JOB_FAILED',
    message: `音乐生成失败：${view.errorMessage ?? '未知原因'}`,
    retryable: true,
    fields: [],
  }, 0);
}

/**
 * 只有“当前等待的任务”能更新界面：新提交会取代旧任务，旧任务的提交或查询结果晚到时直接丢弃；
 * 失败时保留上一次成功的结果。
 */
export function useMusicJob() {
  const [pending, setPendingState] = useState<TrackedJob | null>(null);
  const [result, setResult] = useState<TrackedJob | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [submitting, setSubmitting] = useState(false);
  const [slow, setSlow] = useState(false);
  const pendingRef = useRef<TrackedJob | null>(null);
  const submitToken = useRef(0);

  const setPending = useCallback((job: TrackedJob | null) => {
    pendingRef.current = job;
    setPendingState(job);
  }, []);

  const settle = useCallback((job: TrackedJob) => {
    if (job.view.status === 'succeeded') {
      setResult(job);
      setPending(null);
    } else if (job.view.status === 'failed') {
      setError(jobFailure(job.view));
      setPending(null);
    } else {
      setPending(job);
    }
  }, [setPending]);

  const submit = useCallback(async (payload: MusicJobCreate, snapshot: string) => {
    const token = ++submitToken.current;
    setSubmitting(true);
    setError(null);
    try {
      const view = await createMusicJob(payload);
      if (token === submitToken.current) settle({ view, snapshot });
    } catch (caught) {
      if (token === submitToken.current) setError(caught);
    } finally {
      if (token === submitToken.current) setSubmitting(false);
    }
  }, [settle]);

  const pendingId = pending?.view.id ?? null;

  useEffect(() => {
    if (!pendingId) return;
    let active = true;
    let failures = 0;
    let timer = 0;
    const startedAt = Date.now();
    const controller = new AbortController();
    setSlow(false);
    async function poll() {
      try {
        const view = await getMusicJob(pendingId!, controller.signal);
        const current = pendingRef.current;
        if (!active || current?.view.id !== view.id) return;
        failures = 0;
        settle({ view, snapshot: current.snapshot });
        if (view.status === 'succeeded' || view.status === 'failed') return;
        setSlow(Date.now() - startedAt > SLOW_MS);
      } catch (caught) {
        if (!active) return;
        failures += 1;
        if (failures >= MAX_POLL_FAILURES) {
          setError(caught);
          setPending(null);
          return;
        }
      }
      timer = window.setTimeout(poll, POLL_MS);
    }
    timer = window.setTimeout(poll, POLL_MS / 2);
    return () => { active = false; window.clearTimeout(timer); controller.abort(); };
  }, [pendingId, settle, setPending]);

  return { pending, result, error, submitting, slow, submit };
}
