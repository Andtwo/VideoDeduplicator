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

内容策略后台位于 `http://服务器IP:9000/admin/strategies`。生产环境必须配置管理令牌：

```bash
export VD_ADMIN_TOKEN='使用足够长的随机令牌'
uvicorn web.app:app --host 0.0.0.0 --port 9000 --workers 1
```

浏览器首次访问后台时输入该令牌，令牌只保存在当前浏览器会话中。未配置 `VD_ADMIN_TOKEN` 时，后台 API 只允许本机访问。

必须使用一个 Uvicorn worker。任务队列在单进程中执行，任务元数据写入 `uploads/<task_id>/task.json`，服务重启后会恢复排队任务，并将运行中断的任务标记为失败。

## 功能

- 内容视频 A：必填
- 素材视频 B：可选
- 音频文件：可选，仅在随机到 BGM 替换时使用
- 影视名称：可选，显示在输出画面左上角
- 用户端页面不展示处理策略，提交方式保持不变
- 后台可选择固定步骤或从候选步骤中随机至少 3 项
- 策略可保存为同名递增版本，并明确选择当前启用版本
- 每个任务提交时保存策略版本和完整运行快照，后续切换不影响已排队任务
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
VD_ADMIN_TOKEN=...          内容策略后台管理令牌
```

过期任务会自动删除上传文件、临时文件和输出视频。策略版本持久化在 `web_data/strategies.json`，部署备份时需要包含该文件。
