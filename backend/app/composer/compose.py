"""作曲入口：歌词结构 + 音乐规划 → 时长与节奏 → 旋律 → 校验后的乐谱。"""

from __future__ import annotations

from dataclasses import dataclass

from app.composer.accompaniment import generate_accompaniment
from app.composer.arrangement import Arrangement, arrange
from app.composer.harmony import chord_timeline
from app.composer.melody import MelodyContext, generate_melody
from app.lyrics.parser import ParsedLyrics
from app.presets import get_emotion_rule, get_style, load_composition
from app.schemas.plan import MusicPlan
from app.schemas.score import LyricLine, Score, ScoreSection

COMPOSER_VERSION = "rules-1"


@dataclass
class Composition:
    score: Score
    arrangement: Arrangement


def compose(parsed: ParsedLyrics, plan: MusicPlan, style_id: str, emotion_id: str) -> Composition:
    style = get_style(style_id)
    emotion = get_emotion_rule(emotion_id)
    arrangement = arrange(parsed, plan, style, load_composition())
    timeline = chord_timeline(arrangement)
    melody = generate_melody(MelodyContext(
        arrangement=arrangement,
        style=style,
        timeline=timeline,
        chorus_lift=plan.chorus_lift_semitones,
        velocity_offset=emotion.velocity_offset,
    ))
    accompaniment = generate_accompaniment(
        arrangement, timeline, melody_low=style.melody_range[0], velocity_offset=emotion.velocity_offset
    )
    score = Score(
        bpm=arrangement.bpm,
        key=arrangement.key,
        mode=arrangement.mode,
        sections=[
            ScoreSection(id=s.id, type=s.type, start_tick=s.start_tick, duration_ticks=s.end_tick - s.start_tick)
            for s in arrangement.sections
        ],
        lyric_lines=[
            LyricLine(id=lp.line.id, text=lp.line.text, section_id=s.id)
            for s in arrangement.sections for lp in s.lines
        ],
        tracks=[
            {"role": "melody", "program": 0, "notes": melody},
            {"role": "accompaniment", "program": 0, "notes": accompaniment},
        ],
    )
    return Composition(score=score, arrangement=arrangement)
