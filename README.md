# AB Video Processor

[简体中文](./README.md) | [English](./README_en.md)

用于视频帧混合、格式转换与视觉特征实验的桌面工具。

项目通过对两段视频进行抽帧、混合与重新编码，研究不同帧率、编码参数和 GPU 加速方案对输出视频视觉表现及数据特征的影响。仓库名 `AB-Video-Deduplicator` 为项目早期命名，现以 AB Video Processor 名义维护。

> 请仅处理拥有合法使用权的素材。本项目为早期实验版本，仅供技术研究与学习交流，不用于绕过平台审核、版权识别或其他安全机制。

## 项目背景

在视频处理和内容生产流程中，经常需要验证不同帧率、分辨率、混合策略和编码方式对输出结果的影响。手工执行 FFmpeg 命令不利于非技术用户重复调整和比较参数。

本项目将相关处理流程封装为图形化工具，提供可重复的参数配置与进度反馈，让同一组实验可以在不同素材上快速复现。

## 主要能力

- 读取两段视频并分析基础媒体信息（分辨率、帧率、时长、编码格式）
- 按配置进行抽帧与帧混合，提供 50%（60fps）、75%（120fps）、87.5%（240fps）三档处理强度
- 自动将素材视频的分辨率对齐到内容视频，统一帧率与编码参数
- **后期效果管线**（可选启用，支持随机参数区间，逐任务抽取）：
  - 变速（1.05 ~ 1.2 倍速，音画同步 atempo）
  - 中心裁剪缩放（画面放大 110% ~ 120%）
  - 水平镜像翻转
  - 滤镜（暖色 / 冷色 / 复古 / 黑白 / 提亮，默认 10% 低强度）
  - 画面特效（胶片颗粒 / 暗角 / 泛光 / 漏光，低强度）
  - 四角贴纸（程序化生成的装饰贴纸，位置与角度随机）
- **包装能力**：字幕条（多行文本或 SRT）、花字、全片进度条、片头片尾（标题动画，同管道单次编码）
- **音频处理**：保留原声 / BGM 替换 / 原声与 BGM 混音 / 外部配音替换，自动处理变速同步与片头片尾静音对齐
- 在兼容环境下启用 NVIDIA NVENC 硬件编码加速，大幅提升处理速度
- 基于 PyQt5 的图形界面，无需命令行知识，实时展示处理进度与详细日志
- 跨平台运行（Windows / macOS / Linux，需正确安装依赖）

## 📸 软件截图

<p align="center">
  <a href="https://www.bilibili.com/video/BV1HwgrzbEow" target="_blank">
    <img src="./assets/cover_demo.png" alt="演示视频封面" width="800"/>
  </a>
  <br>
  <em>处理流程演示（点击封面跳转 B 站观看演示视频）</em>
</p>

<p align="center">
  <img src="./assets/cover_software.png" alt="软件主界面" width="800"/>
  <br>
  <em>软件主界面</em>
</p>

## 技术流程

```text
Video A + Video B
    -> Media inspection
    -> Resolution alignment
    -> Frame sampling and mixing
    -> Post effects (speed / zoom / mirror / filter / fx / stickers)
    -> Branding (intro / captions / fancy text / progress bar / outro)
    -> FFmpeg encoding
    -> Audio composition (atempo / BGM / voice, silence alignment)
    -> Output validation
```

### 帧混合原理

工具的底层策略是"高帧率抽帧混合"，而非滤镜、缩放这类表层处理：

1. **输入两段视频**：内容视频 A 与一段独立的素材视频 B。
2. **构造高帧率输出流**：创建一个 60 / 120 / 240 fps 的目标视频流。
3. **按算法插入帧**：将视频 A 的帧逐一插入输出流的关键位置，相邻 A 帧之间用视频 B 的帧填充。
4. **重新编码输出**：播放器按高帧率解码时，人眼感知的仍是视频 A 的连续画面；而从文件数据层面看，输出包含大量来自视频 B 的帧，其 MD5 与数据特征与源文件完全不同。

各档强度对应的帧构成如下：

| 处理强度 | 目标 FPS | A:B 帧大致比例 |
| :--- | :---: | :---: |
| **50%** | 60 | 1 : 1 |
| **75%** | 120 | 1 : 3 |
| **87.5%** | 240 | 1 : 7 |

主要技术：Python、PyQt5、NumPy、OpenCV、FFmpeg、Pillow。

