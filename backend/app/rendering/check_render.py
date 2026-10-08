"""WAV 渲染检查：渲染一段旋律加和弦，检查非空、无削顶；缺音源时应返回错误。"""

from app.rendering.audio import RenderError, render_wav
from app.rendering.midi import write_midi
from app.schemas.score import Score
from app.settings import PROJECT_ROOT

CHECK_DIR = PROJECT_ROOT / "runtime" / "checks"
TAIL_SECONDS = 2.0


def demo_score() -> Score:
    """四小节 C–G–Am–F：右手简单旋律，左手低音加三和弦。"""
    q = 480
    melody = [64, 62, 60, 62, 64, 64, 64, None, 62, 62, 64, 62, 60, None, None, None]
    melody_notes, tick = [], 0
    for i, pitch in enumerate(melody):
        if pitch is not None:
            length = q
            while i + 1 < len(melody) and melody[i + 1] is None and length < 4 * q:
                length += q
                i += 1
            melody_notes.append({"pitch": pitch, "startTick": tick, "durationTicks": length, "velocity": 92})
        tick += q
    chords = [(36, [48, 52, 55]), (43, [47, 50, 55]), (45, [48, 52, 57]), (41, [45, 48, 53])]
    accompaniment = []
    for bar, (bass, triad) in enumerate(chords):
        start = bar * 4 * q
        accompaniment.append({"pitch": bass, "startTick": start, "durationTicks": 4 * q, "velocity": 70})
        for half in (0, 2 * q):
            accompaniment += [
                {"pitch": p, "startTick": start + half, "durationTicks": 2 * q, "velocity": 58} for p in triad
            ]
    return Score.model_validate({
        "bpm": 96,
        "sections": [{"id": "verse_1", "type": "verse", "startTick": 0, "durationTicks": 16 * q}],
        "tracks": [
            {"role": "melody", "program": 0, "notes": melody_notes},
            {"role": "accompaniment", "program": 0, "notes": accompaniment},
        ],
    })


def main() -> int:
    score = demo_score()
    midi_path = write_midi(score, CHECK_DIR / "render_test.mid", tail_seconds=TAIL_SECONDS)
    wav_path = CHECK_DIR / "render_test.wav"
    ok = True
    try:
        info = render_wav(midi_path, wav_path)
    except RenderError as exc:
        print(f"❌ 渲染失败 [{exc.code}]：{exc.message}")
        return 1
    print(f"✅ 已渲染 {info.path}")
    print(
        f"   大小 {info.size_bytes / 1024:.0f} KB，时长 {info.duration_seconds:.2f} 秒"
        f"（乐谱 {score.duration_seconds:.1f} 秒＋尾音），{info.channels} 声道 {info.sample_rate} Hz"
    )
    print(f"   峰值 {info.peak:.3f}（{info.peak_dbfs:.1f} dBFS），削顶采样 {info.clipped_samples} 个")
    ok &= info.size_bytes > 0 and info.clipped_samples == 0 and info.duration_seconds >= score.duration_seconds

    try:
        render_wav(midi_path, CHECK_DIR / "should_not_exist.wav", soundfont_path="")
        print("❌ 未配置音源时没有报错")
        ok = False
    except RenderError as exc:
        print(f"✅ 缺音源时返回错误 [{exc.code}]：{exc.message}")
    try:
        render_wav(midi_path, CHECK_DIR / "should_not_exist.wav", soundfont_path="tools/soundfonts/missing.sf2")
        print("❌ 音源文件不存在时没有报错")
        ok = False
    except RenderError as exc:
        print(f"✅ 音源文件不存在时返回错误 [{exc.code}]：{exc.message}")

    print("\n检查通过，请用播放器打开上面的 WAV 试听：应能听到钢琴旋律和低音和弦。" if ok else "\n检查失败。")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
