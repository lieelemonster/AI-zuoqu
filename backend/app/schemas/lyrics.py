"""三版歌词结果。"""

from typing import Literal

from pydantic import Field, model_validator

from app.schemas.base import ApiModel

LyricApproach = Literal["story", "emotion", "imagery"]
LYRIC_APPROACHES: tuple[LyricApproach, ...] = ("story", "emotion", "imagery")
LYRICS_MAX_LENGTH = 2000


class LyricVariant(ApiModel):
    id: str = Field(min_length=1, max_length=40)
    approach: LyricApproach
    title: str = Field(default="", max_length=60)
    text: str = Field(min_length=1, max_length=LYRICS_MAX_LENGTH)


class LyricsResult(ApiModel):
    variants: list[LyricVariant] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def _one_variant_per_approach(self) -> "LyricsResult":
        approaches = sorted(v.approach for v in self.variants)
        if approaches != sorted(LYRIC_APPROACHES):
            raise ValueError("三版歌词必须分别是故事叙述、情绪表达、意象表达各一版")
        if len({v.id for v in self.variants}) != len(self.variants):
            raise ValueError("歌词版本 ID 不能重复")
        return self
