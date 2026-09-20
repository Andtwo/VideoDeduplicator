"""事件类型常量与属性构造（区间桶计算、错误归类）。

所有维度一律使用区间桶，不上传精确值组合；
错误只上传归类结果，不上传原始异常文本。
"""

EVENT_APP_FIRST_OPEN = "app_first_open"
EVENT_APP_OPEN = "app_open"
EVENT_TASK_STARTED = "task_started"
EVENT_TASK_SUCCESS = "task_success"
EVENT_TASK_FAILED = "task_failed"
EVENT_TELEMETRY_DISABLED = "telemetry_disabled"

ALLOWED_EVENTS = frozenset({
    EVENT_APP_FIRST_OPEN,
    EVENT_APP_OPEN,
    EVENT_TASK_STARTED,
    EVENT_TASK_SUCCESS,
    EVENT_TASK_FAILED,
    EVENT_TELEMETRY_DISABLED,
})


def resolution_bucket(width, height):
    """按短边像素归类分辨率，避免精确组合成为弱指纹。"""
    short_side = min(width, height)
    if short_side <= 720:
        return "<=720p"
    if short_side <= 1080:
        return "1080p"
    if short_side <= 1440:
        return "1440p"
    if short_side <= 2160:
        return "2160p"
    return "other"


def duration_bucket(seconds):
    if seconds < 60:
        return "<1min"
    if seconds < 180:
        return "1-3min"
    if seconds < 600:
        return "3-10min"
    if seconds < 1800:
        return "10-30min"
    return ">30min"


def processing_seconds_bucket(seconds):
    if seconds < 10:
        return "<10s"
    if seconds < 30:
        return "10-30s"
    if seconds < 60:
        return "30-60s"
    if seconds < 180:
        return "1-3min"
    if seconds < 600:
        return "3-10min"
    return ">10min"


def os_version_bucket(platform):
    """粗粒度系统分类，不采集精确系统版本号。"""
    if platform == "win32":
        return "windows"
    if platform == "darwin":
        return "macos"
    if platform.startswith("linux"):
        return "linux"
    return "other"


def classify_error(exc, use_gpu=False):
    """把异常归类为 (error_type, error_stage)，不向上传递原始文本。"""
    message = str(exc or "")
    if "无法获取视频信息" in message or "视频元数据" in message:
        return "video_probe_failed", "probe"
    if "FFmpeg处理失败" in message:
        return ("nvenc_failed" if use_gpu else "ffmpeg_failed"), "resize"
    if "FFmpeg写入视频失败" in message or "未能创建输出文件" in message:
        return ("nvenc_failed" if use_gpu else "output_write_failed"), "encode"
    if isinstance(exc, FileNotFoundError):
        return "video_probe_failed", "probe"
    # 音频合并阶段是最后一步 CalledProcessError
    import subprocess
    if isinstance(exc, subprocess.CalledProcessError):
        return "audio_merge_failed", "audio_merge"
    return "unknown", "unknown"
