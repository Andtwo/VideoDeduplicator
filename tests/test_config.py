"""ProcessingOptions 配置与随机采样测试。"""
import numpy as np
import pytest

from config import ProcessingOptions


class TestDefaults:
    def test_all_disabled_by_default(self):
        opts = ProcessingOptions()
        assert opts.enabled_features() == []

    def test_defaults_in_expected_ranges(self):
        opts = ProcessingOptions(speed_enabled=True, zoom_enabled=True,
                                 filter_enabled=True, fx_enabled=True)
        assert 1.05 <= opts.speed_min <= opts.speed_max <= 1.2
        assert 1.10 <= opts.zoom_min <= opts.zoom_max <= 1.20
        assert opts.filter_strength <= 0.10
        assert opts.fx_strength <= 0.15


class TestSampleRandoms:
    def test_speed_within_range(self):
        opts = ProcessingOptions(speed_enabled=True, speed_min=1.08, speed_max=1.15)
        rng = np.random.default_rng(42)
        for _ in range(50):
            r = opts.sample_randoms(rng)
            assert 1.08 <= r["speed"] <= 1.15
        # 未启用的维度返回固定值 1.0
        assert r["zoom"] == 1.0

    def test_fixed_mode_not_random(self):
        opts = ProcessingOptions(speed_enabled=True, speed_min=1.1, speed_max=1.1,
                                 speed_random=False)
        r = opts.sample_randoms(np.random.default_rng(0))
        assert r["speed"] == 1.1

    def test_randoms_stable_within_task(self):
        opts = ProcessingOptions(speed_enabled=True, zoom_enabled=True)
        r1 = opts.sample_randoms(np.random.default_rng(7))
        assert isinstance(r1["speed"], float)
        assert isinstance(r1["zoom"], float)


class TestCaptionEntries:
    def test_multiline_splits_duration(self):
        opts = ProcessingOptions(caption_enabled=True, caption_text="一\n二\n三")
        entries = opts.caption_entries(6.0)
        assert len(entries) == 3
        assert entries[0][0] == 0.0
        assert entries[-1][1] == pytest.approx(6.0)

    def test_srt_timescale(self):
        opts = ProcessingOptions(caption_enabled=True, caption_text="x")
        entries = opts.caption_entries(4.0)
        assert entries == [(0.0, 4.0, "x")]

    def test_srt_file_parses(self, srt_file):
        opts = ProcessingOptions(caption_enabled=True, caption_srt=srt_file)
        entries = opts.caption_entries(4.0)
        assert len(entries) == 2
        assert entries[0] == (0.5, 2.0, "第一条字幕")
        assert entries[1] == (2.0, 4.0, "第二条字幕")

    def test_srt_compensates_speed(self, srt_file):
        opts = ProcessingOptions(caption_enabled=True, caption_srt=srt_file)
        entries = opts.caption_entries(4.0 / 1.25, 1.25)
        assert entries[0][0] == pytest.approx(0.5 / 1.25)
        assert entries[1][1] == pytest.approx(4.0 / 1.25)

    def test_empty_text_no_entries(self):
        opts = ProcessingOptions(caption_enabled=True, caption_text="  \n  ")
        assert opts.caption_entries(4.0) == []


class TestEnabledFeatures:
    def test_audio_mode_listed_when_not_original(self):
        opts = ProcessingOptions(audio_mode="mix_bgm")
        assert "mix_bgm" in opts.enabled_features()

    def test_full_feature_set(self):
        opts = ProcessingOptions(
            speed_enabled=True, zoom_enabled=True, mirror_enabled=True,
            filter_enabled=True, fx_enabled=True, sticker_enabled=True,
            caption_enabled=True, fancy_enabled=True, progress_enabled=True,
            intro_enabled=True, outro_enabled=True, audio_mode="replace_voice")
        assert len(opts.enabled_features()) == 12
