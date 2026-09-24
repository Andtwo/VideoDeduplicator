"""未启用步骤的参数不应阻止策略保存。"""
import pytest
from web.strategy import DEFAULT_CONFIG, generate_strategy, validate_strategy_config
from web.strategy_store import StrategyStore


DEPENDENCIES = [
    ("zoom", "zoom_min"), ("speed", "speed_min"),
    ("intro", "intro_min"), ("outro", "outro_min"),
    ("drop_frames", "drop_min"), ("sticker", "sticker_layout"),
    ("filter", "filter_strength"), ("fx", "fx_styles"),
]


@pytest.mark.parametrize("step,key", DEPENDENCIES)
def test_disabled_parameter_is_ignored_but_enabled_parameter_is_validated(step, key):
    raw = {**DEFAULT_CONFIG, "selection_mode": "fixed",
           "steps": ["fancy", "progress", "caption_bar"], key: "invalid"}
    normalized = validate_strategy_config(raw)
    if key == "sticker_layout":
        assert normalized["sticker_layouts"] == [DEFAULT_CONFIG[key]]
    else:
        assert normalized[key] == DEFAULT_CONFIG[key]
    with pytest.raises(ValueError):
        validate_strategy_config({**raw, "steps": raw["steps"] + [step]})


def test_store_can_save_disabled_invalid_ranges(tmp_path):
    store = StrategyStore(tmp_path / "strategies.json")
    config = {**DEFAULT_CONFIG, "selection_mode": "fixed",
              "steps": ["fancy", "progress", "caption_bar"],
              "zoom_min": 999, "speed_min": "", "intro_min": None,
              "drop_min": -1, "filter_strength": "invalid", "aspect_ratio": "9:16"}
    version = store.create_version("联动验证", "", config)
    store.activate(version["id"])
    snapshot = store.snapshot_for_task()
    assert snapshot["aspect_ratio"] == "9:16"
    assert snapshot["speed"] == snapshot["zoom"] == 1.0
    assert snapshot["drop_per_second"] == 0
    assert generate_strategy(config=config)["steps"] == config["steps"]
