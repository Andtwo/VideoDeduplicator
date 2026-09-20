"""AB Video Processor 匿名统计接收服务。

- POST /api/events：事件接收（白名单 + 字段过滤 + 限流 + event_id 幂等）
- GET  /api/health：探活
- GET  /api/stats：基础统计（需 X-Stats-Token 头）

合规约束见 docs/PRD-telemetry.md：不记录 IP，不回显客户端内容。
"""

import json
import os
import re
import sqlite3
import time
from collections import defaultdict, deque
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

DB_PATH = os.environ.get("TELEMETRY_DB", os.path.join(os.path.dirname(__file__), "data", "events.db"))
STATS_TOKEN = os.environ.get("TELEMETRY_STATS_TOKEN", "")

ALLOWED_EVENTS = {
    "app_first_open", "app_open", "task_started",
    "task_success", "task_failed", "telemetry_disabled",
}

ALLOWED_PROPERTIES = {
    "task_id", "fps", "use_gpu", "resolution_bucket", "duration_bucket",
    "processing_seconds_bucket", "error_type", "error_stage",
}

ALLOWED_RESOLUTION = {"<=720p", "1080p", "1440p", "2160p", "other"}
ALLOWED_DURATION = {"<1min", "1-3min", "3-10min", "10-30min", ">30min"}
ALLOWED_PROCESSING = {"<10s", "10-30s", "30-60s", "1-3min", "3-10min", ">10min"}
ALLOWED_ERROR_TYPE = {
    "video_probe_failed", "ffmpeg_failed", "nvenc_failed",
    "output_write_failed", "audio_merge_failed", "unknown",
}
ALLOWED_ERROR_STAGE = {"probe", "resize", "mix", "encode", "audio_merge", "unknown"}
ALLOWED_FPS = {60, 120, 240}

UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
MAX_STR_LEN = 64
RATE_LIMIT_PER_MINUTE = 60
_TZ_CN = timezone(timedelta(hours=8))

app = FastAPI(title="AB Video Processor Telemetry", docs_url=None, redoc_url=None)
_rate_windows = defaultdict(deque)
_db_lock = __import__("threading").Lock()


