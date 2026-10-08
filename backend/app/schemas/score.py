"""程序生成的乐谱。时间统一用整数 tick，只在渲染边界换算成秒。"""

from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.schemas.base import ApiModel
from app.schemas.plan import MAX_BPM, MIN_BPM, Key, Mode, SectionType, _require_four_four

PPQ = 480
TICKS_PER_BAR = PPQ * 4


class NoteEvent(ApiModel):
    pitch: int = Field(ge=0, le=127)
    start_tick: int = Field(ge=0)
    duration_ticks: int = Field(gt=0)
    velocity: int = Field(default=80, ge=1, le=127)
    lyric_line_id: str | None = None
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=1)

    @property
    def end_tick(self) -> int:
        return self.start_tick + self.duration_ticks

    @model_validator(mode="after")
    def _char_range(self) -> "NoteEvent":
        has_start, has_end = self.char_start is not None, self.char_end is not None
        if has_start != has_end:
            raise ValueError("charStart 与 charEnd 必须同时提供")
        if has_start and self.char_end <= self.char_start:
            raise ValueError("charEnd 必须大于 charStart（半开区间）")
        if has_start and self.lyric_line_id is None:
            raise ValueError("提供歌词字符范围时必须同时提供 lyricLineId")
        return self


class ScoreSection(ApiModel):
    id: str = Field(min_length=1, max_length=40)
    type: SectionType
    start_tick: int = Field(ge=0)
    duration_ticks: int = Field(gt=0)

    @property
    def end_tick(self) -> int:
        return self.start_tick + self.duration_ticks


class LyricLine(ApiModel):
    id: str = Field(min_length=1, max_length=40)
    text: str = Field(min_length=1, max_length=200)
    section_id: str = Field(min_length=1, max_length=40)


class Track(ApiModel):
    role: Literal["melody", "accompaniment"]
    program: int = Field(default=0, ge=0, le=127)
    notes: list[NoteEvent] = Field(default_factory=list)


class Score(ApiModel):
    schema_version: Literal[1] = 1
    ppq: Literal[480] = PPQ
    bpm: int = Field(ge=MIN_BPM, le=MAX_BPM)
    meter: list[int] = Field(default_factory=lambda: [4, 4])
    key: Key = "C"
    mode: Mode = "major"
    sections: list[ScoreSection] = Field(min_length=1)
    lyric_lines: list[LyricLine] = Field(default_factory=list)
    tracks: list[Track] = Field(min_length=1, max_length=2)

    _meter = field_validator("meter")(_require_four_four)

    @property
    def total_ticks(self) -> int:
        return self.sections[-1].end_tick

    def ticks_to_seconds(self, ticks: int) -> float:
        return ticks / self.ppq * 60 / self.bpm

    @property
    def duration_seconds(self) -> float:
        return self.ticks_to_seconds(self.total_ticks)

    def track(self, role: str) -> Track | None:
        return next((t for t in self.tracks if t.role == role), None)

    @model_validator(mode="after")
    def _consistency(self) -> "Score":
        expected = 0
        for i, section in enumerate(self.sections):
            if section.start_tick != expected:
                raise ValueError(f"sections.{i}（{section.id}）必须从 tick {expected} 开始，段落需首尾相接")
            expected = section.end_tick
        section_ids = [s.id for s in self.sections]
        if len(set(section_ids)) != len(section_ids):
            raise ValueError("段落 ID 不能重复")

        line_ids = [line.id for line in self.lyric_lines]
        if len(set(line_ids)) != len(line_ids):
            raise ValueError("歌词行 ID 不能重复")
        for i, line in enumerate(self.lyric_lines):
            if line.section_id not in section_ids:
                raise ValueError(f"lyricLines.{i}.sectionId 引用了不存在的段落 {line.section_id}")

        roles = [t.role for t in self.tracks]
        if len(set(roles)) != len(roles):
            raise ValueError("旋律与伴奏各只能有一条轨道")
        if "melody" not in roles:
            raise ValueError("乐谱必须包含旋律轨道（melody）")

        total = self.total_ticks
        known_lines = set(line_ids)
        for t, track in enumerate(self.tracks):
            for n, note in enumerate(track.notes):
                where = f"tracks.{t}.notes.{n}"
                if note.end_tick > total:
                    raise ValueError(f"{where} 结束于 tick {note.end_tick}，超出乐谱总长 {total}")
                if note.lyric_line_id is not None and note.lyric_line_id not in known_lines:
                    raise ValueError(f"{where}.lyricLineId 引用了不存在的歌词行 {note.lyric_line_id}")

        melody = sorted(self.track("melody").notes, key=lambda note: note.start_tick)
        for previous, current in zip(melody, melody[1:]):
            if current.start_tick < previous.end_tick:
                raise ValueError(
                    f"旋律在 tick {current.start_tick} 处与前一个音符重叠，单声部旋律不允许重叠"
                )
        return self
