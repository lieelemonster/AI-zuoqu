"""简单和弦伴奏：低音＋和弦层，织体由风格节奏模板决定；音区和力度都避开主旋律。

织体用（起点拍, 时值拍, 声部）描述，声部为 bass（低音）、chord（整个和弦）或和弦内的序号音。
"""

from __future__ import annotations

from app.composer.arrangement import Arrangement, SectionPlan
from app.composer.harmony import Chord
from app.schemas.score import PPQ, TICKS_PER_BAR, NoteEvent

BASS_FLOOR = 36
BASS_VELOCITY = 70
CHORD_VELOCITY = 56

# 每两拍一组的织体；"r1" 表示高八度的根音，"3"/"5" 为和弦第二、三个音。
FIGURES: dict[str, list[tuple[float, float, str]]] = {
    "block": [(0, 2, "bass"), (0, 0.9, "chord"), (1, 0.9, "chord")],
    "arpeggio": [(0, 2, "bass"), (0.5, 1.5, "5"), (1, 1, "r1"), (1.5, 0.5, "3")],
    "broken": [(0, 2, "bass"), (1, 1, "chord")],
    "fingerpick": [(0, 1, "bass"), (0.5, 0.5, "3"), (1, 0.5, "5"), (1.5, 0.5, "3")],
    "pulse": [(0, 0.45, "bass"), (0.5, 0.45, "bass"), (1, 0.45, "bass"), (1.5, 0.45, "bass"),
              (0, 0.9, "chord"), (1, 0.9, "chord")],
    "offbeat": [(0, 0.9, "bass"), (1, 0.9, "bass"), (0.5, 0.4, "chord"), (1.5, 0.4, "chord")],
}
# 以四拍为一组的织体。
BAR_FIGURES: dict[str, list[tuple[float, float, str]]] = {
    "sustain": [(0, 4, "bass"), (0, 4, "chord")],
    "stab": [(0, 1.5, "bass"), (1.5, 0.5, "bass"), (2.5, 1.5, "bass"),
             (0, 1, "chord"), (2.5, 1, "chord")],
}


def _voicing(chord: Chord, floor: int) -> list[int]:
    """在 floor 之上的一个八度内排列和弦音（密集排列），保持在主旋律音域以下。"""
    return sorted(next(p for p in range(floor, floor + 12) if p % 12 == pc) for pc in chord.pcs)


def _bass(chord: Chord) -> int:
    return next(p for p in range(BASS_FLOOR, BASS_FLOOR + 12) if p % 12 == chord.root_pc)


def _voice(part: str, chord: Chord, voicing: list[int]) -> list[int]:
    if part == "bass":
        return [_bass(chord)]
    if part == "chord":
        return voicing
    if part == "r1":
        return [_bass(chord) + 12]
    index = {"3": 1, "5": 2}[part]
    return [voicing[min(index, len(voicing) - 1)]]


def _figure_events(figure: str, start: int, beats: int) -> list[tuple[int, int, str]]:
    events = []
    if figure in BAR_FIGURES:
        for group in range(0, beats, 4):
            for offset, length, part in BAR_FIGURES[figure]:
                if group + offset < beats:
                    events.append((start + round((group + offset) * PPQ),
                                   round(min(length, beats - group - offset) * PPQ), part))
        return events
    for group in range(0, beats, 2):
        for offset, length, part in FIGURES[figure]:
            events.append((start + round((group + offset) * PPQ), round(length * PPQ), part))
    return events


def _section_notes(section: SectionPlan, chords: list[Chord], floor: int, velocity_shift: int,
                   final_bars: int) -> list[NoteEvent]:
    notes = []
    figure = section.rhythm.accompaniment
    accent = 6 if section.type == "chorus" else (-4 if section.type in ("intro", "outro") else 0)
    ending_start = section.end_tick - final_bars * TICKS_PER_BAR if final_bars else None
    for chord in chords:
        if ending_start is not None and chord.start_tick >= ending_start:
            continue
        voicing = _voicing(chord, floor)
        beats = (chord.end_tick - chord.start_tick) // PPQ
        for tick, length, part in _figure_events(figure, chord.start_tick, beats):
            base = BASS_VELOCITY if part in ("bass", "r1") else CHORD_VELOCITY
            strong = 4 if (tick - chord.start_tick) % (2 * PPQ) == 0 else 0
            for pitch in _voice(part, chord, voicing):
                notes.append(NoteEvent(
                    pitch=pitch, start_tick=tick, duration_ticks=length,
                    velocity=max(30, min(110, base + accent + strong + velocity_shift)),
                ))
    if ending_start is not None:
        notes += _final_chord(chords[-1], ending_start, section.end_tick, floor, velocity_shift)
    return notes


def _final_chord(chord: Chord, start: int, end: int, floor: int, velocity_shift: int) -> list[NoteEvent]:
    """结尾主和弦：低音＋和弦层，持续到乐曲最后，由钢琴自然衰减收尾。"""
    bass = _bass(chord)
    pitches = [bass, *_voicing(chord, floor)]
    return [
        NoteEvent(pitch=p, start_tick=start, duration_ticks=end - start,
                  velocity=max(30, min(110, (BASS_VELOCITY if p == bass else CHORD_VELOCITY) - 2 + velocity_shift)))
        for p in sorted(set(pitches))
    ]


def _remove_same_pitch_overlaps(notes: list[NoteEvent]) -> list[NoteEvent]:
    """同一音高的音符若重叠，截短前一个，避免 MIDI 中提前关音或重复触发。"""
    notes = sorted(notes, key=lambda n: (n.pitch, n.start_tick))
    cleaned: list[NoteEvent] = []
    for note in notes:
        if cleaned and cleaned[-1].pitch == note.pitch and cleaned[-1].end_tick > note.start_tick:
            previous = cleaned[-1]
            if note.start_tick == previous.start_tick:
                if note.duration_ticks > previous.duration_ticks:
                    cleaned[-1] = note
                continue
            cleaned[-1] = previous.model_copy(update={"duration_ticks": note.start_tick - previous.start_tick})
        cleaned.append(note)
    return sorted(cleaned, key=lambda n: (n.start_tick, n.pitch))


def generate_accompaniment(arrangement: Arrangement, timeline: list[Chord], melody_low: int,
                           velocity_offset: int = 0) -> list[NoteEvent]:
    floor = min(48, melody_low - 12)
    shift = velocity_offset // 2
    notes = []
    for section in arrangement.sections:
        chords = [c for c in timeline if section.start_tick <= c.start_tick < section.end_tick]
        final_bars = 0
        if section is arrangement.sections[-1]:
            final_bars = 2 if section.bars >= 3 else 1
        notes += _section_notes(section, chords, floor, shift, final_bars)
    return _remove_same_pitch_overlaps(notes)
