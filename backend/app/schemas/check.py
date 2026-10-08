"""数据格式检查：示例乐谱应通过，非法音高、时值和不足三版的歌词应被拒绝。"""

import copy
import json
from pathlib import Path

from pydantic import BaseModel, ValidationError

from app.schemas.base import format_validation_error
from app.schemas.lyrics import LyricsResult
from app.schemas.score import Score

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures"


def _expect_rejected(title: str, model: type[BaseModel], data: dict) -> bool:
    try:
        model.model_validate(data)
    except ValidationError as exc:
        print(f"✅ {title}：被拒绝")
        for line in format_validation_error(exc):
            print(f"   {line}")
        return True
    print(f"❌ {title}：本应被拒绝却通过了")
    return False


def main() -> int:
    score_data = json.loads((FIXTURES / "example_score.json").read_text(encoding="utf-8"))
    lyrics_data = json.loads((FIXTURES / "example_lyrics.json").read_text(encoding="utf-8"))
    ok = True

    score = Score.model_validate(score_data)
    melody = score.track("melody")
    print(
        f"✅ 示例乐谱校验通过：{len(score.sections)} 个段落，旋律 {len(melody.notes)} 个音符，"
        f"乐谱时长 {score.duration_seconds:.1f} 秒"
    )
    LyricsResult.model_validate(lyrics_data)
    print("✅ 示例三版歌词校验通过")

    bad_pitch = copy.deepcopy(score_data)
    bad_pitch["tracks"][0]["notes"][0]["pitch"] = 128
    ok &= _expect_rejected("音高设为 128", Score, bad_pitch)

    bad_duration = copy.deepcopy(score_data)
    bad_duration["tracks"][0]["notes"][0]["durationTicks"] = 0
    ok &= _expect_rejected("时值设为 0", Score, bad_duration)

    two_variants = {"variants": lyrics_data["variants"][:2]}
    ok &= _expect_rejected("歌词只有两版", LyricsResult, two_variants)

    print("\n全部检查符合预期。" if ok else "\n存在不符合预期的检查。")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
