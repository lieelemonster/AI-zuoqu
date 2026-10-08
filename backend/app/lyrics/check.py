"""歌词结构检查：识别主歌/副歌及歌词行；缺副歌标题时提示补齐且不改原文。"""

from app.lyrics.parser import SECTION_LABELS, parse_lyrics

SAMPLE = "[主歌]\n夏夜的风\n[副歌]\n一起向前走"
MISSING_CHORUS = "[主歌]\n夏夜的风\n吹过2024年的Summer night\n一起向前走"


def show(title: str, text: str) -> bool:
    original = text
    parsed = parse_lyrics(text)
    print(f"== {title}")
    print("输入：" + text.replace("\n", "⏎"))
    for section in parsed.sections:
        print(f"  {SECTION_LABELS[section.type]}（{section.id}，标题「{section.label}」）")
        for line in section.lines:
            units = "｜".join(line.clean_text[s:e] for s, e in line.units)
            print(f"    {line.id}：「{line.text}」→ {line.unit_count} 个演唱单位：{units}")
    for error in parsed.errors:
        print(f"  提示：{error}")
    unchanged = text == original
    print(f"  原文未被修改：{'是' if unchanged else '否'}\n")
    return unchanged


def main() -> int:
    ok = show("标准示例", SAMPLE)
    sample = parse_lyrics(SAMPLE)
    ok &= sample.ok and [s.type for s in sample.sections] == ["verse", "chorus"]
    ok &= [line.text for line in sample.lines] == ["夏夜的风", "一起向前走"]
    ok &= show("缺少副歌标题", MISSING_CHORUS)
    missing = parse_lyrics(MISSING_CHORUS)
    ok &= not missing.ok and any("副歌" in e for e in missing.errors)
    print("全部检查符合预期。" if ok else "存在不符合预期的检查。")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
