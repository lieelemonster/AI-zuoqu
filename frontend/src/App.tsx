import { useCallback, useEffect, useRef, useState, type MouseEvent, type ReactNode } from 'react';
import { generateLyrics, getPresets } from './api/creative';
import { ApiError } from './api/client';
import { getHealth } from './api/health';
import { newRequestId } from './api/music';
import { useMusicJob } from './hooks/useMusicJob';
import type { CreativeInput, LyricVariant, MusicJobCreate, PresetOption, Presets } from './types/api';

type Step = 0 | 1 | 2;
type View = 'create' | 'mine';

interface Card {
  id: string;
  name: string;
  en: string;
  color: string;
}

interface Song {
  id: string;
  title: string;
  styleId: string;
  mood: string;
  theme: string;
  lyrics: string;
  duration: number;
  createdAt: number;
  audioUrl: string;
  downloadUrl: string | null;
}

const LIBRARY_KEY = 'xinpu-songs';
const PALETTE = ['#5ef0e0', '#ffb547', '#a78bfa', '#ff4d6d', '#7ee787', '#ff2bd6', '#facc15', '#60a5fa', '#c4b5fd', '#fb7185'];
const META: Record<string, { en: string; color: string }> = {
  pop: { en: 'POP', color: '#5ef0e0' },
  folk: { en: 'FOLK', color: '#ffb547' },
  guofeng: { en: 'GUFENG', color: '#7ee787' },
  rock: { en: 'ROCK', color: '#ff4d6d' },
  rnb: { en: 'RNB', color: '#ff2bd6' },
  electronic: { en: 'EDM', color: '#60a5fa' },
  rap: { en: 'RAP', color: '#facc15' },
  sweet: { en: 'SWEET', color: '#ff2bd6' },
  happy: { en: 'HAPPY', color: '#facc15' },
  sad: { en: 'BLUE', color: '#60a5fa' },
  missing: { en: 'MISSING', color: '#a78bfa' },
  warm: { en: 'WARM', color: '#ffb547' },
  relaxed: { en: 'EASE', color: '#7ee787' },
  lonely: { en: 'LONE', color: '#818cf8' },
  nostalgic: { en: 'NOSTALGIA', color: '#c4b5fd' },
  passionate: { en: 'BURN', color: '#ff4d6d' },
  hopeful: { en: 'HOPE', color: '#5ef0e0' },
  love: { en: 'LOVE', color: '#ff4d6d' },
  friendship: { en: 'FRIENDS', color: '#facc15' },
  family: { en: 'FAMILY', color: '#ffb547' },
  campus: { en: 'CAMPUS', color: '#60a5fa' },
  dream: { en: 'DREAM', color: '#a78bfa' },
  healing: { en: 'HEAL', color: '#7ee787' },
  memory: { en: 'MEMORY', color: '#c4b5fd' },
  hometown: { en: 'HOMETOWN', color: '#7ee787' },
  travel: { en: 'TRAVEL', color: '#5ef0e0' },
  daily: { en: 'DAILY', color: '#ffb547' },
};
const APPROACH_LABEL = { story: '故事叙述', emotion: '情绪表达', imagery: '意象表达' } as const;

function cardsOf(options: PresetOption[]): Card[] {
  return options.map((option, index) => ({
    id: option.id,
    name: option.name,
    en: META[option.id]?.en ?? option.id.toUpperCase(),
    color: META[option.id]?.color ?? PALETTE[index % PALETTE.length],
  }));
}

