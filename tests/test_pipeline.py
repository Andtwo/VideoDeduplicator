"""端到端管线测试：合成视频 -> VideoProcessor -> 输出校验。"""
import os

import pytest

from config import ProcessingOptions
from pipeline import VideoProcessor
from conftest import probe


def make_processor(qapp, video_a, video_b, out_path, tmp_dir, options):
    return VideoProcessor(video_a, video_b, str(out_path), 60, str(tmp_dir), options=options)


class TestBasicPipeline:
    def test_no_effects_passthrough(self, qapp, wait_process, video_a, video_b, tmp_path):
        out = tmp_path / "plain.mp4"
        p = make_processor(qapp, video_a, video_b, out, tmp_path / "tmp", ProcessingOptions())
        wait_process(p)
        info = probe(out)
        assert info["duration"] == pytest.approx(4.0, abs=0.2)
        assert "video" in info["streams"] and "audio" in info["streams"]

    def test_speed_changes_duration(self, qapp, wait_process, video_a, video_b, tmp_path):
        out = tmp_path / "fast.mp4"
        opts = ProcessingOptions(speed_enabled=True, speed_min=1.2, speed_max=1.2,
                                 speed_random=False)
        p = make_processor(qapp, video_a, video_b, out, tmp_path / "tmp", opts)
        wait_process(p)
        assert probe(out)["duration"] == pytest.approx(4.0 / 1.2, abs=0.15)

    def test_visual_effects_combined(self, qapp, wait_process, video_a, video_b, tmp_path):
        out = tmp_path / "fx.mp4"
        opts = ProcessingOptions(
            speed_enabled=True, speed_min=1.1, speed_max=1.1, speed_random=False,
            zoom_enabled=True, zoom_min=1.12, zoom_max=1.12, zoom_random=False,
            mirror_enabled=True, filter_enabled=True, fx_enabled=True, sticker_enabled=True)
        p = make_processor(qapp, video_a, video_b, out, tmp_path / "tmp", opts)
        wait_process(p)
        assert probe(out)["duration"] == pytest.approx(4.0 / 1.1, abs=0.15)


class TestAudioModes:
    def test_replace_bgm(self, qapp, wait_process, video_a, video_b, bgm_file, tmp_path):
        out = tmp_path / "bgm.mp4"
        opts = ProcessingOptions(audio_mode="replace_bgm", audio_file=bgm_file, bgm_volume=0.3)
        p = make_processor(qapp, video_a, video_b, out, tmp_path / "tmp", opts)
        wait_process(p)
        info = probe(out)
        assert "audio" in info["streams"]
        assert info["duration"] == pytest.approx(4.0, abs=0.2)

    def test_mix_bgm_with_intro(self, qapp, wait_process, video_a, video_b, bgm_file, tmp_path):
        out = tmp_path / "mix.mp4"
        opts = ProcessingOptions(
            intro_enabled=True, intro_text="片头", intro_duration=1.0,
            audio_mode="mix_bgm", audio_file=bgm_file, bgm_volume=0.3)
        p = make_processor(qapp, video_a, video_b, out, tmp_path / "tmp", opts)
        wait_process(p)
        assert probe(out)["duration"] == pytest.approx(5.0, abs=0.2)

    def test_replace_voice(self, qapp, wait_process, video_a, video_b, bgm_file, tmp_path):
        out = tmp_path / "voice.mp4"
        opts = ProcessingOptions(audio_mode="replace_voice", audio_file=bgm_file)
        p = make_processor(qapp, video_a, video_b, out, tmp_path / "tmp", opts)
        wait_process(p)
        assert "audio" in probe(out)["streams"]


class TestBranding:
    def test_intro_outro_duration(self, qapp, wait_process, video_a, video_b, tmp_path):
        out = tmp_path / "brand.mp4"
        opts = ProcessingOptions(
            intro_enabled=True, intro_text="I", intro_duration=1.5,
            outro_enabled=True, outro_text="O", outro_duration=1.0,
            progress_enabled=True, caption_enabled=True, caption_text="字\n幕",
            fancy_enabled=True, fancy_text="花")
        p = make_processor(qapp, video_a, video_b, out, tmp_path / "tmp", opts)
        wait_process(p)
        assert probe(out)["duration"] == pytest.approx(6.5, abs=0.2)

    def test_srt_captions(self, qapp, wait_process, video_a, video_b, srt_file, tmp_path):
        out = tmp_path / "srt.mp4"
        opts = ProcessingOptions(caption_enabled=True, caption_srt=srt_file)
        p = make_processor(qapp, video_a, video_b, out, tmp_path / "tmp", opts)
        wait_process(p)
        assert probe(out)["duration"] == pytest.approx(4.0, abs=0.2)


class TestEdgeCases:
    def test_no_audio_source(self, qapp, wait_process, video_no_audio, video_b, tmp_path):
        out = tmp_path / "silent.mp4"
        opts = ProcessingOptions(mirror_enabled=True)
        p = make_processor(qapp, video_no_audio, video_b, out, tmp_path / "tmp", opts)
        wait_process(p)
        info = probe(out)
        assert "audio" not in info["streams"]  # 纯视频输出

    def test_no_audio_source_with_mix_bgm(self, qapp, wait_process, video_no_audio,
                                          video_b, bgm_file, tmp_path):
        # 无原声 + 混音模式 -> 降级 BGM 替换
        out = tmp_path / "silent_bgm.mp4"
        opts = ProcessingOptions(audio_mode="mix_bgm", audio_file=bgm_file, bgm_volume=0.3)
        p = make_processor(qapp, video_no_audio, video_b, out, tmp_path / "tmp", opts)
        wait_process(p)
        assert "audio" in probe(out)["streams"]

    def test_portrait_video(self, qapp, wait_process, video_portrait, video_b, tmp_path):
        out = tmp_path / "portrait.mp4"
        opts = ProcessingOptions(
            zoom_enabled=True, zoom_min=1.1, zoom_max=1.1, zoom_random=False,
            sticker_enabled=True, caption_enabled=True, caption_text="竖屏测试")
        p = make_processor(qapp, video_portrait, video_b, out, tmp_path / "tmp", opts)
        wait_process(p)
        assert probe(out)["duration"] == pytest.approx(3.0, abs=0.2)

    def test_all_features_max_combination(self, qapp, wait_process, video_a, video_b,
                                          bgm_file, srt_file, tmp_path):
        """全部 12 项功能同时开启。"""
        out = tmp_path / "max.mp4"
        opts = ProcessingOptions(
            speed_enabled=True, speed_min=1.1, speed_max=1.1, speed_random=False,
            zoom_enabled=True, zoom_min=1.15, zoom_max=1.15, zoom_random=False,
            mirror_enabled=True, filter_enabled=True, fx_enabled=True, sticker_enabled=True,
            caption_enabled=True, caption_srt=srt_file,
            fancy_enabled=True, fancy_text="花字",
            progress_enabled=True,
            intro_enabled=True, intro_text="片头", intro_duration=1.0,
            outro_enabled=True, outro_text="片尾", outro_duration=1.0,
            audio_mode="mix_bgm", audio_file=bgm_file, bgm_volume=0.25)
        p = make_processor(qapp, video_a, video_b, out, tmp_path / "tmp", opts)
        wait_process(p)
        # 4s/1.1 + 2s 包装
        assert probe(out)["duration"] == pytest.approx(4.0 / 1.1 + 2.0, abs=0.25)
