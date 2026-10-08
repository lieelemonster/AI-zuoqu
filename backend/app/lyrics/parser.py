"""歌词结构识别：段落标题、乐句（非空行）与字符映射。只读取歌词，从不改写原文。

字符索引规则：每行先去掉标点、符号和空白，得到“清洗文本”，索引为其中的 Unicode 字符位置，
区间为半开区间 [start, end)。演唱单位（一个音符可对应的最小歌词片段）计数规则：
- 每个汉字（及其他非拉丁文字字符）算 1 个单位；
- 每个阿拉伯数字算 1 个单位（按中文逐字读法，如 2024 读作“二零二四”）；
- 连续拉丁字母（可含撇号）组成的英文单词整体算 1 个单位。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from app.schemas.plan import SectionType

_BRACKET_HEADER = re.compile(r"^\s*[\[【]\s*(?P<name>[^\]】]{1,20}?)\s*[\]】]\s*$")
_COLON_HEADER = re.compile(r"^\s*(?P<name>[^:：\s]{1,12}(?:\s*\S{1,3})?)\s*[:：]\s*$")
_NAME = re.compile(
    r"^(?P<base>主歌|副歌|桥段|预副歌|导歌|verse|chorus|hook|bridge|pre-?chorus)"
    r"\s*[0-9一二三四五ⅠⅡⅢA-Da-d]?$",
    re.IGNORECASE,
)
_SECTION_TYPES: dict[str, SectionType] = {
    "主歌": "verse", "verse": "verse", "预副歌": "verse", "导歌": "verse",
    "prechorus": "verse", "pre-chorus": "verse",
    "副歌": "chorus", "chorus": "chorus", "hook": "chorus",
    "桥段": "bridge", "bridge": "bridge",
}
SECTION_LABELS: dict[SectionType, str] = {"verse": "主歌", "chorus": "副歌", "bridge": "桥段"}


@dataclass(frozen=True)
class ParsedLine:
    id: str
    text: str
    clean_text: str
    units: list[tuple[int, int]]
    line_number: int

    @property
    def unit_count(self) -> int:
        return len(self.units)


@dataclass(frozen=True)
class ParsedSection:
    id: str
    type: SectionType
    label: str
    lines: list[ParsedLine]
    line_number: int


@dataclass
class ParsedLyrics:
    sections: list[ParsedSection] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def lines(self) -> list[ParsedLine]:
        return [line for section in self.sections for line in section.lines]


class LyricsStructureError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("；".join(errors))
        self.errors = errors


def clean_text(text: str) -> str:
    """去掉标点、符号、空白，保留文字与数字。"""
    return "".join(ch for ch in text if unicodedata.category(ch)[0] in ("L", "N"))


def _is_latin(ch: str) -> bool:
    return ch.isascii() and ch.isalpha()


def split_units(clean: str) -> list[tuple[int, int]]:
    units, i = [], 0
    while i < len(clean):
        if _is_latin(clean[i]):
            j = i
            while j < len(clean) and _is_latin(clean[j]):
                j += 1
            units.append((i, j))
            i = j
        else:
            units.append((i, i + 1))
            i += 1
    return units


def _units_for_line(text: str) -> tuple[str, list[tuple[int, int]]]:
    # 英文单词之间的空格在清洗时会被去掉，先按空白分词再拼接，保证单词边界不丢失。
    clean, units = "", []
    for token in text.split():
        token_clean = clean_text(token)
        offset = len(clean)
        units += [(offset + s, offset + e) for s, e in split_units(token_clean)]
        clean += token_clean
    return clean, units


def header_type(line: str) -> tuple[bool, SectionType | None, str]:
    """返回（是否像标题，识别出的段落类型，标题文字）。"""
    match = _BRACKET_HEADER.match(line) or _COLON_HEADER.match(line)
    if not match:
        return False, None, ""
    name = match.group("name").strip()
    known = _NAME.match(name.replace(" ", "")) or _NAME.match(name)
    if not known:
        return bool(_BRACKET_HEADER.match(line)), None, name
    base = known.group("base").lower().replace(" ", "")
    return True, _SECTION_TYPES[base], name


def parse_lyrics(text: str) -> ParsedLyrics:
    result = ParsedLyrics()
    counters: dict[str, int] = {}
    current: dict | None = None
    drafts: list[dict] = []
    line_counter = 0

    for number, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped:
            continue
        is_header, section_type, name = header_type(stripped)
        if is_header and section_type is None:
            result.errors.append(f"第 {number} 行：无法识别的段落标题「{name}」，请改为 [主歌]、[副歌] 或 [桥段]")
            current = None
            continue
        if is_header:
            counters[section_type] = counters.get(section_type, 0) + 1
            current = {
                "id": f"{section_type}_{counters[section_type]}", "type": section_type,
                "label": name, "lines": [], "line_number": number,
            }
            drafts.append(current)
            continue
        if current is None:
            if not result.errors or "缺少段落标题" not in result.errors[-1]:
                result.errors.append(f"第 {number} 行「{stripped[:12]}」前缺少段落标题，请在上方补上 [主歌] 或 [副歌]")
            continue
        clean, units = _units_for_line(stripped)
        if not units:
            result.warnings.append(f"第 {number} 行没有可演唱的文字，已跳过")
            continue
        line_counter += 1
        current["lines"].append(ParsedLine(f"line_{line_counter}", stripped, clean, units, number))

    for draft in drafts:
        if not draft["lines"]:
            result.errors.append(f"第 {draft['line_number']} 行：段落「{draft['label']}」下没有歌词")
        result.sections.append(ParsedSection(**draft))

    types = {s.type for s in result.sections if s.lines}
    if "verse" not in types:
        result.errors.append("缺少 [主歌] 段落标题，请在主歌歌词上方补齐")
    if "chorus" not in types:
        result.errors.append("缺少 [副歌] 段落标题，请在副歌歌词上方补齐")
    return result


def require_structure(text: str) -> ParsedLyrics:
    parsed = parse_lyrics(text)
    if not parsed.ok:
        raise LyricsStructureError(parsed.errors)
    return parsed
