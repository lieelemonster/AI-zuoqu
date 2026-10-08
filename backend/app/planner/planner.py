"""AI 音乐规划：只允许引用风格配置中已有的模板；无效时最多修复一次，再回退到默认规划。"""

from __future__ import annotations

import json
import logging
from typing import Literal

from pydantic import ConfigDict, Field, ValidationError

from app.composer.arrangement import LyricsLengthError, arrange
from app.lyrics.parser import ParsedLyrics
from app.planner import mock_plan  # noqa: F401  注册离线演示模型的规划用途
from app.presets import (default_plan, get_emotion_rule, get_style, load_composition, load_presets,
                         plan_errors)
from app.providers import ProviderError, TextModelProvider
from app.schemas.base import ApiModel, format_validation_error
from app.schemas.input import CreativeInput
from app.schemas.plan import Key, Mode, MusicPlan, SectionType

logger = logging.getLogger(__name__)

PROMPT_VERSION = "plan-1"
MIN_MELODY_SPAN = 12
PlanSource = Literal["ai", "ai_repaired", "default"]


class _ModelSection(ApiModel):
    model_config = ConfigDict(extra="ignore")
    type: SectionType
    bars: int = Field(ge=1, le=32)
    chord_pattern_id: str
    rhythm_pattern_id: str


class _ModelPlan(ApiModel):
    model_config = ConfigDict(extra="ignore")
    bpm: int
    key: Key
    mode: Mode
    sections: list[_ModelSection]
    melody_range: list[int]
    chorus_lift_semitones: int = 0


class PlanAttempt(ApiModel):
    kind: Literal["initial", "repair"]
    output: dict | None = None
    errors: list[str] = Field(default_factory=list)


class PlanRecord(ApiModel):
    """内部记录：实际使用的规划来源、模型、每次尝试的输出与问题。不展示在用户界面。"""
    source: PlanSource
    model_id: str
    prompt_version: str = PROMPT_VERSION
    attempts: list[PlanAttempt] = Field(default_factory=list)
    fallback_reason: str = ""


def allowed_templates(style_id: str) -> dict:
    style = get_style(style_id)
    low, high = style.melody_range
    return {
        "bpmRange": style.bpm_range,
        "modes": style.modes,
        "defaultKeys": style.default_keys,
        "melodyRange": [low - 5, high + 5],
        "chorusLiftMax": style.chorus_lift_max,
        "chordPatterns": [{"id": p.id, "for": p.for_, "chords": p.chords, "beatsPerChord": p.beats_per_chord}
                          for p in style.chord_patterns],
        "rhythmPatterns": [{"id": p.id, "for": p.for_, "notesPerBar": p.notes_per_bar,
                            "syncopation": p.syncopation, "hook": p.hook, "accompaniment": p.accompaniment}
                           for p in style.rhythm_patterns],
    }


def build_prompts(data: CreativeInput, parsed: ParsedLyrics) -> tuple[str, str]:
    presets = load_presets()
    name = lambda options, value: next(o.name for o in options if o.id == value)  # noqa: E731
    emotion = get_emotion_rule(data.emotion_id)
    system = """你是作曲编排助手。根据歌词结构、主题、情绪和风格，为一段约 1 分钟的钢琴旋律与伴奏小样做简短的音乐规划，只输出 JSON。
规则：
1. chordPatternId 和 rhythmPatternId 只能从“可用模板”中选择，并且模板的 for 列表必须包含该段落的 type。
2. bpm 在 bpmRange 内；mode 在 modes 内；key 为 C、C#、D、Eb、E、F、F#、G、Ab、A、Bb、B 之一；melodyRange 为 [最低音, 最高音] 的 MIDI 音高，在给定范围内且至少相差 12。
3. sections 按顺序为：intro（1～4 小节）、歌词中的各段（verse／chorus／bridge，顺序与歌词一致）、outro（2～4 小节）。歌词段小节数按行数估计，每行约 2 小节。
4. chorusLiftSemitones 为副歌比主歌升高的半音数，0～chorusLiftMax。情绪越激昂、明亮，速度和副歌升高可以越多；忧伤、怀念则速度偏慢、多用小调。
输出格式：{"bpm": 96, "key": "C", "mode": "major", "melodyRange": [60, 79], "chorusLiftSemitones": 2, "sections": [{"type": "intro", "bars": 2, "chordPatternId": "...", "rhythmPatternId": "..."}, ...]}"""
    info = {
        "styleId": data.style_id,
        "emotionId": data.emotion_id,
        "主题": name(presets.themes, data.theme_id),
        "情绪": name(presets.emotions, data.emotion_id),
        "风格": name(presets.styles, data.style_id),
        "情绪建议": {"mode": emotion.mode, "bpmOffset": emotion.bpm_offset, "chorusLift": emotion.chorus_lift},
        "歌词结构": [{"type": s.type, "lines": len(s.lines)} for s in parsed.sections],
    }
    user = (f"创作信息（JSON）：{json.dumps(info, ensure_ascii=False)}\n"
            f"可用模板（JSON）：{json.dumps(allowed_templates(data.style_id), ensure_ascii=False)}\n"
            "请给出音乐规划。")
    return system, user


