import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas import CreativeInput, LyricsResult, MusicJobCreate, MusicPlan, Score
from app.schemas.base import format_validation_error

FIXTURES = Path(__file__).parent / "fixtures"
SCORE = json.loads((FIXTURES / "example_score.json").read_text(encoding="utf-8"))
LYRICS = json.loads((FIXTURES / "example_lyrics.json").read_text(encoding="utf-8"))


def errors_of(model, data) -> list[str]:
    with pytest.raises(ValidationError) as info:
        model.model_validate(data)
    return format_validation_error(info.value)


def test_example_score_is_valid():
    score = Score.model_validate(SCORE)
    assert score.total_ticks == 3840
    assert score.duration_seconds == pytest.approx(4.8)
    assert score.to_json_dict()["tracks"][0]["notes"][0]["startTick"] == 0


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [("pitch", 128, "tracks.0.notes.0.pitch"), ("durationTicks", 0, "tracks.0.notes.0.durationTicks")],
)
def test_invalid_note_reports_field(field, value, expected):
    data = copy.deepcopy(SCORE)
    data["tracks"][0]["notes"][0][field] = value
    assert any(line.startswith(expected) for line in errors_of(Score, data))


def test_melody_overlap_rejected():
    data = copy.deepcopy(SCORE)
    data["tracks"][0]["notes"][1]["startTick"] = 240
    assert any("重叠" in line for line in errors_of(Score, data))


def test_accompaniment_chords_may_overlap():
    Score.model_validate(SCORE)
    assert SCORE["tracks"][1]["notes"][0]["startTick"] == SCORE["tracks"][1]["notes"][1]["startTick"]


def test_note_past_end_rejected():
    data = copy.deepcopy(SCORE)
    data["tracks"][0]["notes"][-1]["durationTicks"] = 5000
    assert any("超出乐谱总长" in line for line in errors_of(Score, data))


def test_section_gap_rejected():
    data = copy.deepcopy(SCORE)
    data["sections"][1]["startTick"] = 2000
    assert any("首尾相接" in line for line in errors_of(Score, data))


def test_unknown_lyric_line_rejected():
    data = copy.deepcopy(SCORE)
    data["tracks"][0]["notes"][0]["lyricLineId"] = "line_x"
    assert any("不存在的歌词行" in line for line in errors_of(Score, data))


def test_lyrics_require_three_distinct_approaches():
    LyricsResult.model_validate(LYRICS)
    assert errors_of(LyricsResult, {"variants": LYRICS["variants"][:2]}) == ["variants：至少需要 3 项"]
    duplicated = copy.deepcopy(LYRICS)
    duplicated["variants"][2]["approach"] = "story"
    assert any("各一版" in line for line in errors_of(LyricsResult, duplicated))


def test_music_plan_requires_verse_and_chorus():
    plan = {
        "bpm": 100, "key": "C", "mode": "major", "melodyRange": [60, 79], "seed": 1,
        "sections": [
            {"type": "verse", "bars": 8, "chordPatternId": "pop_a", "rhythmPatternId": "sparse"},
            {"type": "outro", "bars": 4, "chordPatternId": "end", "rhythmPatternId": "end"},
        ],
    }
    assert any("副歌" in line for line in errors_of(MusicPlan, plan))
    plan["sections"][1]["type"] = "chorus"
    assert MusicPlan.model_validate(plan).meter == [4, 4]
    plan["meter"] = [3, 4]
    assert any("4/4" in line for line in errors_of(MusicPlan, plan))


def test_creative_input_and_job_request():
    data = {"themeId": "love", "emotionId": "sweet", "styleId": "pop"}
    assert CreativeInput.model_validate(data).story == ""
    assert any(line.startswith("styleId") for line in errors_of(CreativeInput, {**data, "styleId": ""}))
    job = {"requestId": "req_12345678", "input": data, "lyrics": "[主歌]\n夏夜的风"}
    assert MusicJobCreate.model_validate(job).source_revision == 0
    assert any(line.startswith("lyrics") for line in errors_of(MusicJobCreate, {**job, "lyrics": "   "}))
