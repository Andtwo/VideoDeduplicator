"""帧级读写管道：FFmpeg rawvideo 流式读取。"""

import sys
import subprocess


def frame_reader(video_path, width, height):
    """按帧读取视频，生成 BGR numpy 帧（不做缩放，要求与声明分辨率一致）。"""
    command = [
        'ffmpeg', '-i', video_path,
        '-vf', f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2',
        '-f', 'image2pipe', '-pix_fmt', 'bgr24', '-vcodec', 'rawvideo', '-'
    ]
    creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
    pipe = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        bufsize=width * height * 3 * 10,
        creationflags=creation_flags
    )
    frame_size = width * height * 3
    try:
        while True:
            raw_frame = pipe.stdout.read(frame_size)
            if not raw_frame or len(raw_frame) != frame_size:
                break
            import numpy as np
            frame = np.frombuffer(raw_frame, dtype='uint8').reshape((height, width, 3))
            yield frame
    finally:
        pipe.kill()
        pipe.wait()


def resampled_frame_reader(video_path, width, height, source_fps, target_fps, frame_count):
    """按目标帧率流式重采样，支持丢帧和重复帧且保持完整时间轴。"""
    reader = frame_reader(video_path, width, height)
    current = None
    source_index = -1
    try:
        for output_index in range(frame_count):
            wanted = int(output_index * source_fps / target_fps)
            while source_index < wanted:
                current = next(reader)
                source_index += 1
            if current is None:
                return
            yield current.copy()
    except StopIteration:
        return
    finally:
        reader.close()


def looping_frame_reader(video_path, width, height):
    """循环读取视频，但不缓存解码帧，适合长素材视频。"""
    while True:
        yielded = False
        for frame in frame_reader(video_path, width, height):
            yielded = True
            yield frame
        if not yielded:
            return