### 模块结构

```text
src/
  main.py       # PyQt5 界面（后期处理面板分两页：画面与音频 / 包装）
  config.py     # ProcessingOptions 数据模型（全部后期参数集中定义）
  pipeline.py   # VideoProcessor 线程：帧循环 / 变速筛选 / 音轨合成
  effects.py    # 像素级效果：缩放 / 镜像 / 滤镜 / 特效 / 贴纸 / 字幕 / 花字 / 进度条
  branding.py   # 片头片尾帧生成器（渐变背景 + 标题动画）
  assets.py     # 贴纸程序化生成、SRT 解析、系统字体查找
  frame_io.py   # FFmpeg rawvideo 管道读写
  media.py      # 媒体探测 / 分辨率对齐 / 音轨检测
```

## 快速开始

### 环境要求

- Python 3.8+
- FFmpeg（需加入 `PATH`；Windows 可从 [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) 下载，macOS 用 `brew install ffmpeg`，Linux 用 `sudo apt install ffmpeg`）

```bash
git clone https://github.com/toki-plus/AB-Video-Deduplicator.git
cd AB-Video-Deduplicator
python -m venv venv
```

激活虚拟环境后安装依赖并启动：

```bash
pip install -r requirements.txt
pyrcc5 src/resources.qrc -o src/resources.py   # 编译 Qt 图标资源
python src/main.py
```

## 使用说明

1. 选择两段拥有合法使用权的视频素材（内容视频 A 与素材视频 B）。
2. 选择处理强度（建议从 60fps 档开始测试）和输出目录。
3. 在“后期处理”面板按需勾选功能：
   - **画面与音频页**：变速、缩放、镜像、滤镜、特效、贴纸、BGM / 配音；
   - **包装页**：字幕条（多行文本或 SRT 文件）、花字、进度条、片头片尾。
   - 变速与缩放支持随机区间（同一任务内参数保持一致，多次任务间随机变化）。
4. 如本机具备兼容的 NVIDIA 环境，可启用 GPU 加速。
5. 启动任务，处理结果保存在 `output` 目录，检查输出视频的画面、音频和时长。

## 测试

```bash
pip install pytest
python -m pytest tests/ -q
```

覆盖范围：配置与随机采样、SRT 解析与时间换算、各像素效果、包装层渲染、端到端管线（含无音轨、竖屏、全功能组合等边界场景）。

## 当前限制

- 输出效果受源视频分辨率、帧率和编码格式影响。
- GPU 加速依赖本机 FFmpeg 构建与驱动环境。
- 片头片尾标题、影视名称和花字依赖系统中文字体。Linux 部署必须安装中文字体，否则中文文字可能显示为方框；详见 [`web/README.md`](web/README.md) 的部署说明。

## 📂 更多项目

- [video-mover](https://github.com/toki-plus/video-mover) — 多平台内容分发自动化流水线：素材处理、文案生成、定时调度与多平台适配
- [ai-highlight-clip](https://github.com/toki-plus/ai-highlight-clip) — 长视频智能初筛：Whisper 转写 + LLM 评分 + 人工终审，分钟级定位高光片段
- [ai-ttv-workflow](https://github.com/toki-plus/ai-ttv-workflow) — 文案到短视频的桌面工作流，关键节点保留人工确认
- [ai-video-workflow](https://github.com/toki-plus/ai-video-workflow) — 多模型 AIGC 视频生成流水线：文生图、图生视频、文生音乐的异步编排
- [ai-mixed-cut](https://github.com/toki-plus/ai-mixed-cut) — 素材库结构化与脚本重组的视频再创作工作流
- [ai-trader-for-mt4](https://github.com/toki-plus/ai-trader-for-mt4) — LLM×MT4 受控执行框架：工具约束、风控规则、状态管理与异步桥接
- [ai-trader-for-mt5](https://github.com/toki-plus/ai-trader-for-mt5) — 面向 MT5 的 AI 交易助手与 EA 工程化框架
- [auto-usps-tracker](https://github.com/toki-plus/auto-usps-tracker) — 跨境电商批量物流追踪与 Excel 报告自动化
- [netease-downloader](https://github.com/toki-plus/netease-downloader) — 网易云音乐下载桌面应用：扫码登录、下载队列、ID3 元数据写入

## License

See [LICENSE](./LICENSE).
