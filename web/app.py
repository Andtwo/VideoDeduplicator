"""Linux Web 服务入口（方案 A 单机）。

用法：
    uvicorn web.app:app --host 0.0.0.0 --port 8000 --workers 1

Worker 使用进程内线程池，方案 A 同时最多跑 1-2 个任务，其余排队。
"""
import os
import shutil
import threading
import uuid
from queue import Queue

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from web.worker import run_job

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOADS = os.path.join(BASE, "uploads")
OUTPUTS = os.path.join(BASE, "web_outputs")
os.makedirs(UPLOADS, exist_ok=True)
os.makedirs(OUTPUTS, exist_ok=True)

app = FastAPI(title="VideoDeduplicator Web")
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")

_tasks = {}        # task_id -> {status, log, output, title}
_queue = Queue()
_lock = threading.Lock()
_MAX_WORKERS = 1   # 方案 A：8 核 16GB，先单 worker，稳优先


def _worker():
    while True:
        task_id, job = _queue.get()
        _tasks[task_id]["status"] = "processing"
        try:
            run_job(job, on_status=lambda m: _log(task_id, m))
            _tasks[task_id]["status"] = "done"
            _tasks[task_id]["output"] = job["output_path"]
        except Exception as e:
            _tasks[task_id]["status"] = "error"
            _log(task_id, f"错误: {e}")
        _queue.task_done()


def _log(tid, msg):
    with _lock:
        _tasks[tid]["log"] = (_tasks[tid].get("log", "") + msg + "\n")[-4000:]


for _ in range(_MAX_WORKERS):
    threading.Thread(target=_worker, daemon=True).start()


@app.get("/", response_class=HTMLResponse)
def index():
    with open(os.path.join(os.path.dirname(__file__), "templates", "index.html"), encoding="utf-8") as f:
        return f.read()


@app.post("/api/process")
async def process(
    video_a: UploadFile = File(...),
    video_b: UploadFile = File(None),
    audio_file: UploadFile = File(None),
    title: str = Form(""),
):
    tid = uuid.uuid4().hex[:8]
    up = os.path.join(UPLOADS, tid)
    os.makedirs(up, exist_ok=True)

    def _save(f, name):
        if not f or not f.filename:
            return ""
        path = os.path.join(up, name)
        with open(path, "wb") as w:
            shutil.copyfileobj(f.file, w)
        return path

    job = {
        "task_id": tid,
        "title": title.strip(),
        "video_a_path": _save(video_a, "a.mp4"),
        "video_b_path": _save(video_b, "b.mp4"),
        "audio_file_path": _save(audio_file, "audio.m4a"),
        "output_path": os.path.join(OUTPUTS, f"{tid}_{title.strip() or 'output'}.mp4"),
        "temp_dir": os.path.join(up, "tmp"),
        "strategy": None,
    }
    _tasks[tid] = {"status": "queued", "log": "", "output": "", "title": title}
    _queue.put((tid, job))
    return {"task_id": tid}


@app.get("/api/status/{tid}")
def status(tid: str):
    t = _tasks.get(tid)
    if not t:
        return {"error": "not found"}
    return t


@app.get("/api/download/{tid}")
def download(tid: str):
    t = _tasks.get(tid)
    if not t or t["status"] != "done":
        return {"error": "not ready"}
    return FileResponse(t["output"], filename=os.path.basename(t["output"]))
