"""Web 服务、OCR 配置和流式帧读取回归测试。"""
import json
import os
import time
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from fastapi.testclient import TestClient

from frame_io import looping_frame_reader
from web import app as web_app
from web import ocr_subs
from web.overlays import TitleOverlay
from web.strategy import DEFAULT_CONFIG, generate_strategy, validate_strategy_config
from web.strategy_store import StrategyStore
from web.worker import WebVideoProcessor, run_job


def test_strategy_puts_mirror_first_and_caption_bar_last():
    import random

    for seed in range(200):
        strategy = generate_strategy(rng=random.Random(seed))
        if "mirror" in strategy["steps"]:
            assert strategy["steps"][0] == "mirror"
            assert "caption_bar" in strategy["steps"]


def test_strategy_config_fixed_mode_and_input_capabilities():
    config = {
        **DEFAULT_CONFIG,
        "selection_mode": "fixed",
        "steps": ["mirror", "zoom", "sticker"],
        "audio_modes": ["replace_bgm"],
        "fps_options": [60, 120],
    }
    strategy = generate_strategy(config=config, has_audio_file=False, has_video_b=False)
    assert strategy["steps"] == ["mirror", "zoom", "sticker", "caption_bar"]
    assert strategy["audio_mode"] == "original"
    assert strategy["fps"] == 30


def test_random_step_range_is_clamped_to_selected_candidates():
    config = validate_strategy_config({
        **DEFAULT_CONFIG,
        "selection_mode": "random",
        "steps": ["zoom", "fancy", "drop_frames"],
        "min_steps": 3,
        "max_steps": 6,
    })
    assert config["min_steps"] == 3
    assert config["max_steps"] == 3
    strategy = generate_strategy(config=config)
    assert set(strategy["steps"]) == {"zoom", "fancy", "drop_frames"}


def test_strategy_config_requires_three_steps():
    with pytest.raises(ValueError, match="至少选择 3"):
        validate_strategy_config({**DEFAULT_CONFIG, "steps": ["zoom", "fx"]})


def test_strategy_store_versions_and_immutable_snapshot(tmp_path):
    store = StrategyStore(tmp_path / "strategies.json")
    original = store.snapshot_for_task(title="旧任务")
    created = store.create_version(
        "剧情号策略", "固定镜像版本",
        {**DEFAULT_CONFIG, "selection_mode": "fixed", "steps": ["mirror", "zoom", "sticker"]},
    )
    assert created["version"] == 1
    second = store.create_version(
        "剧情号策略", "第二版",
        {**DEFAULT_CONFIG, "selection_mode": "fixed", "steps": ["zoom", "fx", "progress"]},
    )
    assert second["version"] == 2
    store.activate(second["id"])
    current = store.snapshot_for_task(title="新任务")
    assert current["strategy_version_id"] == second["id"]
    assert current["steps"] == ["zoom", "fx", "progress"]
    assert original["strategy_version_id"] != current["strategy_version_id"]
    with pytest.raises(ValueError, match="不能删除"):
        store.delete(second["id"])


def test_admin_strategy_api_and_page(tmp_path, monkeypatch):
    store = StrategyStore(tmp_path / "strategies.json")
    monkeypatch.setattr(web_app, "STRATEGY_STORE", store)
    monkeypatch.setattr(web_app, "ADMIN_TOKEN", "secret")
    with TestClient(web_app.app) as client:
        assert client.get("/admin/strategies").status_code == 200
        assert client.get("/api/admin/strategies").status_code == 401
        headers = {"X-Admin-Token": "secret"}
        listed = client.get("/api/admin/strategies", headers=headers)
        assert listed.status_code == 200
        response = client.post(
            "/api/admin/strategies",
            headers=headers,
            json={
                "name": "内容策略",
                "description": "用于测试",
                "config": {**DEFAULT_CONFIG, "selection_mode": "fixed", "steps": ["zoom", "fx", "sticker"]},
            },
        )
        assert response.status_code == 201
        version_id = response.json()["id"]
        assert client.post(f"/api/admin/strategies/{version_id}/activate", headers=headers).status_code == 200
        assert client.delete(f"/api/admin/strategies/{version_id}", headers=headers).status_code == 409


def test_title_overlay_defers_layout_until_frame_size_is_known():
    overlay = TitleOverlay("老九门", 0, 0)
    assert overlay.enabled
    assert not overlay.ready
    assert overlay.w == 0


def test_web_processor_initializes_title_from_real_frame_size():
    class ProcessorStub:
        _postprocess_frame = WebVideoProcessor._postprocess_frame

    processor = ProcessorStub()
    processor._title_overlay = TitleOverlay("老九门", 0, 0)
    frame = np.full((1080, 1920, 3), 180, dtype=np.uint8)
    output = processor._postprocess_frame(frame.copy())
    assert processor._title_overlay.ready
    assert processor._title_overlay.font.size == 54
    assert processor._title_overlay.w > 100
    assert processor._title_overlay.x0 == 57
    assert not np.array_equal(output[40:130, 50:300], frame[40:130, 50:300])


