"""视频处理管线：帧混合、后期效果与编码编排。

处理流程：
  1. 媒体探测与分辨率对齐
  2. 高帧率帧混合（核心算法不变）
  3. 逐帧后期效果（缩放/镜像/滤镜/特效/贴纸）
  4. 变速筛选（帧级跳帧，音画同步由 atempo 保证）
  5. 音轨合成（原声变速 / BGM / 配音）
"""

import os
import sys
import time
import subprocess

import numpy as np

from PyQt5.QtCore import QThread, pyqtSignal

from media import get_video_info, resize_video, has_audio_stream
from frame_io import frame_reader, looping_frame_reader, resampled_frame_reader
from config import ProcessingOptions
from effects import EffectPipeline, ProgressBarOverlay
from branding import intro_frames, outro_frames
from telemetry import events as telemetry_events


def get_a_positions(fps, N_a):
    """计算视频A帧在高帧率输出流中的插入位置。"""
    if fps == 60:
        return {m if m <= 2 else 2 + 2 * (m - 2) for m in range(N_a)}
    elif fps == 120:
        return {m if m <= 1 else 1 + 4 * (m - 1) for m in range(N_a)}
    elif fps == 240:
        if N_a == 0:
            return set()
        if N_a <= 2:
            return set(range(N_a))
        positions = {0, 1}
        next_pos = 1
        intervals = [8, 9, 7]
        for i in range(2, N_a):
            next_pos += intervals[(i - 2) % 3]
            positions.add(next_pos)
        return positions
    else:
        # 无素材混合时按内容视频原帧率输出
        return set(range(N_a))


def run_ffmpeg(cmd_list, log_path=None):
    """执行 FFmpeg 命令，失败时抛出带日志尾部的异常。"""
    creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
    if log_path:
        with open(log_path, "wb") as log_f:
            result = subprocess.run(cmd_list, stdout=subprocess.DEVNULL, stderr=log_f,
                                    creationflags=creation_flags)
        if result.returncode != 0:
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                log_tail = f.read()[-2000:]
            raise RuntimeError(f"FFmpeg执行失败: {log_tail}")
    else:
        result = subprocess.run(cmd_list, capture_output=True, text=True,
                                encoding='utf-8', creationflags=creation_flags)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg执行失败：\n{result.stderr[-2000:]}")


