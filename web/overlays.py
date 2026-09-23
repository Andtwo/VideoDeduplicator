"""左上角影视名称叠加层。"""
import cv2
import numpy as np
from PIL import Image, ImageDraw

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from assets import load_font


class TitleOverlay:
    """左上角半透明底条 + 影视名称文字。"""

    def __init__(self, title, width, height):
        self.title = title.strip()
        self.enabled = bool(self.title)
        self.ready = self.enabled and width > 0 and height > 0
        self.w = 0
        if not self.ready:
            return
        font_size = max(24, int(height * 0.08))
        font = load_font(font_size)
        pad = max(6, font_size // 3)
        probe = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
        bbox = probe.textbbox((0, 0), title, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        self.x0 = int(width * 0.03)
        self.y0 = int(height * 0.04)
        self.w = tw + pad * 2
        self.h = th + pad * 2
        self.pad = pad
        self.font = font

    def apply(self, frame):
        if not self.ready:
            return frame
        x0, y0 = self.x0, self.y0
        x1 = min(frame.shape[1], x0 + self.w)
        y1 = min(frame.shape[0], y0 + self.h)
        if x1 <= x0 or y1 <= y0:
            return frame
        # 半透明底
        region = frame[y0:y1, x0:x1].astype(np.float32)
        region = region * 0.55
        frame[y0:y1, x0:x1] = region.astype(np.uint8)
        # 文字
        img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        d = ImageDraw.Draw(img)
        d.text((x0 + self.pad, y0 + self.pad), self.title,
               font=self.font, fill=(255, 255, 255))
        return cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)
