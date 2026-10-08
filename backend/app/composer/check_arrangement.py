"""时长与节奏分配检查：24 小节 100 BPM 为 57.6 秒；短歌词有句间停顿；过长歌词提示缩短且不删词。"""

from app.composer.arrangement import Arrangement, LyricsLengthError, arrange
from app.lyrics.parser import parse_lyrics
from app.presets import default_plan, get_style, load_composition
from app.schemas.score import PPQ

STANDARD = """[主歌]
夏夜的风吹过街角
路灯拉长我们影子
单车铃声穿过小巷
笑声落在时光里面
[副歌]
一起向前走不回头
把梦想装进行囊里
就算风雨也不害怕
我们唱着歌向前走"""

SHORT = "[主歌]\n夏夜的风\n晚霞很红\n[副歌]\n一起向前走\n不要回头"

LONG = "[主歌]\n" + "\n".join(["我们在城市的灯火里慢慢长大"] * 20) + "\n[副歌]\n" + "\n".join(["一起向前走不回头看昨天的自己"] * 20)


def describe(arrangement: Arrangement) -> None:
    for section in arrangement.sections:
        extra = f"（含 {section.gap_bars} 小节间奏）" if section.gap_bars else ""
        print(f"  {section.id:<10} {section.bars:>2} 小节{extra}  和弦 {section.chord.id} / 节奏 {section.rhythm.id}")
        for lp in section.lines:
            rest_beats = lp.rest_ticks / PPQ
            print(f"      {lp.line.text}：{lp.line.unit_count} 字，{lp.bars} 小节，{len(lp.notes)} 个音符，句尾停顿 {rest_beats:g} 拍")


def main() -> int:
    composition = load_composition()
    style = get_style("pop")
    ok = True

    plan = default_plan("pop", "sweet", seed=1).model_copy(update={"bpm": 100})
    plan.sections[0].bars = 4
    plan.sections[-1].bars = 4
    standard = arrange(parse_lyrics(STANDARD), plan, style, composition)
    score = standard.skeleton_score()
    print(f"== 标准歌词（流行，规划 {plan.bpm} BPM）")
    describe(standard)
    print(
        f"  合计 {standard.total_bars} 小节 × 4 拍 × 60 ÷ {standard.bpm} = {score.duration_seconds:.1f} 秒乐谱，"
        f"另计尾音 {standard.tail_seconds:g} 秒 → 约 {standard.total_seconds:.1f} 秒\n"
    )
    ok &= standard.total_bars == 24 and standard.bpm == 100 and abs(score.duration_seconds - 57.6) < 1e-9

    short = arrange(parse_lyrics(SHORT), default_plan("pop", "sweet", seed=1), style, composition)
    print(f"== 短歌词（4 句）→ {short.bpm} BPM，{short.total_bars} 小节，约 {short.total_seconds:.1f} 秒")
    describe(short)
    rests = [lp.rest_ticks for s in short.sections for lp in s.lines]
    ok &= all(r >= PPQ for r in rests) and composition.min_seconds <= short.total_seconds <= composition.max_seconds
    print()

    long_parsed = parse_lyrics(LONG)
    original = LONG
    print(f"== 过长歌词（{len(long_parsed.lines)} 句）")
    try:
        arrange(long_parsed, default_plan("pop", "sweet", seed=1), style, composition)
        print("  ❌ 没有提示缩短")
        ok = False
    except LyricsLengthError as exc:
        print(f"  提示 [{exc.code}]：{exc.message}")
        print(f"  歌词未被删改：{'是' if LONG == original and len(parse_lyrics(LONG).lines) == 40 else '否'}")

    print("\n全部检查符合预期。" if ok else "\n存在不符合预期的检查。")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
