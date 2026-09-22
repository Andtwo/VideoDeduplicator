"""端到端管线测试：合成视频 -> VideoProcessor -> 输出校验。"""
import os
import subprocess

import cv2
import numpy as np
import pytest

from config import ProcessingOptions
from pipeline import VideoProcessor
from conftest import _make_video, probe


def make_processor(qapp, video_a, video_b, out_path, tmp_dir, options):
    return VideoProcessor(video_a, video_b, str(out_path), 60, str(tmp_dir), options=options)


class TestBasicPipeline:
    def test_mirror_flips_final_output_frame(self, qapp, wait_process, tmp_path):
        src = tmp_path / "split.mp4"
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=red:size=80x80:rate=30:duration=1",
            "-f", "lavfi", "-i", "color=c=blue:size=80x80:rate=30:duration=1",
            "-filter_complex", "[0:v][1:v]hstack=inputs=2[v]",
            "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src)
        ], check=True, capture_output=True)
        out = tmp_path / "mirrored.mp4"
        p = VideoProcessor(str(src), "", str(out), 30, str(tmp_path / "tmp"),
                           options=ProcessingOptions(mirror_enabled=True))
        wait_process(p)
        cap = cv2.VideoCapture(str(out))
        ok, frame = cap.read()
        cap.release()
        assert ok
        left = frame[:, :40].mean(axis=(0, 1))
        right = frame[:, -40:].mean(axis=(0, 1))
        assert left[0] > left[2] + 80   # BGR: 左侧应变成蓝色
        assert right[2] > right[0] + 80  # 右侧应变成红色

    def test_original_audio_keeps_waveform_after_remux(self, qapp, wait_process,
                                                        video_a, tmp_path):
        """原声保留输出应与源音频在解码后保持高相关，避免 AAC remux 相位错位。"""
        out = tmp_path / "original_audio.mp4"
        p = VideoProcessor(video_a, "", str(out), 30, str(tmp_path / "tmp"),
                           options=ProcessingOptions())
        wait_process(p)

        def wav(path, wav_path):
            subprocess.run([
                "ffmpeg", "-y", "-v", "error", "-i", str(path),
                "-vn", "-ac", "1", "-ar", "8000", "-c:a", "pcm_s16le", str(wav_path)
            ], check=True, capture_output=True)
            return np.fromfile(wav_path, dtype=np.int16, offset=44).astype(np.float32)

        src = wav(video_a, tmp_path / "src.wav")
        got = wav(out, tmp_path / "out.wav")
        best = 0.0
        for shift in range(-40, 41):
            if shift >= 0:
                left = src[shift:]
                right = got[:len(left)]
            else:
                right = got[-shift:]
                left = src[:len(right)]
            n = min(len(left), len(right))
            if n < 1000:
                continue
            x = left[:n] - left[:n].mean()
            y = right[:n] - right[:n].mean()
            corr = float(np.dot(x, y) / (np.linalg.norm(x) * np.linalg.norm(y) + 1e-9))
            best = max(best, corr)
        assert best > 0.98

    def test_no_video_b_passthrough(self, qapp, wait_process, video_a, tmp_path):
        """不选素材视频：跳过帧混合，仅按原帧率输出内容视频。"""
        out = tmp_path / "no_b.mp4"
        p = VideoProcessor(video_a, "", str(out), 30, str(tmp_path / "tmp"),
                           options=ProcessingOptions())
        wait_process(p)
        info = probe(out)
        assert info["duration"] == pytest.approx(4.0, abs=0.2)
        assert "video" in info["streams"] and "audio" in info["streams"]

    @pytest.mark.parametrize("source_fps", [24, 60])
    def test_no_video_b_resamples_full_source_timeline(self, qapp, wait_process,
                                                        tmp_path, source_fps):
        src = _make_video(tmp_path / f"source_{source_fps}.mp4", 160, 120, 2.0,
                          fps=source_fps)
        out = tmp_path / f"out_{source_fps}.mp4"
        p = VideoProcessor(src, "", str(out), 30, str(tmp_path / f"tmp_{source_fps}"),
                           options=ProcessingOptions())
        wait_process(p)
        assert probe(out)["duration"] == pytest.approx(2.0, abs=0.12)

    def test_no_video_b_60fps_reaches_source_ending(self, qapp, wait_process, tmp_path):
        src = tmp_path / "source_60_color.mp4"
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=red:size=160x120:rate=60:duration=1",
            "-f", "lavfi", "-i", "color=c=blue:size=160x120:rate=60:duration=1",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]",
            "-map", "[v]", "-map", "2:a", "-c:v", "libx264", "-c:a", "aac",
            "-pix_fmt", "yuv420p", "-shortest", str(src),
        ], check=True, capture_output=True)
        out = tmp_path / "source_60_out.mp4"
        p = VideoProcessor(str(src), "", str(out), 30, str(tmp_path / "tmp_60_color"),
                           options=ProcessingOptions())
        wait_process(p)
        cap = cv2.VideoCapture(str(out))
        cap.set(cv2.CAP_PROP_POS_MSEC, 1750)
        ok, frame = cap.read()
        cap.release()
        assert ok
        assert frame[..., 0].mean() > frame[..., 2].mean() + 80

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

    def test_drop_frames_shortens_video_and_keeps_audio_synced(self, qapp, wait_process,
                                                                 video_a, tmp_path):
        out = tmp_path / "dropped.mp4"
        opts = ProcessingOptions(drop_enabled=True, drop_per_second=3)
        p = VideoProcessor(video_a, "", str(out), 30, str(tmp_path / "tmp"), options=opts)
        wait_process(p)
        info = probe(out)
        assert info["duration"] == pytest.approx(3.6, abs=0.12)
        assert "video" in info["streams"] and "audio" in info["streams"]

    def test_drop_positions_are_distributed_per_second(self, qapp, video_a, tmp_path):
        opts = ProcessingOptions(drop_enabled=True, drop_per_second=2)
        p = VideoProcessor(video_a, "", str(tmp_path / "out.mp4"), 30,
                           str(tmp_path / "tmp"), options=opts)
        positions = p._sample_drop_positions(75, np.random.default_rng(1))
        assert len(positions) == 6
        assert sum(0 <= value < 30 for value in positions) == 2
        assert sum(30 <= value < 60 for value in positions) == 2
        assert sum(60 <= value < 75 for value in positions) == 2

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

    def test_voice_change_keeps_audio_and_duration(self, qapp, wait_process,
                                                    video_a, tmp_path):
        out = tmp_path / "changed_voice.mp4"
        opts = ProcessingOptions(audio_mode="voice_change")
        p = VideoProcessor(video_a, "", str(out), 30, str(tmp_path / "tmp"), options=opts)
        wait_process(p)
        info = probe(out)
        assert "audio" in info["streams"]
        assert info["duration"] == pytest.approx(4.0, abs=0.2)

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

    def test_no_audio_source_with_voice_change_falls_back_to_video(self, qapp, wait_process,
                                                                    video_no_audio, tmp_path):
        out = tmp_path / "silent_voice_change.mp4"
        opts = ProcessingOptions(audio_mode="voice_change")
        p = VideoProcessor(video_no_audio, "", str(out), 30, str(tmp_path / "tmp"), opts)
        wait_process(p)
        info = probe(out)
        assert "audio" not in info["streams"]
        assert info["duration"] == pytest.approx(3.0, abs=0.15)

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
