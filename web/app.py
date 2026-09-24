"""Linux Web 服务入口：单进程持久化队列与受限上传。"""
import hmac
import json
import os
import re
import shutil
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from queue import Empty, Full, Queue

from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from web.strategy_store import StrategyStore, StrategyConflictError
from web.worker import run_job

BASE = Path(__file__).resolve().parent.parent
UPLOADS = BASE / "uploads"
OUTPUTS = BASE / "web_outputs"
WEB_DATA = BASE / "web_data"
UPLOADS.mkdir(exist_ok=True)
OUTPUTS.mkdir(exist_ok=True)
WEB_DATA.mkdir(exist_ok=True)
STRATEGY_STORE = StrategyStore(WEB_DATA / "strategies.json")
from web.analytics import Analytics
ANALYTICS = Analytics(WEB_DATA / "analytics.sqlite3")

MAX_UPLOAD_BYTES = int(os.getenv("VD_MAX_UPLOAD_MB", "2048")) * 1024 * 1024
MAX_PENDING_TASKS = int(os.getenv("VD_MAX_PENDING_TASKS", "20"))
TASK_TTL_SECONDS = int(os.getenv("VD_TASK_TTL_HOURS", "24")) * 3600
MIN_FREE_BYTES = int(os.getenv("VD_MIN_FREE_GB", "5")) * 1024 * 1024 * 1024
MAX_TITLE_LENGTH = 80
CHUNK_SIZE = 1024 * 1024
ADMIN_TOKEN = os.getenv("VD_ADMIN_TOKEN", "").strip()
LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}

_tasks = {}
_queue = Queue(maxsize=MAX_PENDING_TASKS)
_lock = threading.RLock()
_stop = threading.Event()
_threads_started = False


def _task_file(task_id):
    return UPLOADS / task_id / "task.json"


def _public_task(task):
    return {
        "status": task["status"],
        "log": task.get("log", ""),
        "title": task.get("title", ""),
        "created_at": task.get("created_at"),
        "updated_at": task.get("updated_at"),
        "strategy_name": task.get("strategy_name", ""),
        "strategy_version": task.get("strategy_version"),
    }


def _persist_task(task_id):
    task = _tasks[task_id]
    path = _task_file(task_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


def _update_task(task_id, **changes):
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            return
        task.update(changes)
        if changes.get('status') == 'processing':
            task['started_at'] = time.time()
        if changes.get('status') in ('done', 'error'):
            task['ended_at'] = time.time()
        ANALYTICS.task(task)
        task["updated_at"] = time.time()
        _persist_task(task_id)


def _log(task_id, message):
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            return
        task["log"] = (task.get("log", "") + str(message) + "\n")[-12000:]
        task["updated_at"] = time.time()
        _persist_task(task_id)


def _worker():
    while not _stop.is_set():
        try:
            task_id = _queue.get(timeout=1)
        except Empty:
            continue
        try:
            with _lock:
                task = _tasks.get(task_id)
                job = task.get("job") if task else None
            if not job:
                continue
            _update_task(task_id, status="processing")
            run_job(job, on_status=lambda message: _log(task_id, message))
            _update_task(task_id, status="done", output=job["output_path"])
        except Exception as exc:
            _update_task(task_id, status="error", error_summary=type(exc).__name__)
            _log(task_id, f"错误: {exc}")
        finally:
            _queue.task_done()


def _cleanup_loop():
    while not _stop.wait(600):
        _cleanup_expired()


def _cleanup_expired(now=None):
    now = now or time.time()
    with _lock:
        expired = [
            task_id for task_id, task in _tasks.items()
            if task.get("status") in ("done", "error")
            and now - task.get("updated_at", now) > TASK_TTL_SECONDS
        ]
        for task_id in expired:
            task = _tasks.pop(task_id)
            output = task.get("output") or task.get("job", {}).get("output_path")
            if output:
                try:
                    Path(output).unlink(missing_ok=True)
                except OSError:
                    pass
            shutil.rmtree(UPLOADS / task_id, ignore_errors=True)


def _load_tasks():
    restored = []
    for path in UPLOADS.glob("*/task.json"):
        try:
            task = json.loads(path.read_text(encoding="utf-8"))
            task_id = task["task_id"]
            if task.get("status") == "processing":
                task["status"] = "error"
                task["log"] = (task.get("log", "") + "服务重启，任务已中断\n")[-12000:]
                task["updated_at"] = time.time()
            _tasks[task_id] = task
            _persist_task(task_id)
            ANALYTICS.task(task)
            if task.get("status") == "queued" and task.get("job"):
                restored.append(task_id)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    _cleanup_expired()
    for task_id in restored[:MAX_PENDING_TASKS]:
        _queue.put_nowait(task_id)
    for task_id in restored[MAX_PENDING_TASKS:]:
        _update_task(task_id, status="error")
        _log(task_id, "服务重启后队列容量不足，任务未恢复")


def _start_threads():
    global _threads_started
    with _lock:
        if _threads_started:
            return
        _threads_started = True
        _load_tasks()
        threading.Thread(target=_worker, name="video-worker", daemon=True).start()
        threading.Thread(target=_cleanup_loop, name="task-cleaner", daemon=True).start()


@asynccontextmanager
async def lifespan(_app):
    _start_threads()
    yield


app = FastAPI(title="VideoDeduplicator Web", lifespan=lifespan)
app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).parent / "static", check_dir=False),
    name="static",
)


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return _render_page("index.html", request)


