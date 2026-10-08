"""单句歌词的节奏分配：在若干小节内为每个演唱单位安排起点与时值，句尾留长音和换气停顿。

做法：先决定这句占用多少拍（主体拍数），再把字分配到每一拍，每拍按字数选一个节奏型；
没有分到字的拍延长前一个音；最后一个字加上句尾长音，剩余时间就是句间停顿。
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from app.presets import RhythmPattern
from app.schemas.score import TICKS_PER_BAR

MAX_LINE_BARS = 4
MIN_REST_BEATS = 0.5

# 每拍内的节奏型（单位：格）。grid 8 每拍 2 格，grid 16 每拍 4 格。
CELLS = {
    8: {1: [[2]], 2: [[1, 1]]},
    16: {
        1: [[4]],
        2: [[2, 2], [3, 1], [2, 2]],
        3: [[2, 1, 1], [1, 1, 2], [1, 2, 1]],
        4: [[1, 1, 1, 1]],
    },
}
SYNCOPATED = {(16, 2): [3, 1], (16, 3): [1, 2, 1]}


@dataclass(frozen=True)
class RhythmNote:
    start_tick: int
    duration_ticks: int
    unit: tuple[int, int]

    @property
    def end_tick(self) -> int:
        return self.start_tick + self.duration_ticks


def notes_per_beat(pattern: RhythmPattern) -> float:
    low, high = pattern.notes_per_bar
    return max((low + high) / 2, 1) / 4


def natural_bars(units: int, pattern: RhythmPattern) -> int:
    """按风格的平均密度估计一句需要的小节数（含句尾长音）。"""
    beats = units / notes_per_beat(pattern) + pattern.phrase_end_beats
    bars = max(1, math.ceil(beats / 4 - 0.25))
    if bars == 3:
        # 三小节乐句不规整：放得下就收成两小节，否则放宽到四小节。
        bars = 2 if minimum_bars(units, pattern) <= 2 else 4
    return min(bars, MAX_LINE_BARS)


def minimum_bars(units: int, pattern: RhythmPattern) -> int:
    """按每拍最多能放的字数，一句至少需要的小节数。"""
    max_per_beat = max(CELLS[pattern.grid])
    beats = units / max_per_beat + MIN_REST_BEATS + 0.5
    return max(1, math.ceil(beats / 4))


def _distribute(n: int, beats: int, rng: random.Random, max_per_beat: int) -> list[int]:
    """把 n 个字分到 beats 拍，首拍至少一个字；字少于拍数时部分拍为 0（延长前一个音）。"""
    counts = [0] * beats
    counts[0] = 1
    remaining = n - 1
    if n >= beats:
        for i in range(1, beats):
            counts[i] = 1
        remaining = n - beats
        candidates = list(range(beats))
        while remaining > 0:
            open_beats = [i for i in candidates if counts[i] < max_per_beat]
            # 偏向在后半拍组和弱拍加字，句首更从容。
            weights = [1.0 + (i % 2) * 0.6 + i / beats for i in open_beats]
            pick = rng.choices(open_beats, weights=weights)[0]
            counts[pick] += 1
            remaining -= 1
    else:
        # 字少于拍数：在偶数拍（强拍）优先落字，其余拍延长。
        slots = sorted(range(1, beats), key=lambda i: (i % 2, rng.random()))
        for i in slots[:remaining]:
            counts[i] = 1
    return counts


def line_rhythm(
    units: list[tuple[int, int]],
    bars: int,
    pattern: RhythmPattern,
    rng: random.Random,
    start_tick: int,
    dense: bool = False,
) -> list[RhythmNote]:
    """在 bars 小节内排好一句的音符；句尾到下一句之间至少留半拍换气。"""
    n = len(units)
    if n == 0:
        return []
    grid = pattern.grid
    slot = TICKS_PER_BAR // grid
    per_beat = grid // 4
    cells = CELLS[grid]
    max_per_beat = max(cells)
    line_beats = bars * 4

    hold_slots = round(pattern.phrase_end_beats * per_beat)
    rest_slots = max(1, round(MIN_REST_BEATS * per_beat))
    min_beats = math.ceil(n / max_per_beat)
    available = line_beats - math.ceil((hold_slots + rest_slots) / per_beat)
    while available < min_beats and hold_slots > 1:
        hold_slots -= 1
        available = line_beats - math.ceil((hold_slots + rest_slots) / per_beat)
    if available < min_beats:
        raise ValueError(f"{n} 个字无法放进 {bars} 小节")

    target = round(n / notes_per_beat(pattern))
    if dense:
        target = min(target, max(min_beats, math.ceil(n / 2)))
    else:
        target = max(target, round(available * 0.5))
    body_beats = min(max(target, min_beats), available)

    counts = _distribute(n, body_beats, rng, max_per_beat)
    durations: list[int] = []
    for count in counts:
        if count == 0:
            durations[-1] += per_beat
            continue
        options = cells[count]
        syncopated = SYNCOPATED.get((grid, count))
        cell = syncopated if syncopated and rng.random() < pattern.syncopation else rng.choice(options)
        durations.extend(cell)

    if grid == 8 and pattern.syncopation > 0:
        for i in range(len(durations) - 2):
            if durations[i] == durations[i + 1] == 2 and rng.random() < pattern.syncopation:
                durations[i], durations[i + 1] = 3, 1

    durations[-1] += hold_slots
    used = sum(durations)
    offset = 0
    if pattern.syncopation >= 0.3 and rng.random() < pattern.syncopation * 0.5 and used + rest_slots + 1 <= bars * grid:
        offset = 1

    notes, cursor = [], offset
    for unit, length in zip(units, durations):
        notes.append(RhythmNote(start_tick + cursor * slot, length * slot, unit))
        cursor += length
    return notes
