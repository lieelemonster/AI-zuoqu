import pytest

from app.rendering.audio import RenderError, inspect_wav, render_wav
from app.rendering.check_render import demo_score
from app.rendering.environment import check_fluidsynth, check_soundfont
from app.rendering.midi import write_midi

audio_tools = pytest.mark.skipif(
    not (check_fluidsynth().ok and check_soundfont().ok), reason="未配置 FluidSynth 或钢琴音源"
)


@audio_tools
def test_render_demo_has_sound_without_clipping(tmp_path):
    score = demo_score()
    midi = write_midi(score, tmp_path / "demo.mid", tail_seconds=2.0)
    info = render_wav(midi, tmp_path / "demo.wav")
    assert info.peak > 0.05 and info.clipped_samples == 0
    assert score.duration_seconds < info.duration_seconds < score.duration_seconds + 2.5
    assert inspect_wav(tmp_path / "demo.wav").duration_seconds == pytest.approx(info.duration_seconds)
    assert not list(tmp_path.glob(".*.tmp.wav"))


@audio_tools
def test_missing_soundfont_returns_error(tmp_path):
    midi = write_midi(demo_score(), tmp_path / "demo.mid")
    with pytest.raises(RenderError) as info:
        render_wav(midi, tmp_path / "x.wav", soundfont_path=str(tmp_path / "none.sf2"))
    assert info.value.code == "SOUNDFONT_UNAVAILABLE"
    assert not (tmp_path / "x.wav").exists()


def test_missing_fluidsynth_returns_error(tmp_path):
    with pytest.raises(RenderError) as info:
        render_wav(tmp_path / "a.mid", tmp_path / "x.wav", fluidsynth_path="")
    assert info.value.code == "FLUIDSYNTH_UNAVAILABLE"
