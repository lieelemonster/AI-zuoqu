import json
from pathlib import Path

import mido
import pytest

from app.rendering.check_midi import middle_c_score
from app.rendering.midi import read_midi_notes, score_to_midi, write_midi
from app.schemas import Score

FIXTURES = Path(__file__).parent / "fixtures"


def test_middle_c_round_trip(tmp_path):
    _, notes = read_midi_notes(write_midi(middle_c_score(), tmp_path / "c.mid"))
    melody = [n for n in notes if n.track_name == "melody"]
    assert [(n.pitch, n.start_tick, n.duration_ticks) for n in melody] == [(60, 0, 480)]
    assert melody[0].duration_seconds == pytest.approx(0.5)
    assert {n.channel for n in notes if n.track_name == "accompaniment"} == {1}


def test_example_score_round_trip_preserves_every_note(tmp_path):
    score = Score.model_validate(json.loads((FIXTURES / "example_score.json").read_text(encoding="utf-8")))
    _, notes = read_midi_notes(write_midi(score, tmp_path / "e.mid"))
    for track in score.tracks:
        expected = sorted((n.pitch, n.start_tick, n.duration_ticks) for n in track.notes)
        actual = sorted((n.pitch, n.start_tick, n.duration_ticks) for n in notes if n.track_name == track.role)
        assert actual == expected


def test_repeated_same_pitch_is_not_cut_short(tmp_path):
    score = middle_c_score()
    melody = score.track("melody")
    melody.notes.append(melody.notes[0].model_copy(update={"start_tick": 480}))
    _, notes = read_midi_notes(write_midi(score, tmp_path / "r.mid"))
    assert sorted((n.start_tick, n.duration_ticks) for n in notes if n.track_name == "melody") == [(0, 480), (480, 480)]


def test_tempo_and_tail_in_conductor_track():
    midi = score_to_midi(middle_c_score(), tail_seconds=2.0)
    conductor = midi.tracks[0]
    tempo = next(m.tempo for m in conductor if m.type == "set_tempo")
    assert mido.tempo2bpm(tempo) == pytest.approx(120)
    end = sum(m.time for m in conductor)
    assert end == 1920 + 1920  # 2 秒尾音在 120 BPM 下为 4 拍
