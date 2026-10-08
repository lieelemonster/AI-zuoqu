"""单个 worker 进程：认领排队任务，依次完成音乐规划、作曲、渲染、编码与成品检查。

与网页接口分开运行，渲染时不影响接口响应。每个任务的文件放在 runtime/jobs/<任务ID>/。
"""

from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

from app.composer.compose import COMPOSER_VERSION, compose
from app.lyrics.parser import require_structure
from app.planner.planner import PROMPT_VERSION, plan_music
from app.providers import ProviderError, TextModelProvider, get_provider
from app.rendering.pipeline import render_score
from app.schemas.job import GenerationJob
from app.settings import settings
from app.storage.jobs import JobStore, get_store, runtime_dir

logger = logging.getLogger("worker")
POLL_SECONDS = 1.0


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

    result = render_score(composition.score, job_directory(job.id), name="song",
                          on_stage=lambda stage: store.set_stage(job.id, stage))
    audio = result.audio
    if not audio.ok:
        raise RuntimeError("成品检查未通过：" + "；".join(audio.errors))
    store.succeed(job.id, score_path=_relative(result.score_path), midi_path=_relative(result.midi_path),
                  audio_path=_relative(result.mp3_path),
                  duration_seconds=round(audio.duration_seconds, 2))
    logger.info("%s 完成：%.1f 秒 MP3，用时 %.1f 秒", job.id, audio.duration_seconds, time.monotonic() - started)


def run_once(store: JobStore, provider: TextModelProvider | None = None) -> GenerationJob | None:
    job = store.claim_next()
    if job is None:
        return None
    logger.info("开始处理 %s（风格 %s，种子 %d）", job.id, job.input_snapshot.style_id, job.seed)
    process_job(store, job, provider if provider is not None else _provider())
    return store.get(job.id)


def main() -> int:
    parser = argparse.ArgumentParser(description="音乐任务 worker")
    parser.add_argument("--once", action="store_true", help="处理一个排队任务后退出")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s",
                        datefmt="%H:%M:%S")
    store = get_store()
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
