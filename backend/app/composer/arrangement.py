"""段落时长分配：按歌词分句和风格密度安排整小节，并在速度范围内让成品接近目标时长。

时间统一用 tick；只在估算成品秒数时换算：秒 = 小节数 × 4 × 60 ÷ BPM。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field, replace
from itertools import product

from app.composer.rhythm import MAX_LINE_BARS, RhythmNote, line_rhythm, minimum_bars, natural_bars
from app.lyrics.parser import ParsedLine, ParsedLyrics
from app.presets import ChordPattern, CompositionConfig, RhythmPattern, StyleConfig
from app.schemas.plan import MusicPlan, PlanSection, SectionType
from app.schemas.score import TICKS_PER_BAR, LyricLine, Score, ScoreSection

# 拉伸级别：-1 按最大密度压缩；0 每句自然长度；1 同段统一为最长句；2 统一并加倍；3 每句 4 小节。
STRETCH_LEVELS = (-1, 0, 1, 2, 3)
STRETCH_PENALTY = {-1: 6.0, 0: 0.0, 1: 1.0, 2: 5.0, 3: 9.0}
INTRO_OPTIONS = range(0, 5)
OUTRO_OPTIONS = range(2, 5)
GAP_OPTIONS = (0, 1, 2)
# 歌词偏短时可在末尾再唱一遍副歌，比把每句拉得很长更像歌。
REPEAT_OPTIONS = (0, 1)
REPEAT_PENALTY = 2.5
TARGET_TOLERANCE_SECONDS = 5.0
SAFETY_MARGIN_SECONDS = 3.0


class LyricsLengthError(ValueError):
    """歌词长度不适合 45～75 秒的小样；只提示用户修改，不自动删改歌词。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class LinePlan:
    line: ParsedLine
    start_bar: int
    bars: int
    notes: list[RhythmNote] = field(default_factory=list)

    @property
    def rest_ticks(self) -> int:
        """句尾到下一句起点的停顿长度。"""
        end = (self.start_bar + self.bars) * TICKS_PER_BAR
        return end - (self.notes[-1].end_tick if self.notes else self.start_bar * TICKS_PER_BAR)


@dataclass
class SectionPlan:
    id: str
    type: SectionType
    start_bar: int
    bars: int
    chord: ChordPattern
    rhythm: RhythmPattern
    lines: list[LinePlan] = field(default_factory=list)
    gap_bars: int = 0

    @property
    def start_tick(self) -> int:
        return self.start_bar * TICKS_PER_BAR

    @property
    def end_tick(self) -> int:
        return (self.start_bar + self.bars) * TICKS_PER_BAR


@dataclass
class Arrangement:
    bpm: int
    key: str
    mode: str
    seed: int
    sections: list[SectionPlan]
    tail_seconds: float
    stretch_level: int

    @property
    def total_bars(self) -> int:
        return sum(s.bars for s in self.sections)

    @property
    def score_seconds(self) -> float:
        return self.total_bars * 4 * 60 / self.bpm

    @property
    def total_seconds(self) -> float:
        return self.score_seconds + self.tail_seconds

    def skeleton_score(self, pitch: int = 60) -> Score:
        """只含段落、歌词行和节奏的乐谱（统一音高），用于检查时长与节奏。"""
        lines = [
            LyricLine(id=lp.line.id, text=lp.line.text, section_id=s.id)
            for s in self.sections for lp in s.lines
        ]
        notes = [
            {"pitch": pitch, "startTick": n.start_tick, "durationTicks": n.duration_ticks, "velocity": 80,
             "lyricLineId": lp.line.id, "charStart": n.unit[0], "charEnd": n.unit[1]}
            for s in self.sections for lp in s.lines for n in lp.notes
        ]
        return Score(
            bpm=self.bpm, key=self.key, mode=self.mode,
            sections=[ScoreSection(id=s.id, type=s.type, start_tick=s.start_tick,
                                   duration_ticks=s.end_tick - s.start_tick) for s in self.sections],
            lyric_lines=lines,
            tracks=[{"role": "melody", "program": 0, "notes": notes}],
        )


def _template_for(style: StyleConfig, plan: MusicPlan, section_type: SectionType, occurrence: int):
    """同类型第 occurrence 次出现时使用规划中第 occurrence 个同类型段落的模板，不足则沿用最后一个。"""
    matches = [s for s in plan.sections if s.type == section_type]
    if matches:
        chosen: PlanSection = matches[min(occurrence, len(matches) - 1)]
        return style.chord_pattern(chosen.chord_pattern_id), style.rhythm_pattern(chosen.rhythm_pattern_id), chosen
    chord = next(p for p in style.chord_patterns if section_type in p.for_)
    rhythm = next(p for p in style.rhythm_patterns if section_type in p.for_)
    return chord, rhythm, None


def _line_bars(lines: list[ParsedLine], rhythm: RhythmPattern, level: int) -> list[int]:
    natural = [natural_bars(l.unit_count, rhythm) for l in lines]
    if level == -1:
        return [minimum_bars(l.unit_count, rhythm) for l in lines]
    if level == 0:
        return natural
    uniform = max(natural)
    if level == 1:
        return [uniform] * len(lines)
    if level == 2:
        return [min(MAX_LINE_BARS, max(uniform * 2, 2))] * len(lines)
    return [MAX_LINE_BARS] * len(lines)


