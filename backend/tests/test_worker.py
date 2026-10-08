import pytest

from app import worker
from app.providers.mock import MockProvider
from app.rendering.environment import check_audio_environment
from app.schemas.job import MusicJobCreate
from app.storage.jobs import JobStore

LYRICS = "[主歌]\n晚风吹过街角\n你笑着回头\n路灯一盏一盏\n照亮我们的路\n[副歌]\n就这样走下去\n不怕夜太长\n就这样走下去\n心里有光"
needs_audio = pytest.mark.skipif(not all(r.ok for r in check_audio_environment()), reason="音频工具未安装")


def request(request_id: str, style="pop") -> MusicJobCreate:
    return MusicJobCreate.model_validate({
        "requestId": request_id, "lyrics": LYRICS,
        "input": {"themeId": "love", "emotionId": "sweet", "styleId": style},
    })


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "runtime_dir", lambda: tmp_path)
    return JobStore(tmp_path / "app.db")


def test_claim_is_fifo_and_exclusive(store):
    first, _ = store.create(request("req_claim_0001"))
    second, _ = store.create(request("req_claim_0002"))
    claimed = store.claim_next()
    assert claimed.id == first.id and claimed.status == "running" and claimed.started_at
    assert store.claim_next().id == second.id
    assert store.claim_next() is None


def test_empty_queue_returns_none(store):
    assert worker.run_once(store, MockProvider()) is None


@needs_audio
def test_worker_runs_plan_compose_render(store, tmp_path):
    job, _ = store.create(request("req_worker_0001"))
    stages = []
    original = store.set_stage
    store.set_stage = lambda job_id, stage: (stages.append(stage), original(job_id, stage))
    done = worker.run_once(store, MockProvider())
    assert done.id == job.id and done.status == "succeeded" and done.stage == "done"
    assert stages == ["composing", "rendering", "encoding", "checking"]
    assert 45 <= done.duration_seconds <= 75
    assert done.plan_source == "ai" and done.model_id == "mock" and done.composer_version
    assert done.audio_path == f"jobs/{job.id}/song.mp3" and (tmp_path / done.audio_path).stat().st_size > 100_000
    assert store.plan_record(job.id)["source"] == "ai"


def test_render_failure_marks_job_failed(store, tmp_path, monkeypatch):
    monkeypatch.setattr(worker.settings, "fluidsynth_path", "/nonexistent/fluidsynth")
    job, _ = store.create(request("req_fail_0001"))
    done = worker.run_once(store, MockProvider())
    assert done.status == "failed" and done.error_code == "FLUIDSYNTH_UNAVAILABLE" and done.finished_at
    assert done.audio_path is None and not (tmp_path / "jobs" / job.id).exists()


def test_unexpected_error_is_internal_error_and_worker_continues(store, monkeypatch):
    store.create(request("req_fail_0002"))
    store.create(request("req_fail_0003"))
    monkeypatch.setattr(worker, "compose", lambda *a: (_ for _ in ()).throw(KeyError("boom")))
    first = worker.run_once(store, MockProvider())
    second = worker.run_once(store, MockProvider())
    assert first.error_code == "INTERNAL_ERROR" and "boom" not in first.error_message
    assert second.status == "failed"


def test_bad_audio_check_fails_job(store, monkeypatch):
    from app.rendering.encode import AudioCheck
    from app.rendering.pipeline import RenderResult

    def fake_render(score, directory, name, on_stage):
        directory.mkdir(parents=True)
        paths = [directory / f"{name}{s}" for s in (".score.json", ".mid", ".mp3")]
        for p in paths:
            p.write_bytes(b"x")
        return RenderResult(paths[0], paths[1], None, paths[2], AudioCheck(paths[2], False, 20.0, 1, "mp3", ["时长过短"]))

    monkeypatch.setattr(worker, "render_score", fake_render)
    store.create(request("req_fail_0004"))
    done = worker.run_once(store, MockProvider())
    assert done.error_code == "AUDIO_CHECK_FAILED" and "时长过短" in done.error_message


def test_restart_marks_stale_running_jobs_failed(store, tmp_path):
    job, _ = store.create(request("req_stale_0001"))
    queued, _ = store.create(request("req_stale_0002"))
    store.claim_next()
    (tmp_path / "jobs" / job.id / "work").mkdir(parents=True)
    worker.recover(store)
    stale = store.get(job.id)
    assert stale.status == "failed" and stale.error_code == "WORKER_INTERRUPTED"
    assert store.get(queued.id).status == "queued"
    assert not (tmp_path / "jobs" / job.id).exists()


def test_cleanup_keeps_recent_jobs(store, tmp_path):
    ids = []
    for i in range(4):
        job, _ = store.create(request(f"req_keep_{i:04d}"))
        store.claim_next()
        (tmp_path / "jobs" / job.id).mkdir(parents=True)
        (tmp_path / "jobs" / job.id / "song.mp3").write_bytes(b"x")
        store.succeed(job.id, score_path="s", midi_path="m", audio_path=f"jobs/{job.id}/song.mp3",
                      duration_seconds=60)
        ids.append(job.id)
    worker.cleanup_old_jobs(store, keep=2)
    assert [(tmp_path / "jobs" / i).exists() for i in ids] == [False, False, True, True]
    assert store.get(ids[0]).audio_path is None and store.get(ids[3]).audio_path


@needs_audio
def test_new_jobs_do_not_overwrite_previous_audio(store, tmp_path, monkeypatch):
    store.create(request("req_keep_audio_1"))
    first = worker.run_once(store, MockProvider())
    before = (tmp_path / first.audio_path).read_bytes()
    monkeypatch.setattr(worker.settings, "fluidsynth_path", "/nonexistent/fluidsynth")
    store.create(request("req_keep_audio_2"))
    assert worker.run_once(store, MockProvider()).status == "failed"
    monkeypatch.undo()
    monkeypatch.setattr(worker, "runtime_dir", lambda: tmp_path)
    store.create(request("req_keep_audio_3"))
    third = worker.run_once(store, MockProvider())
    assert third.audio_path != first.audio_path
    assert (tmp_path / first.audio_path).read_bytes() == before
    assert not (tmp_path / "jobs" / third.id / "work").exists()
    assert sorted(p.name for p in (tmp_path / "jobs" / third.id).iterdir()) == ["song.mid", "song.mp3",
                                                                               "song.score.json"]


@needs_audio
def test_worker_without_model_uses_default_plan(store, monkeypatch):
    store.create(request("req_worker_0002", style="folk"))
    monkeypatch.setattr(worker, "_provider", lambda: None)
    done = worker.run_once(store)
    assert done.status == "succeeded" and done.plan_source == "default"
    assert store.plan_record(done.id)["fallbackReason"]
