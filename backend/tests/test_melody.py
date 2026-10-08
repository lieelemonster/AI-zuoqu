from statistics import mean

import pytest

from app.composer.check_arrangement import SHORT, STANDARD
from app.composer.compose import compose
from app.composer.harmony import KEY_PC, chord_pcs
from app.lyrics.parser import parse_lyrics
from app.presets import default_plan, get_style, load_presets

STYLES = [s.id for s in load_presets().styles]


def make(style_id="pop", emotion_id="sweet", seed=42, lyrics=STANDARD):
    return compose(parse_lyrics(lyrics), default_plan(style_id, emotion_id, seed), style_id, emotion_id).score


def pitches_of(score, section_type):
    ids = {s.id for s in score.sections if s.type == section_type}
    lines = {l.id for l in score.lyric_lines if l.section_id in ids}
    return [n.pitch for n in score.track("melody").notes if n.lyric_line_id in lines]


def test_same_input_rules_and_seed_give_same_notes():
    assert make(seed=42) == make(seed=42)
    first = [n.pitch for n in make(seed=42).track("melody").notes]
    assert first != [n.pitch for n in make(seed=43).track("melody").notes]


def test_chord_spelling():
    assert chord_pcs("1", "C", "major") == (0, (0, 4, 7))
    assert chord_pcs("5", "A", "minor") == (4, (4, 7, 11))
    assert chord_pcs("5:M", "A", "minor") == (4, (4, 8, 11))
    assert chord_pcs("2:7", "F", "major") == (7, (7, 10, 2, 5))


@pytest.mark.parametrize("style_id", STYLES)
@pytest.mark.parametrize("emotion_id", ["happy", "sad", "warm", "passionate"])
@pytest.mark.parametrize("lyrics", [STANDARD, SHORT], ids=["standard", "short"])
def test_melody_rules_hold_for_every_style(style_id, emotion_id, lyrics):
    score = make(style_id, emotion_id, seed=11, lyrics=lyrics)
    low, high = get_style(style_id).melody_range
    melody = score.track("melody").notes
    assert all(low <= n.pitch <= high for n in melody)
    assert all(n.lyric_line_id for n in melody if n.char_start is not None)

    lyric_units = sum(len(l.units) for l in parse_lyrics(lyrics).lines)
    assert sum(1 for n in melody if n.lyric_line_id) == lyric_units

    verse, chorus = pitches_of(score, "verse"), pitches_of(score, "chorus")
    assert mean(chorus) - mean(verse) >= 1.5 or max(chorus) - max(verse) >= 2

    last = max(melody, key=lambda n: n.start_tick)
    assert last.pitch % 12 == KEY_PC[score.key]
    assert last.end_tick == score.total_ticks


def test_rap_verse_is_a_narrow_rhythmic_motif():
    score = make("rap", "passionate", seed=3)
    verse = pitches_of(score, "verse")
    assert max(verse) - min(verse) <= 7
    assert len(set(verse)) <= 5


def test_chorus_hook_repeats():
    score = make("pop", "sweet", seed=42)
    chorus_lines = [l.id for l in score.lyric_lines if l.section_id.startswith("chorus")]
    melody = score.track("melody").notes
    line = lambda lid: [n.pitch for n in melody if n.lyric_line_id == lid]  # noqa: E731
    assert line(chorus_lines[0]) == line(chorus_lines[2])
