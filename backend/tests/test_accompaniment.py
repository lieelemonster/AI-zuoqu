import pytest

from app.composer.check_arrangement import SHORT, STANDARD
from app.composer.check_demo import RAP
from app.composer.compose import compose
from app.composer.harmony import KEY_PC, chord_at, chord_timeline
from app.lyrics.parser import parse_lyrics
from app.presets import default_plan, get_style, load_presets

STYLES = [s.id for s in load_presets().styles]


@pytest.mark.parametrize("style_id", STYLES)
@pytest.mark.parametrize("emotion_id", ["sweet", "sad", "passionate"])
@pytest.mark.parametrize("lyrics", [STANDARD, SHORT, RAP], ids=["standard", "short", "rap"])
def test_accompaniment_aligned_and_ending_stable(style_id, emotion_id, lyrics):
    result = compose(parse_lyrics(lyrics), default_plan(style_id, emotion_id, 9), style_id, emotion_id)
    score, timeline = result.score, chord_timeline(result.arrangement)
    accompaniment = score.track("accompaniment").notes
    melody = score.track("melody").notes
    assert accompaniment

    assert all(n.start_tick % 240 == 0 for n in accompaniment)
    assert all(chord_at(timeline, n.start_tick).contains(n.pitch) for n in accompaniment)
    assert all(n.end_tick <= score.total_ticks for n in accompaniment)
    assert max(n.pitch for n in accompaniment) < get_style(style_id).melody_range[0]
    assert max(n.velocity for n in accompaniment) < min(n.velocity for n in melody if n.lyric_line_id) + 10

    for section in score.sections:
        assert any(section.start_tick <= n.start_tick < section.start_tick + section.duration_ticks for n in accompaniment)

    tonic = KEY_PC[score.key]
    final = [n for n in accompaniment if n.end_tick == score.total_ticks]
    assert final and min(n.pitch for n in final) % 12 == tonic
    assert timeline[-1].root_pc == tonic


def test_no_same_pitch_overlap_in_accompaniment():
    score = compose(parse_lyrics(STANDARD), default_plan("folk", "warm", 1), "folk", "warm").score
    by_pitch = {}
    for note in sorted(score.track("accompaniment").notes, key=lambda n: n.start_tick):
        previous = by_pitch.get(note.pitch)
        assert previous is None or previous.end_tick <= note.start_tick
        by_pitch[note.pitch] = note
