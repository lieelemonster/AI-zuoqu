"""AI 音乐规划：只允许引用风格配置中已有的模板；无效时最多修复一次，再回退到默认规划。"""

from __future__ import annotations

import json
import logging
from typing import Literal

from pydantic import ConfigDict, Field, ValidationError

from app.composer.arrangement import LyricsLengthError, arrange
from app.lyrics.parser import ParsedLyrics
from app.planner import mock_plan  # noqa: F401  注册离线演示模型的规划用途
from app.presets import default_plan, get_style, load_composition, load_presets, plan_errors
from app.providers import ProviderError, TextModelProvider
from app.schemas.base import ApiModel, format_validation_error
from app.schemas.input import CreativeInput
from app.schemas.plan import Key, Mode, MusicPlan, SectionType

logger = logging.getLogger(__name__)

PROMPT_VERSION = "plan-2"
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


SYSTEM_PROMPT = """你是中文歌曲钢琴小样的音乐规划协作者。
根据用户最终确认的歌词、音乐风格和情绪，制定后端能够执行的音乐规划。

目标成品为45～75秒的钢琴主旋律与简单伴奏，无人声。
创作流程是先写词，再让旋律适配歌词。

【创作原则】
歌词偏向诗意、画面感强、适度含蓄。
音乐应承接歌词情绪，保留呼吸和留白。
不要因为歌词诗意，就固定选择悲伤、慢速或小调。

【歌词适配】
保留全部歌词，不删字、改字或改变顺序。
根据词组、语义重心、自然停顿和句尾韵脚规划乐句。
避免在完整词语中间安排明显的换气停顿。
不要仅按字数为所有字平均分配时值。
长句采用允许范围内更密的节奏或更多小节；
短句通过句尾延长、休止或旋律回应保留空间。
主旋律应能供人自然试唱。

【旋律与段落】
主歌建立一个简洁、可辨识的旋律动机。
旋律变化围绕动机展开，兼顾重复与变奏。
副歌与主歌保持联系，同时在音区、节奏、
动机展开或力度中形成可辨识的变化。
副歌核心句应成为旋律记忆点。
不要机械地让每首副歌都更高、更响、更密；
克制或释然的情绪可以通过收束和留白表达。
遵守指定音域和音程限制，避免无目的的大幅跳进。

【和声与伴奏】
根据风格和情绪选择已有的和弦方案。
伴奏应为旋律留出音区、力度和节奏空间。
不要每拍都填满，不让伴奏掩盖主旋律。
重要乐句落点应有和声支撑。
说唱风格以节奏组织和简洁动机为主。

【时长与结尾】
根据速度、拍号、小节数和尾音共同规划时长。
段落小节数合计必须符合总小节预算。
为最后一个音或和弦保留自然衰减时间。
选择完整的收束方式，不依赖截断音频满足时长。
歌词无法在约束内适配时，由后端返回明确提示，
不得通过删词或越过参数上限假装完成。

【执行约束】
只使用服务端提供的模板、和弦方案和节奏模式。
所有参数必须在服务端允许的范围内。
只输出已有schema支持的字段，不新增字段。
上述音乐建议通过后端已支持的参数表达。

【输出】
输出前检查模板合法性、参数范围、歌词覆盖、
段落预算、主副歌变化和包含尾音的预计时长。
只返回符合output_schema的合法JSON。
不输出解释、Markdown、检查过程或自评分。"""


def build_prompts(data: CreativeInput, parsed: ParsedLyrics) -> tuple[str, str]:
    presets = load_presets()
    name = lambda options, value: next(o.name for o in options if o.id == value)  # noqa: E731
    limits = allowed_templates(data.style_id)
    info = {
        "styleId": data.style_id,
        "emotionId": data.emotion_id,
        "主题": name(presets.themes, data.theme_id),
        "情绪": name(presets.emotions, data.emotion_id),
        "音乐风格": name(presets.styles, data.style_id),
        "拍号": [4, 4],
        "歌词": [{"type": section.type, "lines": [line.text for line in section.lines]} for section in parsed.sections],
    }
    output_schema = {
        "bpm": f"整数，必须在 {limits['bpmRange']} 内",
        "key": "C、C#、D、Eb、E、F、F#、G、Ab、A、Bb、B 之一，优先使用 defaultKeys",
        "mode": "必须是 modes 中的一项",
        "melodyRange": "长度为 2 的数组 [最低音, 最高音]，MIDI 音高，落在允许的 melodyRange 内，且至少相差 12",
        "chorusLiftSemitones": f"副歌相对主歌升高的半音数，0 到 {limits['chorusLiftMax']}。可以为 0，用留白或节奏形成副歌",
        "sections": [{
            "type": "intro、verse、chorus、bridge 或 outro",
            "bars": "该段小节数。顺序为 intro（1～4）、与歌词一致的各段、outro（2～4）。歌词段按行数估计，长句可以更多小节",
            "chordPatternId": "只能用可用模板里的 id，且该模板的 for 必须包含本段 type",
            "rhythmPatternId": "只能用可用模板里的 id，且该模板的 for 必须包含本段 type",
        }],
    }
    user = (f"创作信息（JSON）：{json.dumps(info, ensure_ascii=False)}\n"
            f"可用模板（JSON）：{json.dumps(limits, ensure_ascii=False)}\n"
            f"output_schema（JSON）：{json.dumps(output_schema, ensure_ascii=False)}\n"
            "请只返回符合 output_schema 的 JSON。")
    return SYSTEM_PROMPT, user


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
