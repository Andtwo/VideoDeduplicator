"""素材模块：贴纸程序化生成（PIL）、缓存与系统字体查找。

贴纸不依赖外部素材文件，首次使用时生成并缓存到用户目录
~/.video_assets_cache/stickers/，避免仓库携带二进制资源。
"""

import os
import math

from PIL import Image, ImageDraw, ImageFont

STICKER_KINDS = ["star", "heart", "sparkle", "ring", "dots", "ribbon", "tape", "badge"]

_CACHE_DIR = os.path.join(os.path.expanduser("~"), ".video_assets_cache", "stickers")

# 常见平台中文字体候选（花字/字幕渲染用）
_FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def find_font():
    """返回第一个存在的系统字体路径，找不到返回 None。"""
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            return path
    return None


def load_font(size):
    path = find_font()
    if path:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _star_points(cx, cy, r_out, r_in, n=5, rot=-90):
    pts = []
    for k in range(n * 2):
        r = r_out if k % 2 == 0 else r_in
        a = math.radians(rot + k * 180.0 / n)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def _draw_sticker(kind, size):
    """在 RGBA 画布上绘制单个贴纸。"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    line = max(2, size // 28)

    if kind == "star":
        d.polygon(_star_points(size * 0.5, size * 0.52, size * 0.46, size * 0.20),
                  fill=(255, 202, 44, 240), outline=(255, 255, 255, 255), width=line)

    elif kind == "heart":
        # 两圆 + 三角近似心形
        r = size * 0.21
        cy = size * 0.40
        d.ellipse([size * 0.5 - 2 * r, cy - r, size * 0.5, cy + r], fill=(255, 92, 138, 240))
        d.ellipse([size * 0.5, cy - r, size * 0.5 + 2 * r, cy + r], fill=(255, 92, 138, 240))
        d.polygon([(size * 0.085, cy + size * 0.06), (size * 0.915, cy + size * 0.06),
                   (size * 0.5, size * 0.90)], fill=(255, 92, 138, 240))
        d.ellipse([size * 0.32, cy - size * 0.16, size * 0.44, cy - size * 0.02],
                  fill=(255, 178, 205, 235))

    elif kind == "sparkle":
        d.polygon(_star_points(size * 0.5, size * 0.5, size * 0.48, size * 0.10, n=4),
                  fill=(255, 255, 255, 245))
        d.polygon(_star_points(size * 0.26, size * 0.28, size * 0.16, size * 0.05, n=4),
                  fill=(255, 232, 120, 240))
        d.polygon(_star_points(size * 0.74, size * 0.70, size * 0.20, size * 0.06, n=4),
                  fill=(255, 232, 120, 235))

    elif kind == "ring":
        d.ellipse([size * 0.06, size * 0.06, size * 0.94, size * 0.94],
                  outline=(80, 220, 235, 250), width=line + size // 40)
        d.ellipse([size * 0.28, size * 0.28, size * 0.72, size * 0.72],
                  outline=(255, 255, 255, 220), width=max(1, line - 1))

    elif kind == "dots":
        palette = [(255, 107, 129, 235), (255, 202, 44, 235), (80, 220, 135, 235),
                   (96, 178, 255, 235), (200, 130, 255, 235)]
        cells = [(0.26, 0.28, 0.13), (0.66, 0.22, 0.09), (0.42, 0.58, 0.17),
                 (0.80, 0.58, 0.10), (0.24, 0.84, 0.09), (0.68, 0.86, 0.13)]
        for (cx, cy, r), color in zip(cells, palette):
            d.ellipse([size * (cx - r), size * (cy - r), size * (cx + r), size * (cy + r)],
                      fill=color)

    elif kind == "ribbon":
        s = img.rotate(45, expand=False)
        d2 = ImageDraw.Draw(s)
        d2.rectangle([size * 0.02, size * 0.40, size * 0.98, size * 0.62],
                     fill=(255, 82, 82, 235))
        for i in range(6):
            x0 = size * (0.06 + i * 0.16)
            d2.polygon([(x0, size * 0.40), (x0 + size * 0.08, size * 0.40),
                        (x0 + size * 0.16, size * 0.62), (x0 + size * 0.08, size * 0.62)],
                       fill=(255, 255, 255, 235))
        img = s

    elif kind == "tape":
        d.rounded_rectangle([size * 0.08, size * 0.34, size * 0.92, size * 0.68],
                            radius=size // 16, fill=(255, 224, 130, 175))
        for i in range(4):
            x0 = size * (0.16 + i * 0.19)
            d.line([(x0, size * 0.34), (x0 + size * 0.10, size * 0.68)],
                   fill=(240, 240, 240, 160), width=max(1, size // 44))

    elif kind == "badge":
        d.ellipse([size * 0.05, size * 0.05, size * 0.95, size * 0.95],
                  fill=(255, 255, 255, 240))
        d.ellipse([size * 0.10, size * 0.10, size * 0.90, size * 0.90],
                  fill=(255, 152, 56, 245))
        d.polygon(_star_points(size * 0.5, size * 0.5, size * 0.26, size * 0.11),
                  fill=(255, 255, 255, 250))

    return img


def get_sticker(kind, size):
    """获取指定类型与尺寸的贴纸 RGBA 图（带缓存）。"""
    if kind not in STICKER_KINDS:
        raise ValueError(f"未知贴纸类型: {kind}")
    size = max(16, int(size) // 16 * 16)  # 量化到 16 的倍数，控制缓存数量
    os.makedirs(_CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(_CACHE_DIR, f"{kind}_{size}.png")
    if os.path.exists(cache_path):
        try:
            return Image.open(cache_path).convert("RGBA")
        except Exception:
            pass
    img = _draw_sticker(kind, size)
    try:
        img.save(cache_path)
    except Exception:
        pass  # 缓存失败不影响功能
    return img
