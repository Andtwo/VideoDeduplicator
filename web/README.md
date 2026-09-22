# Linux Web 服务版（方案 A）

## 环境

- Python 3.12
- FFmpeg 和 FFprobe 已加入 `PATH`
- 8 核 CPU、16 GB 内存、200-500 GB NVMe

## 安装与启动

```bash
python3 -m venv venv_web
source venv_web/bin/activate
pip install -r requirements-web.txt
uvicorn web.app:app --host 0.0.0.0 --port 9000 --workers 1
```

浏览器打开 `http://服务器IP:9000`。

必须使用一个 Uvicorn worker。任务队列在单进程中执行，任务元数据写入 `uploads/<task_id>/task.json`，服务重启后会恢复排队任务，并将运行中断的任务标记为失败。

## 功能

- 内容视频 A：必填
- 素材视频 B：可选
- 音频文件：可选，仅在随机到 BGM 替换时使用
- 影视名称：可选，显示在输出画面左上角
- 服务端随机生成至少 3 个画面处理步骤
- 镜像时始终覆盖底部原硬字幕区域；OCR 成功时重绘正常方向字幕
- 音频模式：原声、BGM 替换、简单变声
- 真实删帧：每秒随机删除 1-3 帧，音频和 OCR 字幕同步调整

## OCR 模型

PaddleOCR 3.x 只读取以下项目内模型，不会在运行时下载模型：

```text
models/PP-OCRv6_medium_det/
models/PP-OCRv6_medium_rec/
```

部署时必须携带这两个目录。

## 资源限制

可通过环境变量调整：

```text
VD_MAX_UPLOAD_MB=2048       单任务全部上传文件的总大小上限
VD_MAX_PENDING_TASKS=20     等待队列上限
VD_TASK_TTL_HOURS=24        完成或失败任务的保留时间
VD_MIN_FREE_GB=5            接受上传所需的最低磁盘余量
```

过期任务会自动删除上传文件、临时文件和输出视频。
