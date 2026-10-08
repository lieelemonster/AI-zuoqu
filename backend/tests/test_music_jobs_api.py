import sqlite3
import threading

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.job import MusicJobCreate
from app.storage.jobs import JobStore, get_store

LYRICS = "[主歌]\n晚风吹过街角\n你笑着回头\n路灯一盏一盏\n照亮我们的路\n[副歌]\n就这样走下去\n不怕夜太长\n就这样走下去\n心里有光"
INPUT = {"themeId": "love", "emotionId": "sweet", "styleId": "pop", "story": ""}


def body(request_id="req_00000001", lyrics=LYRICS, **extra):
    return {"requestId": request_id, "input": INPUT, "lyrics": lyrics, **extra}


@pytest.fixture
def store(tmp_path):
    return JobStore(tmp_path / "app.db")


@pytest.fixture
def client(store):
    app.dependency_overrides[get_store] = lambda: store
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_submit_returns_queued_job(client, store):
    response = client.post("/api/music-jobs", json=body())
    assert response.status_code == 201
    view = response.json()
    assert view["id"].startswith("job_") and view["status"] == "queued" and view["stage"] == "queued"
    assert view["audioUrl"] is None and "lyricsSnapshot" not in view
    assert client.get(f"/api/music-jobs/{view['id']}").json()["status"] == "queued"
    job = store.get(view["id"])
    assert job.lyrics_snapshot == LYRICS and job.input_snapshot.style_id == "pop" and job.seed is not None


def test_same_request_id_returns_same_job(client, store):
    first = client.post("/api/music-jobs", json=body())
    second = client.post("/api/music-jobs", json=body())
    assert second.status_code == 200 and second.json()["id"] == first.json()["id"]
    assert len(store.recent()) == 1


def test_edited_lyrics_create_new_job_with_new_snapshot(client, store):
    first = client.post("/api/music-jobs", json=body()).json()["id"]
    edited = LYRICS.replace("晚风吹过街角", "细雨落在窗前")
    second = client.post("/api/music-jobs", json=body("req_00000002", edited, sourceRevision=1)).json()["id"]
    assert first != second
    assert store.get(first).lyrics_snapshot == LYRICS
    assert store.get(second).lyrics_snapshot == edited and store.get(second).source_revision == 1


def test_regenerate_gets_new_seed(store):
    seeds = {store.create(MusicJobCreate.model_validate(body(f"req_seed_{i:04d}")))[0].seed for i in range(8)}
    assert len(seeds) > 1


@pytest.mark.parametrize(("lyrics", "code"), [
    ("就这样走下去\n心里有光", "LYRICS_STRUCTURE"),
    ("[副歌]\n就这样走下去\n心里有光", "LYRICS_STRUCTURE"),
    ("[主歌]\n" + "\n".join(["我们一起走过春夏秋冬的街"] * 16) + "\n[副歌]\n" + "\n".join(["永远记得你"] * 12),
     "LYRICS_TOO_LONG"),
])
def test_bad_lyrics_are_rejected_before_queueing(client, store, lyrics, code):
    response = client.post("/api/music-jobs", json=body(lyrics=lyrics))
    assert response.status_code == 422 and response.json()["error"]["code"] == code
    assert store.recent() == []


@pytest.mark.parametrize("payload", [
    body(lyrics=""), body(request_id="短"), {**body(), "input": {**INPUT, "styleId": "jazz"}},
    {**body(), "audioPath": "/etc/passwd"},
])
def test_invalid_payloads(client, payload):
    assert client.post("/api/music-jobs", json=payload).status_code == 422


def test_unknown_job_is_404(client):
    response = client.get("/api/music-jobs/job_missing")
    assert response.status_code == 404 and response.json()["error"]["code"] == "JOB_NOT_FOUND"


def test_concurrent_duplicate_submissions_create_one_job(store):
    request = MusicJobCreate.model_validate(body("req_concurrent"))
    ids = []
    threads = [threading.Thread(target=lambda: ids.append(store.create(request)[0].id)) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(set(ids)) == 1


def test_default_database_lives_in_runtime_dir():
    from app.settings import PROJECT_ROOT
    from app.storage.jobs import runtime_dir
    assert runtime_dir() == PROJECT_ROOT / "runtime"


def test_database_has_no_secret_columns(store):
    with sqlite3.connect(store.path) as conn:
        columns = [r[1] for r in conn.execute("PRAGMA table_info(jobs)")]
    assert not any("key" in c.lower() or "secret" in c.lower() for c in columns)
