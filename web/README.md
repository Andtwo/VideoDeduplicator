# Linux Web 服务版（方案 A）

## 启动

```bash
python3 -m venv venv_web
source venv_web/bin/activate
pip install -r requirements.txt paddleocr paddlepaddle fastapi uvicorn python-multipart
uvicorn web.app:app --host 0.0.0.0 --port 8000 --workers 1
```

## 访问

浏览器打开 `http://localhost:8000`

## 功能

- 内容视频 A：必填
- 素材视频 B：可选
- 音频文件：可选（用于 BGM 替换）
- 影视名称：可选（显示在左上角）
- 页面不提供功能选择，服务端随机生成至少 3 个处理步骤
- 随机到镜像时，OCR 提取原视频字幕后压回（方向正常）
- 随机步骤池：缩放 / 镜像 / 滤镜 / 特效 / 贴纸 / 花字 / 进度条 / 压字幕条 / 删帧 / 片头 / 片尾
- 音频随机池：原声 / BGM 替换 / 简单变声
- 删帧：每秒随机删 1-3 帧（真实删除，视频变短）

## 模型

OCR 模型首次使用自动下载到 `models/` 目录。

## 并发

方案 A：8 核 16GB，单 Worker，任务排队。
