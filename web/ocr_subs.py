"""OCR 提取视频内嵌硬字幕，模型固定从项目 models/ 加载。"""
import json
import os
import subprocess
import threading

import cv2

_MODELS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "models"))
_DET_MODEL_DIR = os.path.join(_MODELS_DIR, "PP-OCRv6_medium_det")
_REC_MODEL_DIR = os.path.join(_MODELS_DIR, "PP-OCRv6_medium_rec")
_OCR = None
_OCR_LOCK = threading.Lock()


def _ensure_models():
    """检查 PaddleOCR 3.x 模型完整性，禁止运行时隐式下载。"""
    required = (
        os.path.join(_DET_MODEL_DIR, "inference.yml"),
        os.path.join(_DET_MODEL_DIR, "inference.pdiparams"),
        os.path.join(_REC_MODEL_DIR, "inference.yml"),
        os.path.join(_REC_MODEL_DIR, "inference.pdiparams"),
    )
    missing = [path for path in required if not os.path.isfile(path)]
    if missing:
        relative = [os.path.relpath(path, _MODELS_DIR) for path in missing]
        raise RuntimeError("OCR 模型不完整: " + ", ".join(relative))


def _get_ocr():
    global _OCR
    if _OCR is not None:
        return _OCR
    with _OCR_LOCK:
        if _OCR is None:
            _ensure_models()
            os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
            from paddleocr import PaddleOCR
            _OCR = PaddleOCR(
                text_detection_model_name="PP-OCRv6_medium_det",
                text_detection_model_dir=_DET_MODEL_DIR,
                text_recognition_model_name="PP-OCRv6_medium_rec",
                text_recognition_model_dir=_REC_MODEL_DIR,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
            )
    return _OCR


def extract_subtitles(video_path, sample_interval=1.0, bottom_ratio=0.35):
    """提取硬字幕，返回 ``(start, end, text, top_ratio, bottom_ratio)``。"""
    duration = _probe_duration(video_path)
    if duration <= 0:
        return []
    ocr = _get_ocr()
    entries = []
    t = 0.0
    while t < duration:
        frame = _grab_frame(video_path, t)
        if frame is None:
            break
        text, top, bottom = _ocr_bottom_entry(ocr, frame, bottom_ratio)
        if text:
            entries.append((t, min(t + sample_interval, duration), text, top, bottom))
        t += sample_interval

    merged = []
    for start, end, text, top, bottom in entries:
        if merged and merged[-1][2] == text and abs(merged[-1][1] - start) < 0.01:
            previous = merged[-1]
            merged[-1] = (previous[0], end, text, min(previous[3], top), max(previous[4], bottom))
        else:
            merged.append((start, end, text, top, bottom))
    return merged


def _probe_duration(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", path],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return 0.0
    try:
        return float(json.loads(result.stdout)["format"]["duration"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return 0.0


def _grab_frame(path, t):
    cap = cv2.VideoCapture(path)
    try:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        return frame if ok else None
    finally:
        cap.release()


def _ocr_bottom_entry(ocr, frame, bottom_ratio):
    height, width = frame.shape[:2]
    roi_y0 = int(height * (1 - bottom_ratio))
    result = ocr.predict(frame[roi_y0:height, 0:width])
    texts = []
    top = height
    bottom = 0
    for page in result:
        polygons = page.get("rec_polys", page.get("dt_polys", []))
        for text, score, polygon in zip(
            page.get("rec_texts", []), page.get("rec_scores", []), polygons
        ):
            ys = [float(point[1]) + roi_y0 for point in polygon]
            box_top, box_bottom = min(ys), max(ys)
            box_height = box_bottom - box_top
            normalized = text.strip()
            if score <= 0.5 or not normalized:
                continue
            if box_height > height * 0.12:
                continue
            if len(normalized) == 1 and score < 0.9:
                continue
            texts.append(normalized)
            top = min(top, box_top)
            bottom = max(bottom, box_bottom)
    if not texts:
        return "", 0.0, 0.0
    padding = max(6, int(height * 0.012))
    top_ratio = max(0.0, (top - padding) / height)
    bottom_ratio_value = min(1.0, (bottom + padding) / height)
    return " ".join(texts).strip(), top_ratio, bottom_ratio_value


def _ocr_bottom_text(ocr, frame, bottom_ratio):
    """兼容旧测试/调用，仅返回文本。"""
    return _ocr_bottom_entry(ocr, frame, bottom_ratio)[0]
