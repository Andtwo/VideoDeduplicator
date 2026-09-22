"""Web 处理任务执行器：复用 src/pipeline.py 核心，附加 Web 策略。"""
import os
import sys
import traceback

SRC = os.path.join(os.path.dirname(__file__), "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import numpy as np
from config import ProcessingOptions
from pipeline import VideoProcessor as QtVideoProcessor
from overlays import TitleOverlay
from strategy import generate_strategy
from ocr_subs import extract_subtitles


def run_job(job, on_status=None):
    """执行一个 Web 任务，返回输出路径或抛异常。"""
    def status(msg):
        if on_status:
            on_status(msg)

    title = job.get("title", "")
    has_b = bool(job.get("video_b_path"))
    has_audio = bool(job.get("audio_file_path"))
    strategy = job.get("strategy") or generate_strategy(has_audio, has_b, title)
    steps = strategy["steps"]
    status(f"随机策略: {', '.join(steps)} / 音频={strategy['audio_mode']} / fps={strategy['fps']}")

    opts = ProcessingOptions()
    if "zoom" in steps:
        opts.zoom_enabled, opts.zoom_random, opts.zoom_min, opts.zoom_max = True, False, strategy["zoom"], strategy["zoom"]
    if "mirror" in steps:
        opts.mirror_enabled = True
    if "filter" in steps:
        opts.filter_enabled, opts.filter_style, opts.filter_strength = True, strategy["filter_style"], 0.35
    if "fx" in steps:
        opts.fx_enabled, opts.fx_style, opts.fx_strength = True, strategy["fx_style"], 0.25
    if "sticker" in steps:
        opts.sticker_enabled = True
    if "fancy" in steps:
        opts.fancy_enabled, opts.fancy_text = True, title or "VideoDeduplicator"
    if "progress" in steps:
        opts.progress_enabled = True
    if "intro" in steps:
        opts.intro_enabled, opts.intro_text, opts.intro_duration = True, title or "Intro", strategy["intro_duration"]
    if "outro" in steps:
        opts.outro_enabled, opts.outro_text, opts.outro_duration = True, title or "Outro", strategy["outro_duration"]
    if "drop_frames" in steps:
        opts.drop_enabled = True
        opts.drop_per_second = strategy["drop_per_second"]

    # 音频
    if strategy["audio_mode"] == "replace_bgm" and has_audio:
        opts.audio_mode = "replace_bgm"
        opts.audio_file = job["audio_file_path"]
        opts.bgm_volume = 0.4
    elif strategy["audio_mode"] == "voice_change":
        opts.audio_mode = "voice_change"

    # OCR 字幕（镜像后压条）
    if "caption_bar" in steps:
        try:
            entries = extract_subtitles(job["video_a_path"])
            if entries:
                opts.caption_enabled = True
                opts.caption_ocr_entries = entries
                status(f"OCR 提取到 {len(entries)} 条字幕")
        except Exception as e:
            status(f"OCR 失败，跳过字幕条: {e}")

    title_overlay = TitleOverlay(title, 0, 0) if title else None

    processor = WebVideoProcessor(
        job["video_a_path"], job["video_b_path"], job["output_path"],
        strategy["fps"], job["temp_dir"], opts, title_overlay, status)
    processor.run()
    return job["output_path"]


class WebVideoProcessor(QtVideoProcessor):
    """去掉 Qt 信号，改用回调；附加左上角标题叠加。"""

    def __init__(self, video_a, video_b, output, fps, temp_dir, opts, title_overlay, status_cb):
        from PyQt5.QtCore import QThread
        QThread.__init__(self)
        self.video_a_path = video_a
        self.video_b_path = video_b
        self.output_path = output
        self.fps = fps
        self.temp_dir = temp_dir
        self.options = opts
        self.use_gpu = False
        self.telemetry = None
        self.task_id = None
        self._title_overlay = title_overlay
        self._status_cb = status_cb

        class _Sig:
            def emit(self, *a, **k):
                pass
        self.progress = _Sig()
        self.status = _Sig()
        self.finished = _Sig()
        self.error = _Sig()

    def run(self):
        orig_emit = self.status.emit
        self.status.emit = self._status_cb
        try:
            super().run()
        finally:
            self.status.emit = orig_emit

    def _apply_title(self, frame):
        if self._title_overlay and self._title_overlay.enabled:
            if self._title_overlay.w == 0:
                h, w = frame.shape[:2]
                self._title_overlay = TitleOverlay(self._title_overlay.title, w, h)
            return self._title_overlay.apply(frame)
        return frame
