import type { LyricVariant } from '../types/api';
import { APPROACH_LABELS } from './LyricsVariants';

export const LYRICS_MAX_LENGTH = 2000;

interface Props {
  variant: LyricVariant;
  text: string;
  edited: boolean;
  switchedNotice: boolean;
  busy: boolean;
  onChange: (text: string) => void;
  onReset: () => void;
  onGenerate: () => void;
}

export default function LyricsEditor({ variant, text, edited, switchedNotice, busy, onChange, onReset, onGenerate }: Props) {
  const empty = text.trim().length === 0;
  const lines = text.split('\n').filter((line) => line.trim()).length;
  const name = `${APPROACH_LABELS[variant.approach]}${variant.title ? `《${variant.title}》` : ''}`;
  return (
    <div className="editor">
      {switchedNotice && <p className="switch-notice" role="status">已切换为编辑：{name}</p>}
      <div className="editor-head">
        <label htmlFor="lyrics-editor">正在编辑：<strong>{name}</strong>{edited && <span className="badge edited">已修改</span>}</label>
        {edited && <button type="button" className="link-button" onClick={onReset}>恢复原文</button>}
      </div>
      <textarea
        id="lyrics-editor"
        value={text}
        maxLength={LYRICS_MAX_LENGTH}
        rows={Math.min(Math.max(lines + 2, 10), 22)}
        onChange={(event) => onChange(event.target.value)}
      />
      <p className="editor-tip">保留 [主歌]、[副歌] 等段落标题，每行是一个乐句。共 {lines} 行，{text.length}/{LYRICS_MAX_LENGTH} 字。</p>
      <div className="actions">
        <button type="button" className="primary" disabled={empty || busy} onClick={onGenerate}>
          {busy ? '提交中…' : '生成音乐小样'}
        </button>
        {empty && <span className="hint">歌词为空，无法生成音乐</span>}
      </div>
    </div>
  );
}
