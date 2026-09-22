"""效果管线与素材生成测试。"""
import numpy as np
import pytest

from config import ProcessingOptions
from effects import (EffectPipeline, ZoomCrop, Mirror, ColorFilter,
                     GrainFx, VignetteFx, BloomFx, LeakFx, StickerOverlay,
                     CaptionBar, FancyText, ProgressBarOverlay)

H, W = 240, 320


def make_frame(seed=0):
    rng = np.random.default_rng(seed)
    return rng.integers(0, 255, (H, W, 3), dtype=np.uint8)


class TestPixelEffects:
    def test_all_effects_preserve_shape(self):
        rng = np.random.default_rng(0)
        frame = make_frame()
        effects = [
            ZoomCrop(1.15), Mirror(),
            ColorFilter("warm", 0.10, rng), ColorFilter("mono", 0.10, rng),
            GrainFx(0.12, rng, (H, W)), VignetteFx(0.12, rng, (H, W)),
            BloomFx(0.12, rng, (H, W)), LeakFx(0.12, rng, (H, W)),
            StickerOverlay(rng, W, H),
        ]
        for fx in effects:
            out = fx.apply(frame, 0)
            assert out.shape == (H, W, 3)
            assert out.dtype == np.uint8, type(fx).__name__

    def test_mirror_flips(self):
        frame = make_frame()
        out = Mirror().apply(frame, 0)
        np.testing.assert_array_equal(out, frame[:, ::-1])

    def test_zoom_crops_center(self):
        frame = make_frame()
        out = ZoomCrop(1.2).apply(frame, 0)
        # 放大后形状不变, 中心区域来自原图中心(插值后均值接近)
        assert out.shape == (H, W, 3)
        c_out = out[H // 2 - 5:H // 2 + 5, W // 2 - 5:W // 2 + 5].astype(float)
        c_src = frame[H // 2 - 5:H // 2 + 5, W // 2 - 5:W // 2 + 5].astype(float)
        assert abs(c_out.mean() - c_src.mean()) < 8.0

    def test_identity_when_no_effects(self):
        opts = ProcessingOptions()
        rng = np.random.default_rng(0)
        pipeline = EffectPipeline(opts, rng, W, H, fps=30, content_duration=4.0, speed=1.0)
        assert pipeline.is_identity
        frame = make_frame()
        np.testing.assert_array_equal(pipeline.apply(frame, 0), frame)

    def test_pipeline_all_effects(self):
        opts = ProcessingOptions(
            speed_enabled=True, zoom_enabled=True, mirror_enabled=True,
            filter_enabled=True, fx_enabled=True, sticker_enabled=True,
            caption_enabled=True, caption_text="测试",
            fancy_enabled=True, fancy_text="花")
        rng = np.random.default_rng(1)
        pipeline = EffectPipeline(opts, rng, W, H, fps=30, content_duration=4.0, speed=1.1)
        assert not pipeline.is_identity
        frame = make_frame()
        for idx in (0, 30, 90):
            out = pipeline.apply(frame, idx)
            assert out.shape == (H, W, 3)

    def test_pipeline_applies_mirror_to_video_frame(self):
        opts = ProcessingOptions(mirror_enabled=True)
        pipeline = EffectPipeline(opts, np.random.default_rng(0), W, H,
                                  fps=30, content_duration=4.0, speed=1.0)
        frame = make_frame()
        np.testing.assert_array_equal(pipeline.apply(frame, 0), frame[:, ::-1])


class TestBrandingOverlays:
    def test_caption_bar_shows_and_hides(self):
        bar = CaptionBar([(0.0, 2.0, "hello")], W, H, fps=30)
        frame = make_frame()
        # 字幕时间窗内：底部区域被压暗
        shown = bar.apply(frame, 30)   # t=1.0
        hidden = bar.apply(frame, 90)  # t=3.0
        assert shown[H - 40:].mean() < frame[H - 40:].mean()
        np.testing.assert_array_equal(hidden, frame)

    def test_fancy_text_draws(self):
        fancy = FancyText("标题", np.random.default_rng(0), W, H)
        frame = make_frame(3)
        out = fancy.apply(frame, 0)
        assert out[: H // 4].mean() != frame[: H // 4].mean()

    def test_progress_bar_fill(self):
        pb = ProgressBarOverlay(W, H)
        frame = np.full((H, W, 3), 60, dtype=np.uint8)  # 纯灰帧: 轨道≈33, 填充G=144
        half = pb.apply(frame, 0.5)
        row = half[pb.track_y:pb.track_y + pb.bar_h].astype(int)
        g = row[:, :, 1].mean(axis=0)
        filled = np.where(g > 110)[0]
        assert len(filled) > 0
        assert filled.max() / W == pytest.approx(0.5, abs=0.05)
        assert g[:10].mean() > 120
        assert g[-10:].mean() < 60


class TestAssets:
    def test_parse_srt(self, srt_file):
        from assets import parse_srt
        entries = parse_srt(srt_file)
        assert entries == [(0.5, 2.0, "第一条字幕"), (2.0, 4.0, "第二条字幕")]

    def test_sticker_cache(self):
        from assets import get_sticker, STICKER_KINDS
        img = get_sticker(STICKER_KINDS[0], 64)
        assert img.size[0] == 64
        img2 = get_sticker(STICKER_KINDS[0], 64)
        assert img2.size[0] == 64

    def test_find_font(self):
        from assets import find_font
        path = find_font()
        assert path is None or isinstance(path, str)


class TestBranding:
    def test_intro_frames(self):
        from branding import intro_frames
        rng = np.random.default_rng(0)
        frames = list(intro_frames(W, H, 30, 1.0, "标题", rng))
        assert len(frames) == 30
        for f in frames:
            assert f.shape == (H, W, 3)
            assert f.dtype == np.uint8

    def test_outro_frames(self):
        from branding import outro_frames
        rng = np.random.default_rng(0)
        frames = list(outro_frames(W, H, 30, 0.5, "", rng))
        assert len(frames) == 15

    def test_title_horizontally_centered(self):
        """标题文本应水平居中（回归: 曾被绘制在左边缘）。"""
        from branding import intro_frames
        rng = np.random.default_rng(0)
        frames = list(intro_frames(W, H, 30, 1.0, "片头", rng))
        f = frames[-1]  # 淡入完成后 alpha=1
        region = f[int(H * 0.38):int(H * 0.58)]
        bright_cols = np.where((region > 200).any(axis=(0, 2)))[0]
        assert len(bright_cols) > 0, "未检测到标题文本"
        center = (bright_cols.min() + bright_cols.max()) / 2
        assert abs(center - W / 2) < W * 0.1, f"标题未居中: 中点 {center:.0f}, 画面中心 {W // 2}"
