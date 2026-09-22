"""处理选项配置模型：所有后期功能参数集中定义。"""

import os
from dataclasses import dataclass, field


FILTER_STYLES = ["random", "warm", "cool", "vintage", "mono", "bright"]
FX_STYLES = ["random", "grain", "vignette", "bloom", "leak"]

# ⑤ 音频模式：保留原声 / BGM替换 / 原声+BGM混音 / 外部配音替换
AUDIO_MODES = ["original", "replace_bgm", "mix_bgm", "replace_voice"]


@dataclass
class ProcessingOptions:
    # ① 变速（1.05 ~ 1.2 倍速，音画同步 atempo）
    speed_enabled: bool = False
    speed_random: bool = True
    speed_min: float = 1.05
    speed_max: float = 1.20

    # ② 裁剪缩放（画面放大 110% ~ 120%，中心裁剪后还原分辨率）
    zoom_enabled: bool = False
    zoom_random: bool = True
    zoom_min: float = 1.10
    zoom_max: float = 1.20

    # ③ 镜像翻转（水平翻转）
    mirror_enabled: bool = False

    # ⑥ 滤镜（默认强度 10%）
    filter_enabled: bool = False
    filter_style: str = "random"
    filter_strength: float = 0.10

    # ⑦ 画面特效（低强度，不明显）
    fx_enabled: bool = False
    fx_style: str = "random"
    fx_strength: float = 0.12

    # ⑧ 四角贴纸（四角随机贴纸，大小随机）
    sticker_enabled: bool = False

    # ⑤ 音频：BGM 替换 / 混音 / 配音替换
    audio_mode: str = "original"
    audio_file: str = ""      # BGM 或配音文件路径
    bgm_volume: float = 0.3   # BGM 音量（替换与混音模式生效）

    # ④ 包装：字幕条 / 花字 / 进度条 / 片头片尾
    caption_enabled: bool = False
    caption_text: str = ""       # 多行文本，每行一条均分时长
    caption_srt: str = ""        # SRT 文件路径（优先于多行文本）
    fancy_enabled: bool = False
    fancy_text: str = ""         # 花字内容
    progress_enabled: bool = False
    intro_enabled: bool = False
    intro_text: str = ""
    intro_duration: float = 1.5  # 秒
    outro_enabled: bool = False
    outro_text: str = ""
    outro_duration: float = 1.0  # 秒

    # Web 版扩展：删帧（模式 B：真实删除，视频变短）
    drop_enabled: bool = False
    drop_per_second: int = 0     # 每秒删除的帧数（1-3）

    # Web 版扩展：OCR 提取的字幕条目（优先于 caption_text/caption_srt）
    caption_ocr_entries: list = field(default_factory=list)

    def sample_randoms(self, rng):
        """任务开始时确定本条视频的随机参数，返回 dict。同一次任务内保持一致。"""
        speed = rng.uniform(self.speed_min, self.speed_max) if self.speed_enabled else 1.0
        if not self.speed_random:
            speed = self.speed_min
        zoom = rng.uniform(self.zoom_min, self.zoom_max) if self.zoom_enabled else 1.0
        if not self.zoom_random:
            zoom = self.zoom_min
        return {"speed": speed, "zoom": zoom}

    def enabled_features(self):
        """返回启用的功能名列表（用于日志与遥测）。"""
        names = []
        if self.speed_enabled:
            names.append("speed")
        if self.zoom_enabled:
            names.append("zoom")
        if self.mirror_enabled:
            names.append("mirror")
        if self.filter_enabled:
            names.append("filter")
        if self.fx_enabled:
            names.append("fx")
        if self.sticker_enabled:
            names.append("sticker")
        if self.audio_mode != "original":
            names.append(self.audio_mode)
        if self.caption_enabled:
            names.append("caption")
        if self.fancy_enabled:
            names.append("fancy")
        if self.progress_enabled:
            names.append("progress")
        if self.intro_enabled:
            names.append("intro")
        if self.outro_enabled:
            names.append("outro")
        return names

    def caption_entries(self, content_duration, speed=1.0):
        """返回字幕条目 [(start, end, text), ...]，时间轴为内容段输出时间。

        SRT 时间轴基于原视频，需除以 speed 换算；多行文本均分时长。
        OCR 条目优先，时间轴已是输出时间。
        """
        if self.caption_ocr_entries:
            return self.caption_ocr_entries
        if self.caption_srt and os.path.exists(self.caption_srt):
            from assets import parse_srt
            entries = parse_srt(self.caption_srt)
            if speed > 1.001:
                entries = [(s / speed, e / speed, t) for s, e, t in entries]
            return entries
        lines = [line.strip() for line in self.caption_text.splitlines() if line.strip()]
        if not lines:
            return []
        seg = content_duration / len(lines)
        return [(i * seg, (i + 1) * seg, text) for i, text in enumerate(lines)]
