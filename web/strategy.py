"""Web 服务版随机处理策略生成。

页面不提供功能选择，服务端随机生成至少 3 个处理步骤。
随机到镜像时强制追加压字幕条（OCR 提取原视频字幕后压回）。
"""
import random

# 画面步骤池（片头片尾、配音均允许随机）
VISUAL_STEPS = [
    "zoom", "mirror", "filter", "fx", "sticker",
    "fancy", "progress", "caption_bar", "drop_frames",
    "intro", "outro",
]

# 必须至少随机到的步骤数
MIN_STEPS = 3
MAX_STEPS = 6


def generate_strategy(has_audio_file=False, has_video_b=False, title="", rng=None):
    """生成一条随机处理策略，返回 dict（与 WebOptions 对应）。"""
    rng = rng or random.Random()
    n = rng.randint(MIN_STEPS, min(MAX_STEPS, len(VISUAL_STEPS)))
    steps = rng.sample(VISUAL_STEPS, n)

    # 镜像反转后必须压字幕条
    if "mirror" in steps:
        steps = ["mirror"] + [step for step in steps if step != "mirror"]
        if "caption_bar" not in steps:
            steps.append("caption_bar")

    # 音频模式：原声 / BGM 替换 / 简单变声
    audio_modes = ["original", "voice_change"]
    if has_audio_file:
        audio_modes.append("replace_bgm")
    audio_mode = rng.choice(audio_modes)

    # 帧混合：有视频 B 才随机强度
    fps = 30
    if has_video_b:
        fps = rng.choice([60, 120])

    strategy = {
        "title": title,
        "steps": steps,
        "audio_mode": audio_mode,
        "fps": fps,
        "drop_per_second": rng.randint(1, 3) if "drop_frames" in steps else 0,
        "speed": round(rng.uniform(1.05, 1.2), 2) if "speed" in steps else 1.0,
        "zoom": round(rng.uniform(1.10, 1.20), 2) if "zoom" in steps else 1.0,
        "filter_style": rng.choice(["warm", "cool", "vintage", "mono", "bright"]) if "filter" in steps else None,
        "fx_style": rng.choice(["grain", "vignette", "bloom", "leak"]) if "fx" in steps else None,
        "intro_duration": round(rng.uniform(0.8, 1.5), 1) if "intro" in steps else 0,
        "outro_duration": round(rng.uniform(0.8, 1.2), 1) if "outro" in steps else 0,
    }
    return strategy
