"""七种风格验证：每种风格用一版短歌词走完整流程（歌词 → 规划 → 作曲 → 渲染），输出试听文件与客观指标。

客观指标只能发现明显问题；“好不好听、情绪是否贴合”仍需逐一试听。
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from pathlib import Path

from app.composer.check_demo import only, rms_db
from app.composer.compose import compose
from app.composer.harmony import KEY_PC
from app.lyrics.generator import generate_lyrics
from app.lyrics.parser import parse_lyrics
from app.planner.planner import plan_music
from app.presets import load_presets
from app.providers.mock import MockProvider
from app.rendering.audio import render_wav
from app.rendering.midi import write_midi
from app.rendering.pipeline import render_score
from app.schemas.input import CreativeInput
from app.settings import PROJECT_ROOT

CHECK_DIR = PROJECT_ROOT / "runtime" / "checks" / "styles"
CASES = [
    ("pop", "love", "sweet"),
    ("folk", "hometown", "nostalgic"),
    ("guofeng", "memory", "missing"),
    ("rock", "dream", "passionate"),
    ("rnb", "love", "lonely"),
    ("electronic", "travel", "happy"),
    ("rap", "dream", "hopeful"),
]
BEAT = 480


@dataclass
class StyleReport:
    style: str
    emotion: str
    bpm: int
    key: str
    sections: str
    duration: float
    lyric_coverage: float
    chorus_lift: float
    verse_density: float
    chorus_density: float
    distinct_durations: int
    offbeat_ratio: float
    repeat_ratio: float
    max_leap: int
    ending_ok: bool
    lead_db: float
    decay_db: float
    audio_ok: bool
    path: Path
    problems: list[str]

    @property
    def ok(self) -> bool:
        return not self.problems


def _section_notes(score, melody, section_type):
    ranges = [(s.start_tick, s.start_tick + s.duration_ticks) for s in score.sections if s.type == section_type]
    return [n for n in melody if any(a <= n.start_tick < b for a, b in ranges)], sum(b - a for a, b in ranges)


def analyse(style_id: str, theme_id: str, emotion_id: str, seed: int = 11) -> StyleReport:
    names = {o.id: o.name for o in load_presets().emotions}
    data = CreativeInput(theme_id=theme_id, emotion_id=emotion_id, style_id=style_id)
    lyrics = generate_lyrics(data, MockProvider()).variants[0].text
    parsed = parse_lyrics(lyrics)
    plan, _ = plan_music(data, parsed, MockProvider(), seed=seed)
    composition = compose(parsed, plan, style_id, emotion_id)
    score, arrangement = composition.score, composition.arrangement
    melody = score.track("melody").notes
    accompaniment = score.track("accompaniment").notes

    covered = total = 0
    for line in parsed.lines:
        chars = set()
        for n in melody:
            if n.lyric_line_id == line.id and n.char_start is not None:
                chars.update(range(n.char_start, n.char_end))
        covered += len(chars & set(range(len(line.clean_text))))
        total += len(line.clean_text)

    verse, verse_ticks = _section_notes(score, melody, "verse")
    chorus, chorus_ticks = _section_notes(score, melody, "chorus")
    seconds = lambda ticks: score.ticks_to_seconds(ticks)  # noqa: E731
    sung = verse + chorus
    intervals = [abs(b.pitch - a.pitch) for a, b in zip(sung, sung[1:])]
    tonic = KEY_PC[score.key]
    final_melody = max(melody, key=lambda n: n.start_tick)
    final_chord = [n for n in accompaniment if n.end_tick == score.total_ticks]
    ending_ok = (final_melody.pitch % 12 == tonic and final_melody.end_tick == score.total_ticks
                 and bool(final_chord) and min(n.pitch for n in final_chord) % 12 == tonic)

    CHECK_DIR.mkdir(parents=True, exist_ok=True)
    result = render_score(score, CHECK_DIR, style_id)
    tail = arrangement.tail_seconds
    mel = render_wav(write_midi(only(score, "melody"), CHECK_DIR / "_m.mid", tail), CHECK_DIR / "_m.wav")
    acc = render_wav(write_midi(only(score, "accompaniment"), CHECK_DIR / "_a.mid", tail), CHECK_DIR / "_a.wav")
    lead = rms_db(mel.path) - rms_db(acc.path)
    end = result.wav.duration_seconds
    final_start = score.ticks_to_seconds(final_chord[0].start_tick) if final_chord else end - 2
    decay = rms_db(result.wav.path, final_start, final_start + 0.5) - rms_db(result.wav.path, end - 0.3, end)
    for name in ("_m.mid", "_m.wav", "_a.mid", "_a.wav", f"{style_id}.wav", f"{style_id}.mid", f"{style_id}.score.json"):
        (CHECK_DIR / name).unlink(missing_ok=True)

    report = StyleReport(
        style=style_id, emotion=names[emotion_id], bpm=score.bpm, key=f"{score.key} {score.mode}",
        sections=" → ".join(f"{s.type}{s.duration_ticks // 1920}" for s in score.sections),
        duration=result.audio.duration_seconds or 0.0,
        lyric_coverage=covered / total if total else 0.0,
        chorus_lift=(statistics.mean(n.pitch for n in chorus) - statistics.mean(n.pitch for n in verse)),
        verse_density=len(verse) / seconds(verse_ticks), chorus_density=len(chorus) / seconds(chorus_ticks),
        distinct_durations=len({n.duration_ticks for n in sung}),
        offbeat_ratio=sum(1 for n in sung if n.start_tick % BEAT) / len(sung),
        repeat_ratio=sum(1 for i in intervals if i == 0) / len(intervals),
        max_leap=max(intervals), ending_ok=ending_ok, lead_db=lead, decay_db=decay,
        audio_ok=result.audio.ok, path=result.mp3_path, problems=[],
    )
    report.problems = problems(report)
    return report


def problems(r: StyleReport) -> list[str]:
    found = []
    if not r.audio_ok or not 45 <= r.duration <= 75:
        found.append(f"时长 {r.duration:.1f} 秒不合格")
    if "verse" not in r.sections or "chorus" not in r.sections:
        found.append("缺少主歌或副歌")
    if r.lyric_coverage < 1:
        found.append(f"有 {1 - r.lyric_coverage:.0%} 的字没有对应音符")
    if not r.ending_ok or r.decay_db < 20:
        found.append("结尾没有落在主音或没有自然衰减")
    if r.lead_db < 3:
        found.append(f"旋律只比伴奏响 {r.lead_db:.1f} dB，可能被伴奏盖住")
    if r.style != "rap" and r.chorus_lift < 1:
        found.append(f"副歌平均音高只比主歌高 {r.chorus_lift:.1f} 个半音，变化不明显")
    if r.max_leap > 12:
        found.append(f"旋律出现 {r.max_leap} 个半音的大跳，不易演唱")
    if r.repeat_ratio > (0.45 if r.style == "rap" else 0.3):
        found.append(f"同音重复占 {r.repeat_ratio:.0%}，旋律偏单调")
    if r.distinct_durations < 3:
        found.append("节奏时值种类太少，听起来机械")
    return found


def main() -> int:
    style_names = {o.id: o.name for o in load_presets().styles}
    reports = [analyse(*case) for case in CASES]
    header = "| 风格 | 情绪 | 速度/调 | 结构（段落+小节） | 时长 | 字有音符 | 副歌升高 | 主歌/副歌 音符每秒 | 时值种类 | 反拍占比 | 同音重复 | 最大跳进 | 旋律比伴奏响 | 结尾衰减 | 结论 |"
    print(header)
    print("|" + "---|" * 15)
    for r in reports:
        print(f"| {style_names[r.style]} | {r.emotion} | {r.bpm} BPM {r.key} | {r.sections} | {r.duration:.1f}s"
              f" | {r.lyric_coverage:.0%} | {r.chorus_lift:+.1f} | {r.verse_density:.1f}/{r.chorus_density:.1f}"
              f" | {r.distinct_durations} | {r.offbeat_ratio:.0%} | {r.repeat_ratio:.0%} | {r.max_leap}"
              f" | {r.lead_db:.1f} dB | {r.decay_db:.0f} dB | {'✅' if r.ok else '❌ ' + '；'.join(r.problems)} |")
    print(f"\n试听文件：{CHECK_DIR}/<风格ID>.mp3")
    ok = all(r.ok for r in reports)
    print("全部风格通过客观检查（听感仍需逐一试听）。" if ok else "存在需要修正的风格。")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
