import type { JobStage, MusicJobView } from '../types/api';
import ErrorNotice from './ErrorNotice';

const STAGES: { stage: JobStage; label: string }[] = [
  { stage: 'queued', label: '排队' },
  { stage: 'planning', label: '规划音乐' },
  { stage: 'composing', label: '生成旋律与伴奏' },
  { stage: 'rendering', label: '钢琴渲染' },
  { stage: 'encoding', label: '编码 MP3' },
  { stage: 'checking', label: '检查成品' },
];

function formatDuration(seconds: number | null): string {
  if (seconds === null) return '';
  const whole = Math.floor(seconds);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, '0')}`;
}

interface Props {
  pending: MusicJobView | null;
  slow: boolean;
  result: MusicJobView | null;
  error: unknown;
  onRetry: () => void;
}

export default function MusicPanel({ pending, slow, result, error, onRetry }: Props) {
  const current = pending ? STAGES.findIndex((s) => s.stage === pending.stage) : -1;
  return (
    <div className="music">
      <p className="music-label">钢琴旋律与伴奏小样，无人声演唱</p>

      {pending && (
        <div className="progress" role="status" aria-live="polite">
          <p className="waiting"><span className="spinner" aria-hidden="true" />音乐生成中：{STAGES[Math.max(current, 0)].label}…</p>
          <ol className="stages">
            {STAGES.map((s, index) => (
              <li key={s.stage} className={index < current ? 'done' : index === current ? 'active' : ''}>{s.label}</li>
            ))}
          </ol>
          {slow && <p className="muted">生成时间比平时长，请确认 worker 已启动（bash scripts/dev.sh worker）。</p>}
        </div>
      )}

      {error !== null && error !== undefined && <ErrorNotice error={error} onRetry={pending ? undefined : onRetry} />}

      {result?.audioUrl && (
        <div className="player">
          <audio key={result.id} controls preload="metadata" src={result.audioUrl}>
            你的浏览器不支持音频播放。
          </audio>
          <div className="player-actions">
            <span className="muted">时长 {formatDuration(result.durationSeconds)} · MP3</span>
            {result.downloadUrl && <a className="secondary" href={result.downloadUrl} download>下载音频</a>}
          </div>
        </div>
      )}
    </div>
  );
}