class VideoProcessor(QThread):
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, video_a_path, video_b_path, output_path, fps, temp_dir,
                 options=None, use_gpu=False, telemetry=None, task_id=None):
        super().__init__()
        self.video_a_path = video_a_path
        self.video_b_path = video_b_path
        self.output_path = output_path
        self.fps = fps
        self.temp_dir = temp_dir
        self.options = options or ProcessingOptions()
        self.use_gpu = use_gpu
        self.telemetry = telemetry
        self.task_id = task_id

    def run(self):
        start_time = time.time()
        rng = np.random.default_rng()
        writer_process = None
        writer_stderr = None
        width_a = height_a = 0
        duration_a = 0.0
        temp_b_path = os.path.join(self.temp_dir, "resized_b.mp4")
        temp_output_path = os.path.join(self.temp_dir, "temp_output.mp4")
        writer_log_path = os.path.join(self.temp_dir, "ffmpeg_writer.log")
        path_b_to_process = self.video_b_path
        temp_files_to_clean = [temp_output_path, writer_log_path]
        reader_a_gen = None
        reader_b_gen = None
        try:
            if not os.path.exists(self.temp_dir):
                os.makedirs(self.temp_dir)
            self.status.emit(f"开始处理，检查视频信息... (t={time.time() - start_time:.2f}s)")
            self.progress.emit(5)
            width_a, height_a, fps_a, duration_a, total_frames_a = get_video_info(self.video_a_path)
            self.status.emit(f"视频A信息: {width_a}x{height_a}, {fps_a:.2f}fps, {duration_a:.2f}s, {total_frames_a}帧")
            has_b = bool(self.video_b_path)
            if has_b:
                width_b, height_b, _, _, _ = get_video_info(self.video_b_path)
                self.status.emit(f"视频B信息: {width_b}x{height_b}")
                if (width_a, height_a) != (width_b, height_b):
                    self.status.emit(f"分辨率不一致，将视频B ({width_b}x{height_b}) 调整为视频A的尺寸 ({width_a}x{height_a})... (t={time.time() - start_time:.2f}s)")
                    resize_video(self.video_b_path, temp_b_path, width_a, height_a, self.use_gpu)
                    path_b_to_process = temp_b_path
                    temp_files_to_clean.append(temp_b_path)
                else:
                    self.status.emit("分辨率一致，跳过尺寸调整。")
            else:
                self.status.emit("未选择素材视频，跳过帧混合，仅应用后期效果。")
            if not duration_a or duration_a <= 0:
                raise ValueError("无法获取视频A的有效时长，处理中止。")
            self.progress.emit(10)

            # 确定本条视频的随机参数（任务内保持一致）
            randoms = self.options.sample_randoms(rng)
            speed = randoms["speed"]
            content_duration = duration_a / speed
            total_frames_c = int(round(duration_a * self.fps))
            total_out_frames = int(round(total_frames_c / speed))
            drop_positions = self._sample_drop_positions(total_out_frames, rng)
            kept_content_frames = total_out_frames - len(drop_positions)
            self.options.caption_time_map = self._build_caption_time_map(
                total_out_frames, drop_positions, speed)
            effect_pipeline = EffectPipeline(
                self.options, rng, width_a, height_a,
                fps=self.fps,
                content_duration=kept_content_frames / self.fps,
                speed=speed,
                zoom_scale=randoms["zoom"],
            )
            self._report_params(effect_pipeline, speed, randoms["zoom"])
            intro_n = int(round(self.options.intro_duration * self.fps)) if self.options.intro_enabled else 0
            outro_n = int(round(self.options.outro_duration * self.fps)) if self.options.outro_enabled else 0
            progress_overlay = (ProgressBarOverlay(width_a, height_a)
                                if self.options.progress_enabled else None)
            total_final_frames = intro_n + kept_content_frames + outro_n
            total_final_duration = total_final_frames / self.fps
            drop_summary = f", 删帧 {len(drop_positions)} 帧" if drop_positions else ""
            self.status.emit(f"目标视频C: {self.fps}fps, 总帧数: {total_frames_c} -> 输出 {kept_content_frames} 帧{drop_summary}"
                             + (f" (含片头 {intro_n} + 片尾 {outro_n} 帧, 总时长 {total_final_duration:.2f}s)"
                                if intro_n or outro_n else f" (时长 {kept_content_frames / self.fps:.2f}s)"))
            self.status.emit(f"准备帧序列混合... (t={time.time() - start_time:.2f}s)")
            positions_a = get_a_positions(self.fps, total_frames_a) if has_b else set(range(total_frames_c))
            encoder = 'h264_nvenc' if self.use_gpu else 'libx264'
            quality_param = '-preset p6' if self.use_gpu else '-crf 23'
            writer_cmd = [
                'ffmpeg', '-y', '-f', 'rawvideo', '-vcodec', 'rawvideo',
                '-pix_fmt', 'bgr24', '-s', f'{width_a}x{height_a}', '-r', str(self.fps),
                '-i', '-', '-c:v', encoder
            ]
            writer_cmd.extend(quality_param.split())
            writer_cmd.extend(['-pix_fmt', 'yuv420p', temp_output_path])
            creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            # stderr 写入日志文件：避免长视频时 stderr 管道缓冲区写满导致互相死锁
            writer_stderr = open(writer_log_path, "wb")
            writer_process = subprocess.Popen(
                writer_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=writer_stderr,
                creationflags=creation_flags
            )
            self.status.emit(("开始混合帧..." if has_b else "开始逐帧处理...") + f" (t={time.time() - start_time:.2f}s)")
            self.progress.emit(20)
            # 片头帧直接写入编码管道（与主视频同参数，无需 concat）
            if intro_n:
                self.status.emit(f"写入片头 {intro_n} 帧...")
                for k, frame in enumerate(intro_frames(width_a, height_a, self.fps,
                                                       self.options.intro_duration, self.options.intro_text, rng)):
                    if progress_overlay is not None:
                        frame = progress_overlay.apply(frame, k / max(1, total_final_frames - 1))
                    frame = self._postprocess_frame(frame)
                    writer_process.stdin.write(frame.tobytes())
            try:
                if has_b:
                    reader_a_gen = frame_reader(self.video_a_path, width_a, height_a)
                else:
                    reader_a_gen = resampled_frame_reader(
                        self.video_a_path, width_a, height_a,
                        fps_a, self.fps, total_frames_c)
                if has_b:
                    reader_b_gen = looping_frame_reader(path_b_to_process, width_a, height_a)
                else:
                    reader_b_gen = None
                a_frame_counter = 0
                last_j = -1
                written_frames = 0
                candidate_frame = 0
                global_j = float(intro_n)
                for i in range(total_frames_c):
                    frame_to_write = None
                    try:
                        if i in positions_a and a_frame_counter < total_frames_a:
                            frame_to_write = next(reader_a_gen)
                            a_frame_counter += 1
                        elif reader_b_gen is not None:
                            frame_to_write = next(reader_b_gen)
                        else:
                            # 无素材混合：直接按序读取内容视频帧
                            frame_to_write = next(reader_a_gen)
                        # 变速筛选：输出帧 j = floor(i / speed)，j 前进才写入
                        if speed > 1.001:
                            j = int(i / speed)
                            if j <= last_j:
                                continue
                            last_j = j
                        current_candidate = candidate_frame
                        candidate_frame += 1
                        if current_candidate in drop_positions:
                            continue
                        if not effect_pipeline.is_identity:
                            frame_to_write = effect_pipeline.apply(frame_to_write, written_frames)
                        if progress_overlay is not None:
                            progress = global_j / max(1, total_final_frames - 1)
                            frame_to_write = progress_overlay.apply(frame_to_write, progress)
                        frame_to_write = self._postprocess_frame(frame_to_write)
                        writer_process.stdin.write(frame_to_write.tobytes())
                        written_frames += 1
                        global_j += 1
                        if (i + 1) % 50 == 0 or (i + 1) == total_frames_c:
                            progress = 20 + int(70 * (i + 1) / total_frames_c)
                            self.progress.emit(min(progress, 89))
                            self.status.emit(f"处理帧: {i + 1} / {total_frames_c} (t={time.time() - start_time:.2f}s)")
                    except StopIteration:
                        self.status.emit(f"警告: 视频流在第 {i} 帧提前结束。")
                        break
            finally:
                if reader_a_gen:
                    reader_a_gen.close()
                if reader_b_gen is not None:
                    reader_b_gen.close()
            # 片尾帧
            if outro_n:
                self.status.emit(f"写入片尾 {outro_n} 帧...")
                outro_start = intro_n + written_frames
                for k, frame in enumerate(outro_frames(width_a, height_a, self.fps,
                                                       self.options.outro_duration, self.options.outro_text, rng)):
                    if progress_overlay is not None:
                        frame = progress_overlay.apply(frame, (outro_start + k) / max(1, total_final_frames - 1))
                    frame = self._postprocess_frame(frame)
                    writer_process.stdin.write(frame.tobytes())
            self.status.emit(f"混合完成，正在生成最终视频文件... (t={time.time() - start_time:.2f}s)")
            writer_process.stdin.close()
            writer_process.stdin = None  # 避免 wait/communicate 对已关闭 stdin 再次 flush
            writer_process.wait()
            writer_stderr.close()
            if writer_process.returncode != 0:
                with open(writer_log_path, "r", encoding="utf-8", errors="ignore") as f:
                    log_tail = f.read()[-2000:]
                raise RuntimeError(f"FFmpeg写入视频失败: {log_tail}")
            self.progress.emit(90)
            self.status.emit(f"处理音轨... (t={time.time() - start_time:.2f}s)")
            final_duration = (intro_n + written_frames + outro_n) / self.fps
            intro_ms = int(round(intro_n / self.fps * 1000))
            keep_ratio = written_frames / max(1, candidate_frame)
            audio_speed = speed / max(keep_ratio, 1e-6)
            self._compose_audio(temp_output_path, self.output_path, audio_speed, final_duration,
                                intro_ms, os.path.join(self.temp_dir, "ffmpeg_audio.log"))
            temp_files_to_clean.append(os.path.join(self.temp_dir, "temp_voice.wav"))
            self.progress.emit(100)
            self.status.emit(f"视频处理完成! (总耗时: {time.time() - start_time:.2f}s)")
            self._track_task_success(time.time() - start_time, width_a, height_a,
                                     duration_a, final_duration)
            self.finished.emit()
        except Exception as e:
            import traceback
            self._track_task_failed(e)
            self.error.emit(f"错误：{str(e)}\n{traceback.format_exc()}")
        finally:
            if writer_process and writer_process.poll() is None:
                writer_process.kill()
                writer_process.wait()
            if writer_stderr and not writer_stderr.closed:
                writer_stderr.close()
            for f in temp_files_to_clean:
                if os.path.exists(f):
                    try:
                        os.remove(f)
                    except OSError as e:
                        self.status.emit(f"无法删除临时文件 {f}: {e}")

    def _sample_drop_positions(self, frame_count, rng):
        """按输出时间轴每秒随机选择要真实删除的帧。"""
        if not self.options.drop_enabled or self.options.drop_per_second <= 0:
            return set()
        positions = set()
        for start in range(0, frame_count, self.fps):
            end = min(start + self.fps, frame_count)
            count = min(self.options.drop_per_second, max(0, end - start - 1))
            if count:
                picks = rng.choice(np.arange(start, end), size=count, replace=False)
                positions.update(int(value) for value in picks)
        return positions

    def _build_caption_time_map(self, frame_count, drop_positions, speed):
        """构建输出时间到原视频时间的映射，供 OCR 字幕同步使用。"""
        mapping = []
        output_index = 0
        for candidate in range(frame_count):
            if candidate in drop_positions:
                continue
            source_time = candidate * speed / self.fps
            mapping.append((output_index / self.fps, source_time))
            output_index += 1
        return mapping

    def _postprocess_frame(self, frame):
        """供 Web 等前端添加最终叠加层；桌面处理默认保持原帧。"""
        return frame

    def _report_params(self, effect_pipeline, speed, zoom):
        """日志输出本条视频实际采样的参数。"""
        parts = []
        if self.options.speed_enabled:
            parts.append(f"变速 {speed:.3f}x")
        if self.options.zoom_enabled:
            parts.append(f"放大 {zoom * 100:.0f}%")
        if self.options.mirror_enabled:
            parts.append("镜像")
        if self.options.filter_enabled:
            parts.append(f"滤镜[{effect_pipeline.filter_style}] {self.options.filter_strength * 100:.0f}%")
        if self.options.fx_enabled:
            parts.append(f"特效[{effect_pipeline.fx_style}] {self.options.fx_strength * 100:.0f}%")
        if self.options.sticker_enabled:
            parts.append("四角贴纸")
        if self.options.caption_enabled:
            parts.append("字幕条")
        if self.options.fancy_enabled:
            parts.append("花字")
        if self.options.progress_enabled:
            parts.append("进度条")
        if self.options.drop_enabled:
            parts.append(f"每秒删帧 {self.options.drop_per_second}")
        if self.options.intro_enabled:
            parts.append(f"片头{self.options.intro_duration:.1f}s")
        if self.options.outro_enabled:
            parts.append(f"片尾{self.options.outro_duration:.1f}s")
        if self.options.audio_mode == "replace_bgm":
            parts.append("BGM替换")
        elif self.options.audio_mode == "mix_bgm":
            parts.append("BGM混音")
        elif self.options.audio_mode == "replace_voice":
            parts.append("配音替换")
        elif self.options.audio_mode == "voice_change":
            parts.append("简单变声")
        if parts:
            self.status.emit("后期参数: " + ", ".join(parts))
        else:
            self.status.emit("后期处理未启用，仅帧混合。")

    def _compose_audio(self, temp_output_path, output_path, speed, total_duration,
                       intro_ms, audio_log_path):
        """音轨合成：变速 atempo、BGM 替换/混音、配音替换，片头片尾静音对齐。

        统一输出立体声 44100Hz AAC，时长对齐 total_duration。
        """
        opts = self.options
        mode = opts.audio_mode
        has_voice = has_audio_stream(self.video_a_path)

        # 原声处理链：统一立体声 + 变速 + 片头静音。
        # 注意: ffmpeg 8.x 中 atempo+adelay 链式组合会产生损坏的输出，
        # 片头静音改用 aevalsrc 静音源 + concat 滤镜实现
        def voice_chain():
            parts = ["aformat=channel_layouts=stereo", "aresample=44100"]
            tempo = speed
            if mode == "voice_change":
                pitch = 1.08
                parts.extend([f"asetrate={int(44100 * pitch)}", "aresample=44100"])
                tempo /= pitch
            if abs(tempo - 1.0) > 0.001:
                parts.append(f"atempo={tempo:.4f}")
            if intro_ms > 0:
                intro_sec = intro_ms / 1000.0
                voice = "[0:a]" + ",".join(parts) + "[v]"
                # 静音前缀 + 尾部 apad（靠 -t 截断对齐总时长）
                return (f"aevalsrc=0|0:d={intro_sec:.3f}:s=44100[sl];"
                        f"{voice};[sl][v]concat=n=2:v=0:a=1,apad[a0]"), "[a0]"
            return "[0:a]" + ",".join(parts + ["apad"]) + "[v]", "[v]"

        temp_audio = os.path.join(self.temp_dir, "temp_audio.m4a")

        if mode in ("original", "voice_change") and not has_voice:
            # 无原声：简单变声无法执行，降级为纯视频输出。
            self.status.emit("视频A无音轨，输出纯视频。")
            run_ffmpeg(['ffmpeg', '-y', '-i', temp_output_path, '-c', 'copy', output_path],
                       audio_log_path)
            return

        if mode == "replace_voice":
            if not opts.audio_file or not os.path.exists(opts.audio_file):
                raise ValueError(f"配音模式需要有效的音频文件: {opts.audio_file or '（未选择）'}")
            self.status.emit(f"使用配音替换原声: {os.path.basename(opts.audio_file)}")
            if intro_ms > 0:
                intro_sec = intro_ms / 1000.0
                graph = (f"aevalsrc=0|0:d={intro_sec:.3f}:s=44100[sl];"
                         f"[0:a]aformat=channel_layouts=stereo,aresample=44100[v];"
                         f"[sl][v]concat=n=2:v=0:a=1,apad[a]")
                out_label = "[a]"
            else:
                graph = "[0:a]aformat=channel_layouts=stereo,aresample=44100,apad[a]"
                out_label = "[a]"
            run_ffmpeg([
                'ffmpeg', '-y', '-i', opts.audio_file,
                '-filter_complex', graph,
                '-map', out_label, '-t', f'{total_duration:.3f}',
                '-c:a', 'aac', '-b:a', '128k', '-ar', '44100', temp_audio
            ], audio_log_path)
        elif mode == "replace_bgm" or (mode == "mix_bgm" and not has_voice):
            if not opts.audio_file or not os.path.exists(opts.audio_file):
                raise ValueError(f"当前音频模式需要有效的音频文件: {opts.audio_file or '（未选择）'}")
            if mode == "mix_bgm" and not has_voice:
                self.status.emit("视频A无音轨，混音模式降级为 BGM 替换。")
            else:
                self.status.emit(f"使用 BGM 替换原声: {os.path.basename(opts.audio_file)}")
            run_ffmpeg([
                'ffmpeg', '-y', '-stream_loop', '-1', '-i', opts.audio_file,
                '-filter_complex', f"[0:a]aformat=channel_layouts=stereo,aresample=44100,volume={opts.bgm_volume:.2f}[a]",
                '-map', '[a]', '-t', f'{total_duration:.3f}',
                '-c:a', 'aac', '-b:a', '128k', '-ar', '44100', temp_audio
            ], audio_log_path)
        elif mode == "mix_bgm":
            if not opts.audio_file or not os.path.exists(opts.audio_file):
                raise ValueError(f"当前音频模式需要有效的音频文件: {opts.audio_file or '（未选择）'}")
            self.status.emit(f"原声与 BGM 混音（BGM 音量 {opts.bgm_volume:.0%}）: {os.path.basename(opts.audio_file)}")
            voice_graph, voice_label = voice_chain()
            run_ffmpeg([
                'ffmpeg', '-y', '-i', self.video_a_path, '-stream_loop', '-1', '-i', opts.audio_file,
                '-filter_complex',
                voice_graph + f";[1:a]aformat=channel_layouts=stereo,aresample=44100,volume={opts.bgm_volume:.2f}[a1];"
                f"{voice_label}[a1]amix=inputs=2:duration=longest:normalize=0[aout]",
                '-map', '[aout]', '-t', f'{total_duration:.3f}',
                '-c:a', 'aac', '-b:a', '128k', '-ar', '44100', temp_audio
            ], audio_log_path)
        else:
            # original：保留原声（变速 + 片头静音 + 尾部补齐）
            voice_graph, voice_label = voice_chain()
            # 先将原声转成 PCM WAV，再在中间域编码 AAC。
            # FFmpeg 8 对 AAC 首帧 priming 很敏感：如果直接从 AAC 输入解码并编码后再与视频 remux，
            # 部分播放器/二次解码器会把 priming 样本计入波形，听感上表现为相位错乱。
            temp_voice = os.path.join(self.temp_dir, "temp_voice.wav")
            run_ffmpeg([
                'ffmpeg', '-y', '-i', self.video_a_path,
                '-filter_complex', voice_graph,
                '-map', voice_label, '-t', f'{total_duration:.3f}',
                '-c:a', 'pcm_s16le', '-ar', '44100', temp_voice
            ], audio_log_path)
            run_ffmpeg([
                'ffmpeg', '-y', '-i', temp_voice,
                '-c:a', 'aac', '-b:a', '128k', '-ar', '44100', temp_audio
            ], audio_log_path)
            try:
                os.remove(temp_voice)
            except OSError:
                pass

        # 不用 -shortest：amix 产出的音轨时长元数据可能为 N/A，
        # ffmpeg 7 下 copy 模式 -shortest 会直接产出空文件；改用 -t 对齐两流
        run_ffmpeg([
            'ffmpeg', '-y', '-i', temp_output_path, '-i', temp_audio,
            '-map', '0:v', '-map', '1:a', '-c', 'copy',
            '-t', f'{total_duration:.3f}', output_path
        ], audio_log_path)
        try:
            os.remove(temp_audio)
        except OSError:
            pass

    def _track_task_success(self, elapsed, width_a, height_a, duration_a, out_duration):
        if not self.telemetry:
            return
        self.telemetry.track(telemetry_events.EVENT_TASK_SUCCESS, {
            "task_id": self.task_id,
            "fps": self.fps,
            "use_gpu": self.use_gpu,
            "resolution_bucket": telemetry_events.resolution_bucket(width_a, height_a),
            "duration_bucket": telemetry_events.duration_bucket(duration_a),
            "processing_seconds_bucket": telemetry_events.processing_seconds_bucket(elapsed),
        })

    def _track_task_failed(self, exc):
        if not self.telemetry:
            return
        error_type, error_stage = telemetry_events.classify_error(exc, self.use_gpu)
        self.telemetry.track(telemetry_events.EVENT_TASK_FAILED, {
            "task_id": self.task_id,
            "fps": self.fps,
            "use_gpu": self.use_gpu,
            "error_type": error_type,
            "error_stage": error_stage,
        })
