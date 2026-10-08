"""用户创作信息。预设 ID 是否存在由配置模块校验。"""

from pydantic import Field

from app.schemas.base import ApiModel

STORY_MAX_LENGTH = 500


class CreativeInput(ApiModel):
    theme_id: str = Field(min_length=1, max_length=40)
    emotion_id: str = Field(min_length=1, max_length=40)
    style_id: str = Field(min_length=1, max_length=40)
    story: str = Field(default="", max_length=STORY_MAX_LENGTH)
