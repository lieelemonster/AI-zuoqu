import { useState, type FormEvent } from 'react';
import type { CreativeInput, PresetOption, Presets } from '../types/api';

export const STORY_MAX_LENGTH = 500;

type RequiredField = 'themeId' | 'emotionId' | 'styleId';

const GROUPS: { field: RequiredField; key: keyof Presets; label: string }[] = [
  { field: 'themeId', key: 'themes', label: '主题' },
  { field: 'emotionId', key: 'emotions', label: '情绪' },
  { field: 'styleId', key: 'styles', label: '音乐风格' },
];

interface Props {
  presets: Presets;
  value: CreativeInput;
  onChange: (value: CreativeInput) => void;
  onSubmit: () => void;
  busy: boolean;
}

function OptionGroup({ name, label, options, selected, missing, onSelect }: {
  name: string;
  label: string;
  options: PresetOption[];
  selected: string;
  missing: boolean;
  onSelect: (id: string) => void;
}) {
  return (
    <fieldset className={`option-group${missing ? ' missing' : ''}`}>
      <legend>{label}<span className="required">必选</span></legend>
      <div className="chips">
        {options.map((option) => (
          <label key={option.id} className={`chip${selected === option.id ? ' selected' : ''}`}>
            <input
              type="radio"
              name={name}
              value={option.id}
              checked={selected === option.id}
              onChange={() => onSelect(option.id)}
            />
            {option.name}
          </label>
        ))}
      </div>
      {missing && <p className="field-error" role="alert">请选择{label}</p>}
    </fieldset>
  );
}

export default function CreativeForm({ presets, value, onChange, onSubmit, busy }: Props) {
  const [attempted, setAttempted] = useState(false);
  const missing = GROUPS.filter((g) => !value[g.field]).map((g) => g.field);

  function submit(event: FormEvent) {
    event.preventDefault();
    setAttempted(true);
    if (missing.length === 0 && !busy) onSubmit();
  }

  return (
    <form className="creative-form" onSubmit={submit} noValidate>
      {GROUPS.map((group) => (
        <OptionGroup
          key={group.field}
          name={group.field}
          label={group.label}
          options={presets[group.key]}
          selected={value[group.field]}
          missing={attempted && missing.includes(group.field)}
          onSelect={(id) => onChange({ ...value, [group.field]: id })}
        />
      ))}
      <label className="story">
        <span className="story-label">故事描述<span className="optional">选填</span></span>
        <textarea
          value={value.story}
          maxLength={STORY_MAX_LENGTH}
          rows={4}
          placeholder="可以补充人物、经历、场景或想表达的内容，例如：毕业那天和好朋友在操场看最后一次日落"
          onChange={(event) => onChange({ ...value, story: event.target.value })}
        />
        <span className="counter">{value.story.length}/{STORY_MAX_LENGTH}</span>
      </label>
      <div className="actions">
        <button type="submit" className="primary" disabled={busy}>
          {busy ? '歌词生成中…' : '生成歌词'}
        </button>
        {attempted && missing.length > 0 && (
          <span className="hint">还需选择：{GROUPS.filter((g) => missing.includes(g.field)).map((g) => g.label).join('、')}</span>
        )}
      </div>
    </form>
  );
}