def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS telemetry_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL UNIQUE,
            anonymous_id TEXT NOT NULL,
            event TEXT NOT NULL,
            app_version TEXT,
            app_build TEXT,
            platform TEXT,
            os_version_bucket TEXT,
            client_timestamp TEXT,
            server_timestamp TEXT NOT NULL,
            properties TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_event ON telemetry_events(event)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_anonymous_id ON telemetry_events(anonymous_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_server_timestamp ON telemetry_events(server_timestamp)")
    return conn


db = get_db()


def is_rate_limited(ip):
    now = time.time()
    window = _rate_windows[ip]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= RATE_LIMIT_PER_MINUTE:
        return True
    window.append(now)
    # 防止内存膨胀，最多保留 10000 个 IP 窗口
    if len(_rate_windows) > 10000:
        _rate_windows.clear()
    return False


def clip_str(value):
    if not isinstance(value, str):
        return None
    return value[:MAX_STR_LEN]


def sanitize_properties(raw):
    if not isinstance(raw, dict):
        return {}
    if len(json.dumps(raw, ensure_ascii=False)) > 2048:
        return {}
    clean = {}
    for key in ALLOWED_PROPERTIES:
        if key not in raw:
            continue
        value = raw[key]
        if key == "task_id":
            if isinstance(value, str) and UUID_RE.match(value):
                clean[key] = value.lower()
        elif key == "fps":
            if value in ALLOWED_FPS:
                clean[key] = value
        elif key == "use_gpu":
            clean[key] = bool(value)
        elif key == "resolution_bucket":
            if value in ALLOWED_RESOLUTION:
                clean[key] = value
        elif key == "duration_bucket":
            if value in ALLOWED_DURATION:
                clean[key] = value
        elif key == "processing_seconds_bucket":
            if value in ALLOWED_PROCESSING:
                clean[key] = value
        elif key == "error_type":
            if value in ALLOWED_ERROR_TYPE:
                clean[key] = value
        elif key == "error_stage":
            if value in ALLOWED_ERROR_STAGE:
                clean[key] = value
    return clean


@app.post("/api/events")
async def receive_event(request: Request):
    client_ip = request.client.host if request.client else "unknown"
    if is_rate_limited(client_ip):
        return JSONResponse({"ok": False}, status_code=429)

    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"ok": False}, status_code=400)

    if not isinstance(payload, dict):
        return JSONResponse({"ok": False}, status_code=400)

    event_id = payload.get("event_id")
    anonymous_id = payload.get("anonymous_id")
    event = payload.get("event")

    if not (isinstance(event_id, str) and UUID_RE.match(event_id)):
        return JSONResponse({"ok": False}, status_code=400)
    if not (isinstance(anonymous_id, str) and UUID_RE.match(anonymous_id)):
        return JSONResponse({"ok": False}, status_code=400)
    if event not in ALLOWED_EVENTS:
        # 合法结构但事件名不在白名单：不报错也不落库，避免泄露校验细节
        return {"ok": True}

    properties = sanitize_properties(payload.get("properties"))
    server_timestamp = datetime.now(_TZ_CN).isoformat()

    try:
        with _db_lock:
            db.execute(
                """INSERT INTO telemetry_events
                   (event_id, anonymous_id, event, app_version, app_build,
                    platform, os_version_bucket, client_timestamp,
                    server_timestamp, properties)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event_id.lower(), anonymous_id.lower(), event,
                    clip_str(payload.get("app_version")),
                    clip_str(payload.get("app_build")),
                    clip_str(payload.get("platform")),
                    clip_str(payload.get("os_version_bucket")),
                    clip_str(payload.get("client_timestamp")),
                    server_timestamp,
                    json.dumps(properties, ensure_ascii=False),
                ),
            )
            db.commit()
    except sqlite3.IntegrityError:
        # event_id 重复：幂等忽略
        return JSONResponse({"ok": True, "duplicate": True}, status_code=202)
    except Exception:
        return JSONResponse({"ok": False}, status_code=500)

    return {"ok": True}


@app.get("/")
async def root():
    return {
        "service": "ab-video-processor-telemetry",
        "endpoints": ["POST /api/events", "GET /api/health", "GET /api/stats"],
    }


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/stats")
async def stats(request: Request):
    if not STATS_TOKEN or request.headers.get("X-Stats-Token") != STATS_TOKEN:
        return JSONResponse({"ok": False}, status_code=403)

    with _db_lock:
        rows = db.execute("""
            SELECT event, COUNT(*) AS cnt, COUNT(DISTINCT anonymous_id) AS devices
            FROM telemetry_events GROUP BY event
        """).fetchall()
        failed = db.execute("""
            SELECT json_extract(properties, '$.error_type') AS error_type, COUNT(*) AS cnt
            FROM telemetry_events WHERE event = 'task_failed'
            GROUP BY error_type ORDER BY cnt DESC
        """).fetchall()
        tasks_started = db.execute("""
            SELECT COUNT(DISTINCT json_extract(properties, '$.task_id'))
            FROM telemetry_events WHERE event = 'task_started'
        """).fetchone()[0]
        tasks_success = db.execute("""
            SELECT COUNT(DISTINCT json_extract(properties, '$.task_id'))
            FROM telemetry_events WHERE event = 'task_success'
        """).fetchone()[0]

    return {
        "events": {r[0]: {"count": r[1], "devices": r[2]} for r in rows},
        "tasks_started": tasks_started,
        "tasks_success": tasks_success,
        "success_rate": round(tasks_success / tasks_started, 4) if tasks_started else None,
        "failed_by_error_type": {r[0]: r[1] for r in failed if r[0]},
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8765)
