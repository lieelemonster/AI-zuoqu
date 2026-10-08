"""加载 backend/config 中的预设与风格规则，并按稳定 ID 查找。"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.base import ApiModel
from app.schemas.input import CreativeInput
from app.schemas.plan import MAX_BPM, MIN_BPM, Key, Mode, MusicPlan, PlanSection, SectionType

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"
CHORD_PATTERN = r"^[1-7](:7|:M)?$"
Accompaniment = Literal["sustain", "block", "arpeggio", "broken", "fingerpick", "pulse", "offbeat", "stab"]


class UnknownPresetError(ValueError):
    """预设 ID 不存在。"""


class PresetOption(ApiModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1)


class Presets(ApiModel):
    version: int
    themes: list[PresetOption]
    emotions: list[PresetOption]
    styles: list[PresetOption]


class ChordPattern(ApiModel):
    id: str
    for_: list[SectionType] = Field(alias="for", min_length=1)
    chords: list[str] = Field(min_length=1)
    beats_per_chord: Literal[2, 4] = 4

    @model_validator(mode="after")
    def _chords_format(self) -> "ChordPattern":
        bad = [c for c in self.chords if not re.match(CHORD_PATTERN, c)]
        if bad:
            raise ValueError(f"和弦模板 {self.id} 含无法识别的和弦 {bad}")
        return self


class RhythmPattern(ApiModel):
    id: str
    for_: list[SectionType] = Field(alias="for", min_length=1)
    grid: Literal[8, 16]
    notes_per_bar: list[int] = Field(min_length=2, max_length=2)
    phrase_end_beats: float = Field(ge=0, le=4)
    syncopation: float = Field(ge=0, le=1)
    hook: bool = False
    accompaniment: Accompaniment


class EmotionRule(ApiModel):
    mode: Mode
    bpm_offset: int = Field(ge=-20, le=20)
    velocity_offset: int = Field(ge=-20, le=20)
    chorus_lift: int = Field(ge=0, le=7)


class StyleConfig(ApiModel):
    style_id: str
    version: int
    bpm_range: list[int] = Field(min_length=2, max_length=2)
    default_bpm: int
    modes: list[Mode] = Field(min_length=1)
    default_keys: dict[Mode, Key]
    melody_range: list[int] = Field(min_length=2, max_length=2)
    melody_scale: Literal["diatonic", "pentatonic"]
    rhythmic_melody: bool = False
    chorus_lift_max: int = Field(ge=0, le=7)
    chord_patterns: list[ChordPattern] = Field(min_length=1)
    rhythm_patterns: list[RhythmPattern] = Field(min_length=1)
    default_sections: list[PlanSection] = Field(min_length=2)

    def chord_pattern(self, pattern_id: str) -> ChordPattern | None:
        return next((p for p in self.chord_patterns if p.id == pattern_id), None)

    def rhythm_pattern(self, pattern_id: str) -> RhythmPattern | None:
        return next((p for p in self.rhythm_patterns if p.id == pattern_id), None)

    def template_errors(self, sections: list[PlanSection]) -> list[str]:
        """返回规划段落中引用不存在或不适用模板的问题。"""
        errors = []
        for i, section in enumerate(sections):
            chord = self.chord_pattern(section.chord_pattern_id)
            rhythm = self.rhythm_pattern(section.rhythm_pattern_id)
            if chord is None:
                errors.append(f"sections.{i}.chordPatternId：风格 {self.style_id} 中没有和弦模板 {section.chord_pattern_id}")
            elif section.type not in chord.for_:
                errors.append(f"sections.{i}.chordPatternId：和弦模板 {chord.id} 不适用于 {section.type} 段落")
            if rhythm is None:
                errors.append(f"sections.{i}.rhythmPatternId：风格 {self.style_id} 中没有节奏模板 {section.rhythm_pattern_id}")
            elif section.type not in rhythm.for_:
                errors.append(f"sections.{i}.rhythmPatternId：节奏模板 {rhythm.id} 不适用于 {section.type} 段落")
        return errors

    @model_validator(mode="after")
    def _self_consistent(self) -> "StyleConfig":
        low, high = self.bpm_range
        if not (MIN_BPM <= low <= self.default_bpm <= high <= MAX_BPM):
            raise ValueError(f"风格 {self.style_id} 的 BPM 范围或默认 BPM 不合法")
        if set(self.default_keys) != set(self.modes):
            raise ValueError(f"风格 {self.style_id} 需要为每种调式提供默认调")
        ids = [p.id for p in self.chord_patterns] + [p.id for p in self.rhythm_patterns]
        if len(ids) != len(set(ids)):
            raise ValueError(f"风格 {self.style_id} 的模板 ID 重复")
        errors = self.template_errors(self.default_sections)
        if errors:
            raise ValueError("；".join(errors))
        return self


class StylesFile(ApiModel):
    version: int
    notes: str = ""
    emotions: dict[str, EmotionRule]
    styles: list[StyleConfig]


class CompositionConfig(ApiModel):
    """成品时长范围、钢琴尾音预算与编码参数。"""

    version: int
    target_seconds: float = Field(gt=0)
    min_seconds: float = Field(gt=0)
    max_seconds: float = Field(gt=0)
    tail_seconds: float = Field(ge=0, le=5)
    mp3_bitrate: str = Field(pattern=r"^\d{2,3}k$")
    target_peak_dbfs: float = Field(le=0)

    @model_validator(mode="after")
    def _ordered(self) -> "CompositionConfig":
        if not self.min_seconds < self.target_seconds < self.max_seconds:
            raise ValueError("需满足 minSeconds < targetSeconds < maxSeconds")
        return self


@lru_cache
def load_composition() -> CompositionConfig:
    return CompositionConfig.model_validate(
        json.loads((CONFIG_DIR / "composition.json").read_text(encoding="utf-8"))
    )


@lru_cache
def load_presets() -> Presets:
    return Presets.model_validate(json.loads((CONFIG_DIR / "presets.json").read_text(encoding="utf-8")))


@lru_cache
def load_styles() -> StylesFile:
    styles = StylesFile.model_validate(json.loads((CONFIG_DIR / "styles.json").read_text(encoding="utf-8")))
    presets = load_presets()
    style_ids = {s.style_id for s in styles.styles}
    if style_ids != {s.id for s in presets.styles}:
        raise ValueError("styles.json 中的风格必须与 presets.json 的风格一一对应")
    if set(styles.emotions) != {e.id for e in presets.emotions}:
        raise ValueError("styles.json 中的情绪规则必须覆盖 presets.json 的全部情绪")
    return styles


def _require(kind: str, value: str, options: list[PresetOption]) -> None:
    if value not in {o.id for o in options}:
        raise UnknownPresetError(f"未知的{kind} ID：{value}")


def validate_creative_input(data: CreativeInput) -> CreativeInput:
    presets = load_presets()
    _require("主题", data.theme_id, presets.themes)
    _require("情绪", data.emotion_id, presets.emotions)
    _require("风格", data.style_id, presets.styles)
    return data


def get_style(style_id: str) -> StyleConfig:
    for style in load_styles().styles:
        if style.style_id == style_id:
            return style
    raise UnknownPresetError(f"未知的风格 ID：{style_id}")


def get_emotion_rule(emotion_id: str) -> EmotionRule:
    rule = load_styles().emotions.get(emotion_id)
    if rule is None:
        raise UnknownPresetError(f"未知的情绪 ID：{emotion_id}")
    return rule


def default_plan(style_id: str, emotion_id: str, seed: int) -> MusicPlan:
    """风格默认规划，按情绪调整调式、速度和副歌升高幅度。"""
    style = get_style(style_id)
    emotion = get_emotion_rule(emotion_id)
    mode = emotion.mode if emotion.mode in style.modes else style.modes[0]
    low, high = style.bpm_range
    return MusicPlan(
        bpm=min(max(style.default_bpm + emotion.bpm_offset, low), high),
        key=style.default_keys[mode],
        mode=mode,
        sections=[s.model_copy() for s in style.default_sections],
        melody_range=list(style.melody_range),
        chorus_lift_semitones=min(emotion.chorus_lift, style.chorus_lift_max),
        seed=seed,
    )


def plan_errors(plan: MusicPlan, style_id: str) -> list[str]:
    """规划需引用该风格已有模板，且速度、调式、音区在风格允许范围内。"""
    style = get_style(style_id)
    errors = style.template_errors(plan.sections)
    low, high = style.bpm_range
    if not low <= plan.bpm <= high:
        errors.append(f"bpm：风格 {style_id} 允许 {low}～{high}，收到 {plan.bpm}")
    if plan.mode not in style.modes:
        errors.append(f"mode：风格 {style_id} 不支持 {plan.mode}")
    r_low, r_high = style.melody_range
    if plan.melody_range[0] < r_low - 5 or plan.melody_range[1] > r_high + 5:
        errors.append(f"melodyRange：超出风格 {style_id} 允许的音区 {r_low - 5}～{r_high + 5}")
    if plan.chorus_lift_semitones > style.chorus_lift_max:
        errors.append(f"chorusLiftSemitones：风格 {style_id} 最多升高 {style.chorus_lift_max} 个半音")
    return errors


def main() -> int:
    presets = load_presets()
    styles = load_styles()
    for title, options in (("主题", presets.themes), ("情绪", presets.emotions), ("风格", presets.styles)):
        print(f"{title}（{len(options)}）：" + "、".join(f"{o.name}[{o.id}]" for o in options))
    print()
    ok = True
    names = {o.id: o.name for o in presets.styles}
    for style in styles.styles:
        plan = default_plan(style.style_id, "sweet", seed=1)
        errors = plan_errors(plan, style.style_id)
        bars = sum(s.bars for s in plan.sections)
        mark = "✅" if not errors else "❌"
        ok &= not errors
        print(
            f"{mark} {names[style.style_id]}[{style.style_id}]：和弦模板 {len(style.chord_patterns)} 个、"
            f"节奏模板 {len(style.rhythm_patterns)} 个；默认规划 {plan.bpm} BPM {plan.key} {plan.mode}，"
            f"{bars} 小节约 {bars * 4 * 60 / plan.bpm:.1f} 秒，模板引用全部可找到"
            if not errors else f"{mark} {style.style_id}：{errors}"
        )
    sad = default_plan("pop", "sad", seed=1)
    print(f"\n情绪影响示例：流行＋悲伤 → {sad.bpm} BPM {sad.key} {sad.mode}")
    try:
        get_style("jazz")
    except UnknownPresetError as exc:
        print(f"✅ 未知风格被拒绝：{exc}")
    else:
        ok = False
        print("❌ 未知风格 jazz 未被拒绝")
    print("\n全部检查符合预期。" if ok else "\n存在不符合预期的检查。")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
