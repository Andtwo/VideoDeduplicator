"""后期效果管线：像素级处理在帧循环中逐帧应用。

处理顺序：几何（缩放）-> 色调（滤镜 -> 特效）-> 叠加（贴纸/字幕/花字）。
水平镜像属于最终帧处理，在 pipeline.py 中所有叠加完成后统一执行。
静态叠加层（贴纸）在初始化时预合成，每帧仅做一次 alpha 混合。
"""

import cv2
import numpy as np
from PIL import Image, ImageDraw
from PIL import Image as _PILImage

from config import FILTER_STYLES, FX_STYLES
from assets import STICKER_KINDS, get_sticker, load_font

Image_FLIP = _PILImage.FLIP_LEFT_RIGHT
Image_BICUBIC = _PILImage.BICUBIC


def _blend(orig, filtered, strength):
    """按强度混合原图与处理后图像，strength 0~1。"""
    if strength <= 0:
        return orig
    if strength >= 1:
        return filtered
    return cv2.addWeighted(orig, 1.0 - strength, filtered, strength, 0)


class ZoomCrop:
    """中心裁剪后放大还原，实现画面整体放大。"""

    def __init__(self, scale):
        if scale < 1.0:
            raise ValueError("缩放比例必须 >= 1.0")
        self.scale = scale

    def apply(self, frame, index):
        if self.scale <= 1.001:
            return frame
        h, w = frame.shape[:2]
        cw, ch = int(w / self.scale), int(h / self.scale)
        x0, y0 = (w - cw) // 2, (h - ch) // 2
        crop = frame[y0:y0 + ch, x0:x0 + cw]
        return cv2.resize(crop, (w, h), interpolation=cv2.INTER_LINEAR)


class Mirror:
    """水平镜像翻转（返回连续内存，保证后续 cv2 调用跨版本安全）。"""

    def apply(self, frame, index):
        return np.ascontiguousarray(frame[:, ::-1])


def _saturate(img, factor):
    """快速饱和度调整（亮度平面外推，避免 HSV 往返转换）。"""
    if abs(factor - 1.0) < 1e-3:
        return img
    lum = img[:, :, 0] * 0.114 + img[:, :, 1] * 0.587 + img[:, :, 2] * 0.299
    out = lum[..., None] + (img.astype(np.float32) - lum[..., None]) * factor
    return np.clip(out, 0, 255).astype(np.uint8)


def _apply_lut(img, luts):
    """逐通道 LUT 变换，luts 为 (B,G,R) 三个 256 长度数组。"""
    out = np.empty_like(img)
    for c in range(3):
        out[:, :, c] = luts[c][img[:, :, c]]
    return out


class ColorFilter:
    """滤镜：预设风格处理，再按强度与原图混合。"""

    def __init__(self, style, strength, rng):
        if strength < 0 or strength > 1:
            raise ValueError("滤镜强度必须在 0~1 之间")
        self.strength = strength
        self.style = rng.choice(FILTER_STYLES[1:]) if style == "random" else style

    def _process(self, img):
        s = self.style
        if s == "mono":
            lum = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            return cv2.cvtColor(lum, cv2.COLOR_GRAY2BGR)
        if s == "warm":
            img = _saturate(img, 1.18)
            r = np.arange(256, dtype=np.int16) + 12
            b = np.arange(256, dtype=np.int16) - 12
            return _apply_lut(img, (np.clip(b, 0, 255).astype(np.uint8),
                                    np.arange(256, dtype=np.uint8),
                                    np.clip(r, 0, 255).astype(np.uint8)))
        if s == "cool":
            img = _saturate(img, 1.15)
            r = np.arange(256, dtype=np.int16) - 12
            b = np.arange(256, dtype=np.int16) + 12
            return _apply_lut(img, (np.clip(b, 0, 255).astype(np.uint8),
                                    np.arange(256, dtype=np.uint8),
                                    np.clip(r, 0, 255).astype(np.uint8)))
        if s == "vintage":
            img = _saturate(img, 0.72)
            b = (np.arange(256, dtype=np.float32) * 0.92 + 14)
            g = (np.arange(256, dtype=np.float32) * 0.96 + 6)
            r = (np.arange(256, dtype=np.float32) * 1.02)
            return _apply_lut(img, tuple(np.clip(x, 0, 255).astype(np.uint8) for x in (b, g, r)))
        if s == "bright":
            x = np.arange(256, dtype=np.float32) / 255.0
            y = np.clip(x ** 0.88, 0, 1) * 255.0
            lut = y.astype(np.uint8)
            return _apply_lut(img, (lut, lut, lut))
        raise ValueError(f"未知滤镜风格: {s}")

    def apply(self, frame, index):
        return _blend(frame, self._process(frame), self.strength)


