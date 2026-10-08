import pytest

from app.composer.arrangement import LyricsLengthError, arrange
from app.composer.check_arrangement import LONG, SHORT, STANDARD
from app.lyrics.parser import parse_lyrics
from app.presets import default_plan, get_style, load_composition, load_presets
from app.schemas.score import PPQ, TICKS_PER_BAR

COMPOSITION = load_composition()


def pop_plan(bpm=100, intro=4, outro=4):
    plan = default_plan("pop", "sweet", seed=1).model_copy(update={"bpm": bpm})
    plan.sections[0].bars = intro
    plan.sections[-1].bars = outro
    return plan


def test_24_bars_at_100_bpm_is_57_6_seconds_plus_tail():
    arrangement = arrange(parse_lyrics(STANDARD), pop_plan(), get_style("pop"), COMPOSITION)
    score = arrangement.skeleton_score()
    assert arrangement.total_bars == 24 and arrangement.bpm == 100
    assert score.total_ticks == 24 * TICKS_PER_BAR
    assert score.duration_seconds == pytest.approx(57.6)
    assert arrangement.total_seconds == pytest.approx(57.6 + COMPOSITION.tail_seconds)


def test_every_unit_gets_one_note_inside_its_line():
    arrangement = arrange(parse_lyrics(STANDARD), pop_plan(), get_style("pop"), COMPOSITION)
    for section in arrangement.sections:
        for lp in section.lines:
            assert [n.unit for n in lp.notes] == lp.line.units
            line_end = (lp.start_bar + lp.bars) * TICKS_PER_BAR
            assert lp.notes[0].start_tick >= lp.start_bar * TICKS_PER_BAR
            assert lp.notes[-1].end_tick <= line_end - PPQ // 2
            assert all(a.end_tick <= b.start_tick for a, b in zip(lp.notes, lp.notes[1:]))


def test_short_lyrics_have_pauses_between_lines():
    arrangement = arrange(parse_lyrics(SHORT), default_plan("pop", "sweet", 1), get_style("pop"), COMPOSITION)
    assert COMPOSITION.min_seconds <= arrangement.total_seconds <= COMPOSITION.max_seconds
    assert all(lp.rest_ticks >= 2 * PPQ for s in arrangement.sections for lp in s.lines)


def test_long_lyrics_prompt_to_shorten_without_deleting():
    parsed = parse_lyrics(LONG)
    with pytest.raises(LyricsLengthError) as info:
        arrange(parsed, default_plan("pop", "sweet", 1), get_style("pop"), COMPOSITION)
    assert info.value.code == "LYRICS_TOO_LONG"
    assert "删减" in info.value.message
    assert len(parsed.lines) == 40


def test_single_overlong_line_reported():
    text = "[主歌]\n" + "长" * 60 + "\n[副歌]\n一起向前走"
    with pytest.raises(LyricsLengthError) as info:
        arrange(parse_lyrics(text), default_plan("pop", "sweet", 1), get_style("pop"), COMPOSITION)
    assert info.value.code == "LINE_TOO_LONG"


def test_fast_style_with_short_lyrics_repeats_chorus_with_same_melody():
    from app.composer.compose import compose

    parsed = parse_lyrics(STANDARD)
    plan = default_plan("rock", "passionate", 11)
    arrangement = arrange(parsed, plan, get_style("rock"), COMPOSITION)
    types = [s.type for s in arrangement.sections]
    assert types.count("chorus") == 2 and types[-2] == "chorus"
    first, again = [s for s in arrangement.sections if s.type == "chorus"]
    assert again.id == f"{first.id}_repeat"
    assert [lp.line.text for lp in again.lines] == [lp.line.text for lp in first.lines]
    assert max(lp.bars for s in arrangement.sections for lp in s.lines) <= 2

    score = compose(parsed, plan, "rock", "passionate").score
    melody = score.track("melody").notes
    sung = lambda section_id: [n.pitch for n in melody
                               if n.lyric_line_id in {l.id for l in score.lyric_lines if l.section_id == section_id}]
    assert sung(first.id) == sung(again.id)


def test_slow_style_does_not_repeat_when_lyrics_fill_the_time():
    arrangement = arrange(parse_lyrics(STANDARD), default_plan("folk", "nostalgic", 1), get_style("folk"), COMPOSITION)
    assert [s.type for s in arrangement.sections].count("chorus") == 1


def test_same_input_same_rhythm():
    a = arrange(parse_lyrics(STANDARD), pop_plan(), get_style("pop"), COMPOSITION).skeleton_score()
    b = arrange(parse_lyrics(STANDARD), pop_plan(), get_style("pop"), COMPOSITION).skeleton_score()
    assert a == b


@pytest.mark.parametrize("style_id", [s.id for s in load_presets().styles])
@pytest.mark.parametrize("emotion_id", ["happy", "sad", "relaxed", "passionate"])
@pytest.mark.parametrize("lyrics", [STANDARD, SHORT], ids=["standard", "short"])
def test_all_styles_fit_duration(style_id, emotion_id, lyrics):
    arrangement = arrange(parse_lyrics(lyrics), default_plan(style_id, emotion_id, 5), get_style(style_id), COMPOSITION)
    assert COMPOSITION.min_seconds + 2 <= arrangement.total_seconds <= COMPOSITION.max_seconds - 2
    assert arrangement.sections[-1].type == "outro"
    arrangement.skeleton_score()