def _render_page(filename, request):
    # 代理覆盖该请求头；仅接受路径字符，避免注入 HTML 或跨域地址。
    prefix = request.headers.get("x-forwarded-prefix", request.scope.get("root_path", "")).rstrip("/")
    if prefix and (not re.fullmatch(r"(?:/[A-Za-z0-9_-]+)+", prefix)):
        raise HTTPException(400, "无效的部署路径前缀")
    html = (Path(__file__).parent / "templates" / filename).read_text(encoding="utf-8")
    return html.replace("__APP_BASE__", prefix)


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


def _require_admin(request: Request, x_admin_token: str = Header("")):
    if ADMIN_TOKEN:
        token = x_admin_token
        if not token or not hmac.compare_digest(token, ADMIN_TOKEN):
            raise HTTPException(401, "管理令牌无效")
        return
    client_host = request.client.host if request.client else ""
    if client_host not in LOCAL_HOSTS:
        raise HTTPException(403, "未配置 VD_ADMIN_TOKEN 时，后台仅允许本机访问")


@app.get("/admin/strategies", response_class=HTMLResponse)
def strategy_admin(request: Request):
    if not ADMIN_TOKEN:
        _require_admin(request)
    html = _render_page("strategy_admin.html", request)
    return html.replace("__ADMIN_TOKEN_REQUIRED__", "true" if ADMIN_TOKEN else "false")


@app.post('/api/usage', status_code=204)
async def usage(request: Request):
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 1024:
            raise HTTPException(413, '请求过大')
    try:
        data = json.loads(body)
    except (ValueError, UnicodeError):
        raise HTTPException(422, '无效的访问数据')
    if not isinstance(data, dict) or any(not isinstance(data.get(k), str) or not re.fullmatch(r'[a-f0-9]{32}', data[k]) for k in ('page', 'visitor')):
        raise HTTPException(422, '无效的访问标识')
    ANALYTICS.visit(data['page'], data['visitor'])
    return Response(status_code=204)


@app.get('/admin/statistics', response_class=HTMLResponse)
def statistics_page(request: Request):
    if not ADMIN_TOKEN:
        _require_admin(request)
    return _render_page('statistics.html', request)


@app.get('/api/admin/statistics')
def statistics(request: Request, start: str, end: str, x_admin_token: str = Header('')):
    from datetime import date
    _require_admin(request, x_admin_token)
    try:
        first, last = date.fromisoformat(start), date.fromisoformat(end)
        if first > last or (last-first).days > 366:
            raise ValueError()
    except ValueError:
        raise HTTPException(422, '请选择有效日期，范围不超过一年')
    return ANALYTICS.report(first.isoformat(), last.isoformat())


@app.get("/api/admin/strategies", dependencies=[])
def list_strategies(request: Request, x_admin_token: str = Header("")):
    _require_admin(request, x_admin_token)
    return {"versions": STRATEGY_STORE.list_versions(), "token_required": bool(ADMIN_TOKEN)}


