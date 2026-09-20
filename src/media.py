"""媒体信息探测与分辨率对齐。"""

import os
import sys
import cv2
import ffmpeg
import subprocess


def get_video_info(video_path):
    """读取视频基础信息，返回 (width, height, fps, duration, total_frames)。"""
    try:
        probe = ffmpeg.probe(video_path, cmd='ffprobe')
        video_stream = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)
        if not video_stream:
            raise ValueError("未找到视频流")
        width = int(video_stream['width'])
        height = int(video_stream['height'])
        r_frame_rate = video_stream.get('r_frame_rate', '0/1')
        if '/' in r_frame_rate:
            num, den = map(int, r_frame_rate.split('/'))
            fps = num / den if den > 0 else 0
        else:
            fps = float(r_frame_rate)
        duration_str = video_stream.get('duration')
        if duration_str:
            duration = float(duration_str)
        else:
            duration = float(probe.get('format', {}).get('duration', 0))
        total_frames_str = video_stream.get('nb_frames', '0')
        if total_frames_str != '0' and total_frames_str.isdigit():
            total_frames = int(total_frames_str)
        else:
            if duration > 0 and fps > 0:
                total_frames = int(duration * fps)
            else:
                cap = cv2.VideoCapture(video_path)
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                cap.release()
        if fps == 0 or total_frames == 0 or duration == 0:
            raise ValueError("视频元数据不完整或无效 (fps/duration/frames is zero)")
        return width, height, fps, duration, total_frames
    except Exception as e:
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                raise ValueError(f"无法打开视频文件: {video_path}")
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = total_frames / fps if fps > 0 else 0
            cap.release()
            if fps == 0 or total_frames == 0:
                raise ValueError("OpenCV无法获取有效的视频信息")
            return width, height, fps, duration, total_frames
        except Exception as cv_e:
            raise RuntimeError(f"无法获取视频信息 {video_path}: FFmpeg错误: {e}, OpenCV回退错误: {cv_e}")


def has_audio_stream(video_path):
    """判断文件是否包含音频流。"""
    try:
        probe = ffmpeg.probe(video_path, cmd='ffprobe')
        return any(stream.get('codec_type') == 'audio' for stream in probe.get('streams', []))
    except Exception:
        return False


def resize_video(input_path, output_path, width, height, use_gpu=False):
    """将视频缩放并填充到目标分辨率。"""
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"输入视频文件 {input_path} 不存在！")
    encoder = 'h264_nvenc' if use_gpu else 'libx264'
    quality_param = '-preset p6' if use_gpu else '-crf 23'
    cmd_list = [
        'ffmpeg', '-y', '-i', input_path,
        '-vf', f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2',
        '-c:v', encoder,
    ]
    cmd_list.extend(quality_param.split())
    cmd_list.extend(['-c:a', 'aac', '-b:a', '128k', output_path])
    try:
        creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        result = subprocess.run(
            cmd_list,
            check=True,
            capture_output=True,
            text=True,
            encoding='utf-8',
            creationflags=creation_flags
        )
        if not os.path.exists(output_path):
            raise RuntimeError(f"FFmpeg未能创建输出文件 {output_path}")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"FFmpeg处理失败：\nSTDOUT: {e.stdout}\nSTDERR: {e.stderr}")
