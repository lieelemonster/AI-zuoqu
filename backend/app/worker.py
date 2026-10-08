"""单个 worker 进程：认领排队任务，依次完成音乐规划、作曲、渲染、编码与成品检查。

与网页接口分开运行，渲染时不影响接口响应。每个任务使用独立目录 runtime/jobs/<任务ID>/：
先在其中的 work/ 生成，成品检查通过后才改名为最终 song.mp3，失败不会影响其他任务的音频。
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import time
from pathlib import Path

from app.composer.arrangement import LyricsLengthError
from app.composer.compose import COMPOSER_VERSION, compose
from app.lyrics.parser import LyricsStructureError, require_structure
from app.planner.planner import PROMPT_VERSION, plan_music
from app.providers import ProviderError, TextModelProvider, get_provider
from app.rendering.audio import RenderError
from app.rendering.pipeline import render_score
from app.schemas.job import GenerationJob
from app.settings import settings
from app.storage.jobs import JobStore, get_store, runtime_dir

logger = logging.getLogger("worker")
POLL_SECONDS = 1.0


class AudioCheckError(Exception):
    pass


def job_directory(job_id: str) -> Path:
    return runtime_dir() / "jobs" / job_id


def _relative(path: Path) -> str:
    return str(path.relative_to(runtime_dir()))


def _provider() -> TextModelProvider | None:
    try:
        return get_provider()
    except ProviderError as exc:
        logger.warning("文本模型不可用，将使用默认规划：%s", exc.message)
        return None


def describe_error(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, RenderError):
        return exc.code, exc.message
    if isinstance(exc, LyricsStructureError):
        return "LYRICS_STRUCTURE", "歌词结构不完整：" + "；".join(exc.errors)
    if isinstance(exc, LyricsLengthError):
        return exc.code, exc.message
    if isinstance(exc, AudioCheckError):
        return "AUDIO_CHECK_FAILED", f"生成的音频未通过检查：{exc}"
    return "INTERNAL_ERROR", "生成过程中出现意外错误，请重新生成"


def process_job(store: JobStore, job: GenerationJob, provider: TextModelProvider | None) -> None:
    started = time.monotonic()
    data = job.input_snapshot
    parsed = require_structure(job.lyrics_snapshot)

    plan, record = plan_music(data, parsed, provider, seed=job.seed)
    store.record_plan(job.id, plan_source=record.source, model_id=record.model_id, prompt_version=PROMPT_VERSION,
                      plan_record=record.to_json_dict(), composer_version=COMPOSER_VERSION,
                      soundfont_version=Path(settings.soundfont_path).name)
    logger.info("%s 规划完成：来源 %s，%d BPM %s %s", job.id, record.source, plan.bpm, plan.key, plan.mode)

    store.set_stage(job.id, "composing")
    composition = compose(parsed, plan, data.style_id, data.emotion_id)

    directory = job_directory(job.id)
    work = directory / "work"
    shutil.rmtree(work, ignore_errors=True)
    result = render_score(composition.score, work, name="song",
                          on_stage=lambda stage: store.set_stage(job.id, stage))
    if not result.audio.ok:
        raise AudioCheckError("；".join(result.audio.errors))

    final = {}
    for path in (result.score_path, result.midi_path, result.mp3_path):
        final[path.suffix] = directory / path.name
        os.replace(path, final[path.suffix])
    shutil.rmtree(work, ignore_errors=True)
    store.succeed(job.id, score_path=_relative(final[".json"]), midi_path=_relative(final[".mid"]),
                  audio_path=_relative(final[".mp3"]), duration_seconds=round(result.audio.duration_seconds, 2))
    logger.info("%s 完成：%.1f 秒 MP3，用时 %.1f 秒", job.id, result.audio.duration_seconds,
                time.monotonic() - started)


def run_once(store: JobStore, provider: TextModelProvider | None = None) -> GenerationJob | None:
    job = store.claim_next()
    if job is None:
        return None
    logger.info("开始处理 %s（风格 %s，种子 %d）", job.id, job.input_snapshot.style_id, job.seed)
    try:
        process_job(store, job, provider if provider is not None else _provider())
    except Exception as exc:
        code, message = describe_error(exc)
        logger.error("%s 失败：[%s] %s", job.id, code, message, exc_info=code == "INTERNAL_ERROR")
        store.fail(job.id, code, message)
        _remove_work(job.id)
    cleanup_old_jobs(store, settings.job_retention)
    return store.get(job.id)


def cleanup_old_jobs(store: JobStore, keep: int) -> None:
    """只保留最近 keep 个已结束任务的文件；keep≤0 表示不清理。"""
    if keep <= 0:
        return
    for job_id in store.expired_jobs(keep):
        directory = job_directory(job_id)
        if directory.exists():
            shutil.rmtree(directory, ignore_errors=True)
            store.clear_files(job_id)
            logger.info("已清理较早任务的文件：%s", job_id)


def _remove_work(job_id: str) -> None:
    directory = job_directory(job_id)
    shutil.rmtree(directory / "work", ignore_errors=True)
    if directory.is_dir() and not any(directory.iterdir()):
        directory.rmdir()


def recover(store: JobStore) -> None:
    for job_id in store.fail_stale_running():
        _remove_work(job_id)
        logger.warning("%s 在上次运行中被中断，已标记为失败", job_id)


def main() -> int:
    parser = argparse.ArgumentParser(description="音乐任务 worker")
    parser.add_argument("--once", action="store_true", help="处理一个排队任务后退出")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s",
                        datefmt="%H:%M:%S")
    store = get_store()
    recover(store)
    logger.info("worker 已启动，数据库 %s，每 %.0f 秒检查一次排队任务（Ctrl+C 退出）", store.path, POLL_SECONDS)
    try:
        while True:
            job = run_once(store)
            if args.once:
                return 0
            if job is None:
                time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        logger.info("worker 已停止")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