@app.post("/api/admin/strategies", status_code=201)
async def create_strategy(request: Request, x_admin_token: str = Header("")):
    _require_admin(request, x_admin_token)
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError("请求内容必须是对象")
        return STRATEGY_STORE.create_version(
            payload.get("name"), payload.get("description"), payload.get("config")
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/admin/strategies/batch-delete", status_code=204)
async def delete_strategy_batch(request: Request, x_admin_token: str = Header("")):
    _require_admin(request, x_admin_token)
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError("请求内容必须是对象")
        STRATEGY_STORE.delete_versions(payload.get("ids"))
    except KeyError as exc:
        raise HTTPException(404, "策略版本不存在") from exc
    except (ValueError, TypeError) as exc:
        raise HTTPException(409, str(exc)) from exc
    return Response(status_code=204)


@app.put("/api/admin/strategies/{version_id}")
async def update_strategy(version_id: str, request: Request, x_admin_token: str = Header("")):
    _require_admin(request, x_admin_token)
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError("请求内容必须是对象")
        return STRATEGY_STORE.update_version(
            version_id, payload.get("name"), payload.get("description"),
            payload.get("config"), payload.get("expected_revision"))
    except StrategyConflictError as exc:
        raise HTTPException(409, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, "策略版本不存在") from exc
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/admin/strategies/{version_id}/activate")
def activate_strategy(version_id: str, request: Request, x_admin_token: str = Header("")):
    _require_admin(request, x_admin_token)
    try:
        return STRATEGY_STORE.activate(version_id)
    except KeyError as exc:
        raise HTTPException(404, "策略版本不存在") from exc


@app.delete("/api/admin/strategies/{version_id}", status_code=204)
def delete_strategy(version_id: str, request: Request, x_admin_token: str = Header("")):
    _require_admin(request, x_admin_token)
    try:
        STRATEGY_STORE.delete(version_id)
    except KeyError as exc:
        raise HTTPException(404, "策略版本不存在") from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return Response(status_code=204)


async def _save_upload(upload, path, expected_type, total_size):
    if not upload or not upload.filename:
        return "", total_size
    content_type = (upload.content_type or "").lower()
    if content_type and not content_type.startswith(expected_type + "/"):
        raise HTTPException(415, f"{upload.filename} 不是有效的{expected_type}文件")
    written = 0
    with path.open("wb") as handle:
        while chunk := await upload.read(CHUNK_SIZE):
            written += len(chunk)
            total_size += len(chunk)
            if written > MAX_UPLOAD_BYTES or total_size > MAX_UPLOAD_BYTES:
                raise HTTPException(413, f"上传文件总大小不能超过 {MAX_UPLOAD_BYTES // 1024 // 1024} MB")
            handle.write(chunk)
    if written == 0:
        raise HTTPException(400, f"{upload.filename} 是空文件")
    return str(path), total_size


def _safe_download_name(title):
    cleaned = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", "_", title).strip(" ._")
    return (cleaned[:MAX_TITLE_LENGTH] or "output") + ".mp4"


@app.post("/api/process", status_code=202)
async def process(
    video_a: UploadFile = File(...),
    video_b: UploadFile = File(None),
    audio_file: UploadFile = File(None),
    title: str = Form(""),
):
    _start_threads()
    title = title.strip()
    if not title:
        raise HTTPException(422, "影视名称不能为空")
    if len(title) > MAX_TITLE_LENGTH:
        raise HTTPException(422, f"影视名称不能超过 {MAX_TITLE_LENGTH} 个字符")
    if _queue.full():
        raise HTTPException(429, "任务队列已满，请稍后重试")
    if shutil.disk_usage(BASE).free < MIN_FREE_BYTES:
        raise HTTPException(507, "服务器可用磁盘空间不足")

    task_id = uuid.uuid4().hex
    upload_dir = UPLOADS / task_id
    upload_dir.mkdir(parents=True, exist_ok=False)
    try:
        total_size = 0
        video_a_path, total_size = await _save_upload(video_a, upload_dir / "a.mp4", "video", total_size)
        video_b_path, total_size = await _save_upload(video_b, upload_dir / "b.mp4", "video", total_size)
        audio_path, total_size = await _save_upload(audio_file, upload_dir / "audio.m4a", "audio", total_size)
        output_path = OUTPUTS / f"{task_id}.mp4"
        strategy = STRATEGY_STORE.snapshot_for_task(
            has_audio_file=bool(audio_path),
            has_video_b=bool(video_b_path),
            title=title,
        )
        job = {
            "task_id": task_id,
            "title": title,
            "video_a_path": video_a_path,
            "video_b_path": video_b_path,
            "audio_file_path": audio_path,
            "output_path": str(output_path),
            "temp_dir": str(upload_dir / "tmp"),
            "strategy": strategy,
        }
        now = time.time()
        task = {
            "task_id": task_id,
            "status": "queued",
            "log": "",
            "output": "",
            "title": title,
            "download_name": _safe_download_name(title),
            "strategy_version_id": strategy["strategy_version_id"],
            "strategy_name": strategy["strategy_name"],
            "strategy_version": strategy["strategy_version"],
            "created_at": now,
            "updated_at": now,
            "job": job,
        }
        with _lock:
            _tasks[task_id] = task
            _persist_task(task_id)
        try:
            ANALYTICS.task(task)
            _queue.put_nowait(task_id)
        except Full:
            with _lock:
                _tasks.pop(task_id, None)
                with ANALYTICS.connect() as db:
                    db.execute('DELETE FROM jobs WHERE id=?', (task_id,))
            raise HTTPException(429, "任务队列已满，请稍后重试")
        return {"task_id": task_id}
    except Exception:
        if task_id not in _tasks:
            shutil.rmtree(upload_dir, ignore_errors=True)
        raise
    finally:
        await video_a.close()
        if video_b:
            await video_b.close()
        if audio_file:
            await audio_file.close()


@app.get("/api/status/{task_id}")
def status(task_id: str):
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            raise HTTPException(404, "任务不存在或已过期")
        return _public_task(task)


@app.get("/api/download/{task_id}")
def download(task_id: str):
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            raise HTTPException(404, "任务不存在或已过期")
        if task["status"] != "done":
            raise HTTPException(409, "任务尚未完成")
        output = Path(task["output"])
        filename = task["download_name"]
    if not output.is_file():
        raise HTTPException(410, "输出文件已不存在")
    ANALYTICS.download(task_id)
    return FileResponse(output, filename=filename, media_type="video/mp4")