def arrange(parsed: ParsedLyrics, plan: MusicPlan, style: StyleConfig, composition: CompositionConfig) -> Arrangement:
    if not parsed.ok:
        raise LyricsLengthError("LYRICS_STRUCTURE", "；".join(parsed.errors))

    occurrences: dict[str, int] = {}
    lyric_sections = []
    for section in parsed.sections:
        index = occurrences.get(section.type, 0)
        occurrences[section.type] = index + 1
        chord, rhythm, _ = _template_for(style, plan, section.type, index)
        lyric_sections.append((section, chord, rhythm))

    for section, _, rhythm in lyric_sections:
        for line in section.lines:
            if minimum_bars(line.unit_count, rhythm) > MAX_LINE_BARS:
                raise LyricsLengthError(
                    "LINE_TOO_LONG",
                    f"第 {line.line_number} 行有 {line.unit_count} 个字，单句过长，请拆成两行或缩短后再生成",
                )

    intro_chord, intro_rhythm, intro_plan = _template_for(style, plan, "intro", 0)
    outro_chord, outro_rhythm, outro_plan = _template_for(style, plan, "outro", 0)
    preferred_intro = intro_plan.bars if intro_plan else 2
    preferred_outro = outro_plan.bars if outro_plan else 4

    lyric_bars = {
        level: sum(sum(_line_bars(s.lines, r, level)) for s, _, r in lyric_sections) for level in STRETCH_LEVELS
    }
    choruses = [item for item in lyric_sections if item[0].type == "chorus"]
    repeat_source = choruses[-1] if choruses else None
    repeat_bars = {
        level: sum(_line_bars(repeat_source[0].lines, repeat_source[2], level)) if repeat_source else 0
        for level in STRETCH_LEVELS
    }
    repeat_options = REPEAT_OPTIONS if repeat_source else (0,)
    low, high = style.bpm_range
    gap_slots = max(len(lyric_sections) - 1, 0)
    best, best_cost = None, float("inf")
    for bpm, level, intro, outro, gap, repeat in product(
        range(low, high + 1), STRETCH_LEVELS, INTRO_OPTIONS, OUTRO_OPTIONS, GAP_OPTIONS, repeat_options
    ):
        bars = lyric_bars[level] + intro + outro + gap * (gap_slots + repeat) + repeat_bars[level] * repeat
        seconds = bars * 240 / bpm + composition.tail_seconds
        if not composition.min_seconds <= seconds <= composition.max_seconds:
            continue
        # 离上下限太近时加罚分，给实际渲染的尾音误差留余量。
        margin_penalty = 5.0 * (
            max(0.0, composition.min_seconds + SAFETY_MARGIN_SECONDS - seconds)
            + max(0.0, seconds - (composition.max_seconds - SAFETY_MARGIN_SECONDS))
        )
        cost = (
            margin_penalty
            + max(0.0, abs(seconds - composition.target_seconds) - TARGET_TOLERANCE_SECONDS)
            + abs(bpm - plan.bpm) * 0.5
            + STRETCH_PENALTY[level]
            + abs(intro - preferred_intro) * 1.5
            + abs(outro - preferred_outro) * 1.5
            + gap * 3.0
            + repeat * REPEAT_PENALTY
        )
        if cost < best_cost:
            best, best_cost = (bpm, level, intro, outro, gap, repeat), cost

    if best is None:
        shortest = (lyric_bars[-1] + min(OUTRO_OPTIONS)) * 240 / high + composition.tail_seconds
        if shortest > composition.max_seconds:
            total_units = sum(l.unit_count for l in parsed.lines)
            raise LyricsLengthError(
                "LYRICS_TOO_LONG",
                f"歌词共 {len(parsed.lines)} 行、{total_units} 个字，按该风格最快速度也需约 {shortest:.0f} 秒，"
                f"超过 {composition.max_seconds:g} 秒上限，请删减部分歌句后再生成",
            )
        raise LyricsLengthError(
            "LYRICS_TOO_SHORT",
            f"歌词只有 {len(parsed.lines)} 行，拉长停顿后仍不足 {composition.min_seconds:g} 秒，请补充几句歌词",
        )

    bpm, level, intro, outro, gap, repeat = best
    if repeat:
        source, chord, rhythm = repeat_source
        copy = replace(source, id=f"{source.id}_repeat",
                       lines=[replace(line, id=f"{line.id}_repeat") for line in source.lines])
        lyric_sections.append((copy, chord, rhythm))
    rng_seed = plan.seed
    sections: list[SectionPlan] = []
    bar = 0
    if intro:
        sections.append(SectionPlan("intro_1", "intro", bar, intro, intro_chord, intro_rhythm))
        bar += intro
    for index, (section, chord, rhythm) in enumerate(lyric_sections):
        gap_bars = gap if index < len(lyric_sections) - 1 else 0
        bars_per_line = _line_bars(section.lines, rhythm, level)
        plan_section = SectionPlan(section.id, section.type, bar, sum(bars_per_line) + gap_bars, chord, rhythm,
                                   gap_bars=gap_bars)
        line_bar = bar
        for line, line_bars in zip(section.lines, bars_per_line):
            # 同段同字数同长度的句子使用同一节奏，形成可重复的乐句。
            rng = random.Random(f"{rng_seed}:{section.type}:{line.unit_count}:{line_bars}")
            notes = line_rhythm(line.units, line_bars, rhythm, rng, line_bar * TICKS_PER_BAR,
                                dense=style.rhythmic_melody)
            plan_section.lines.append(LinePlan(line, line_bar, line_bars, notes))
            line_bar += line_bars
        sections.append(plan_section)
        bar += plan_section.bars
    sections.append(SectionPlan("outro_1", "outro", bar, outro, outro_chord, outro_rhythm))

    return Arrangement(bpm, plan.key, plan.mode, plan.seed, sections, composition.tail_seconds, level)
