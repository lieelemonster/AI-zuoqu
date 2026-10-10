"""三版歌词生成：组织提示词、调用文本模型、检查结构与时长可行性。"""

from __future__ import annotations

import json
import logging

from typing import Literal

from pydantic import ConfigDict, Field

from app.composer.arrangement import LyricsLengthError, arrange
from app.lyrics import mock_lyrics  # noqa: F401  注册离线演示模型的歌词用途
from app.lyrics.parser import parse_lyrics
from app.presets import default_plan, get_style, load_composition, load_presets
from app.providers import ProviderError, TextModelProvider
from app.schemas.base import ApiModel
from app.schemas.input import CreativeInput
from app.schemas.lyrics import LYRICS_MAX_LENGTH, LyricApproach, LyricsResult, LyricVariant

logger = logging.getLogger(__name__)

PROMPT_VERSION = "lyrics-3"
MAX_ATTEMPTS = 2
APPROACH_NAMES = {"story": "故事叙述版", "emotion": "情绪表达版", "imagery": "意象表达版"}
TYPE_TO_APPROACH: dict[str, LyricApproach] = {
    "narrative": "story",
    "emotional": "emotion",
    "imagery": "imagery",
}
SYSTEM_PROMPT = """你是中文歌曲的作词协作者。根据用户提供的主题、故事、音乐风格、情绪和创作限制，生成适合后续谱曲与试唱的原创中文歌词。

【任务】
一次生成且只生成三版歌词：
1. narrative：故事叙述。用具体场景、人物动作或前后变化推进故事，副歌表达故事的情绪落点。
2. emotional：情绪表达。围绕一种主要感受，用自然、直接的语言表达，副歌突出容易记住的核心句。
3. imagery：意象表达。选择一至两个连贯的意象承载情绪，画面之间有联系，不堆砌互不相关的景物。

三版共享用户指定的主题、情绪和关键故事事实，但应在切入角度、副歌核心句和主要表达上明显不同。不能仅替换同义词或调整句序。

【理解输入】
保留用户提供的人物关系、关键事件和情绪落点，不擅自添加重大经历。
故事为空时，根据主题构建简洁场景，不要求用户补充信息。
音乐风格应影响措辞、句长、重复和节奏，而不只是影响标题。
用户明确提供的段落、句数、字数、关键词和表达偏好，优先于默认写作目标。

【结构与可唱性】
每版必须包含独立一行的 [主歌] 和 [副歌]，主歌在前，副歌在后。
未指定结构时，默认主歌四行、副歌四行，暂不添加桥段。
每行优先控制在六至十二个汉字，标点不计入字数。这是可调整的目标，说唱或用户指定的结构可以突破。
相邻歌词行的长度与语法节奏尽量接近，在完整的语义单位处分行，避免拆开词语。
使用自然、便于发音的词语，避免生僻词和拗口的长修饰语。
同一段内尽量形成自然的韵脚关系，但不能为押韵牺牲语义或正常语序。
副歌集中表达一个核心意思，包含一句容易记住的核心句；可以有目的地重复一至两行，不依靠大量重复填充篇幅。
面向45～75秒的小样保持篇幅紧凑，不承诺仅凭歌词字数就能保证音频时长。

【表达质量】
默认采用自然口语与具体细节相结合的表达。允许诗意，但听者应能理解主旨。
用动作、物件、场景或有来由的感受支撑情绪，减少能套用于任何主题的空泛句子。
不要连续依靠“星辰大海”“追逐梦想”“永不放弃”等套话推进歌词。
情绪变化应有铺垫，避免突然转折。
生成原创表达，不复用现有歌曲的歌词。
每版标题应简短，并与该版的核心表达有关。

【输出前检查】
在内部检查三版数量与类型、段落完整性、用户要求、自然表达、可唱性和三版差异。
发现问题时先修改，再输出。
不输出检查过程、自评分或创作说明。

【输出格式】
只返回合法JSON，不添加Markdown代码围栏、前言或结语。
顶层只有variants字段，其值为包含三个对象的数组。
数组顺序固定为narrative、emotional、imagery。
每个对象只包含：
- type：上述类型之一。
- title：中文标题字符串。
- lyrics：完整歌词字符串，用换行分隔段落标题和歌词行。
不得省略字段、使用null或添加解释性字段。"""


