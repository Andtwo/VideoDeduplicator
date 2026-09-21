"""片头片尾帧生成：PIL 预渲染背景与文本层，逐帧合成后直接写入编码管道。

帧直接进入主编码器，避免二次编码与 concat 参数对齐问题；
音频侧由 pipeline 用静音填充（aevalsrc + concat）对齐片头片尾时长。
"""

import numpy as np
from PIL import Image, ImageDraw

from assets import load_font


def _vertical_gradient(width, height, top, bottom):
    """生成垂直渐变背景 (RGB float)。"""
    t = np.linspace(0, 1, height, dtype=np.float32)[:, None, None]
    top = np.array(top, dtype=np.float32)
    bottom = np.array(bottom, dtype=np.float32)
    return top + (bottom - top) * t


def _decorations(width, height, rng):
    """生成低亮度几何装饰层（固定，RGB float）。"""
    img = Image.new("RGB", (width, height), (0, 0, 0))
    d = ImageDraw.Draw(img, "RGBA")
    for _ in range(rng.integers(3, 6)):
        r = int(rng.uniform(width * 0.04, width * 0.16))
        cx, cy = rng.integers(0, width), rng.integers(0, height)
        alpha = int(rng.uniform(18, 42))
        if rng.random() < 0.5:
            d.ellipse([cx - r, cy - r, cx + r, cy + r],
                      outline=(255, 255, 255, alpha), width=max(1, width // 400))
        else:
            x0, y0 = int(rng.integers(0, width)), int(rng.integers(0, height))
            x1, y1 = int(rng.integers(0, width)), int(rng.integers(0, height))
            d.line([(x0, y0), (x1, y1)], fill=(255, 255, 255, alpha), width=max(1, width // 500))
    return np.asarray(img, dtype=np.float32)


def _text_layer(text, width, height):
    """渲染标题文本层，返回 (rgb float, alpha, x0, y0)。"""
    if not text.strip():
        return None, None, 0, 0
    font = load_font(max(22, int(height * 0.085)))
    probe = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    stroke = max(2, height // 240)
    bbox = probe.textbbox((0, 0), text, font=font, stroke_width=stroke)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad = stroke * 4
    img = Image.new("RGBA", (tw + pad * 2, th + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.text((pad + stroke, pad + stroke), text, font=font, fill=(0, 0, 0, 170),
           stroke_width=stroke, stroke_fill=(0, 0, 0, 190))
    d.text((pad, pad), text, font=font, fill=(255, 255, 255, 255),
           stroke_width=stroke, stroke_fill=(255, 255, 255, 255))
    arr = np.asarray(img, dtype=np.float32)
    rgb = arr[..., :3][..., ::-1]
    alpha = arr[..., 3:4] / 255.0
    x0 = max(0, (width - img.width) // 2)
    y0 = max(0, int(height * 0.40) - img.height // 2)
    x1, y1 = min(x0 + img.width, width), min(y0 + img.height, height)
    return rgb[:y1 - y0, :x1 - x0], alpha[:y1 - y0, :x1 - x0], x0, y0


def _frame_iter(width, height, fps, duration, text, rng, mode):
    """生成片头（淡入）或片尾（淡出）帧迭代器，BGR uint8。"""
    total = max(1, int(round(duration * fps)))
    bg = _vertical_gradient(width, height, (18, 18, 32), (42, 44, 72))  # BGR
    deco = _decorations(width, height, rng)
    base = np.clip(bg + deco, 0, 255)
    layer = _text_layer(text, width, height) if text.strip() else None
    shift = max(1, height // 60)
    for i in range(total):
        t = (i + 1) / total  # 0~1
        if mode == "intro":
            alpha = min(1.0, t / 0.38) ** 1.5
            dy = int((1.0 - min(1.0, t / 0.55)) * shift)
        else:
            alpha = 1.0 if t < 0.6 else max(0.0, 1.0 - (t - 0.6) / 0.4)
            dy = 0
        frame = base.copy()
        if layer is not None and alpha > 0.01:
            rgb, a, x0, y0 = layer
            y_off = max(0, y0 - dy)
            h, w = a.shape[:2]
            y1 = min(y_off + h, height)
            x1 = min(x0 + w, width)
            region = frame[y_off:y1, x0:x1]
            fa = a[:y1 - y_off, :x1 - x0] * alpha
            frame[y_off:y1, x0:x1] = (region * (1.0 - fa)
                                      + rgb[:y1 - y_off, :x1 - x0] * fa)
        yield np.clip(frame, 0, 255).astype(np.uint8)


def intro_frames(width, height, fps, duration, text, rng):
    """片头帧：标题淡入并轻微上移。"""
    return _frame_iter(width, height, fps, duration, text, rng, "intro")


def outro_frames(width, height, fps, duration, text, rng):
    """片尾帧：标题淡出。"""
    return _frame_iter(width, height, fps, duration, text, rng, "outro")
