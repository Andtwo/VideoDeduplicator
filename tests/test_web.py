"""Web 服务、OCR 配置和流式帧读取回归测试。"""
import json
import os
import time
from pathlib import Path
from unittest.mock import patch

import numpy as np
from fastapi.testclient import TestClient

from frame_io import looping_frame_reader
from web import app as web_app
from web import ocr_subs


def test_looping_frame_reader_reopens_without_cycle_cache(monkeypatch):
    calls = []

    def fake_reader(*_args):
        calls.append(1)
        yield np.full((1, 1, 3), len(calls), dtype=np.uint8)
        yield np.full((1, 1, 3), len(calls), dtype=np.uint8)

    monkeypatch.setattr("frame_io.frame_reader", fake_reader)
    reader = looping_frame_reader("b.mp4", 1, 1)
    values = [int(next(reader)[0, 0, 0]) for _ in range(5)]
    reader.close()
    assert values == [1, 1, 2, 2, 3]
    assert len(calls) == 3


def test_ocr_uses_project_models_and_disables_extra_models(monkeypatch):
    captured = {}

    class FakeOCR:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(ocr_subs, "_OCR", None)
    monkeypatch.setattr(ocr_subs, "_ensure_models", lambda: None)
    import paddleocr
    monkeypatch.setattr(paddleocr, "PaddleOCR", FakeOCR)
    ocr_subs._get_ocr()
    assert captured["text_detection_model_dir"].startswith(ocr_subs._MODELS_DIR)
    assert captured["text_recognition_model_dir"].startswith(ocr_subs._MODELS_DIR)
    assert captured["use_doc_orientation_classify"] is False
    assert captured["use_doc_unwarping"] is False
    assert captured["use_textline_orientation"] is False
    ocr_subs._OCR = None


def test_missing_task_status_codes():
    with TestClient(web_app.app) as client:
        assert client.get("/api/status/not-found").status_code == 404
        assert client.get("/api/download/not-found").status_code == 404


def test_pending_download_returns_conflict(tmp_path):
    task_id = "pending-test"
    now = time.time()
    task = {
        "task_id": task_id,
        "status": "queued",
        "log": "",
        "output": "",
        "title": "",
        "download_name": "output.mp4",
        "created_at": now,
        "updated_at": now,
        "job": {},
    }
    with web_app._lock:
        web_app._tasks[task_id] = task
    try:
        with TestClient(web_app.app) as client:
            assert client.get(f"/api/download/{task_id}").status_code == 409
    finally:
        with web_app._lock:
            web_app._tasks.pop(task_id, None)


def test_title_validation_happens_before_upload():
    with TestClient(web_app.app) as client:
        response = client.post(
            "/api/process",
            files={"video_a": ("a.mp4", b"data", "video/mp4")},
            data={"title": "x" * (web_app.MAX_TITLE_LENGTH + 1)},
        )
    assert response.status_code == 422


def test_safe_download_name_removes_path_characters():
    assert web_app._safe_download_name("../a/b:*?\"<>|") == "a_b.mp4"


def test_cleanup_expired_removes_metadata_and_files(tmp_path, monkeypatch):
    uploads = tmp_path / "uploads"
    outputs = tmp_path / "outputs"
    uploads.mkdir()
    outputs.mkdir()
    monkeypatch.setattr(web_app, "UPLOADS", uploads)
    task_id = "expired"
    task_dir = uploads / task_id
    task_dir.mkdir()
    output = outputs / "expired.mp4"
    output.write_bytes(b"video")
    task = {
        "task_id": task_id,
        "status": "done",
        "updated_at": 1.0,
        "output": str(output),
        "job": {"output_path": str(output)},
    }
    with web_app._lock:
        web_app._tasks[task_id] = task
    web_app._cleanup_expired(now=web_app.TASK_TTL_SECONDS + 2)
    assert task_id not in web_app._tasks
    assert not task_dir.exists()
    assert not output.exists()