class _ModelVariant(ApiModel):
    model_config = ConfigDict(extra="ignore")
    type: Literal["narrative", "emotional", "imagery"]
    title: str = Field(default="", max_length=60)
    lyrics: str = Field(min_length=10, max_length=LYRICS_MAX_LENGTH)

    @property
    def approach(self) -> LyricApproach:
        return TYPE_TO_APPROACH[self.type]

    @property
    def text(self) -> str:
        return self.lyrics


class _ModelLyrics(ApiModel):
    model_config = ConfigDict(extra="ignore")
    variants: list[_ModelVariant] = Field(min_length=3, max_length=3)


def _names(data: CreativeInput) -> dict[str, str]:
    presets = load_presets()
    lookup = lambda options, value: next(o.name for o in options if o.id == value)  # noqa: E731
    return {
        "theme": lookup(presets.themes, data.theme_id),
        "emotion": lookup(presets.emotions, data.emotion_id),
        "style": lookup(presets.styles, data.style_id),
    }


def build_prompts(data: CreativeInput) -> tuple[str, str]:
    names = _names(data)
    info = {
        "主题": names["theme"],
        "情绪": names["emotion"],
        "音乐风格": names["style"],
        "故事": data.story,
    }
    user = f"创作信息（JSON）：{json.dumps(info, ensure_ascii=False)}\n请按系统要求生成三版歌词。"
    return SYSTEM_PROMPT, user


def _shape_problems(parsed, data: CreativeInput) -> list[str]:
    """只卡住放不进曲子的结构。行数以提示词的四行默认为主，允许说唱和指定结构略长。"""
    del data
    sections = [section for section in parsed.sections if section.lines]
    if [section.type for section in sections] != ["verse", "chorus"]:
        return ["每版只写一段 [主歌] 和一段 [副歌]，先主歌后副歌，不要加桥段"]
    verse, chorus = sections
    problems = []
    if not 4 <= len(verse.lines) <= 8 or not 4 <= len(chorus.lines) <= 6:
        problems.append(
            f"主歌建议 4 行、副歌建议 4 行，现在是主歌 {len(verse.lines)} 行、副歌 {len(chorus.lines)} 行"
        )
    return problems


def _check_variant(variant: _ModelVariant, data: CreativeInput) -> list[str]:
    name = APPROACH_NAMES[variant.approach]
    parsed = parse_lyrics(variant.text)
    if not parsed.ok:
        return [f"{name}：{e}" for e in parsed.errors]
    problems = [f"{name}：{item}" for item in _shape_problems(parsed, data)]
    try:
        arrange(parsed, default_plan(data.style_id, data.emotion_id, 0), get_style(data.style_id), load_composition())
    except LyricsLengthError as exc:
        problems.append(f"{name}：{exc.message}")
    return problems


def generate_lyrics(data: CreativeInput, provider: TextModelProvider) -> LyricsResult:
    system, user = build_prompts(data)
    last_error: ProviderError | None = None
    feedback: list[str] = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        prompt = user
        if feedback:
            prompt += "\n上一次没有通过检查，请按下面几点整份重写，不要解释：\n" + "\n".join(f"- {item}" for item in feedback)
        try:
            output = provider.complete_json(purpose="lyrics", system=system, user=prompt, schema=_ModelLyrics,
                                            temperature=0.9)
        except ProviderError as exc:
            if exc.code != "MODEL_BAD_RESPONSE":
                raise
            last_error = exc
            logger.warning("歌词格式不符，第 %d 次：%s %s", attempt, exc.message, exc.details)
            continue
        problems = []
        if sorted(v.approach for v in output.variants) != sorted(APPROACH_NAMES):
            problems.append("三版歌词需分别为故事叙述、情绪表达、意象表达各一版")
        for variant in output.variants:
            problems += _check_variant(variant, data)
        if not problems:
            order = list(APPROACH_NAMES)
            variants = sorted(output.variants, key=lambda v: order.index(v.approach))
            return LyricsResult(variants=[
                LyricVariant(id=f"v_{v.approach}", approach=v.approach, title=v.title, text=v.text.strip())
                for v in variants
            ])
        feedback = problems
        last_error = ProviderError("MODEL_BAD_RESPONSE", "模型生成的歌词结构不符合要求", retryable=True,
                                   details=problems)
        logger.warning("歌词结构不符，第 %d 次：%s", attempt, problems)
    raise ProviderError("LYRICS_INVALID", "歌词生成结果不符合要求，请重试", retryable=True,
                        details=last_error.details if last_error else [])
