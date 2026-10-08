"""音乐生成任务：提交请求、内部记录与对外状态。"""

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.base import ApiModel
from app.schemas.input import CreativeInput
from app.schemas.lyrics import LYRICS_MAX_LENGTH

JobStatus = Literal["queued", "running", "succeeded", "failed"]
JobStage = Literal["queued", "planning", "composing", "rendering", "encoding", "checking", "done"]
PlanSource = Literal["ai", "ai_repaired", "default"]


class MusicJobCreate(ApiModel):
    request_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    source_revision: int = Field(default=0, ge=0)
    input: CreativeInput
    lyrics: str = Field(min_length=1, max_length=LYRICS_MAX_LENGTH)
    selected_variant_id: str | None = Field(default=None, max_length=40)


class GenerationJob(ApiModel):
    id: str
    request_id: str
    source_revision: int = 0
    input_snapshot: CreativeInput
    lyrics_snapshot: str
    status: JobStatus = "queued"
    stage: JobStage = "queued"
    error_code: str | None = None
    error_message: str | None = None
    composer_version: str = ""
    prompt_version: str = ""
    soundfont_version: str = ""
    model_id: str = ""
    plan_source: PlanSource | None = None
    seed: int | None = None
    score_path: str | None = None
    midi_path: str | None = None
    audio_path: str | None = None
    duration_seconds: float | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class MusicJobView(ApiModel):
    """返回给前端的任务状态，不包含内部文件路径。"""

    id: str
    status: JobStatus
    stage: JobStage
    error_code: str | None = None
    error_message: str | None = None
    duration_seconds: float | None = None
    audio_url: str | None = None
    download_url: str | None = None
