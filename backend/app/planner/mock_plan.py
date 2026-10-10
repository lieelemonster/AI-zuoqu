"""离线演示模型的音乐规划：按风格默认规划，并让段落顺序与歌词结构一致。"""

from __future__ import annotations

import json

from app.presets import default_plan
from app.providers.mock import register_mock


@register_mock("music_plan")
def mock_music_plan(system: str, user: str) -> object:
    start = user.find("创作信息（JSON）：")
    end = user.find("\n可用模板（JSON）：")
    info = json.loads(user[start + len("创作信息（JSON）："):end]) if start >= 0 and end > start else {}
    plan = default_plan(info.get("styleId", "pop"), info.get("emotionId", "warm"), 0)
    by_type = {s.type: s for s in plan.sections}
    lyric_types = [s["type"] for s in info.get("歌词", info.get("歌词结构", []))] or ["verse", "chorus"]
    sections = [by_type["intro"]] if "intro" in by_type else []
    for section_type in lyric_types:
        template = by_type.get(section_type) or by_type["verse"]
        sections.append(template.model_copy(update={"type": section_type}))
    sections += [by_type["outro"]] if "outro" in by_type else []
    data = plan.to_json_dict()
    data["sections"] = [s.to_json_dict() for s in sections]
    for key in ("seed", "schemaVersion", "meter"):
        data.pop(key, None)
    return data
