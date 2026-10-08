"""MP3 编码与成品检查：约 60 秒的测试成品通过；约 11 秒的短成品因时长不合格而不能标记成功。"""

from app.presets import load_composition
from app.rendering.audio import RenderError, render_wav
from app.rendering.check_render import demo_score
from app.rendering.encode import AudioCheck, check_final_audio, encode_mp3
from app.rendering.midi import write_midi
from app.schemas.score import Score
from app.settings import PROJECT_ROOT

CHECK_DIR = PROJECT_ROOT / "runtime" / "checks"


def repeated(score: Score, times: int) -> Score:
    """把四小节示例重复多次，得到指定长度的测试乐谱。"""
    span = score.total_ticks
    data = score.to_json_dict()
    data["sections"] = [
        {"id": f"verse_{i + 1}", "type": "verse", "startTick": i * span, "durationTicks": span}
        for i in range(times)
    ]
    for track in data["tracks"]:
        track["notes"] = [
            {**note, "startTick": note["startTick"] + i * span} for i in range(times) for note in track["notes"]
        ]
    return Score.model_validate(data)


def build(name: str, score: Score) -> AudioCheck:
    tail = load_composition().tail_seconds
    midi = write_midi(score, CHECK_DIR / f"{name}.mid", tail_seconds=tail)
    wav = render_wav(midi, CHECK_DIR / f"{name}.wav")
    mp3 = encode_mp3(wav.path, CHECK_DIR / f"{name}.mp3")
    return check_final_audio(mp3)


def report(label: str, result: AudioCheck) -> None:
    status = "可标记成功" if result.ok else "不能标记成功"
    print(f"{label}：{result.path.name}，时长 {result.duration_seconds:.2f} 秒，"
          f"{result.size_bytes / 1024:.0f} KB，编码 {result.codec} → {status}")
    for error in result.errors:
        print(f"   原因：{error}")


def main() -> int:
    config = load_composition()
    print(f"允许时长 {config.min_seconds:g}～{config.max_seconds:g} 秒\n")
    try:
        full = build("encode_full", repeated(demo_score(), 6))
        short = build("encode_short", demo_score())
    except RenderError as exc:
        print(f"❌ 生成失败 [{exc.code}]：{exc.message}")
        return 1
    report("✅ 60 秒测试成品" if full.ok else "❌ 60 秒测试成品", full)
    report("✅ 短测试成品" if not short.ok else "❌ 短测试成品", short)
    ok = full.ok and not short.ok
    print(f"\n检查通过，可用 open {full.path} 试听 MP3。" if ok else "\n检查失败。")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
