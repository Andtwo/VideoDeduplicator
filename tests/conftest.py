"""pytest 共享 fixture：合成测试视频与 Qt 应用实例。"""
import os
import subprocess
import sys

import pytest

SRC_DIR = os.path.join(os.path.dirname(__file__), "..", "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("AB_TELEMETRY_ENDPOINT", "http://127.0.0.1:1")


def _make_video(path, width, height, duration, with_audio=True, freq=440):
    """用 ffmpeg 合成测试视频（testsrc + 正弦音轨）。"""
    cmd = ["ffmpeg", "-y",
           "-f", "lavfi", "-i", f"testsrc2=size={width}x{height}:rate=30:duration={duration}"]
    if with_audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency={freq}:duration={duration}"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
    if with_audio:
        cmd += ["-c:a", "aac", "-shortest"]
    cmd += [str(path)]
    subprocess.run(cmd, check=True, capture_output=True)
    return str(path)


def _make_audio(path, duration, freq):
    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={duration}",
           "-c:a", "aac", str(path)]
    subprocess.run(cmd, check=True, capture_output=True)
    return str(path)


@pytest.fixture(scope="session")
def qapp():
    from PyQt5.QtCore import QCoreApplication
    app = QCoreApplication.instance() or QCoreApplication([])
    yield app


@pytest.fixture(scope="session")
def video_a(tmp_path_factory):
    return _make_video(tmp_path_factory.mktemp("va") / "a.mp4", 320, 240, 4.0)


@pytest.fixture(scope="session")
def video_b(tmp_path_factory):
    return _make_video(tmp_path_factory.mktemp("vb") / "b.mp4", 320, 240, 4.0, freq=660)


@pytest.fixture(scope="session")
def video_portrait(tmp_path_factory):
    return _make_video(tmp_path_factory.mktemp("vp") / "p.mp4", 240, 640, 3.0)


@pytest.fixture(scope="session")
def video_no_audio(tmp_path_factory):
    return _make_video(tmp_path_factory.mktemp("vna") / "na.mp4", 320, 240, 3.0, with_audio=False)


@pytest.fixture(scope="session")
def bgm_file(tmp_path_factory):
    return _make_audio(tmp_path_factory.mktemp("bgm") / "bgm.m4a", 2.0, 220)


@pytest.fixture(scope="session")
def srt_file(tmp_path_factory):
    d = tmp_path_factory.mktemp("srt")
    p = d / "sub.srt"
    p.write_text(
        "1\n00:00:00,500 --> 00:00:02,000\n第一条字幕\n\n"
        "2\n00:00:02,000 --> 00:00:04,000\n第二条字幕\n\n",
        encoding="utf-8")
    return str(p)


@pytest.fixture()
def wait_process(qapp):
    """等待 VideoProcessor 结束的辅助器。"""
    def _wait(processor, timeout=120):
        from PyQt5.QtCore import QEventLoop, QTimer
        loop = QEventLoop()
        errors = []
        processor.error.connect(errors.append)
        processor.finished.connect(loop.quit)
        processor.error.connect(loop.quit)
        QTimer.singleShot(timeout * 1000, loop.quit)
        processor.start()
        loop.exec_()
        processor.wait(10000)
        assert not errors, errors
    return _wait


def probe(path):
    """返回 {duration, streams: [(type, ...)]}。"""
    import json
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration", "-show_entries", "stream=codec_type",
         "-of", "json", str(path)],
        check=True, capture_output=True, text=True).stdout
    data = json.loads(out)
    return {
        "duration": float(data["format"]["duration"]),
        "streams": [s["codec_type"] for s in data.get("streams", [])],
    }
