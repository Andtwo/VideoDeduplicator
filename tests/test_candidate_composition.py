import numpy as np
import pytest
from web.strategy import DEFAULT_CONFIG, validate_strategy_config
from effects import StickerOverlay, EffectPipeline
from config import ProcessingOptions


def test_new_candidates_override_invalid_legacy_fields():
    c = validate_strategy_config({**DEFAULT_CONFIG, 'aspect_ratio': 'invalid',
        'sticker_layout': 'invalid', 'aspect_ratios': ['9:16'],
        'sticker_layouts': ['vertical_bars']})
    assert c['aspect_ratios'] == ['9:16']
    assert c['sticker_layouts'] == ['vertical_bars']
    assert 'aspect_ratio' not in c and 'sticker_layout' not in c
    assert validate_strategy_config(c) == c
    with pytest.raises(ValueError):
        validate_strategy_config({**DEFAULT_CONFIG, 'aspect_ratios': []})


@pytest.mark.parametrize('layouts', [
    ['corners','horizontal_bar'], ['horizontal_bar','vertical_bars'],
    ['corners','horizontal_bar','vertical_bars']])
def test_composite_matches_sequential_render_and_uses_one_layer(layouts):
    rng = np.random.default_rng(2)
    frame = np.random.default_rng(3).integers(0,256,(240,320,3),dtype=np.uint8)
    expected = frame.copy()
    for layout in layouts:
        expected = StickerOverlay(rng,320,240,layout=layout).apply(expected,0)
    p = EffectPipeline(ProcessingOptions(sticker_enabled=True,sticker_layouts=layouts),
                       np.random.default_rng(2),320,240)
    actual = p.apply(frame,0)
    # 顺序绘制每层转换 uint8，合成只转换一次；允许累计舍入差。
    assert np.abs(actual.astype(int)-expected.astype(int)).max() <= len(layouts)
    assert len(p.overlays) == 1
    layer = p.overlays[0]
    assert layer.rgb.nbytes + layer.alpha.nbytes == 240*320*4*4