function loadSongs(): Song[] {
  try {
    const raw = localStorage.getItem(LIBRARY_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((item): item is Song => !!item && typeof item === 'object' && typeof item.audioUrl === 'string');
  } catch {
    return [];
  }
}

function errorText(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return '生成失败，请重试';
}

const fmtTime = (seconds: number) => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;
const fmtDate = (time: number) => {
  const date = new Date(time);
  return `${date.getMonth() + 1}.${String(date.getDate()).padStart(2, '0')}`;
};

function Wave({ seed, color, n = 24, className = '' }: { seed: number; color: string; n?: number; className?: string }) {
  return (
    <div className={`flex items-end gap-[2px] ${className}`}>
      {Array.from({ length: n }, (_, i) => (
        <span
          key={i}
          className="flex-1 origin-bottom rounded-full"
          style={{
            height: `${18 + Math.abs(Math.sin(i * (0.4 + seed * 0.13) + seed)) * 70 + ((i * (seed + 3) * 7) % 12)}%`,
            background: color,
            opacity: 0.35 + ((i + seed) % 4) * 0.15,
          }}
        />
      ))}
    </div>
  );
}

function ModeTag({ mode }: { mode: 'lyrics' | 'music' }) {
  const [zh, en] = mode === 'lyrics' ? ['作词', 'LYRICS'] : ['作曲', 'MUSIC'];
  return (
    <div className="mode-tag flex items-center gap-1.5 border border-amber-300/50 bg-amber-300/10 px-2.5 py-1.5 font-mono text-xs tracking-[0.1em] text-amber-300">
      <span className="relative flex h-2 w-2">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-300 opacity-60" />
        <span className="relative inline-flex h-2 w-2 rounded-full bg-amber-300" />
      </span>
      <span className="font-sans font-semibold tracking-[0.15em]">{zh}</span>
      <span className="text-amber-300/60">{en}</span>
    </div>
  );
}

function CopyButton({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
        } catch {
          const area = document.createElement('textarea');
          area.value = text;
          document.body.appendChild(area);
          area.select();
          document.execCommand('copy');
          area.remove();
        }
        setDone(true);
        window.setTimeout(() => setDone(false), 1500);
      }}
      className="border border-white/15 px-2.5 py-1 text-xs text-stone-300 transition hover:border-amber-300 hover:text-amber-300"
    >
      {done ? '已复制' : '复制'}
    </button>
  );
}

function OptCard({ card, index, active, big, onClick }: { card: Card; index: number; active: boolean; big?: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`opt-card group relative flex flex-col overflow-hidden rounded-2xl border p-4 text-left transition active:scale-[0.98] ${
        big ? 'col-span-2 min-h-44' : 'min-h-36'
      } ${active ? 'border-amber-300' : 'border-white/10'}`}
      style={{ background: `linear-gradient(140deg, ${card.color}26, transparent 60%), rgba(255,255,255,0.02)` }}
    >
      <span className="pointer-events-none absolute -top-10 -right-10 h-28 w-28 rounded-full blur-2xl" style={{ background: card.color, opacity: 0.25 }} />
      <div className="relative flex items-center justify-end font-mono text-[10px] tracking-[0.2em]">
        <span className="text-stone-500">{card.en}</span>
      </div>
      <div className={`relative mt-auto font-bold ${big ? 'text-4xl' : 'text-2xl'}`}>{card.name}</div>
      <Wave seed={index + 1} color={card.color} n={big ? 40 : 18} className="relative mt-3 h-6" />
    </button>
  );
}

function LyricLines({ text }: { text: string }) {
  return (
    <div className="space-y-1">
      {text.split('\n').map((line, index) => (
        /^\[.*\]$/.test(line) ? (
          <div key={index} className="pt-3 font-sans text-xs tracking-widest text-amber-300">{line.slice(1, -1)}</div>
        ) : (
          <div key={index} className="text-stone-200">{line}</div>
        )
      ))}
    </div>
  );
}

