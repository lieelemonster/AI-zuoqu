import pytest

from app.presets import load_composition
from app.rendering.audio import render_wav
from app.rendering.check_encode import repeated
from app.rendering.check_render import demo_score
from app.rendering.encode import check_final_audio, encode_mp3
from app.rendering.environment import check_ffmpeg, check_fluidsynth, check_soundfont
from app.rendering.midi import write_midi

pytestmark = pytest.mark.skipif(
    not (check_fluidsynth().ok and check_soundfont().ok and check_ffmpeg().ok), reason="音频工具未配置"
)


def make_mp3(tmp_path, score, name):
    midi = write_midi(score, tmp_path / f"{name}.mid", tail_seconds=load_composition().tail_seconds)
    wav = render_wav(midi, tmp_path / f"{name}.wav")
    return encode_mp3(wav.path, tmp_path / f"{name}.mp3")


def test_sixty_second_mp3_passes(tmp_path):
    result = check_final_audio(make_mp3(tmp_path, repeated(demo_score(), 6), "full"))
    assert result.ok, result.errors
    assert result.codec == "mp3"
    assert 60 <= result.duration_seconds <= 63
    assert not list(tmp_path.glob(".*.tmp.mp3"))


def test_short_mp3_is_not_success(tmp_path):
    result = check_final_audio(make_mp3(tmp_path, demo_score(), "short"))
    assert not result.ok
    assert any("超出允许范围" in e for e in result.errors)


def test_corrupt_or_missing_file_fails(tmp_path):
    bad = tmp_path / "bad.mp3"
    bad.write_bytes(b"not an mp3" * 100)
    assert not check_final_audio(bad).ok
    assert check_final_audio(tmp_path / "none.mp3").errors == ["音频文件不存在或为空"]
