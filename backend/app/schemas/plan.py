"""AI 或默认规则给出的音乐规划；模板 ID 是否存在由风格配置校验。"""

from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.schemas.base import ApiModel

SectionType = Literal["intro", "verse", "chorus", "bridge", "outro"]
Mode = Literal["major", "minor"]
Key = Literal["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
MIN_BPM, MAX_BPM = 50, 200


def _require_four_four(value: list[int]) -> list[int]:
    if list(value) != [4, 4]:
        raise ValueError("首版只支持 4/4 拍")
    return value


class PlanSection(ApiModel):
    type: SectionType
    bars: int = Field(ge=1, le=32)
    chord_pattern_id: str = Field(min_length=1, max_length=60)
    rhythm_pattern_id: str = Field(min_length=1, max_length=60)


class MusicPlan(ApiModel):
    schema_version: Literal[1] = 1
    bpm: int = Field(ge=MIN_BPM, le=MAX_BPM)
    meter: list[int] = Field(default_factory=lambda: [4, 4])
    key: Key
    mode: Mode
    sections: list[PlanSection] = Field(min_length=2, max_length=12)
    melody_range: list[int] = Field(min_length=2, max_length=2)
    chorus_lift_semitones: int = Field(default=0, ge=0, le=7)
    seed: int = Field(ge=0, le=2**31 - 1)

    _meter = field_validator("meter")(_require_four_four)

    @field_validator("melody_range")
    @classmethod
    def _valid_range(cls, value: list[int]) -> list[int]:
        low, high = value
        if not (0 <= low < high <= 127):
            raise ValueError("旋律音区需满足 0 ≤ 最低音 < 最高音 ≤ 127")
        if high - low < 7:
            raise ValueError("旋律音区至少需要 7 个半音")
        return value

    @model_validator(mode="after")
    def _has_verse_and_chorus(self) -> "MusicPlan":
        types = {section.type for section in self.sections}
        if not {"verse", "chorus"} <= types:
            raise ValueError("音乐规划必须同时包含主歌（verse）和副歌（chorus）")
        return self