function WavePlayer({ src, color, seed, stacked = false, extra }: {
  src: string | null;
  color: string;
  seed: number;
  stacked?: boolean;
  extra?: ReactNode;
}) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [pos, setPos] = useState(0);
  const [duration, setDuration] = useState(0);
  const count = stacked ? 64 : 56;
  const bars = Array.from({ length: count }, (_, i) => 20 + Math.abs(Math.sin(i * (stacked ? 0.7 : 0.6) + seed)) * (stacked ? 60 : 65) + ((i * (stacked ? 37 : 29)) % (stacked ? 20 : 15)));

  useEffect(() => {
    setPlaying(false);
    setPos(0);
  }, [src]);

  function toggle() {
    const audio = audioRef.current;
    if (!audio) return;
    if (audio.paused) {
      void audio.play();
      setPlaying(true);
    } else {
      audio.pause();
      setPlaying(false);
    }
  }

  function seek(event: MouseEvent<HTMLDivElement>) {
    const audio = audioRef.current;
    if (!audio || !audio.duration) return;
    const rect = event.currentTarget.getBoundingClientRect();
    audio.currentTime = ((event.clientX - rect.left) / rect.width) * audio.duration;
  }

  const length = duration || 0;
  const playButton = (
    <button
      type="button"
      disabled={!src}
      onClick={toggle}
      aria-label={playing ? '暂停' : '播放'}
      className="grid h-14 w-14 shrink-0 place-items-center rounded-full bg-amber-300 text-xl text-stone-900 hover:bg-amber-200 disabled:bg-white/10 disabled:text-stone-500"
    >
      {playing ? '❚❚' : '▶'}
    </button>
  );
  const waveform = (
    <div className={`flex cursor-pointer items-center ${stacked ? 'mt-8 h-24 gap-[3px]' : 'h-14 gap-[2px]'}`} onClick={seek}>
      {bars.map((height, index) => (
        <span
          key={index}
          className="flex-1 rounded-full"
          style={{
            height: `${height}%`,
            background: length > 0 && index / bars.length < pos / length ? color : 'rgba(255,255,255,0.15)',
          }}
        />
      ))}
    </div>
  );
  const times = (
    <div className="mt-1 flex justify-between font-mono text-xs text-stone-500">
      <span>{fmtTime(pos)}</span>
      <span>{fmtTime(length)}</span>
    </div>
  );
  return (
    <div>
      {src && (
        <audio
          ref={audioRef}
          src={src}
          preload="metadata"
          onLoadedMetadata={(event) => setDuration(event.currentTarget.duration || 0)}
          onTimeUpdate={(event) => setPos(event.currentTarget.currentTime)}
          onEnded={() => { setPlaying(false); setPos(0); }}
          onPause={() => setPlaying(false)}
          onPlay={() => setPlaying(true)}
        />
      )}
      {stacked ? (
        <>
          {waveform}
          <div className="mt-3">{times}</div>
          <div className="mt-6 flex items-center gap-3">
            {playButton}
            {extra}
          </div>
        </>
      ) : (
        <div className="flex items-center gap-4">
          {playButton}
          <div className="flex-1">
            {waveform}
            {times}
          </div>
        </div>
      )}
    </div>
  );
}

function SongSheet({ song, color, onClose, onDelete }: { song: Song; color: string; onClose: () => void; onDelete: () => void }) {
  const [confirm, setConfirm] = useState(false);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div data-theme="neon" className="fixed inset-0 z-50 overflow-y-auto bg-stone-950 text-stone-100 animate-[fadeIn_.3s_ease]" style={{ fontFamily: '"Noto Sans SC", system-ui, sans-serif' }}>
      <div className="relative overflow-hidden" style={{ background: `linear-gradient(160deg, ${color}33, transparent 70%)` }}>
        <span className="pointer-events-none absolute -top-24 -right-16 h-72 w-72 rounded-full blur-3xl" style={{ background: color, opacity: 0.25 }} />
        <div className="relative mx-auto max-w-3xl px-6 pb-8 pt-[max(env(safe-area-inset-top),1rem)]">
          <div className="flex items-center justify-between">
            <button type="button" onClick={onClose} className="cy-back text-sm text-stone-400 hover:text-amber-300">← 返回</button>
            <CopyButton text={song.lyrics} />
          </div>
          <div className="mt-10 font-mono text-[10px] tracking-[0.3em]" style={{ color }}>{fmtDate(song.createdAt)}</div>
          <h2 className="mt-2 text-4xl font-bold sm:text-5xl">{song.title}</h2>
          <div className="mt-4 flex flex-wrap gap-2 text-xs">
            {[song.theme, song.mood].filter(Boolean).map((tag) => (
              <span key={tag} className="border border-white/15 px-2.5 py-1 text-stone-300">{tag}</span>
            ))}
          </div>
          <div className="mt-10">
            <WavePlayer src={song.audioUrl} color={color} seed={song.title.length} />
          </div>
          {song.downloadUrl && (
            <a href={song.downloadUrl} download className="mt-4 inline-block border border-white/15 px-5 py-2 text-sm hover:border-white/40">下载 MP3</a>
          )}
        </div>
      </div>
      <div className="mx-auto max-w-3xl px-6 pb-16 pt-8">
        <div className="text-center font-serif text-lg leading-9">
          <LyricLines text={song.lyrics} />
        </div>
        <div className="mt-12 flex justify-center gap-3 border-t border-white/10 pt-6">
          {confirm ? (
            <>
              <button type="button" onClick={() => setConfirm(false)} className="px-3 py-1.5 text-xs text-stone-400 hover:text-white">取消</button>
              <button type="button" onClick={onDelete} className="border border-rose-400/60 px-3 py-1.5 text-xs text-rose-300 hover:bg-rose-400/10">确认删除</button>
            </>
          ) : (
            <button type="button" onClick={() => setConfirm(true)} className="px-3 py-1.5 text-xs text-stone-500 hover:text-rose-300">删除</button>
          )}
        </div>
      </div>
    </div>
  );
}

