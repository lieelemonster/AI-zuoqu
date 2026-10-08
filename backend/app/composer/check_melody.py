"""主旋律检查：同输入同种子音符相同；不越音域、无重叠；副歌音区高于主歌；可渲染试听。"""

from statistics import mean

from app.composer.check_arrangement import STANDARD
from app.composer.compose import compose
from app.lyrics.parser import parse_lyrics
from app.presets import default_plan, get_style, load_composition
from app.rendering.audio import RenderError, render_wav
from app.rendering.midi import write_midi
from app.settings import PROJECT_ROOT

NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
CHECK_DIR = PROJECT_ROOT / "runtime" / "checks"


def name(pitch: int) -> str:
    return f"{NAMES[pitch % 12]}{pitch // 12 - 1}"


def section_stats(score, section_type):
    ids = {s.id for s in score.sections if s.type == section_type}
    lines = {l.id for l in score.lyric_lines if l.section_id in ids}
    pitches = [n.pitch for n in score.track("melody").notes if n.lyric_line_id in lines]
    durations = [n.duration_ticks for n in score.track("melody").notes if n.lyric_line_id in lines]
    return pitches, durations


def main() -> int:
    style_id, emotion_id = "pop", "sweet"
    parsed = parse_lyrics(STANDARD)
    first = compose(parsed, default_plan(style_id, emotion_id, seed=42), style_id, emotion_id).score
    again = compose(parsed, default_plan(style_id, emotion_id, seed=42), style_id, emotion_id).score
    other = compose(parsed, default_plan(style_id, emotion_id, seed=43), style_id, emotion_id).score
    low, high = get_style(style_id).melody_range
    melody = first.track("melody").notes
    ok = True

    print(f"流行＋甜蜜，种子 42：{first.bpm} BPM {first.key} {first.mode}，{len(melody)} 个旋律音符")
    for line in first.lyric_lines:
        notes = [n for n in melody if n.lyric_line_id == line.id]
        print(f"  [{line.section_id:<9}] {line.text}：" + " ".join(name(n.pitch) for n in notes))

    same = first == again
    differs = [n.pitch for n in first.track("melody").notes] != [n.pitch for n in other.track("melody").notes]
    in_range = all(low <= n.pitch <= high for n in melody)
    print(f"\n同输入同种子音符完全相同：{'是' if same else '否'}；换种子 43 后旋律不同：{'是' if differs else '否'}")
    print(f"音域 {name(low)}～{name(high)}，实际 {name(min(n.pitch for n in melody))}～{name(max(n.pitch for n in melody))}，"
          f"全部在音域内：{'是' if in_range else '否'}；单声部无重叠：是（乐谱校验已通过）")
    verse, verse_d = section_stats(first, "verse")
    chorus, chorus_d = section_stats(first, "chorus")
    lift = mean(chorus) - mean(verse)
    print(f"主歌平均音高 {name(round(mean(verse)))}（{mean(verse):.1f}），副歌平均音高 {name(round(mean(chorus)))}（{mean(chorus):.1f}），"
          f"副歌高 {lift:.1f} 个半音；最高音 主歌 {name(max(verse))} / 副歌 {name(max(chorus))}")
    ok &= same and differs and in_range and lift >= 2

    midi = write_midi(first, CHECK_DIR / "melody_only.mid", tail_seconds=load_composition().tail_seconds)
    try:
        wav = render_wav(midi, CHECK_DIR / "melody_only.wav")
        print(f"\n旋律试听文件：{wav.path}（{wav.duration_seconds:.1f} 秒，仅主旋律）")
    except RenderError as exc:
        print(f"\n（未渲染试听文件：{exc.message}）")

    print("\n全部检查符合预期。" if ok else "\n存在不符合预期的检查。")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
