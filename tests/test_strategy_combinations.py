import random
from itertools import combinations
import numpy as np
import pytest
from web.strategy import DEFAULT_CONFIG, generate_strategy, validate_strategy_config
from config import ProcessingOptions
from effects import EffectPipeline, StickerOverlay

LAYOUTS = ['corners', 'horizontal_bar', 'vertical_bars']

def test_all_seven_combinations_and_aspects():
    config = {**DEFAULT_CONFIG, 'selection_mode':'fixed',
              'steps':['sticker','progress','drop_frames'],
              'aspect_ratios':['4:3','16:9','9:16'], 'sticker_layouts':LAYOUTS}
    snapshots = [generate_strategy(config=config, rng=random.Random(seed)) for seed in range(200)]
    assert {s['aspect_ratio'] for s in snapshots} == {'4:3','16:9','9:16'}
    assert {frozenset(s['sticker_layouts']) for s in snapshots} == {
        frozenset(c) for n in (1,2,3) for c in combinations(LAYOUTS,n)}
    for n in (1,2,3):
        for combo in combinations(LAYOUTS,n):
            pipeline=EffectPipeline(ProcessingOptions(sticker_enabled=True,sticker_layouts=list(combo)),np.random.default_rng(1),320,240)
            assert sum(isinstance(o,StickerOverlay) for o in pipeline.overlays)==n
            frame=np.zeros((240,320,3),dtype=np.uint8)
            assert pipeline.apply(frame,0).shape==frame.shape


def test_legacy_and_disabled_compatibility():
    config=validate_strategy_config({**DEFAULT_CONFIG,'aspect_ratio':'9:16','sticker_layout':'vertical_bars'})
    assert config['aspect_ratios']==['9:16']
    assert config['sticker_layouts']==['vertical_bars']
    config.update(steps=['fancy','progress','drop_frames'],sticker_layouts=[])
    assert generate_strategy(config=config)['sticker_layouts']==[]


@pytest.mark.parametrize('key', ['aspect_ratios','sticker_layouts'])
@pytest.mark.parametrize('value', [[],['invalid'],'corners',None])
def test_invalid_candidates(key,value):
    with pytest.raises(ValueError):
        validate_strategy_config({**DEFAULT_CONFIG,key:value})