function MyView({ songs, styleName, onDelete, onCreate }: { songs: Song[]; styleName: (id: string) => string; onDelete: (id: string) => void; onCreate: () => void }) {
  const [openId, setOpenId] = useState<string | null>(null);
  const open = songs.find((song) => song.id === openId) ?? null;
  if (songs.length === 0) {
    return (
      <section className="flex flex-col items-center pt-24 text-center">
        <Wave seed={2} color="#4b4580" n={28} className="h-12 w-48" />
        <h2 className="mt-8 text-2xl font-bold">还没有作品</h2>
        <button type="button" onClick={onCreate} className="mt-8 bg-amber-300 px-8 py-3 font-semibold text-stone-900 hover:bg-amber-200">开始创作</button>
      </section>
    );
  }
  return (
    <section className="animate-[fadeIn_.35s_ease] pt-4">
      <div className="flex items-end justify-between border-b border-white/10 pb-5">
        <div>
          <div className="font-mono text-xs tracking-[0.3em] text-amber-300">LIBRARY</div>
          <h1 className="mt-2 text-3xl font-bold sm:text-4xl">我的作品</h1>
        </div>
        <div className="flex gap-6 text-right font-mono">
          <div className="text-2xl font-bold text-amber-300">{String(songs.length).padStart(2, '0')}</div>
          <div className="text-[10px] tracking-[0.2em] text-stone-500">TRACKS</div>
        </div>
      </div>
      <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3">
        {songs.map((song, index) => {
          const color = META[song.styleId]?.color ?? '#5ef0e0';
          const firstLine = song.lyrics.split('\n').find((line) => line.trim() && !/^\[.*\]$/.test(line));
          return (
            <button
              type="button"
              key={song.id}
              onClick={() => setOpenId(song.id)}
              className="opt-card group relative flex min-h-60 flex-col overflow-hidden rounded-2xl border border-white/10 p-5 text-left transition active:scale-[0.99]"
              style={{ background: `linear-gradient(150deg, ${color}33, transparent 65%), rgba(255,255,255,0.02)` }}
            >
              <span className="pointer-events-none absolute -top-12 -right-12 h-40 w-40 rounded-full blur-3xl" style={{ background: color, opacity: 0.3 }} />
              <div className="relative font-mono text-[10px] tracking-[0.2em] text-stone-500">{String(index + 1).padStart(2, '0')}</div>
              <div className="relative mt-3 text-3xl font-bold" style={{ color }}>{styleName(song.styleId)}</div>
              <div className="relative font-mono text-[10px] tracking-[0.25em] text-stone-400">{META[song.styleId]?.en ?? song.styleId.toUpperCase()}</div>
              <div className="relative mt-auto pt-5">
                <div className="truncate font-serif text-sm text-stone-300">{firstLine}</div>
                <div className="mt-1 truncate text-base font-semibold">{song.title}</div>
                <div className="mt-1 font-mono text-[10px] tracking-[0.15em] text-stone-500">{fmtDate(song.createdAt)} · {fmtTime(song.duration)}</div>
                <Wave seed={index + 2} color={color} n={22} className="mt-3 h-5" />
              </div>
            </button>
          );
        })}
      </div>
      {open && (
        <SongSheet
          song={open}
          color={META[open.styleId]?.color ?? '#5ef0e0'}
          onClose={() => setOpenId(null)}
          onDelete={() => { setOpenId(null); onDelete(open.id); }}
        />
      )}
    </section>
  );
}

