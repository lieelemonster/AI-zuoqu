import type { LyricApproach, LyricVariant } from '../types/api';

export const APPROACH_LABELS: Record<LyricApproach, string> = {
  story: '故事叙述版',
  emotion: '情绪表达版',
  imagery: '意象表达版',
};

interface Props {
  variants: LyricVariant[];
  selectedId: string | null;
  editedIds: string[];
  onSelect: (id: string) => void;
}

export default function LyricsVariants({ variants, selectedId, editedIds, onSelect }: Props) {
  return (
    <div className="variants" role="radiogroup" aria-label="选择用于作曲的歌词版本">
      {variants.map((variant) => {
        const selected = variant.id === selectedId;
        return (
          <article key={variant.id} className={`variant${selected ? ' selected' : ''}`}>
            <header>
              <div className="variant-tags">
                <span className="badge">{APPROACH_LABELS[variant.approach]}</span>
                {editedIds.includes(variant.id) && <span className="badge edited">已修改</span>}
              </div>
              {variant.title && <h3>{variant.title}</h3>}
            </header>
            <pre>{variant.text}</pre>
            <button
              type="button"
              role="radio"
              aria-checked={selected}
              className={selected ? 'select-button selected' : 'select-button'}
              onClick={() => onSelect(variant.id)}
            >
              {selected ? '✓ 正在编辑这一版' : '选用这一版'}
            </button>
          </article>
        );
      })}
    </div>
  );
}
