"""视频处理管线：帧混合与编码编排。"""

import os
import sys
import time
import itertools
import subprocess

from PyQt5.QtCore import QThread, pyqtSignal

from media import get_video_info, resize_video
from frame_io import frame_reader
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
        raise ValueError("不支持的帧率！")


class VideoProcessor(QThread):
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, video_a_path, video_b_path, output_path, fps, temp_dir, use_gpu=False,
                 telemetry=None, task_id=None):
        super().__init__()
        self.video_a_path = video_a_path
        self.video_b_path = video_b_path
        self.output_path = output_path
        self.fps = fps
        self.temp_dir = temp_dir
        self.use_gpu = use_gpu
        self.telemetry = telemetry
        self.task_id = task_id

    def run(self):
        start_time = time.time()
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
            width_b, height_b, _, _, _ = get_video_info(self.video_b_path)
            self.status.emit(f"视频B信息: {width_b}x{height_b}")
            if not duration_a or duration_a <= 0:
                raise ValueError("无法获取视频A的有效时长，处理中止。")
            if (width_a, height_a) != (width_b, height_b):
                self.status.emit(f"分辨率不一致，将视频B ({width_b}x{height_b}) 调整为视频A的尺寸 ({width_a}x{height_a})... (t={time.time() - start_time:.2f}s)")
                resize_video(self.video_b_path, temp_b_path, width_a, height_a, self.use_gpu)
                path_b_to_process = temp_b_path
                temp_files_to_clean.append(temp_b_path)
            else:
                self.status.emit("分辨率一致，跳过尺寸调整。")
            self.progress.emit(10)
            total_frames_c = int(duration_a * self.fps)
            self.status.emit(f"目标视频C: {self.fps}fps, 时长与A一致({duration_a:.2f}s), 总帧数: {total_frames_c}")
            self.status.emit(f"准备帧序列混合... (t={time.time() - start_time:.2f}s)")
            positions_a = get_a_positions(self.fps, total_frames_a)
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
            self.status.emit(f"开始混合帧... (t={time.time() - start_time:.2f}s)")
            self.progress.emit(20)
            try:
                reader_a_gen = frame_reader(self.video_a_path, width_a, height_a)
                reader_b_gen = frame_reader(path_b_to_process, width_a, height_a)
                reader_b_cycled = itertools.cycle(reader_b_gen)
                a_frame_counter = 0
                for i in range(total_frames_c):
                    frame_to_write = None
                    try:
                        if i in positions_a and a_frame_counter < total_frames_a:
                            frame_to_write = next(reader_a_gen)
                            a_frame_counter += 1
                        else:
                            frame_to_write = next(reader_b_cycled)
                        writer_process.stdin.write(frame_to_write.tobytes())
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
                if reader_b_gen:
                    reader_b_gen.close()
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
            self.status.emit(f"合并音频... (t={time.time() - start_time:.2f}s)")
            final_cmd = [
                'ffmpeg', '-y', '-i', temp_output_path, '-i', self.video_a_path,
                '-c:v', 'copy', '-c:a', 'aac', '-b:a', '128k', '-shortest', self.output_path
            ]
            subprocess.run(
                final_cmd,
                check=True,
                capture_output=True,
                text=True,
                encoding='utf-8',
                creationflags=creation_flags
            )
            self.progress.emit(100)
            self.status.emit(f"视频处理完成! (总耗时: {time.time() - start_time:.2f}s)")
            self._track_task_success(time.time() - start_time, width_a, height_a, duration_a)
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

    def _track_task_success(self, elapsed, width_a, height_a, duration_a):
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