function ComposeView({
  busy, queued, done, failed, title, lyrics, audioUrl, downloadUrl, error, onEdit, onRestart,
}: {
  busy: boolean;
  queued: boolean;
  done: boolean;
  failed: boolean;
  title: string;
  lyrics: string;
  audioUrl: string | null;
  downloadUrl: string | null;
  error: string;
  onEdit: () => void;
  onRestart: () => void;
}) {
  const [downloaded, setDownloaded] = useState(false);
  const [showDone, setShowDone] = useState(false);
  const stages = [
    { key: 'queued', label: '排队中' },
    { key: 'running', label: '规划 · 作曲 · 渲染' },
    { key: 'succeeded', label: '完成' },
  ];
  const index = done ? 2 : queued ? 0 : busy ? 1 : -1;
  return (
    <section className="grid gap-6 pt-6 md:grid-cols-[1.5fr_1fr]">
      <div className="space-y-4">
        {busy && (
          <div className="rounded-2xl border border-amber-300/30 bg-amber-300/5 p-5">
            <div className="flex items-center gap-3 text-sm">
              <span className="h-2 w-2 animate-pulse rounded-full bg-amber-300" />
              正在作曲…
            </div>
            <div className="mt-4 flex gap-2">
              {stages.map((item, itemIndex) => (
                <div key={item.key} className="flex-1">
                  <div className={`h-1 rounded-full ${itemIndex <= index ? 'bg-amber-300' : 'bg-white/10'}`} />
                  <div className={`mt-2 text-xs ${itemIndex <= index ? 'text-stone-200' : 'text-stone-600'}`}>{item.label}</div>
                </div>
              ))}
            </div>
          </div>
        )}
        <div className={`rounded-2xl border border-white/10 bg-gradient-to-br from-stone-900 to-stone-950 p-7 ${!done && 'opacity-40'}`}>
          <h2 className="mt-2 font-serif text-3xl font-bold">{title || '未命名'}</h2>
          <WavePlayer
            src={audioUrl}
            color="#5ef0e0"
            seed={title.length + 3}
            stacked
            extra={downloadUrl ? (
              <a
                href={downloadUrl}
                download
                onClick={() => { setDownloaded(true); setShowDone(true); }}
                className="rounded-full border border-white/15 px-5 py-3 text-sm hover:border-white/40"
              >
                {downloaded ? '已下载' : '下载 MP3'}
              </a>
            ) : (
              <button type="button" disabled className="rounded-full border border-white/15 px-5 py-3 text-sm text-stone-500">下载 MP3</button>
            )}
          />
        </div>
        {failed && (
          <div className="rounded-xl border border-rose-400/30 bg-rose-400/5 px-4 py-3 text-sm text-rose-200">
            {error || '生成失败'}
          </div>
        )}
      </div>
      <aside className="rounded-2xl border border-white/10 p-6">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium">歌词</span>
          <div className="flex items-center gap-3">
            <CopyButton text={lyrics} />
            <button type="button" onClick={onEdit} className="text-xs text-amber-300 hover:underline">编辑</button>
          </div>
        </div>
        <div className="mt-4 space-y-1 font-serif leading-8">
          <LyricLines text={lyrics} />
        </div>
      </aside>
      {showDone && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-6 backdrop-blur-sm" onClick={() => setShowDone(false)}>
          <div onClick={(event) => event.stopPropagation()} className="w-full max-w-sm animate-[fadeIn_.3s_ease] rounded-2xl border border-amber-300/40 bg-stone-900 p-6 shadow-[0_0_40px_rgba(94,240,224,0.15)]">
            <div className="text-center text-lg font-semibold">下载完成</div>
            <div className="mt-6 grid grid-cols-2 gap-3">
              <button type="button" onClick={() => setShowDone(false)} className="rounded-xl border border-white/15 py-3.5 text-stone-200 hover:border-white/40">返回</button>
              <button type="button" onClick={onRestart} className="rounded-xl bg-amber-300 py-3.5 font-semibold text-stone-900 hover:bg-amber-200">再作一首</button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

export default function App() {
  const [view, setView] = useState<View>('create');
  const [songs, setSongs] = useState<Song[]>(loadSongs);
  const [presets, setPresets] = useState<Presets | null>(null);
  const [presetsError, setPresetsError] = useState<unknown>(null);
  const [connection, setConnection] = useState('正在连接后端…');
  const [step, setStep] = useState<Step>(0);
  const [sub, setSub] = useState(0);
  const [styleId, setStyleId] = useState('');
  const [moodId, setMoodId] = useState('');
  const [themeId, setThemeId] = useState('');
  const [story, setStory] = useState('');
  const [loadingLyrics, setLoadingLyrics] = useState(false);
  const [lyricsError, setLyricsError] = useState<unknown>(null);
  const [variants, setVariants] = useState<LyricVariant[]>([]);
  const [lyrics, setLyrics] = useState<string[]>([]);
  const [selected, setSelected] = useState(0);
  const [revision, setRevision] = useState(0);
  const music = useMusicJob();

  useEffect(() => {
    const controller = new AbortController();
    getHealth(controller.signal).then(() => setConnection('后端已连接')).catch(() => setConnection('后端未连接'));
    getPresets().then(setPresets).catch((error: unknown) => setPresetsError(error));
    return () => controller.abort();
  }, []);

  useEffect(() => {
    localStorage.setItem(LIBRARY_KEY, JSON.stringify(songs));
  }, [songs]);

  const styles = presets ? cardsOf(presets.styles) : [];
  const moods = presets ? cardsOf(presets.emotions) : [];
  const themes = presets ? cardsOf(presets.themes) : [];
  const styleName = styles.find((item) => item.id === styleId)?.name ?? '';
  const moodName = moods.find((item) => item.id === moodId)?.name ?? '';
  const themeName = themes.find((item) => item.id === themeId)?.name ?? '';
  const currentLyrics = lyrics[selected] ?? '';
  const input: CreativeInput = { themeId, emotionId: moodId, styleId, story: story.trim() };
  const snapshot = JSON.stringify({ input, lyrics: currentLyrics.trim() });

  const savedResultId = useRef('');
  useEffect(() => {
    const viewJob = music.result?.view;
    if (!viewJob?.audioUrl || savedResultId.current === viewJob.id) return;
    savedResultId.current = viewJob.id;
    const song: Song = {
      id: viewJob.id,
      title: `${themeName}${moodName ? '·' + moodName : ''}`,
      styleId,
      mood: moodName,
      theme: themeName,
      lyrics: currentLyrics,
      duration: viewJob.durationSeconds ?? 0,
      createdAt: Date.now(),
      audioUrl: viewJob.audioUrl,
      downloadUrl: viewJob.downloadUrl,
    };
    setSongs((list) => [song, ...list.filter((item) => item.id !== song.id)]);
  }, [music.result, themeName, moodName, styleId, currentLyrics]);

  const loadOptions = useCallback(() => {
    setPresetsError(null);
    getPresets().then(setPresets).catch((error: unknown) => setPresetsError(error));
  }, []);

  async function genLyrics() {
    setLoadingLyrics(true);
    setLyricsError(null);
    try {
      const result = await generateLyrics(input);
      setVariants(result.variants);
      setLyrics(result.variants.map((variant) => variant.text));
      setSelected(0);
      setRevision((value) => value + 1);
      setStep(1);
    } catch (error) {
      setLyricsError(error);
    } finally {
      setLoadingLyrics(false);
    }
  }

  function compose() {
    const variant = variants[selected];
    if (!currentLyrics.trim() || !variant) return;
    const payload: MusicJobCreate = {
      requestId: newRequestId(),
      sourceRevision: revision,
      input,
      lyrics: currentLyrics.trim(),
      selectedVariantId: variant.id,
    };
    setStep(2);
    void music.submit(payload, snapshot);
  }

  function restart() {
    setStyleId('');
    setMoodId('');
    setThemeId('');
    setStory('');
    setVariants([]);
    setLyrics([]);
    setSelected(0);
    setSub(0);
    setStep(0);
  }

  const groups = [styles, moods, themes];
  const chosen = [styleId, moodId, themeId];
  const chosenNames = [styleName, moodName, themeName];
  const busy = music.pending !== null;

  return (
    <div data-theme="neon" className="min-h-screen bg-stone-950 text-stone-100" style={{ fontFamily: '"Noto Sans SC", system-ui, sans-serif' }}>
      <header className="mx-auto flex max-w-5xl items-center gap-6 px-6 pb-3 pt-[max(env(safe-area-inset-top),0.75rem)]">
        <div className="flex shrink-0 items-center gap-3">
          <div className="cy-logo grid h-10 w-10 shrink-0 place-items-center bg-amber-300 text-lg leading-none font-bold text-stone-900">谱</div>
          <div className="leading-tight whitespace-nowrap">
            <div className="text-lg font-semibold tracking-[0.2em]">心谱</div>
            <p className="sr-only" role="status">{connection}</p>
          </div>
        </div>
        <div className="ml-auto">
          {view === 'create' && <ModeTag mode={step === 2 ? 'music' : 'lyrics'} />}
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 pb-32">
        {view === 'mine' && (
          <MyView
            songs={songs}
            styleName={(id) => styles.find((item) => item.id === id)?.name ?? META[id]?.en ?? id}
            onDelete={(id) => setSongs((list) => list.filter((song) => song.id !== id))}
            onCreate={() => setView('create')}
          />
        )}

        {view === 'create' && step === 0 && (
          <section className="mx-auto max-w-3xl pt-2">
            <div className="flex h-8 items-center justify-between">
              {sub > 0 ? (
                <button type="button" onClick={() => setSub(sub - 1)} className="cy-back text-sm text-stone-400 hover:text-amber-300">← 返回</button>
              ) : <span />}
              <div className="flex gap-1.5">
                {chosenNames.slice(0, sub).map((name, index) => (
                  <button type="button" key={index} onClick={() => setSub(index)} className="border border-amber-300/40 bg-amber-300/10 px-2.5 py-1 text-xs text-amber-300">{name}</button>
                ))}
              </div>
            </div>
            <div key={sub} className="animate-[fadeIn_.35s_ease]">
              <div className="mt-6 font-mono text-xs tracking-[0.3em] text-amber-300">{['STYLE', 'MOOD', 'THEME', 'STORY'][sub]}</div>
              <h1 className="mt-2 text-3xl font-bold sm:text-4xl">
                {['请选择您的音乐风格', '这首歌是什么情绪？', '想写关于什么？', '有想讲的故事吗？'][sub]}
                {sub === 3 && <span className="ml-3 inline-block -translate-y-1 border border-white/20 px-2 py-0.5 align-middle text-xs font-normal tracking-widest text-stone-400">可选</span>}
              </h1>
              {!presets && !presetsError && <p className="mt-8 text-stone-400">正在加载选项…</p>}
              {presetsError !== null && (
                <div className="mt-8 rounded-xl border border-rose-400/30 bg-rose-400/5 px-4 py-3 text-sm text-rose-200">
                  {errorText(presetsError)}
                  <button type="button" onClick={loadOptions} className="ml-3 underline">重新加载</button>
                </div>
              )}
              {presets && sub < 3 && (
                <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3">
                  {groups[sub].map((card, index) => (
                    <OptCard
                      key={card.id}
                      card={card}
                      index={index}
                      big={sub === 0 && index === 0}
                      active={chosen[sub] === card.id}
                      onClick={() => {
                        if (sub === 0) setStyleId(card.id);
                        else if (sub === 1) setMoodId(card.id);
                        else setThemeId(card.id);
                        setRevision((value) => value + 1);
                        setSub(sub + 1);
                      }}
                    />
                  ))}
                </div>
              )}
              {presets && sub === 3 && (
                <div className="mt-6">
                  <textarea
                    value={story}
                    onChange={(event) => { setStory(event.target.value.slice(0, 500)); setRevision((value) => value + 1); }}
                    rows={7}
                    maxLength={500}
                    placeholder="可以补充人物、经历、场景或想表达的内容"
                    className="w-full resize-none rounded-2xl border border-white/10 bg-white/[0.03] p-5 outline-none placeholder:text-stone-600 focus:border-amber-300/60"
                  />
                  <div className="mt-2 text-right font-mono text-[10px] text-stone-500">{story.length} / 500</div>
                  <button
                    type="button"
                    disabled={!styleId || !moodId || !themeId || loadingLyrics}
                    onClick={() => { void genLyrics(); }}
                    className="mt-6 w-full rounded-xl bg-amber-300 py-4 font-semibold text-stone-900 transition hover:bg-amber-200 disabled:bg-white/10 disabled:text-stone-500"
                  >
                    {loadingLyrics ? '正在写词…' : '生成三版歌词'}
                  </button>
                  {lyricsError !== null && <p className="mt-3 text-sm text-rose-200">{errorText(lyricsError)}</p>}
                </div>
              )}
            </div>
          </section>
        )}

        {view === 'create' && step === 1 && (
          <section className="pt-6">
            <button type="button" onClick={() => setStep(0)} className="cy-back mb-4 text-sm text-stone-400 hover:text-amber-300">← 返回</button>
            <h2 className="font-serif text-3xl font-bold">选一版，改成你的</h2>
            <div className="mt-5 grid grid-cols-3 border border-white/10 p-1">
              {variants.map((variant, index) => (
                <button
                  type="button"
                  key={variant.id}
                  onClick={() => setSelected(index)}
                  className={`py-2 text-sm transition ${selected === index ? 'bg-amber-300 font-semibold text-stone-900' : 'text-stone-400 hover:text-white'}`}
                >
                  {APPROACH_LABEL[variant.approach]}
                </button>
              ))}
            </div>
            <div className="mt-6 grid gap-6 md:grid-cols-[1.5fr_1fr]">
              <div className="relative rounded-2xl border border-white/10 bg-white/[0.03] p-6">
                <div className="absolute top-4 right-4"><CopyButton text={currentLyrics} /></div>
                <textarea
                  value={currentLyrics}
                  onChange={(event) => {
                    const next = [...lyrics];
                    next[selected] = event.target.value;
                    setLyrics(next);
                    setRevision((value) => value + 1);
                  }}
                  rows={14}
                  className="w-full resize-none bg-transparent pr-14 font-serif text-lg leading-8 outline-none"
                />
              </div>
              <aside className="space-y-4">
                <button
                  type="button"
                  disabled={!currentLyrics.trim() || music.submitting}
                  onClick={compose}
                  className="w-full rounded-xl bg-amber-300 py-3.5 font-semibold text-stone-900 hover:bg-amber-200 disabled:bg-white/10 disabled:text-stone-500"
                >
                  {music.submitting ? '提交中…' : '用这版歌词作曲'}
                </button>
                {!currentLyrics.trim() && <p className="mt-3 text-sm text-rose-200">歌词为空，无法生成音乐</p>}
              </aside>
            </div>
          </section>
        )}

        {view === 'create' && step === 2 && (
          <ComposeView
            busy={busy}
            queued={music.pending?.view.stage === 'queued'}
            done={music.result?.view.audioUrl != null && !busy}
            failed={music.error !== null}
            title={`${themeName}${moodName ? '·' + moodName : ''}`}
            lyrics={currentLyrics}
            audioUrl={music.result?.view.audioUrl ?? null}
            downloadUrl={music.result?.view.downloadUrl ?? null}
            error={music.error ? errorText(music.error) : ''}
            onEdit={() => setStep(1)}
            onRestart={restart}
          />
        )}
      </main>

      <nav className="tabbar fixed inset-x-0 bottom-0 z-40 border-t border-white/10 bg-stone-950/90 pb-[env(safe-area-inset-bottom)] backdrop-blur">
        <div className="mx-auto grid max-w-md grid-cols-2">
          {([['create', '创作', 'CREATE'], ['mine', '我的', 'LIBRARY']] as const).map(([key, label, en]) => (
            <button
              type="button"
              key={key}
              onClick={() => setView(key)}
              aria-current={view === key ? 'page' : undefined}
              className={`relative flex flex-col items-center gap-0.5 py-3 transition ${view === key ? 'text-amber-300' : 'text-stone-500 hover:text-stone-300'}`}
            >
              {view === key && <span className="absolute inset-x-8 top-0 h-0.5 bg-amber-300 shadow-[0_0_10px_currentColor]" />}
              <span className="flex items-center gap-1.5 text-sm font-semibold tracking-[0.2em]">
                {label}
                {key === 'mine' && <span className="font-mono text-[10px] font-normal opacity-70">{songs.length}</span>}
              </span>
              <span className="font-mono text-[9px] tracking-[0.25em] opacity-60">{en}</span>
            </button>
          ))}
        </div>
      </nav>
    </div>
  );
}
