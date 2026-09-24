import numpy as np
import pytest
from effects import StickerOverlay, ProgressBarOverlay
from web.strategy import DEFAULT_CONFIG
from web.strategy_store import StrategyStore, StrategyConflictError


def test_update_preserves_version_and_task_snapshot(tmp_path):
    store = StrategyStore(tmp_path / 'strategies.json')
    current = store.active_version()
    old = store.snapshot_for_task()
    result = store.update_version(current['id'], current['name'], '修改', {**DEFAULT_CONFIG, 'aspect_ratio': '9:16'}, expected_revision=0)
    assert result['version'] == current['version']
    assert len(store.list_versions()) == 1
    assert old['aspect_ratio'] == 'source'
    assert store.snapshot_for_task()['aspect_ratio'] == '9:16'


def test_stale_revision_cannot_overwrite_saved_configuration(tmp_path):
    store = StrategyStore(tmp_path / 'strategies.json')
    original = store.active_version()
    first = store.update_version(original['id'], original['name'], 'A',
                                 {**DEFAULT_CONFIG, 'aspect_ratio': '9:16'}, 0)
    assert first['revision'] == 1
    for revision in (0, None, True, '1'):
        with pytest.raises(StrategyConflictError):
            store.update_version(original['id'], original['name'], 'B',
                                 DEFAULT_CONFIG, revision)
        assert store.active_version()['config']['aspect_ratio'] == '9:16'
    # 重新加载后提交新修订号可以保存，外部版本号保持不变。
    updated = store.update_version(first['id'], first['name'], 'C',
                                   {**first['config'], 'sticker_layout': 'vertical_bars'}, 1)
    assert updated['revision'] == 2
    assert updated['version'] == original['version']
    assert updated['config']['aspect_ratio'] == '9:16'


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
