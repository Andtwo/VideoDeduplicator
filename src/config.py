"""处理选项配置模型：所有后期功能参数集中定义。"""

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
        return names
