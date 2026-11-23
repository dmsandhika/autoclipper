import importlib
import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def web(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOCLIPPER_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setenv("AUTOCLIPPER_LLM", "anthropic")
    import autoclipper.config, autoclipper.pipeline, autoclipper.web as w

    for m in (autoclipper.config, autoclipper.pipeline, w):
        importlib.reload(m)
    return w


def test_health_and_config(web):
    c = TestClient(web.app)
    assert c.get("/api/health").json()["ok"] is True
    assert c.get("/api/config").json()["llm"]["name"] == "anthropic"


@pytest.mark.parametrize("source", ["", "file:///etc/passwd", "/etc/passwd", "ytsearch:cats"])
def test_rejects_non_http_sources(web, source):
    assert TestClient(web.app).post("/api/jobs", json={"source": source}).status_code == 400


def test_validates_options(web):
    c = TestClient(web.app)
    url = "https://youtu.be/dQw4w9WgXcQ"
    assert c.post("/api/jobs", json={"source": url, "n": 99}).status_code == 422
    assert c.post("/api/jobs", json={"source": url, "min": 50, "max": 20}).status_code == 422
    assert c.post("/api/jobs", json={"source": url, "llm": "bogus"}).status_code == 422


def test_delete_project_removes_files(web):
    pl = web.pl
    job = {"id": "abc12345678", "source": "https://x", "title": "T", "created": time.time(), "clips": [],
           "status": "done", "opts": dict(pl.DEFAULT_OPTS)}
    pl.save_job(job)
    web.JOBS[job["id"]] = job
    c = TestClient(web.app)
    assert c.delete(f"/api/jobs/{job['id']}").json() == {"ok": True}
    assert not (pl.WORK / job["id"]).exists()
    assert c.get(f"/api/jobs/{job['id']}/zip").status_code == 404


def test_password_protects_everything_but_health(web, monkeypatch):
    monkeypatch.setattr(web, "PASSWORD", "s3cret")
    c = TestClient(web.app)
    assert c.get("/api/health").status_code == 200
    assert c.get("/api/jobs").status_code == 401
    assert c.get("/api/jobs", auth=("any", "wrong")).status_code == 401
    assert c.get("/api/jobs", auth=("any", "s3cret")).status_code == 200
