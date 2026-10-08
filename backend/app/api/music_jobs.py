from fastapi import APIRouter, Depends, Response

from app.api.errors import AppError
from app.composer.arrangement import LyricsLengthError, arrange
from app.lyrics.parser import parse_lyrics
from app.presets import UnknownPresetError, default_plan, get_style, load_composition, validate_creative_input
from app.schemas.job import GenerationJob, MusicJobCreate, MusicJobView
from app.storage.jobs import JobStore, get_store

router = APIRouter()


def job_view(job: GenerationJob) -> MusicJobView:
    ready = job.status == "succeeded"
    return MusicJobView(
        id=job.id,
        status=job.status,
        stage=job.stage,
        error_code=job.error_code,
        error_message=job.error_message,
        duration_seconds=job.duration_seconds if ready else None,
        audio_url=f"/api/music-jobs/{job.id}/audio" if ready else None,
        download_url=f"/api/music-jobs/{job.id}/download" if ready else None,
    )


def check_lyrics(request: MusicJobCreate) -> None:
    """提交时先检查结构与时长，歌词有问题直接提示修改，不进入队列。"""
    try:
        validate_creative_input(request.input)
    except UnknownPresetError as exc:
        raise AppError(422, "INVALID_INPUT", str(exc), fields=[str(exc)]) from exc
    parsed = parse_lyrics(request.lyrics)
    if not parsed.ok:
        raise AppError(422, "LYRICS_STRUCTURE", "歌词结构不完整：" + "；".join(parsed.errors), fields=parsed.errors)
    style_id, emotion_id = request.input.style_id, request.input.emotion_id
    try:
        arrange(parsed, default_plan(style_id, emotion_id, 0), get_style(style_id), load_composition())
    except LyricsLengthError as exc:
        raise AppError(422, exc.code, exc.message, fields=[exc.message]) from exc


@router.post("/music-jobs", response_model=MusicJobView, status_code=201, tags=["music-jobs"])
def create_music_job(request: MusicJobCreate, response: Response,
                     store: JobStore = Depends(get_store)) -> MusicJobView:
    existing = store.get_by_request(request.request_id)
    if existing is not None:
        response.status_code = 200
        return job_view(existing)
    check_lyrics(request)
    job, created = store.create(request)
    if not created:
        response.status_code = 200
    return job_view(job)


@router.get("/music-jobs/{job_id}", response_model=MusicJobView, tags=["music-jobs"])
def get_music_job(job_id: str, store: JobStore = Depends(get_store)) -> MusicJobView:
    job = store.get(job_id)
    if job is None:
        raise AppError(404, "JOB_NOT_FOUND", "找不到该音乐任务")
    return job_view(job)
