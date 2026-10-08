"""主旋律规则：强拍落和弦音、弱拍级进，句子走拱形轮廓；副歌音区更高、句首上行，并重复核心乐句。

所有随机选择都来自以种子初始化的 random.Random，同一输入、规则版本和种子得到相同音符。
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from app.composer.arrangement import Arrangement, LinePlan, SectionPlan
from app.composer.harmony import KEY_PC, SCALES, Chord, chord_at, scale_pcs
from app.presets import StyleConfig
from app.schemas.score import PPQ, TICKS_PER_BAR, NoteEvent

BASE_VELOCITY = 88
MAX_STEP = 7
ECHO_MIN_GAP = 4 * PPQ
# 说唱主歌的简单动机：相对锚定音的音阶步数，循环使用。
RAP_MOTIFS = ([0, 0, 1, 0], [0, 1, 0, -1], [0, 0, -1, 0, 1, 0], [0, 2, 1, 0])


@dataclass
class _State:
    previous: int | None = None
    before_previous: int | None = None


@dataclass
class MelodyContext:
    arrangement: Arrangement
    style: StyleConfig
    timeline: list[Chord]
    chorus_lift: int
    velocity_offset: int = 0
    low: int = field(init=False)
    high: int = field(init=False)
    scale: list[int] = field(init=False)
    tonic_pc: int = field(init=False)
    degree_pcs: list[int] = field(init=False)

    def __post_init__(self) -> None:
        self.low, self.high = self.style.melody_range
        a = self.arrangement
        pcs = set(scale_pcs(a.key, a.mode, pentatonic=self.style.melody_scale == "pentatonic"))
        self.scale = [p for p in range(self.low, self.high + 1) if p % 12 in pcs]
        self.tonic_pc = KEY_PC[a.key]
        self.degree_pcs = [(self.tonic_pc + s) % 12 for s in SCALES[a.mode]]

    def chord_tones(self, chord: Chord) -> list[int]:
        return [p for p in range(self.low, self.high + 1) if chord.contains(p)]

    def center(self, section_type: str) -> int:
        span = self.high - self.low
        verse = self.low + round(span * 0.4)
        if section_type == "chorus":
            # 副歌音区上移，但中心不超过最高音以下 3 个半音，保证轮廓顶点仍在音域内。
            return min(verse + max(self.chorus_lift, 2) + 2, self.high - 3)
        if section_type == "bridge":
            return verse + 2
        return verse

    def velocity(self, base_shift: int) -> int:
        return max(40, min(120, BASE_VELOCITY + self.velocity_offset + base_shift))


def _is_strong(start_tick: int, duration: int) -> bool:
    return start_tick % (2 * PPQ) == 0 or duration >= PPQ


def _contour(x: float, peak: float, amplitude: float) -> float:
    if x <= peak:
        return amplitude * math.sin(math.pi / 2 * (x / peak if peak else 1))
    return amplitude * math.cos(math.pi / 2 * (x - peak) / (1 - peak))


def _pick(candidates: list[int], target: float, state: _State, rng: random.Random, allow_repeat: bool = False) -> int:
    def cost(p: int) -> float:
        value = abs(p - target)
        if state.previous is not None:
            interval = abs(p - state.previous)
            value += interval * 0.35
            if interval > MAX_STEP:
                value += 6
            elif interval > 4:
                value += 1.5
            if state.before_previous is not None:
                last_move = state.previous - state.before_previous
                if abs(last_move) > 4 and (p - state.previous) * last_move > 0:
                    value += 3  # 大跳之后反向级进
            if p == state.previous:
                value += -0.8 if allow_repeat else (4 if p == state.before_previous else 1.5)
        return value + rng.random() * 0.7

    return min(candidates, key=cost)


def _push(state: _State, pitch: int) -> None:
    state.before_previous, state.previous = state.previous, pitch


def _cadence_candidates(ctx: MelodyContext, chord: Chord, role: str) -> list[int]:
    tones = ctx.chord_tones(chord)
    tonic, third, fifth, second = ctx.degree_pcs[0], ctx.degree_pcs[2], ctx.degree_pcs[4], ctx.degree_pcs[1]
    wanted = {"final": [tonic], "answer": [tonic, third], "question": [fifth, second, third]}[role]
    for pcs in (wanted, [tonic, third, fifth]):
        picks = [p for p in tones if p % 12 in pcs]
        if picks:
            return picks
    return tones or ctx.scale


def _rhythmic_line(ctx: MelodyContext, section: SectionPlan, lp: LinePlan, role: str, state: _State) -> list[int]:
    """说唱：围绕和弦音锚点循环一个两三音的动机，强拍对齐和弦，句尾按问答收束。"""
    motif = random.Random(f"{ctx.arrangement.seed}:motif:{section.type}").choice(RAP_MOTIFS)
    center = ctx.center(section.type)
    first_chord = chord_at(ctx.timeline, lp.notes[0].start_tick)
    anchor = min(ctx.chord_tones(first_chord) or ctx.scale, key=lambda p: (abs(p - center), p))
    base = min(range(len(ctx.scale)), key=lambda i: abs(ctx.scale[i] - anchor))
    pitches = []
    for i, note in enumerate(lp.notes):
        chord = chord_at(ctx.timeline, note.start_tick)
        if i == len(lp.notes) - 1:
            options = _cadence_candidates(ctx, chord, role)
            pitch = min(options, key=lambda p: (abs(p - (pitches[-1] if pitches else anchor)), p))
        else:
            index = min(max(base + motif[i % len(motif)], 0), len(ctx.scale) - 1)
            pitch = ctx.scale[index]
            if _is_strong(note.start_tick, note.duration_ticks) and not chord.contains(pitch):
                near = [p for p in ctx.chord_tones(chord) if abs(p - pitch) <= 2]
                if near:
                    pitch = min(near, key=lambda p: (abs(p - pitch), p))
        _push(state, pitch)
        pitches.append(pitch)
    return pitches


def _line_melody(ctx: MelodyContext, section: SectionPlan, lp: LinePlan, role: str, state: _State,
                 rng: random.Random) -> list[int]:
    n = len(lp.notes)
    chorus = section.type == "chorus"
    if ctx.style.rhythmic_melody and section.type != "chorus":
        return _rhythmic_line(ctx, section, lp, role, state)
    center = ctx.center(section.type)
    peak = 0.35 if chorus else 0.55
    amplitude = 5 if chorus else 4
    end_bias = {"question": 1.0, "answer": -2.0, "final": -3.0}[role]
    pitches = []
    for i, note in enumerate(lp.notes):
        x = i / (n - 1) if n > 1 else 1.0
        target = center + _contour(x, peak, amplitude) + end_bias * x
        if chorus and i == 0:
            target = center - 2  # 副歌句首从低处起，随后上行跳进形成记忆点
        chord = chord_at(ctx.timeline, note.start_tick)
        last = i == n - 1
        if last:
            candidates = _cadence_candidates(ctx, chord, role)
        elif _is_strong(note.start_tick, note.duration_ticks):
            candidates = ctx.chord_tones(chord) or ctx.scale
        else:
            candidates = ctx.scale
        pitch = _pick(candidates, target, state, rng)
        _push(state, pitch)
        pitches.append(pitch)
    return pitches


def _fit_to_chords(ctx: MelodyContext, notes: list[tuple[int, int]], pitches: list[int]) -> list[int]:
    """复用乐句时，强拍音若不在新和弦内，移到最近的和弦音。"""
    fitted = []
    for (start, duration), pitch in zip(notes, pitches):
        chord = chord_at(ctx.timeline, start)
        if _is_strong(start, duration) and not chord.contains(pitch):
            tones = ctx.chord_tones(chord)
            if tones:
                pitch = min(tones, key=lambda p: (abs(p - pitch), p))
        fitted.append(pitch)
    return fitted


def _signature(lp: LinePlan) -> tuple:
    base = lp.start_bar * TICKS_PER_BAR
    return lp.bars, tuple((n.start_tick - base, n.duration_ticks) for n in lp.notes)


def generate_melody(ctx: MelodyContext) -> list[NoteEvent]:
    a = ctx.arrangement
    events: list[NoteEvent] = []
    memory: dict[tuple, list[int]] = {}
    state = _State()
    chorus_opening: list[int] = []

    for section in a.sections:
        if not section.lines:
            continue
        rng = random.Random(f"{a.seed}:melody:{section.type}")
        count = len(section.lines)
        for index, lp in enumerate(section.lines):
            role = "final" if index == count - 1 else ("question" if index % 2 == 0 else "answer")
            signature = _signature(lp)
            key = (section.type, index, signature)
            # 副歌第 3 句与第 1 句节奏相同时直接重复，重复出现的段落沿用首次旋律。
            reuse = memory.get(key)
            if reuse is None and section.type == "chorus" and index >= 2:
                reuse = memory.get((section.type, index - 2, signature))
                if reuse is not None and role == "final":
                    reuse = None
            if reuse is not None:
                timing = [(n.start_tick, n.duration_ticks) for n in lp.notes]
                pitches = _fit_to_chords(ctx, timing, reuse)
                for p in pitches:
                    _push(state, p)
            else:
                pitches = _line_melody(ctx, section, lp, role, state, rng)
            memory.setdefault(key, pitches)
            if section.type == "chorus" and not chorus_opening:
                chorus_opening = pitches[:4]

            accent = 6 if section.type == "chorus" else 0
            for i, (note, pitch) in enumerate(zip(lp.notes, pitches)):
                strong = 4 if note.start_tick % TICKS_PER_BAR == 0 else 0
                tail = -2 if i == len(pitches) - 1 else 0
                events.append(NoteEvent(
                    pitch=pitch, start_tick=note.start_tick, duration_ticks=note.duration_ticks,
                    velocity=ctx.velocity(accent + strong + tail),
                    lyric_line_id=lp.line.id, char_start=note.unit[0], char_end=note.unit[1],
                ))

    events += _echo_fills(ctx, events)
    events += _intro_motif(ctx, chorus_opening)
    events += _outro_ending(ctx, events)
    events.sort(key=lambda e: e.start_tick)
    return events


def _echo_fills(ctx: MelodyContext, lyric_notes: list[NoteEvent]) -> list[NoteEvent]:
    """句间停顿超过 4 拍时，用较轻的力度回响上一句结尾两个音，避免长时间空白。"""
    if ctx.style.rhythmic_melody or not lyric_notes:
        return []
    fills = []
    ordered = sorted(lyric_notes, key=lambda e: e.start_tick)
    for current, following in zip(ordered, ordered[1:]):
        gap = following.start_tick - current.end_tick
        if gap < ECHO_MIN_GAP or current.lyric_line_id == following.lyric_line_id:
            continue
        line = [e for e in ordered if e.lyric_line_id == current.lyric_line_id]
        start = -(-current.end_tick // PPQ) * PPQ + PPQ
        lengths = [PPQ, 2 * PPQ]
        if start + sum(lengths) > following.start_tick - PPQ:
            continue
        for source, length in zip(line[-2:], lengths):
            chord = chord_at(ctx.timeline, start)
            pitch = source.pitch
            if not chord.contains(pitch):
                tones = ctx.chord_tones(chord) or [pitch]
                pitch = min(tones, key=lambda p: (abs(p - pitch), p))
            fills.append(NoteEvent(pitch=pitch, start_tick=start, duration_ticks=length,
                                   velocity=ctx.velocity(-18)))
            start += length
    return fills


def _intro_motif(ctx: MelodyContext, chorus_opening: list[int]) -> list[NoteEvent]:
    """前奏最后两小节预告副歌开头的几个音。"""
    intro = next((s for s in ctx.arrangement.sections if s.type == "intro"), None)
    if intro is None or not chorus_opening or ctx.style.rhythmic_melody:
        return []
    bars = min(2, intro.bars)
    lengths = [PPQ, PPQ, 2 * PPQ, 4 * PPQ] if bars == 2 else [PPQ, PPQ, 2 * PPQ]
    start = intro.end_tick - bars * TICKS_PER_BAR
    timing, cursor = [], start
    for length in lengths[: len(chorus_opening)]:
        timing.append((cursor, length))
        cursor += length
    if cursor < intro.end_tick and timing:
        timing[-1] = (timing[-1][0], intro.end_tick - timing[-1][0])
    pitches = _fit_to_chords(ctx, [(s, max(d, PPQ)) for s, d in timing], chorus_opening[: len(timing)])
    return [NoteEvent(pitch=p, start_tick=s, duration_ticks=d, velocity=ctx.velocity(-12))
            for (s, d), p in zip(timing, pitches)]


def _outro_ending(ctx: MelodyContext, melody: list[NoteEvent]) -> list[NoteEvent]:
    """尾奏：二分音符级进下行，最后用主音长音收束到乐曲结尾。"""
    outro = next((s for s in ctx.arrangement.sections if s.type == "outro"), None)
    if outro is None:
        return []
    final_bars = 2 if outro.bars >= 3 else 1
    lead_bars = outro.bars - final_bars
    previous = max(melody, key=lambda e: e.start_tick).pitch if melody else ctx.center("verse")
    tonic_options = [p for p in range(ctx.low, ctx.high + 1) if p % 12 == ctx.tonic_pc]
    final_pitch = min(tonic_options, key=lambda p: (abs(p - (ctx.center("verse") - 2)), p))
    events = []
    steps = lead_bars * 2
    state = _State(previous=previous)
    rng = random.Random(f"{ctx.arrangement.seed}:outro")
    for i in range(steps):
        start = outro.start_tick + i * 2 * PPQ
        target = previous + (final_pitch + 2 - previous) * (i + 1) / steps
        chord = chord_at(ctx.timeline, start)
        pitch = _pick(ctx.chord_tones(chord) or ctx.scale, target, state, rng)
        _push(state, pitch)
        events.append(NoteEvent(pitch=pitch, start_tick=start, duration_ticks=2 * PPQ, velocity=ctx.velocity(-6)))
    final_start = outro.end_tick - final_bars * TICKS_PER_BAR
    events.append(NoteEvent(pitch=final_pitch, start_tick=final_start, duration_ticks=outro.end_tick - final_start,
                            velocity=ctx.velocity(-4)))
    return events