class GrainFx:
    """胶片颗粒：低强度亮度域噪声（半分辨率生成后放大）。"""

    def __init__(self, strength, rng, shape):
        self.sigma = max(1.0, strength * 42.0)
        self.small_shape = (shape[0] // 2, shape[1] // 2)
        self.rng = rng

    def apply(self, frame, index):
        noise = self.rng.integers(-int(self.sigma), int(self.sigma) + 1,
                                  size=(self.small_shape[0], self.small_shape[1]),
                                  dtype=np.int16)
        noise = cv2.resize(noise, (frame.shape[1], frame.shape[0]),
                           interpolation=cv2.INTER_NEAREST)
        noise = noise[..., None]
        out = frame.astype(np.int16) + noise
        return np.clip(out, 0, 255).astype(np.uint8)


class VignetteFx:
    """暗角：边缘亮度衰减，低强度。"""

    def __init__(self, strength, rng, shape):
        h, w = shape[:2]
        y = np.linspace(-1, 1, h, dtype=np.float32)
        x = np.linspace(-1, 1, w, dtype=np.float32)
        xx, yy = np.meshgrid(x, y)
        radial = np.sqrt(xx * xx + yy * yy) / np.sqrt(2.0)
        radial = np.clip(radial, 0, 1) ** 2.2
        self.mask = (1.0 - strength * radial)[..., None].astype(np.float32)

    def apply(self, frame, index):
        out = frame.astype(np.float32) * self.mask
        return np.clip(out, 0, 255).astype(np.uint8)


class BloomFx:
    """柔光：高斯模糊后屏幕混合，低强度提亮。"""

    def __init__(self, strength, rng, shape):
        self.strength = strength
        self.sigma = max(2.0, shape[1] * 0.012)

    def apply(self, frame, index):
        blurred = cv2.GaussianBlur(frame, (0, 0), self.sigma)
        # 屏幕混合: 255 - (255-a)(255-b)/255
        screen = 255.0 - (255.0 - frame.astype(np.float32)) * (255.0 - blurred.astype(np.float32)) / 255.0
        return _blend(frame, np.clip(screen, 0, 255).astype(np.uint8), self.strength)


class LeakFx:
    """漏光：角落暖色光晕，低强度叠加。"""

    def __init__(self, strength, rng, shape):
        h, w = shape[:2]
        # 随机一角生成径向光斑
        corner = rng.integers(0, 4)
        positions = [(0.15, 0.2), (0.85, 0.2), (0.15, 0.85), (0.85, 0.85)]
        cx, cy = positions[corner]
        y = np.linspace(0, 1, h, dtype=np.float32)
        x = np.linspace(0, 1, w, dtype=np.float32)
        xx, yy = np.meshgrid(x, y)
        dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
        glow = np.clip(1.0 - dist / 0.75, 0, 1) ** 2
        warm = np.zeros((h, w, 3), dtype=np.float32)
        warm[..., 0] = glow * 70.0   # B 通道弱
        warm[..., 1] = glow * 95.0   # G
        warm[..., 2] = glow * 160.0  # R 暖橙
        self.layer = (warm * (strength / 0.12) * 0.6).astype(np.float32)

    def apply(self, frame, index):
        out = frame.astype(np.float32) + self.layer
        return np.clip(out, 0, 255).astype(np.uint8)


class StickerOverlay:
    """四角贴纸：初始化时随机选图、随机大小与位置，预合成 RGBA 层。"""

    def __init__(self, rng, width, height):
        rgb = np.zeros((height, width, 3), dtype=np.float32)
        alpha = np.zeros((height, width), dtype=np.float32)
        corners = [(0, 0), (1, 0), (0, 1), (1, 1)]
        for corner_x, corner_y in corners:
            size = int(width * rng.uniform(0.055, 0.11))
            sticker = get_sticker(rng.choice(STICKER_KINDS), size)
            if rng.random() < 0.5:
                sticker = sticker.transpose(Image_FLIP)
            sticker = sticker.rotate(rng.uniform(-18, 18), expand=True, resample=Image_BICUBIC)
            sw, sh = sticker.size
            # 角落内随机偏移，避免贴纸超出画面
            max_dx, max_dy = width // 6, height // 6
            if corner_x == 0:
                x0 = int(rng.integers(int(width * 0.015), max(1, max_dx)))
            else:
                x0 = int(rng.integers(width - max_dx - sw, max(width - sw - int(width * 0.015), 1)))
            if corner_y == 0:
                y0 = int(rng.integers(int(height * 0.015), max(1, max_dy)))
            else:
                y0 = int(rng.integers(height - max_dy - sh, max(height - sh - int(height * 0.015), 1)))
            x0 = max(0, min(x0, width - sw))
            y0 = max(0, min(y0, height - sh))
            arr = np.asarray(sticker, dtype=np.float32)
            a = arr[..., 3] / 255.0
            # alpha-in（避免贴纸相互覆盖时出现硬边）
            region_a = alpha[y0:y0 + sh, x0:x0 + sw]
            region_rgb = rgb[y0:y0 + sh, x0:x0 + sw]
            keep = (1.0 - a)[..., None]
            rgb[y0:y0 + sh, x0:x0 + sw] = region_rgb * keep + arr[..., :3] * a[..., None]
            alpha[y0:y0 + sh, x0:x0 + sw] = np.maximum(region_a, a)
        self.rgb = rgb
        self.alpha = alpha[..., None]

    def apply(self, frame, index):
        out = frame.astype(np.float32) * (1.0 - self.alpha) + self.rgb * self.alpha
        return np.clip(out, 0, 255).astype(np.uint8)


class CaptionBar:
    """字幕条：底部半透明条 + 白色文本，按内容段时间轴切换。"""

    def __init__(self, entries, width, height, fps):
        self.entries = entries
        self.fps = fps
        bar_h = max(int(height * 0.13), 40)
        self.bar_y = height - bar_h - max(4, height // 120)
        self.bar_h = bar_h
        # 半透明黑色条（预生成 float 层）
        self.bar_rgb = np.zeros((bar_h, width, 3), dtype=np.float32)
        self.bar_alpha = np.full((bar_h, width, 1), 0.55, dtype=np.float32)
        # 预渲染各条目文本层
        font_size = max(16, int(height * 0.042))
        font = load_font(font_size)
        max_width = int(width * 0.86)
        self.text_layers = []
        for _, _, text in entries:
            layer = self._render_text(text, font, font_size, width, bar_h, max_width)
            self.text_layers.append(layer)

    def _render_text(self, text, font, font_size, width, bar_h, max_width):
        """渲染居中多行文本，返回 (y偏移, rgb, alpha)。"""
        img = Image.new("RGBA", (width, bar_h), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        lines = []
        for raw in text.split("\n"):
            lines.extend(self._wrap(raw, font, max_width))
        if len(lines) > 3:  # 最多三行，超出截断
            lines = lines[:3]
        line_h = int(font_size * 1.35)
        total_h = line_h * len(lines)
        y = max(0, (bar_h - total_h) // 2)
        for line in lines:
            bbox = d.textbbox((0, 0), line, font=font)
            x = (width - (bbox[2] - bbox[0])) // 2
            d.text((x, y), line, font=font, fill=(255, 255, 255, 255),
                   stroke_width=max(1, font_size // 24), stroke_fill=(0, 0, 0, 200))
            y += line_h
        arr = np.asarray(img, dtype=np.float32)
        return arr[..., :3][..., ::-1], arr[..., 3:4] / 255.0

    @staticmethod
    def _wrap(text, font, max_width):
        """按像素宽度逐字换行（兼容中文）。"""
        if not text:
            return [""]
        lines, cur = [], ""
        for ch in text:
            if font.getlength(cur + ch) > max_width and cur:
                lines.append(cur)
                cur = ch
            else:
                cur += ch
        lines.append(cur)
        return lines

    def apply(self, frame, content_index):
        t = content_index / self.fps
        # 线性扫描（条目数通常很少）
        for idx, (start, end, _) in enumerate(self.entries):
            if start <= t < end:
                text_rgb, text_a = self.text_layers[idx]
                bar = frame.astype(np.float32)
                bar[self.bar_y:self.bar_y + self.bar_h] = (
                    bar[self.bar_y:self.bar_y + self.bar_h] * (1.0 - self.bar_alpha)
                    + self.bar_rgb * self.bar_alpha)
                th, _ = text_rgb.shape[:2]
                y0 = self.bar_y + (self.bar_h - th) // 2
                region = bar[y0:y0 + th]
                bar[y0:y0 + th] = region * (1.0 - text_a) + text_rgb * text_a
                return np.clip(bar, 0, 255).astype(np.uint8)
        return frame


class FancyText:
    """花字：画面上部大字，渐变填充 + 白描边 + 阴影，任务内静态。"""

    def __init__(self, text, rng, width, height):
        font_size = max(24, int(height * 0.075))
        font = load_font(font_size)
        # 渐变色（从随机色相中选一组高饱和渐变）
        hue = rng.uniform(0, 360)
        c1 = self._hsv_to_bgr(hue, 0.85, 1.0)
        c2 = self._hsv_to_bgr((hue + 60) % 360, 0.9, 1.0)
        pad = font_size // 3
        # 临时画布测文本尺寸
        probe = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
        bbox = probe.textbbox((0, 0), text, font=font,
                              stroke_width=max(2, font_size // 16))
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        layer = Image.new("RGBA", (tw + pad * 4, th + pad * 4), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        # 阴影
        d.text((pad * 2 + font_size // 12, pad * 2 + font_size // 10), text,
               font=font, fill=(0, 0, 0, 160), stroke_width=max(2, font_size // 16),
               stroke_fill=(0, 0, 0, 160))
        # 主文本：先白描边，再渐变填充
        d.text((pad * 2, pad * 2), text, font=font, fill=(255, 255, 255, 255),
               stroke_width=max(2, font_size // 16), stroke_fill=(255, 255, 255, 255))
        mask = Image.new("L", layer.size, 0)
        ImageDraw.Draw(mask).text((pad * 2, pad * 2), text, font=font, fill=255)
        gradient = self._gradient_image(layer.size, c1, c2)
        layer.paste(gradient, (0, 0), mask)
        # 随机水平位置（上部 8%~16% 区域）
        lw, lh = layer.size
        x0 = int(rng.integers(0, max(1, width - lw))) if lw < width else 0
        y0 = int(height * rng.uniform(0.06, 0.12))
        self.layer_rgb = np.zeros((height, width, 3), dtype=np.float32)
        self.layer_a = np.zeros((height, width, 1), dtype=np.float32)
        x1, y1 = min(x0 + lw, width), min(y0 + lh, height)
        arr = np.asarray(layer, dtype=np.float32)[:y1 - y0, :x1 - x0]
        self.layer_rgb[y0:y1, x0:x1] = arr[..., :3][..., ::-1]
        self.layer_a[y0:y1, x0:x1] = arr[..., 3:4] / 255.0

    @staticmethod
    def _hsv_to_bgr(h, s, v):
        import colorsys
        r, g, b = colorsys.hsv_to_rgb(h / 360.0, s, v)
        return int(b * 255), int(g * 255), int(r * 255)

    @staticmethod
    def _gradient_image(size, c1, c2):
        w, h = size
        base = Image.new("RGB", (w, h))
        px = base.load()
        for x in range(w):
            t = x / max(1, w - 1)
            color = tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))
            for y in range(0, h, 4):  # 步进加速，逐列填充
                for yy in range(y, min(y + 4, h)):
                    px[x, yy] = color
        return base

    def apply(self, frame, content_index):
        out = frame.astype(np.float32) * (1.0 - self.layer_a) + self.layer_rgb * self.layer_a
        return np.clip(out, 0, 255).astype(np.uint8)


class ProgressBarOverlay:
    """进度条：画面最底部细条，按全局输出时间推进。"""

    def __init__(self, width, height, color=(226, 144, 74)):  # BGR 主题蓝
        self.width = width
        self.bar_h = max(4, height // 210)
        self.track_y = height - self.bar_h - max(3, height // 300)
        self.color = np.array(color, dtype=np.float32)

    def apply(self, frame, progress):
        out = frame.copy()
        y0, y1 = self.track_y, self.track_y + self.bar_h
        track = out[y0:y1].astype(np.float32) * 0.55  # 半透明轨道
        out[y0:y1] = track.astype(np.uint8)
        fill_w = int(self.width * min(max(progress, 0.0), 1.0))
        if fill_w > 0:
            out[y0:y1, :fill_w] = self.color.astype(np.uint8)
        return out


class EffectPipeline:
    """按配置组装效果并逐帧应用。apply 针对主内容段的输出帧（变速筛选后）。

    顺序：ZoomCrop（几何）-> ColorFilter -> 特效 -> 贴纸/字幕/花字。
    水平镜像在最终帧写入前统一执行，避免只翻转某个叠加层。
    """

    def __init__(self, options, rng, width, height, fps=60, content_duration=None, speed=1.0):
        self.fx_style = None
        self.filter_style = None
        self.zoom = None
        self.effects = []
        if options.filter_enabled:
            fx = ColorFilter(options.filter_style, options.filter_strength, rng)
            self.filter_style = fx.style
            self.effects.append(fx)
        if options.fx_enabled:
            fx_cls = {"grain": GrainFx, "vignette": VignetteFx,
                      "bloom": BloomFx, "leak": LeakFx}
            style = rng.choice(FX_STYLES[1:]) if options.fx_style == "random" else options.fx_style
            self.fx_style = style
            self.effects.append(fx_cls[style](options.fx_strength, rng, (height, width)))
        if options.sticker_enabled:
            self.effects.append(StickerOverlay(rng, width, height))
        if options.caption_enabled and content_duration:
            entries = options.caption_entries(content_duration, speed)
            if entries:
                self.effects.append(CaptionBar(entries, width, height, fps))
        if options.fancy_enabled and options.fancy_text.strip():
            self.effects.append(FancyText(options.fancy_text.strip(), rng, width, height))

    def set_zoom(self, zoom_scale):
        """设置画面放大比例（由 options.sample_randoms 采样后传入）。"""
        if zoom_scale and zoom_scale > 1.001:
            self.zoom = ZoomCrop(zoom_scale)

    def apply(self, frame, out_index):
        if self.zoom is not None:
            frame = self.zoom.apply(frame, out_index)
        for e in self.effects:
            frame = e.apply(frame, out_index)
        return frame

    @property
    def is_identity(self):
        return self.zoom is None and not self.effects