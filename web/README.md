# Linux Web 服务版（方案 A）

## 环境

- Python 3.12
- FFmpeg 和 FFprobe 已加入 `PATH`
- 中文字体（用于影视名称、片头片尾和花字渲染）
- 8 核 CPU、16 GB 内存、200-500 GB NVMe

## 安装与启动

```bash
python3 -m venv venv_web
source venv_web/bin/activate
pip install -r requirements-web.txt
uvicorn web.app:app --host 0.0.0.0 --port 9000 --workers 1
```

浏览器打开 `http://服务器IP:9000`。

### 中文字体（必须安装）

影视名称、片头片尾标题和花字由 Pillow 在服务端渲染。Linux 服务器如果没有中文字体，文字会显示为方框。生产部署前必须安装中文字体；以 TencentOS / RHEL 系为例：

```bash
dnf install -y google-noto-sans-cjk-ttc-fonts
fc-cache -f -v
fc-list :lang=zh | head
```

应能看到 `NotoSansCJK` 字体路径。部署检查时还应确认项目字体查找函数能找到字体：

```bash
venv_web/bin/python -c 'import sys; sys.path.insert(0, "src"); from assets import find_font; print(find_font()); assert find_font()'
```

如果软件安装在 `/opt/VideoDeduplicator`，对应命令为：

```bash
/opt/VideoDeduplicator/venv_web/bin/python -c 'import sys; sys.path.insert(0, "/opt/VideoDeduplicator/src"); from assets import find_font; print(find_font()); assert find_font()'
```

字体安装完成后重启服务，使运行中的 worker 使用新的字体：

```bash
systemctl restart videodeduplicator.service
systemctl is-active videodeduplicator.service
```

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
- 影视名称：必填，显示在输出画面左上角
- 用户端页面不展示处理策略，提交方式保持不变
- 后台可选择固定步骤或从候选步骤中随机至少 3 项
- 策略可保存为同名递增版本，并明确选择当前启用版本
- 每个任务提交时保存策略版本和完整运行快照，后续切换不影响已排队任务
- 镜像时始终覆盖底部原硬字幕区域；OCR 成功时重绘正常方向字幕
- 音频模式：原声、BGM 替换、简单变声
- 真实删帧：每秒随机删除 1-3 帧，音频和 OCR 字幕同步调整

## 部署前检查清单

部署到新服务器前确认：

- [ ] FFmpeg 支持 `libx264`，且服务进程实际使用的是该版本
- [ ] 已安装中文字体，并且 `find_font()` 返回有效字体路径
- [ ] 已携带 `models/PP-OCRv6_medium_det/` 和 `models/PP-OCRv6_medium_rec/`
- [ ] Uvicorn 使用单 worker：`--workers 1`
- [ ] 已配置生产环境 `VD_ADMIN_TOKEN`
- [ ] 用户端提交一个带中文影视名称的短视频，确认左上角文字不是方框

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
