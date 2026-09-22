"""OCR 提取视频内嵌硬字幕（用于镜像后压字幕条）。

模型文件统一放在项目 models/ 目录下，首次使用自动下载。
模型：PP-OCRv4 中文（检测 + 识别 + 方向分类，轻量版，CPU 可跑）。
"""
import os
import subprocess
import tarfile
import urllib.request

import cv2

_MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "models")

# PaddleOCR 官方 PP-OCRv4 中文轻量模型
_MODEL_FILES = {
    "det": (
        "https://paddleocr.bj.bcebos.com/PP-OCRv4/chinese/ch_PP-OCRv4_det_infer.tar",
        "ch_PP-OCRv4_det_infer"),
    "rec": (
        "https://paddleocr.bj.bcebos.com/PP-OCRv4/chinese/ch_PP-OCRv4_rec_infer.tar",
        "ch_PP-OCRv4_rec_infer"),
    "cls": (
        "https://paddleocr.bj.bcebos.com/dygraph_v2.0/ch/ch_ppocr_mobile_v2.0_cls_infer.tar",
        "ch_ppocr_mobile_v2.0_cls_infer"),
}

_OCR = None


def _ensure_models():
    """确保模型文件已下载到 models/ 目录。"""
    os.makedirs(_MODELS_DIR, exist_ok=True)
    for url, dirname in _MODEL_FILES.values():
        dest_dir = os.path.join(_MODELS_DIR, dirname)
        if os.path.isdir(dest_dir) and os.listdir(dest_dir):
            continue
        tar_path = os.path.join(_MODELS_DIR, os.path.basename(url))
        print(f"[OCR] 下载模型 {dirname} ...")
        # 本地代理（如需要外网访问）
        proxies = {"http": "http://127.0.0.1:7890", "https": "http://127.0.0.1:7890"} \
            if os.environ.get("VD_USE_PROXY") else None
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=300) as r, open(tar_path, "wb") as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
        with tarfile.open(tar_path, "r") as tf:
            tf.extractall(_MODELS_DIR)
        os.remove(tar_path)
        print(f"[OCR] 模型 {dirname} 就绪 -> {dest_dir}")


def _get_ocr():
    global _OCR
    if _OCR is None:
        _ensure_models()
        from paddleocr import PaddleOCR
        _OCR = PaddleOCR(lang="ch")
    return _OCR


def extract_subtitles(video_path, sample_interval=1.0, bottom_ratio=0.35):
    """提取视频内嵌字幕，返回 [(start, end, text)]。

    只识别画面底部 bottom_ratio 区域内的文字（常见硬字幕位置）。
    采样间隔 sample_interval 秒，相邻采样点之间的时间区间作为字幕显示窗口。
    """
    info = _probe_duration(video_path)
    if info <= 0:
        return []
    ocr = _get_ocr()
    entries = []
    t = 0.0
    while t < info:
        frame = _grab_frame(video_path, t)
        if frame is None:
            break
        text = _ocr_bottom_text(ocr, frame, bottom_ratio)
        entries.append((t, min(t + sample_interval, info), text) if text else None)
        t += sample_interval
    # 去掉空识别，合并相邻相同文本
    merged = []
    for item in entries:
        if item is None:
            continue
        s, e, text = item
        if merged and merged[-1][2] == text and abs(merged[-1][1] - s) < 0.01:
            merged[-1] = (merged[-1][0], e, text)
        else:
            merged.append((s, e, text))
    return merged


def _probe_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", path],
        capture_output=True, text=True)
    try:
        import json
        return float(json.loads(out.stdout)["format"]["duration"])
    except Exception:
        return 0.0


def _grab_frame(path, t):
    cap = cv2.VideoCapture(path)
    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
    ok, frame = cap.read()
    cap.release()
    return frame if ok else None


def _ocr_bottom_text(ocr, frame, bottom_ratio):
    h, w = frame.shape[:2]
    y0 = int(h * (1 - bottom_ratio))
    roi = frame[y0:h, 0:w]
    result = ocr.predict(roi)
    texts = []
    for page in result:
        for text, score in zip(page.get("rec_texts", []), page.get("rec_scores", [])):
            if score > 0.5:
                texts.append(text)
    return " ".join(texts).strip()
