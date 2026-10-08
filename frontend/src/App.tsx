import { useCallback, useEffect, useRef, useState } from 'react';
import { generateLyrics, getPresets } from './api/creative';
import { getHealth } from './api/health';
import CreativeForm from './components/CreativeForm';
import ErrorNotice from './components/ErrorNotice';
import LyricsVariants from './components/LyricsVariants';
import type { CreativeInput, LyricVariant, Presets } from './types/api';

type Connection = 'checking' | 'connected' | 'failed';

const EMPTY_INPUT: CreativeInput = { themeId: '', emotionId: '', styleId: '', story: '' };

export default function App() {
  const [connection, setConnection] = useState<Connection>('checking');
  const [presets, setPresets] = useState<Presets | null>(null);
  const [presetsError, setPresetsError] = useState<unknown>(null);
  const [input, setInput] = useState<CreativeInput>(EMPTY_INPUT);
  const [variants, setVariants] = useState<LyricVariant[]>([]);
  const [lyricsBusy, setLyricsBusy] = useState(false);
  const [lyricsError, setLyricsError] = useState<unknown>(null);
  const lyricsRequest = useRef(0);

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

  async function requestLyrics() {
    const id = ++lyricsRequest.current;
    setLyricsBusy(true);
    setLyricsError(null);
    try {
      const result = await generateLyrics({ ...input, story: input.story.trim() });
      if (id === lyricsRequest.current) setVariants(result.variants);
    } catch (error) {
      if (id === lyricsRequest.current) setLyricsError(error);
    } finally {
      if (id === lyricsRequest.current) setLyricsBusy(false);
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
          <CreativeForm presets={presets} value={input} onChange={setInput} onSubmit={requestLyrics} busy={lyricsBusy} />
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
          {variants.length > 0 && <LyricsVariants variants={variants} />}
        </section>
      )}
    </main>
  );
}