def validate_plan(output: _ModelPlan, data: CreativeInput, parsed: ParsedLyrics, seed: int) -> tuple[MusicPlan | None, list[str]]:
    try:
        plan = MusicPlan(**output.model_dump(), seed=seed)
    except ValidationError as exc:
        return None, format_validation_error(exc)
    errors = plan_errors(plan, data.style_id)
    if plan.melody_range[1] - plan.melody_range[0] < MIN_MELODY_SPAN:
        errors.append(f"melodyRange：最高音与最低音至少相差 {MIN_MELODY_SPAN} 个半音")
    lyric_types = {s.type for s in parsed.sections}
    missing = lyric_types - {s.type for s in plan.sections}
    if missing:
        errors.append(f"sections：缺少歌词中的段落 {sorted(missing)}")
    if not errors:
        try:
            arrange(parsed, plan, get_style(data.style_id), load_composition())
        except LyricsLengthError as exc:
            errors.append(f"时长：{exc.message}")
    return (None, errors) if errors else (plan, [])


def plan_music(data: CreativeInput, parsed: ParsedLyrics, provider: TextModelProvider | None,
               seed: int) -> tuple[MusicPlan, PlanRecord]:
    model_id = getattr(provider, "model_id", "none")
    record = PlanRecord(source="default", model_id=model_id)
    fallback = lambda reason: _fallback(data, seed, record, reason)  # noqa: E731
    if provider is None:
        return fallback("未配置文本模型")
    system, user = build_prompts(data, parsed)
    for kind in ("initial", "repair"):
        try:
            output = provider.complete_json(purpose="music_plan", system=system, user=user, schema=_ModelPlan,
                                            temperature=0.4)
        except ProviderError as exc:
            record.attempts.append(PlanAttempt(kind=kind, errors=[f"[{exc.code}] {exc.message}", *exc.details]))
            if exc.code != "MODEL_BAD_RESPONSE":
                return fallback(f"模型调用失败：{exc.code}")
            if kind == "initial":
                user = _repair_prompt(user, None, record.attempts[-1].errors)
                continue
            return fallback("修复一次后模型输出仍不符合格式")
        plan, errors = validate_plan(output, data, parsed, seed)
        record.attempts.append(PlanAttempt(kind=kind, output=output.to_json_dict(), errors=errors))
        if plan is not None:
            record.source = "ai" if kind == "initial" else "ai_repaired"
            logger.info("音乐规划来源 %s（模型 %s）", record.source, model_id)
            return plan, record
        logger.warning("音乐规划无效（%s）：%s", kind, errors)
        if kind == "initial":
            user = _repair_prompt(user, output.to_json_dict(), errors)
    return fallback("修复一次后规划仍未通过校验")


def _repair_prompt(user: str, previous: dict | None, errors: list[str]) -> str:
    shown = json.dumps(previous, ensure_ascii=False) if previous else "（无法解析）"
    return (f"{user}\n\n你上一次的输出：{shown}\n存在以下问题：\n" + "\n".join(f"- {e}" for e in errors)
            + "\n请只修正这些问题，重新输出完整的 JSON。")


def _fallback(data: CreativeInput, seed: int, record: PlanRecord, reason: str) -> tuple[MusicPlan, PlanRecord]:
    plan = default_plan(data.style_id, data.emotion_id, seed)
    record.source = "default"
    record.fallback_reason = reason
    logger.warning("音乐规划回退到默认规划：%s", reason)
    return plan, record
