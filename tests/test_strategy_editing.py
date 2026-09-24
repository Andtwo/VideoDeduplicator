import numpy as np
import pytest
from effects import StickerOverlay, ProgressBarOverlay
from web.strategy import DEFAULT_CONFIG
from web.strategy_store import StrategyStore


def test_update_preserves_version_and_task_snapshot(tmp_path):
    store = StrategyStore(tmp_path / 'strategies.json')
    current = store.active_version()
    old = store.snapshot_for_task()
    result = store.update_version(current['id'], current['name'], '修改', {**DEFAULT_CONFIG, 'aspect_ratio': '9:16'})
    assert result['version'] == current['version']
    assert len(store.list_versions()) == 1
    assert old['aspect_ratio'] == 'source'
    assert store.snapshot_for_task()['aspect_ratio'] == '9:16'


def test_batch_delete_is_atomic_and_protects_active(tmp_path):
    store = StrategyStore(tmp_path / 'strategies.json')
    active = store.active_version()
    a = store.create_version('A', '', DEFAULT_CONFIG)
    b = store.create_version('B', '', DEFAULT_CONFIG)
    with pytest.raises(ValueError):
        store.delete_versions([a['id'], active['id']])
    with pytest.raises(KeyError):
        store.delete_versions([a['id'], 'missing'])
    assert len(store.list_versions()) == 3
    store.delete_versions([a['id'], b['id']])
    assert len(store.list_versions()) == 1


@pytest.mark.parametrize('width,height', [(640,360),(360,640),(16,16)])
@pytest.mark.parametrize('layout', ['horizontal_bar','vertical_bars'])
def test_ribbons_are_continuous(width,height,layout):
    overlay = StickerOverlay(np.random.default_rng(1), width,height,layout=layout)
    alpha = overlay.alpha[...,0]
    if layout == 'horizontal_bar':
        assert np.all(alpha[0] > 0)
    else:
        assert np.all(alpha[:,0] > 0) and np.all(alpha[:,-1] > 0)
    assert alpha[height//2,width//2] == 0
    frame = np.full((height,width,3),100,dtype=np.uint8)
    out = overlay.apply(frame,0)
    assert out.shape == frame.shape
    np.testing.assert_array_equal(out[height//2,width//2], frame[height//2,width//2])


def test_progress_is_thicker():
    assert ProgressBarOverlay(1920,1080).bar_h == 20
