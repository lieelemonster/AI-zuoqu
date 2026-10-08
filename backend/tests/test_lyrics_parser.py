import pytest

from app.lyrics.parser import LyricsStructureError, clean_text, parse_lyrics, require_structure


def test_sample_two_sections():
    parsed = parse_lyrics("[主歌]\n夏夜的风\n[副歌]\n一起向前走")
    assert parsed.ok
    assert [(s.id, s.type, [l.text for l in s.lines]) for s in parsed.sections] == [
        ("verse_1", "verse", ["夏夜的风"]),
        ("chorus_1", "chorus", ["一起向前走"]),
    ]


@pytest.mark.parametrize("header", ["[副歌]", "【副歌】", "副歌：", "[副歌2]", "[Chorus]", "Hook:", "[ 副歌 ]"])
def test_header_variants(header):
    parsed = parse_lyrics(f"[主歌]\n夏夜的风\n{header}\n一起向前走")
    assert parsed.ok, parsed.errors
    assert parsed.sections[1].type == "chorus"


def test_repeated_sections_get_numbered_ids_and_global_line_ids():
    text = "[主歌]\n第一句\n[副歌]\n第二句\n[主歌]\n第三句\n[副歌]\n第四句\n[桥段]\n第五句"
    parsed = parse_lyrics(text)
    assert [s.id for s in parsed.sections] == ["verse_1", "chorus_1", "verse_2", "chorus_2", "bridge_1"]
    assert [l.id for l in parsed.lines] == [f"line_{i}" for i in range(1, 6)]


def test_missing_chorus_prompts_without_changing_text():
    text = "[主歌]\n夏夜的风\n一起向前走"
    parsed = parse_lyrics(text)
    assert not parsed.ok
    assert any("[副歌]" in e and "补齐" in e for e in parsed.errors)
    with pytest.raises(LyricsStructureError):
        require_structure(text)
    assert text == "[主歌]\n夏夜的风\n一起向前走"


def test_lines_before_first_header_and_unknown_header():
    parsed = parse_lyrics("夏夜的风\n[尾声]\n再见\n[主歌]\n你好\n[副歌]\n向前")
    assert any("缺少段落标题" in e for e in parsed.errors)
    assert any("无法识别的段落标题「尾声」" in e for e in parsed.errors)


def test_empty_section_is_error():
    parsed = parse_lyrics("[主歌]\n你好\n[副歌]\n")
    assert any("没有歌词" in e for e in parsed.errors)


def test_lyric_line_with_colon_is_not_header():
    parsed = parse_lyrics("[主歌]\n我想对你说：\n[副歌]\n一起向前走")
    assert parsed.ok
    assert parsed.sections[0].lines[0].text == "我想对你说："


def test_char_mapping_rules():
    parsed = parse_lyrics("[主歌]\n你好，2024 Summer night!\n[副歌]\n走")
    line = parsed.lines[0]
    assert line.clean_text == "你好2024Summernight"
    pieces = [line.clean_text[s:e] for s, e in line.units]
    assert pieces == ["你", "好", "2", "0", "2", "4", "Summer", "night"]
    assert clean_text("一起，向前走！") == "一起向前走"


def test_blank_lines_and_punctuation_only_lines_ignored():
    parsed = parse_lyrics("\n[主歌]\n\n夏夜的风\n……\n[副歌]\n一起向前走\n")
    assert parsed.ok
    assert len(parsed.lines) == 2
    assert parsed.warnings
