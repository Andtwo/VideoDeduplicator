"""Web 服务版处理策略生成与配置校验。"""
import random

VISUAL_STEPS = [
    "zoom", "mirror", "filter", "fx", "sticker",
    "fancy", "progress", "caption_bar", "drop_frames", "speed",
    "intro", "outro",
]
AUDIO_MODES = ["original", "voice_change", "replace_bgm"]
FILTER_STYLES = ["warm", "cool", "vintage", "mono", "bright"]
FX_STYLES = ["grain", "vignette", "bloom", "leak"]
FPS_OPTIONS = [30, 60, 120]
MIN_STEPS = 3
MAX_STEPS = 6
DEFAULT_STEPS = [step for step in VISUAL_STEPS if step != "speed"]

DEFAULT_CONFIG = {
    "selection_mode": "random",
    "steps": DEFAULT_STEPS,
    "min_steps": MIN_STEPS,
    "max_steps": MAX_STEPS,
    "audio_modes": AUDIO_MODES.copy(),
    "fps_options": FPS_OPTIONS.copy(),
    "drop_min": 1,
    "drop_max": 3,
    "zoom_min": 1.10,
    "zoom_max": 1.20,
    "speed_min": 1.05,
    "speed_max": 1.20,
    "filter_styles": FILTER_STYLES.copy(),
    "fx_styles": FX_STYLES.copy(),
    "intro_min": 0.8,
    "intro_max": 1.5,
    "outro_min": 0.8,
    "outro_max": 1.2,
}


def _bounded_pair(config, low_key, high_key, minimum, maximum):
    low = float(config.get(low_key, minimum))
    high = float(config.get(high_key, maximum))
    if not minimum <= low <= high <= maximum:
        raise ValueError(f"{low_key}/{high_key} 参数范围无效")
    return low, high


def validate_strategy_config(raw):
    """校验并规范化后台保存的策略配置。"""
    if not isinstance(raw, dict):
        raise ValueError("策略配置必须是对象")
    config = {**DEFAULT_CONFIG, **raw}
    mode = config.get("selection_mode")
    if mode not in ("fixed", "random"):
        raise ValueError("selection_mode 只能是 fixed 或 random")

    steps = list(dict.fromkeys(config.get("steps") or []))
    unknown = sorted(set(steps) - set(VISUAL_STEPS))
    if unknown:
        raise ValueError("未知处理步骤: " + ", ".join(unknown))
    if len(steps) < MIN_STEPS:
        raise ValueError(f"至少选择 {MIN_STEPS} 个处理步骤")

    min_steps = int(config.get("min_steps", MIN_STEPS))
    max_steps = int(config.get("max_steps", MAX_STEPS))
    if mode == "fixed":
        min_steps = max_steps = len(steps)
    elif not MIN_STEPS <= min_steps <= max_steps <= len(steps):
        raise ValueError("随机步骤数量必须在已选步骤范围内，且至少为 3")

    audio_modes = list(dict.fromkeys(config.get("audio_modes") or []))
    if not audio_modes or set(audio_modes) - set(AUDIO_MODES):
        raise ValueError("至少选择一个有效音频模式")
    fps_options = sorted(set(int(value) for value in (config.get("fps_options") or [])))
    if not fps_options or set(fps_options) - set(FPS_OPTIONS):
        raise ValueError("至少选择一个有效输出帧率")

    drop_min, drop_max = _bounded_pair(config, "drop_min", "drop_max", 1, 3)
    zoom_min, zoom_max = _bounded_pair(config, "zoom_min", "zoom_max", 1.0, 1.5)
    speed_min, speed_max = _bounded_pair(config, "speed_min", "speed_max", 0.5, 2.0)
    intro_min, intro_max = _bounded_pair(config, "intro_min", "intro_max", 0.0, 5.0)
    outro_min, outro_max = _bounded_pair(config, "outro_min", "outro_max", 0.0, 5.0)

    filter_styles = list(dict.fromkeys(config.get("filter_styles") or []))
    fx_styles = list(dict.fromkeys(config.get("fx_styles") or []))
    if "filter" in steps and (not filter_styles or set(filter_styles) - set(FILTER_STYLES)):
        raise ValueError("滤镜步骤需要至少一个有效滤镜样式")
    if "fx" in steps and (not fx_styles or set(fx_styles) - set(FX_STYLES)):
        raise ValueError("特效步骤需要至少一个有效特效样式")

    return {
        "selection_mode": mode,
        "steps": steps,
        "min_steps": min_steps,
        "max_steps": max_steps,
        "audio_modes": audio_modes,
        "fps_options": fps_options,
        "drop_min": int(drop_min),
        "drop_max": int(drop_max),
        "zoom_min": round(zoom_min, 2),
        "zoom_max": round(zoom_max, 2),
        "speed_min": round(speed_min, 2),
        "speed_max": round(speed_max, 2),
        "filter_styles": filter_styles,
        "fx_styles": fx_styles,
        "intro_min": round(intro_min, 1),
        "intro_max": round(intro_max, 1),
        "outro_min": round(outro_min, 1),
        "outro_max": round(outro_max, 1),
    }


def generate_strategy(has_audio_file=False, has_video_b=False, title="", rng=None, config=None):
    """根据已启用版本的配置生成一次不可变任务策略。"""
    rng = rng or random.Random()
    config = validate_strategy_config(config or DEFAULT_CONFIG)
    candidates = config["steps"]
    if config["selection_mode"] == "fixed":
        steps = candidates.copy()
    else:
        count = rng.randint(config["min_steps"], config["max_steps"])
        steps = rng.sample(candidates, count)

    if "mirror" in steps:
        steps = ["mirror"] + [step for step in steps if step != "mirror"]
        if "caption_bar" not in steps:
            steps.append("caption_bar")

    available_audio = [mode for mode in config["audio_modes"] if mode != "replace_bgm" or has_audio_file]
    if not available_audio:
        available_audio = ["original"]
    audio_mode = rng.choice(available_audio)

    available_fps = [fps for fps in config["fps_options"] if has_video_b or fps == 30]
    fps = rng.choice(available_fps or [30])
    strategy = {
        "title": title,
        "steps": steps,
        "audio_mode": audio_mode,
        "fps": fps,
        "drop_per_second": rng.randint(config["drop_min"], config["drop_max"]) if "drop_frames" in steps else 0,
        "speed": round(rng.uniform(config["speed_min"], config["speed_max"]), 2) if "speed" in steps else 1.0,
        "zoom": round(rng.uniform(config["zoom_min"], config["zoom_max"]), 2) if "zoom" in steps else 1.0,
        "filter_style": rng.choice(config["filter_styles"]) if "filter" in steps else None,
        "fx_style": rng.choice(config["fx_styles"]) if "fx" in steps else None,
        "intro_duration": round(rng.uniform(config["intro_min"], config["intro_max"]), 1) if "intro" in steps else 0,
        "outro_duration": round(rng.uniform(config["outro_min"], config["outro_max"]), 1) if "outro" in steps else 0,
    }
    return strategy