def test_fancy_text_does_not_duplicate_movie_title(monkeypatch, tmp_path):
    captured = {}

    class ProcessorStub:
        def __init__(self, *_args):
            captured["options"] = _args[5]
            self.failure = ""

        def run(self):
            Path(tmp_path / "out.mp4").write_bytes(b"video")

    monkeypatch.setattr("web.worker.WebVideoProcessor", ProcessorStub)
    job = {
        "title": "老九门",
        "video_a_path": "a.mp4",
        "video_b_path": "",
        "audio_file_path": "",
        "output_path": str(tmp_path / "out.mp4"),
        "temp_dir": str(tmp_path / "tmp"),
        "strategy": {
            "steps": ["fancy", "zoom", "progress"],
            "audio_mode": "original",
            "fps": 30,
            "zoom": 1.1,
        },
    }
    run_job(job)
    assert captured["options"].fancy_text == "精彩片段"


def test_worker_applies_fixed_speed_from_strategy(monkeypatch, tmp_path):
    captured = {}

    class ProcessorStub:
        def __init__(self, *_args):
            captured["options"] = _args[5]
            self.failure = ""

        def run(self):
            Path(tmp_path / "out.mp4").write_bytes(b"video")

    monkeypatch.setattr("web.worker.WebVideoProcessor", ProcessorStub)
    run_job({
        "title": "",
        "video_a_path": "a.mp4",
        "video_b_path": "",
        "audio_file_path": "",
        "output_path": str(tmp_path / "out.mp4"),
        "temp_dir": str(tmp_path / "tmp"),
        "strategy": {
            "steps": ["speed", "zoom", "progress"],
            "audio_mode": "original",
            "fps": 30,
            "speed": 1.08,
            "zoom": 1.1,
        },
    })
    options = captured["options"]
    assert options.speed_enabled
    assert not options.speed_random
    assert options.speed_min == options.speed_max == 1.08


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


def test_ocr_returns_full_frame_vertical_coordinates():
    class FakeOCR:
        def predict(self, _roi):
            return [{
                "rec_texts": ["字幕"],
                "rec_scores": [0.99],
                "rec_polys": [np.array([[10, 20], [100, 20], [100, 50], [10, 50]])],
            }]

    frame = np.zeros((1000, 800, 3), dtype=np.uint8)
    text, top, bottom = ocr_subs._ocr_bottom_entry(FakeOCR(), frame, 0.35)
    assert text == "字幕"
    assert top == pytest.approx((650 + 20 - 12) / 1000)
    assert bottom == pytest.approx((650 + 50 + 12) / 1000)


def test_ocr_rejects_oversized_false_positive():
    class FakeOCR:
        def predict(self, _roi):
            return [{
                "rec_texts": ["C"],
                "rec_scores": [0.88],
                "rec_polys": [np.array([[10, 0], [100, 0], [100, 220], [10, 220]])],
            }]

    frame = np.zeros((1000, 800, 3), dtype=np.uint8)
    assert ocr_subs._ocr_bottom_entry(FakeOCR(), frame, 0.35) == ("", 0.0, 0.0)


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


def test_process_persists_active_strategy_snapshot(tmp_path, monkeypatch):
    uploads = tmp_path / "uploads"
    outputs = tmp_path / "outputs"
    uploads.mkdir()
    outputs.mkdir()
    store = StrategyStore(tmp_path / "strategies.json")
    version = store.create_version(
        "固定策略", "提交时生成快照",
        {**DEFAULT_CONFIG, "selection_mode": "fixed", "steps": ["zoom", "fx", "progress"]},
    )
    store.activate(version["id"])
    monkeypatch.setattr(web_app, "UPLOADS", uploads)
    monkeypatch.setattr(web_app, "OUTPUTS", outputs)
    monkeypatch.setattr(web_app, "STRATEGY_STORE", store)
    monkeypatch.setattr(web_app.shutil, "disk_usage", lambda _path: type("Usage", (), {"free": web_app.MIN_FREE_BYTES + 1})())
    queued = []
    monkeypatch.setattr(web_app._queue, "put_nowait", queued.append)
    monkeypatch.setattr(web_app._queue, "full", lambda: False)
    with TestClient(web_app.app) as client:
        response = client.post(
            "/api/process",
            files={"video_a": ("a.mp4", b"video", "video/mp4")},
            data={"title": "策略快照"},
        )
    assert response.status_code == 202
    task_id = response.json()["task_id"]
    task = json.loads((uploads / task_id / "task.json").read_text(encoding="utf-8"))
    assert task["strategy_version_id"] == version["id"]
    assert task["job"]["strategy"]["steps"] == ["zoom", "fx", "progress"]
    assert task["job"]["strategy"]["fps"] == 30
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
