"""完整小样检查：伴奏与旋律对齐、旋律比伴奏响、结尾为主和弦自然衰减；生成流行与说唱两版 MP3 供试听。"""

import array
import math
import wave

from app.composer.check_arrangement import STANDARD
from app.composer.compose import compose
from app.composer.harmony import KEY_PC, chord_at, chord_timeline
from app.lyrics.parser import parse_lyrics
from app.presets import default_plan
from app.rendering.audio import RenderError, render_wav
from app.rendering.midi import write_midi
from app.rendering.pipeline import render_score
from app.schemas.score import Score
from app.settings import PROJECT_ROOT

CHECK_DIR = PROJECT_ROOT / "runtime" / "checks"
EIGHTH = 240

RAP = """[主歌]
清晨六点闹钟响起我又出发
背着梦想穿过拥挤人潮不害怕
每一步都踩着节拍向前跨
汗水写下属于自己的回答
[副歌]
我们一起向前冲
不管风雨有多重
把青春唱成歌
燃烧在每个梦"""


def rms_db(path, start=0.0, end=None) -> float:
    with wave.open(str(path), "rb") as w:
        rate, channels = w.getframerate(), w.getnchannels()
        w.setpos(int(start * rate))
        frames = (int(end * rate) if end else w.getnframes()) - int(start * rate)
        data = array.array("h")
        data.frombytes(w.readframes(max(frames, 0)))
    if not data:
        return float("-inf")
    rms = math.sqrt(sum(x * x for x in data) / len(data))
    return 20 * math.log10(rms / 32768) if rms else float("-inf")


def only(score: Score, role: str) -> Score:
    data = score.to_json_dict()
    data["tracks"] = [t for t in data["tracks"] if t["role"] == role]
    if role != "melody":
        data["tracks"].append({"role": "melody", "program": 0, "notes": []})
    return Score.model_validate(data)


def check(name: str, lyrics: str, style_id: str, emotion_id: str, seed: int) -> bool:
    composition = compose(parse_lyrics(lyrics), default_plan(style_id, emotion_id, seed), style_id, emotion_id)
    score, arrangement = composition.score, composition.arrangement
    timeline = chord_timeline(arrangement)
    melody, accompaniment = score.track("melody").notes, score.track("accompaniment").notes
    print(f"== {name}：{score.bpm} BPM {score.key} {score.mode}，" + " → ".join(
        f"{s.id}({(s.duration_ticks // 1920)}小节)" for s in score.sections))

    on_grid = all(n.start_tick % EIGHTH == 0 for n in accompaniment)
    in_chord = all(chord_at(timeline, n.start_tick).contains(n.pitch) for n in accompaniment)
    below = max(n.pitch for n in accompaniment if n.start_tick < score.total_ticks - 2 * 1920) < min(n.pitch for n in melody)
    tonic = KEY_PC[score.key]
    final_melody = max(melody, key=lambda n: n.start_tick)
    final_chord = [n for n in accompaniment if n.end_tick == score.total_ticks]
    ending_ok = (final_melody.pitch % 12 == tonic and final_melody.end_tick == score.total_ticks
                 and final_chord and min(n.pitch for n in final_chord) % 12 == tonic)
    print(f"  伴奏起点都在八分音符网格上：{'是' if on_grid else '否'}；伴奏音都属于当时的和弦：{'是' if in_chord else '否'}；"
          f"伴奏音区低于旋律：{'是' if below else '否'}")
    print(f"  结尾：旋律主音长音与主和弦一起持续到最后：{'是' if ending_ok else '否'}")

    try:
        result = render_score(score, CHECK_DIR, name)
        tail = arrangement.tail_seconds
        mel = render_wav(write_midi(only(score, "melody"), CHECK_DIR / f"{name}_m.mid", tail), CHECK_DIR / f"{name}_m.wav")
        acc = render_wav(write_midi(only(score, "accompaniment"), CHECK_DIR / f"{name}_a.mid", tail), CHECK_DIR / f"{name}_a.wav")
    except RenderError as exc:
        print(f"  ❌ 渲染失败：{exc.message}")
        return False
    lead = rms_db(mel.path) - rms_db(acc.path)
    end = result.wav.duration_seconds
    final_start = score.ticks_to_seconds(final_chord[0].start_tick)
    decay = rms_db(result.wav.path, final_start, final_start + 0.5) - rms_db(result.wav.path, end - 0.3, end)
    print(f"  旋律比伴奏响 {lead:.1f} dB；结尾最后 0.3 秒比主和弦起音时低 {decay:.0f} dB（逐渐衰减，无硬切）")
    print(f"  成品：{result.audio.path}，{result.audio.duration_seconds:.1f} 秒 → "
          f"{'合格' if result.audio.ok else '不合格：' + '；'.join(result.audio.errors)}\n")
    for extra in ("_m", "_a"):
        for suffix in (".mid", ".wav"):
            (CHECK_DIR / f"{name}{extra}{suffix}").unlink(missing_ok=True)
    return on_grid and in_chord and below and ending_ok and lead >= 3 and decay >= 20 and result.audio.ok


def main() -> int:
    ok = check("demo_pop", STANDARD, "pop", "sweet", 42)
    ok &= check("demo_rap", RAP, "rap", "passionate", 42)
    print("检查通过。请用 open runtime/checks/demo_pop.mp3 和 open runtime/checks/demo_rap.mp3 试听。" if ok
          else "存在不符合预期的检查。")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
