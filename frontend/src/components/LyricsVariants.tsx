import type { LyricApproach, LyricVariant } from '../types/api';

export const APPROACH_LABELS: Record<LyricApproach, string> = {
  story: '故事叙述版',
  emotion: '情绪表达版',
  imagery: '意象表达版',
};

export default function LyricsVariants({ variants }: { variants: LyricVariant[] }) {
  return (
    <div className="variants">
      {variants.map((variant) => (
        <article key={variant.id} className="variant">
          <header>
            <span className="badge">{APPROACH_LABELS[variant.approach]}</span>
            {variant.title && <h3>{variant.title}</h3>}
          </header>
          <pre>{variant.text}</pre>
        </article>
      ))}
    </div>
  );
}
