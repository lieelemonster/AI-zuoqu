"""调式、音阶与和弦时间线。和弦模板用调内级数表示，按段落起点循环铺满。"""

from __future__ import annotations

from dataclasses import dataclass

from app.composer.arrangement import Arrangement, SectionPlan
from app.schemas.score import PPQ

KEY_PC = {"C": 0, "C#": 1, "D": 2, "Eb": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "Ab": 8, "A": 9, "Bb": 10, "B": 11}
SCALES = {"major": [0, 2, 4, 5, 7, 9, 11], "minor": [0, 2, 3, 5, 7, 8, 10]}
PENTATONIC = {"major": [0, 2, 4, 7, 9], "minor": [0, 3, 5, 7, 10]}


@dataclass(frozen=True)
class Chord:
    start_tick: int
    end_tick: int
    symbol: str
    root_pc: int
    pcs: tuple[int, ...]

    def contains(self, pitch: int) -> bool:
        return pitch % 12 in self.pcs


def scale_pcs(key: str, mode: str, pentatonic: bool = False) -> list[int]:
    tonic = KEY_PC[key]
    steps = PENTATONIC[mode] if pentatonic else SCALES[mode]
    return [(tonic + s) % 12 for s in steps]


def chord_pcs(symbol: str, key: str, mode: str) -> tuple[int, tuple[int, ...]]:
    """'5' 为调内三和弦，'2:7' 为调内七和弦，'5:M' 强制大三和弦。返回（根音，和弦音集合）。"""
    degree, _, suffix = symbol.partition(":")
    index = int(degree) - 1
    scale = SCALES[mode]
    tonic = KEY_PC[key]
    root = (tonic + scale[index]) % 12
    if suffix == "M":
        return root, (root, (root + 4) % 12, (root + 7) % 12)
    count = 4 if suffix == "7" else 3
    pcs = tuple((tonic + scale[(index + 2 * k) % 7]) % 12 for k in range(count))
    return root, pcs


def section_chords(section: SectionPlan, key: str, mode: str) -> list[Chord]:
    pattern = section.chord
    span = pattern.beats_per_chord * PPQ
    total = section.end_tick - section.start_tick
    count = total // span
    symbols = pattern.chords
    if section.type == "outro":
        # 尾奏按模板末尾对齐，保证最后落在模板的结束和弦（主和弦）。
        sequence = [symbols[(len(symbols) - count + i) % len(symbols)] for i in range(count)]
    else:
        sequence = [symbols[i % len(symbols)] for i in range(count)]
    chords = []
    for i, symbol in enumerate(sequence):
        root, pcs = chord_pcs(symbol, key, mode)
        start = section.start_tick + i * span
        chords.append(Chord(start, start + span, symbol, root, pcs))
    return chords


def chord_timeline(arrangement: Arrangement) -> list[Chord]:
    return [c for s in arrangement.sections for c in section_chords(s, arrangement.key, arrangement.mode)]


def chord_at(timeline: list[Chord], tick: int) -> Chord:
    for chord in timeline:
        if chord.start_tick <= tick < chord.end_tick:
            return chord
    return timeline[-1]
