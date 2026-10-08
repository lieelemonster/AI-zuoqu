"""三版歌词生成：组织提示词、调用文本模型、检查结构与时长可行性。"""

from __future__ import annotations

import json
import logging

from pydantic import ConfigDict, Field

from app.composer.arrangement import LyricsLengthError, arrange
from app.lyrics import mock_lyrics  # noqa: F401  注册离线演示模型的歌词用途
from app.lyrics.parser import parse_lyrics
from app.presets import default_plan, get_style, load_composition, load_presets
from app.providers import ProviderError, TextModelProvider
from app.schemas.base import ApiModel
from app.schemas.input import CreativeInput
from app.schemas.lyrics import LyricApproach, LyricsResult, LyricVariant

logger = logging.getLogger(__name__)

PROMPT_VERSION = "lyrics-1"
MAX_ATTEMPTS = 2
APPROACH_NAMES = {"story": "故事叙述版", "emotion": "情绪表达版", "imagery": "意象表达版"}


class _ModelVariant(ApiModel):
    model_config = ConfigDict(extra="ignore")
    approach: LyricApproach
    title: str = Field(default="", max_length=30)
    text: str = Field(min_length=10, max_length=1200)


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
    rap = data.style_id == "rap"
    line_rule = (
        "主歌每行 10～14 个汉字，押韵、节奏感强，像说唱段落；副歌每行 6～10 个汉字，简短上口"
        if rap else "每行 6～10 个汉字，句式整齐、适合配旋律"
    )
    system = f"""你是专业的中文歌词作者。根据用户的创作信息，一次写出三版中文歌词，只输出 JSON。
要求：
1. 三版的侧重点不同：story＝故事叙述（事件、人物和故事发展），emotion＝情绪表达（感受与情绪），imagery＝意象表达（场景、画面和意象）。三版的主题、情绪和风格保持一致。
2. 每版只使用 [主歌] 和 [副歌] 两个段落标题，标题单独占一行，先 [主歌] 后 [副歌]，每段 4 行。
3. 篇幅适合约 1 分钟的音乐小样：{line_rule}。每行就是一个乐句，不要加标点，不要出现英文、阿拉伯数字或括号注释。
4. 副歌突出核心主题、有记忆点，可以重复关键句。
5. 如果用户提供了故事描述，要融入其中的人物、经历、场景或细节。
输出格式：{{"variants": [{{"approach": "story", "title": "歌名", "text": "[主歌]\\n第一句\\n第二句\\n第三句\\n第四句\\n[副歌]\\n第一句\\n第二句\\n第三句\\n第四句"}}, {{"approach": "emotion", ...}}, {{"approach": "imagery", ...}}]}}"""
    info = {"主题": names["theme"], "情绪": names["emotion"], "音乐风格": names["style"],
            "故事描述": data.story or "（未填写）"}
    user = f"创作信息（JSON）：{json.dumps(info, ensure_ascii=False)}\n请写三版歌词。"
    return system, user


def _check_variant(variant: _ModelVariant, data: CreativeInput) -> list[str]:
    name = APPROACH_NAMES[variant.approach]
    parsed = parse_lyrics(variant.text)
    if not parsed.ok:
        return [f"{name}：{e}" for e in parsed.errors]
    try:
        arrange(parsed, default_plan(data.style_id, data.emotion_id, 0), get_style(data.style_id), load_composition())
    except LyricsLengthError as exc:
        return [f"{name}：{exc.message}"]
    return []


def generate_lyrics(data: CreativeInput, provider: TextModelProvider) -> LyricsResult:
    system, user = build_prompts(data)
    last_error: ProviderError | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            output = provider.complete_json(purpose="lyrics", system=system, user=user, schema=_ModelLyrics,
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
        last_error = ProviderError("MODEL_BAD_RESPONSE", "模型生成的歌词结构不符合要求", retryable=True,
                                   details=problems)
        logger.warning("歌词结构不符，第 %d 次：%s", attempt, problems)
    raise ProviderError("LYRICS_INVALID", "歌词生成结果不符合要求，请重试", retryable=True,
                        details=last_error.details if last_error else [])
