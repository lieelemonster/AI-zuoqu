"""音乐规划检查：正常规划只引用已有模板；注入未知模板 ID 时最多修复一次，再回退到默认规划。"""

import json

from app.lyrics.parser import parse_lyrics
from app.planner.planner import plan_music
from app.presets import default_plan, plan_errors
from app.providers import ProviderError, get_provider
from app.providers.base import validate_payload
from app.schemas.input import CreativeInput

LYRICS = "[主歌]\n晚风吹过街角\n你笑着回头\n路灯一盏一盏\n照亮我们的路\n[副歌]\n就这样走下去\n不怕夜太长\n就这样走下去\n心里有光"
INPUT = CreativeInput(theme_id="love", emotion_id="sweet", style_id="pop")


class ScriptedProvider:
    """按顺序返回预设输出的模拟模型，用于演示修复与回退。"""
    model_id = "scripted"

    def __init__(self, *outputs):
        self.outputs, self.calls = list(outputs), 0

    def complete_json(self, *, purpose, system, user, schema, temperature=0.8):
        self.calls += 1
        self.last_user = user
        return validate_payload(self.outputs[min(self.calls, len(self.outputs)) - 1], schema)


def _ai_output(**changes) -> dict:
    data = default_plan("pop", "sweet", 0).to_json_dict()
    for key in ("seed", "schemaVersion", "meter"):
        data.pop(key)
    data["sections"][2]["chordPatternId"] = "pop_chorus_b"
    data.update(changes)
    return data


def _show(title: str, plan, record) -> None:
    print(f"\n{title}")
    print(f"  规划来源：{record.source}；模型：{record.model_id}；尝试次数：{len(record.attempts)}"
          + (f"；回退原因：{record.fallback_reason}" if record.fallback_reason else ""))
    for attempt in record.attempts:
        print(f"  - {attempt.kind}：{'通过' if not attempt.errors else '问题：' + '；'.join(attempt.errors)}")
    sections = "、".join(f"{s.type}({s.chord_pattern_id}/{s.rhythm_pattern_id})" for s in plan.sections)
    print(f"  最终规划：{plan.bpm} BPM {plan.key} {plan.mode}；{sections}")
    print(f"  校验：{'✅ 只引用已有模板' if not plan_errors(plan, 'pop') else '❌ ' + str(plan_errors(plan, 'pop'))}")


def main() -> int:
    parsed = parse_lyrics(LYRICS)
    ok = True
    try:
        provider = get_provider()
    except ProviderError as exc:
        provider = None
        print(f"当前文本模型不可用：[{exc.code}] {exc.message}")
    plan, record = plan_music(INPUT, parsed, provider, seed=7)
    _show(f"1. 当前配置的模型（{getattr(provider, 'model_id', '无')}）规划", plan, record)
    ok &= not plan_errors(plan, "pop")

    good = ScriptedProvider(_ai_output())
    plan, record = plan_music(INPUT, parsed, good, seed=7)
    _show("2. 模拟模型给出有效规划", plan, record)
    ok &= record.source == "ai" and good.calls == 1

    bad = _ai_output()
    bad["sections"][1]["chordPatternId"] = "jazz_ii_v_i"
    fixed = ScriptedProvider(bad, _ai_output())
    plan, record = plan_music(INPUT, parsed, fixed, seed=7)
    _show("3. 注入未知模板 ID，修复一次后通过", plan, record)
    ok &= record.source == "ai_repaired" and fixed.calls == 2

    stubborn = ScriptedProvider(bad)
    plan, record = plan_music(INPUT, parsed, stubborn, seed=7)
    _show("4. 注入未知模板 ID，修复后仍无效 → 默认规划", plan, record)
    ok &= record.source == "default" and stubborn.calls == 2 and not plan_errors(plan, "pop")

    print("\n内部记录示例（第 4 项，将随任务保存，不展示在界面）：")
    print(json.dumps(record.to_json_dict(), ensure_ascii=False, indent=2)[:1200])
    print("\n全部检查符合预期。" if ok else "\n存在不符合预期的检查。")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
