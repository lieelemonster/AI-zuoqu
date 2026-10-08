"""SQLite 任务存储。只做短事务；不在事务中调用模型或渲染音频。数据库与任务文件不保存密钥。"""

from __future__ import annotations

import json
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from app.rendering.environment import resolve_path
from app.schemas.input import CreativeInput
from app.schemas.job import GenerationJob, MusicJobCreate
from app.settings import PROJECT_ROOT, settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL UNIQUE,
    source_revision INTEGER NOT NULL DEFAULT 0,
    input_json TEXT NOT NULL,
    lyrics_snapshot TEXT NOT NULL,
    selected_variant_id TEXT,
    status TEXT NOT NULL,
    stage TEXT NOT NULL,
    error_code TEXT,
    error_message TEXT,
    composer_version TEXT NOT NULL DEFAULT '',
    prompt_version TEXT NOT NULL DEFAULT '',
    soundfont_version TEXT NOT NULL DEFAULT '',
    model_id TEXT NOT NULL DEFAULT '',
    plan_source TEXT,
    plan_record_json TEXT,
    seed INTEGER NOT NULL,
    score_path TEXT,
    midi_path TEXT,
    audio_path TEXT,
    duration_seconds REAL,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS jobs_status_created ON jobs (status, created_at);
"""

_COLUMNS = ("id", "request_id", "source_revision", "lyrics_snapshot", "status", "stage", "error_code",
            "error_message", "composer_version", "prompt_version", "soundfont_version", "model_id",
            "plan_source", "seed", "score_path", "midi_path", "audio_path", "duration_seconds", "created_at",
            "started_at", "finished_at")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class JobStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(SCHEMA)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=10000")
        try:
            yield conn
        finally:
            conn.close()

    def create(self, request: MusicJobCreate) -> tuple[GenerationJob, bool]:
        """创建排队任务；相同 requestId 重复提交时返回原任务和 False。"""
        job_id = f"job_{uuid.uuid4().hex[:16]}"
        with self.connect() as conn:
            try:
                conn.execute(
                    "INSERT INTO jobs (id, request_id, source_revision, input_json, lyrics_snapshot,"
                    " selected_variant_id, status, stage, seed, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, 'queued', 'queued', ?, ?)",
                    (job_id, request.request_id, request.source_revision,
                     json.dumps(request.input.to_json_dict(), ensure_ascii=False), request.lyrics,
                     request.selected_variant_id, secrets.randbelow(2**31), now()),
                )
                created = True
            except sqlite3.IntegrityError:
                created = False
            row = conn.execute("SELECT * FROM jobs WHERE request_id = ?", (request.request_id,)).fetchone()
        return self._job(row), created

    def claim_next(self) -> GenerationJob | None:
        """短事务认领最早的排队任务并标记为运行中。"""
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT id FROM jobs WHERE status = 'queued' ORDER BY created_at, rowid LIMIT 1").fetchone()
                if row:
                    conn.execute("UPDATE jobs SET status = 'running', stage = 'planning', started_at = ?"
                                 " WHERE id = ? AND status = 'queued'", (now(), row["id"]))
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise
        return self.get(row["id"]) if row else None

    def set_stage(self, job_id: str, stage: str) -> None:
        self._update(job_id, stage=stage)

    def record_plan(self, job_id: str, *, plan_source: str, model_id: str, prompt_version: str,
                    plan_record: dict, composer_version: str, soundfont_version: str) -> None:
        self._update(job_id, plan_source=plan_source, model_id=model_id, prompt_version=prompt_version,
                     plan_record_json=json.dumps(plan_record, ensure_ascii=False),
                     composer_version=composer_version, soundfont_version=soundfont_version)

    def succeed(self, job_id: str, *, score_path: str, midi_path: str, audio_path: str,
                duration_seconds: float) -> None:
        self._update(job_id, status="succeeded", stage="done", score_path=score_path, midi_path=midi_path,
                     audio_path=audio_path, duration_seconds=duration_seconds, finished_at=now())

    def fail(self, job_id: str, code: str, message: str) -> None:
        self._update(job_id, status="failed", error_code=code, error_message=message, finished_at=now())

    def fail_stale_running(self) -> list[str]:
        """worker 启动时调用：上次异常退出遗留的运行中任务标记为失败，用户可重新生成。"""
        with self.connect() as conn:
            rows = conn.execute("SELECT id FROM jobs WHERE status = 'running'").fetchall()
            conn.execute(
                "UPDATE jobs SET status = 'failed', error_code = 'WORKER_INTERRUPTED',"
                " error_message = '上次生成过程被中断，请重新生成', finished_at = ? WHERE status = 'running'",
                (now(),))
        return [r["id"] for r in rows]

    def expired_jobs(self, keep: int) -> list[str]:
        """按创建时间保留最近 keep 个已结束任务，返回更早的任务 ID。"""
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id FROM jobs WHERE status IN ('succeeded', 'failed') ORDER BY created_at DESC, rowid DESC"
                " LIMIT -1 OFFSET ?", (keep,)).fetchall()
        return [r["id"] for r in rows]

    def clear_files(self, job_id: str) -> None:
        self._update(job_id, score_path=None, midi_path=None, audio_path=None)

    def _update(self, job_id: str, **fields) -> None:
        assignments = ", ".join(f"{name} = ?" for name in fields)
        with self.connect() as conn:
            conn.execute(f"UPDATE jobs SET {assignments} WHERE id = ?", (*fields.values(), job_id))

    def get(self, job_id: str) -> GenerationJob | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return self._job(row) if row else None

    def get_by_request(self, request_id: str) -> GenerationJob | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE request_id = ?", (request_id,)).fetchone()
        return self._job(row) if row else None

    def plan_record(self, job_id: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute("SELECT plan_record_json FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return json.loads(row[0]) if row and row[0] else None

    def recent(self, limit: int = 10) -> list[GenerationJob]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [self._job(r) for r in rows]

    @staticmethod
    def _job(row: sqlite3.Row) -> GenerationJob:
        data = {k: row[k] for k in _COLUMNS}
        data["input_snapshot"] = CreativeInput.model_validate_json(row["input_json"])
        return GenerationJob.model_validate(data)


@lru_cache
def get_store() -> JobStore:
    return JobStore(runtime_dir() / "app.db")


def runtime_dir() -> Path:
    return resolve_path(str(settings.runtime_dir)) or PROJECT_ROOT / "runtime"


def main() -> int:
    """列出最近的任务，便于本地查看任务快照与状态。"""
    store = get_store()
    jobs = store.recent()
    print(f"数据库：{store.path}；最近 {len(jobs)} 个任务（新→旧）")
    for job in jobs:
        lyrics = job.lyrics_snapshot.replace("\n", " / ")
        print(f"- {job.id}  requestId={job.request_id}  状态={job.status}/{job.stage}  种子={job.seed}"
              f"  修订={job.source_revision}  规划来源={job.plan_source or '-'}"
              + (f"  错误={job.error_code}" if job.error_code else "")
              + (f"  时长={job.duration_seconds:.1f}s" if job.duration_seconds else "")
              + f"\n    歌词快照：{lyrics[:80]}{'…' if len(lyrics) > 80 else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
