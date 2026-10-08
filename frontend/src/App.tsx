import { useCallback, useEffect, useRef, useState } from 'react';
import { generateLyrics, getPresets } from './api/creative';
import { getHealth } from './api/health';
import { ApiError } from './api/client';
import { createMusicJob, getMusicJob, newRequestId } from './api/music';
import CreativeForm from './components/CreativeForm';
import ErrorNotice from './components/ErrorNotice';
import LyricsEditor from './components/LyricsEditor';
import LyricsVariants from './components/LyricsVariants';
import MusicPanel from './components/MusicPanel';
import type { CreativeInput, LyricVariant, MusicJobCreate, MusicJobView, Presets } from './types/api';

type Connection = 'checking' | 'connected' | 'failed';

const EMPTY_INPUT: CreativeInput = { themeId: '', emotionId: '', styleId: '', story: '' };

function jobFailure(view: MusicJobView): ApiError {
  return new ApiError({
    code: view.errorCode ?? 'JOB_FAILED',
    message: `音乐生成失败：${view.errorMessage ?? '未知原因'}`,
    retryable: true,
    fields: [],
  }, 0);
}

export default function App() {
  const [connection, setConnection] = useState<Connection>('checking');
  const [presets, setPresets] = useState<Presets | null>(null);
  const [presetsError, setPresetsError] = useState<unknown>(null);
  const [input, setInput] = useState<CreativeInput>(EMPTY_INPUT);
  const [variants, setVariants] = useState<LyricVariant[]>([]);
  const [lyricsBusy, setLyricsBusy] = useState(false);
  const [lyricsError, setLyricsError] = useState<unknown>(null);
  const lyricsRequest = useRef(0);

  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [switchedNotice, setSwitchedNotice] = useState(false);
  const [revision, setRevision] = useState(0);
  const [musicSubmitting, setMusicSubmitting] = useState(false);
  const [musicError, setMusicError] = useState<unknown>(null);
  const [pendingJob, setPendingJob] = useState<MusicJobView | null>(null);
  const [slowJob, setSlowJob] = useState(false);
  const [result, setResult] = useState<MusicJobView | null>(null);
  const pendingJobId = pendingJob?.id ?? null;

  useEffect(() => {
    if (!pendingJobId) return;
    let active = true;
    let failures = 0;
    let timer = 0;
    const startedAt = Date.now();
    const controller = new AbortController();
    setSlowJob(false);
    async function poll() {
      try {
        const view = await getMusicJob(pendingJobId!, controller.signal);
        if (!active) return;
        failures = 0;
        if (view.status === 'succeeded') {
          setResult(view);
          setPendingJob(null);
          return;
        }
        if (view.status === 'failed') {
          setMusicError(jobFailure(view));
          setPendingJob(null);
          return;
        }
        setPendingJob(view);
        setSlowJob(Date.now() - startedAt > 90_000);
      } catch (error) {
        if (!active) return;
        failures += 1;
        if (failures >= 5) {
          setMusicError(error);
          setPendingJob(null);
          return;
        }
      }
      timer = window.setTimeout(poll, 1000);
    }
    timer = window.setTimeout(poll, 500);
    return () => { active = false; window.clearTimeout(timer); controller.abort(); };
  }, [pendingJobId]);

  const loadPresets = useCallback((signal?: AbortSignal) => {
    setPresetsError(null);
    getPresets(signal)
      .then((data) => { setPresets(data); setConnection('connected'); })
      .catch((error: unknown) => { if (!signal?.aborted) setPresetsError(error); });
  }, []);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 5000);
    getHealth(controller.signal)
      .then(() => { if (active) setConnection('connected'); })
      .catch(() => { if (active) setConnection('failed'); });
    loadPresets();
    return () => { active = false; window.clearTimeout(timeout); controller.abort(); };
  }, [loadPresets]);

  const editedIds = variants.filter((v) => drafts[v.id] !== undefined && drafts[v.id] !== v.text).map((v) => v.id);
  const selected = variants.find((v) => v.id === selectedId) ?? null;
  const draftText = selected ? drafts[selected.id] ?? selected.text : '';

  function changeInput(next: CreativeInput) {
    setInput(next);
    setRevision((r) => r + 1);
  }

  async function requestLyrics() {
    if (editedIds.length > 0 && !window.confirm('重新生成歌词会替换当前三版歌词，你对歌词的修改也会丢失。确定继续吗？')) return;
    const id = ++lyricsRequest.current;
    setLyricsBusy(true);
    setLyricsError(null);
    try {
      const result = await generateLyrics({ ...input, story: input.story.trim() });
      if (id !== lyricsRequest.current) return;
      setVariants(result.variants);
      setDrafts({});
      setSelectedId(null);
      setSwitchedNotice(false);
      setRevision((r) => r + 1);
    } catch (error) {
      if (id === lyricsRequest.current) setLyricsError(error);
    } finally {
      if (id === lyricsRequest.current) setLyricsBusy(false);
    }
  }

  function selectVariant(id: string) {
    if (id === selectedId) return;
    setSwitchedNotice(selectedId !== null);
    setSelectedId(id);
    setMusicError(null);
    setRevision((r) => r + 1);
  }

  function changeDraft(text: string) {
    if (!selected) return;
    setDrafts((current) => ({ ...current, [selected.id]: text }));
    setSwitchedNotice(false);
    setRevision((r) => r + 1);
  }

  function resetDraft() {
    if (!selected) return;
    setDrafts((current) => {
      const next = { ...current };
      delete next[selected.id];
      return next;
    });
    setRevision((r) => r + 1);
  }

  async function submitMusic() {
    if (!selected || !draftText.trim() || musicSubmitting || pendingJob) return;
    const payload: MusicJobCreate = {
      requestId: newRequestId(),
      sourceRevision: revision,
      input: { ...input, story: input.story.trim() },
      lyrics: draftText.trim(),
      selectedVariantId: selected.id,
    };
    setMusicSubmitting(true);
    setMusicError(null);
    try {
      const view = await createMusicJob(payload);
      if (view.status === 'succeeded') setResult(view);
      else if (view.status === 'failed') setMusicError(jobFailure(view));
      else setPendingJob(view);
    } catch (error) {
      setMusicError(error);
    } finally {
      setMusicSubmitting(false);
    }
  }

  const status = {
    checking: '正在连接后端…',
    connected: '后端已连接',
    failed: '后端未连接，请启动后端后刷新页面',
  }[connection];

  return (
    <main>
      <header className="page-header">
        <div>
          <h1>AI 写词与作曲</h1>
          <p className="intro">选择主题、情绪和风格，生成三版中文歌词，再生成约 1 分钟的钢琴旋律与伴奏小样。</p>
        </div>
        <p className="status" role="status"><span className={`dot ${connection}`} aria-hidden="true" />{status}</p>
      </header>

      <section className="panel" aria-labelledby="creative-title">
        <h2 id="creative-title"><span className="step">1</span>创作信息</h2>
        {presets ? (
          <CreativeForm presets={presets} value={input} onChange={changeInput} onSubmit={requestLyrics} busy={lyricsBusy} />
        ) : presetsError ? (
          <ErrorNotice error={presetsError} onRetry={() => loadPresets()} retryLabel="重新加载" />
        ) : (
          <p className="muted">正在加载选项…</p>
        )}
        {lyricsError !== null && <ErrorNotice error={lyricsError} onRetry={lyricsBusy ? undefined : requestLyrics} />}
      </section>

      {(variants.length > 0 || lyricsBusy) && (
        <section className="panel" aria-labelledby="lyrics-title" aria-busy={lyricsBusy}>
          <h2 id="lyrics-title"><span className="step">2</span>歌词</h2>
          {lyricsBusy && <p className="waiting" role="status"><span className="spinner" aria-hidden="true" />歌词生成中，通常需要十几秒到一分钟…</p>}
          {variants.length > 0 && (
            <>
              <p className="muted section-tip">选择一版用于作曲，可在下方直接修改。</p>
              <LyricsVariants variants={variants} selectedId={selectedId} editedIds={editedIds} onSelect={selectVariant} />
            </>
          )}
          {selected && (
            <LyricsEditor
              variant={selected}
              text={draftText}
              edited={editedIds.includes(selected.id)}
              switchedNotice={switchedNotice}
              busy={musicSubmitting || pendingJob !== null}
              onChange={changeDraft}
              onReset={resetDraft}
              onGenerate={submitMusic}
            />
          )}
        </section>
      )}

      {(pendingJob || result || musicError !== null) && (
        <section className="panel" aria-labelledby="music-title" aria-busy={pendingJob !== null}>
          <h2 id="music-title"><span className="step">3</span>音乐小样</h2>
          <MusicPanel pending={pendingJob} slow={slowJob} result={result} error={musicError} onRetry={submitMusic} />
        </section>
      )}
    </main>
  );
}
