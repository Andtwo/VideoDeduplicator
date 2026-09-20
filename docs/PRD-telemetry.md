# PRD：AB Video Processor 匿名使用统计（Telemetry）

版本：v1.0
日期：2026-09-20（UTC+8）
状态：待评审
分支：`feature/telemetry`

---

## 1. 背景

AB Video Processor 目前是 PyQt5 桌面工具，计划打包分发给外部用户使用。
分发后缺少最基本的运营数据反馈，无法回答：

1. 有多少设备实际运行过软件；
2. 软件的启动活跃情况；
3. 用户发起了多少次视频处理任务；
4. 成功输出了多少个成品视频；
5. 失败任务集中在哪些环节。

因此需要在保持桌面版形态不变的前提下，加入一套合规、低侵入、可控的匿名使用统计能力，并配套一个最小化的服务端接收与统计服务。

## 2. 目标与非目标

### 2.1 目标

- 客户端支持匿名事件上报：`app_first_open`、`app_open`、`task_started`、`task_success`、`task_failed`、`telemetry_disabled`；
- 首次启动向用户明确说明统计内容，并提供选择；设置中可随时关闭；
- 埋点失败不影响视频处理主流程，不阻塞、不报错打扰用户；
- 服务端提供事件接收接口，具备白名单校验、字段过滤、限流、幂等去重能力；
- 提供基础统计口径（SQL / 简单查询接口），能回答第 1 节中的五个问题；
- 为后续 Web 平台化预留事件模型扩展空间。

### 2.2 非目标（本期不做）

- 不统计精确"安装量"，以"首次运行设备数"作为近似口径；
- 不收集任何用户身份信息、视频内容、文件名、文件路径；
- 不做用户账号体系；
- 不做离线事件缓存补发（失败即丢弃，后续版本再评估）；
- 不做可视化统计后台页面（本期以 SQL 查询为主）；
- 不接入第三方分析平台；
- 不做自动更新、崩溃堆栈上报（Sentry 类能力）。

## 3. 合规与隐私要求（红线）

### 3.1 禁止采集

以下内容在任何事件中均不得出现：

- 本地文件路径、视频文件名；
- 视频原始内容、截图、视频 MD5 / 哈希；
- 用户名、微信号、手机号、邮箱；
- 设备硬件序列号、硬盘序列号、MAC 地址、主板 UUID 等硬件指纹；
- 完整 Python traceback、完整 FFmpeg stderr（可能含本地路径）；
- 精确 IP（服务端不主动记录客户端 IP 到数据库）。

### 3.2 数据最小化

- 分辨率、时长、处理耗时等维度一律使用区间桶（bucket），不上传精确值组合；
- 错误信息只上传归类后的 `error_type` / `error_stage`，不上传原始错误文本；
- 匿名 ID 使用本地随机生成的 UUID v4，与设备硬件无关，删除配置文件后即失效。

### 3.3 用户知情与可控

- 首次启动弹出统计说明弹窗，用户主动选择后才生效；
- 未做出选择前不上报任何事件（包括 `app_first_open` 本身）；
- 设置面板提供"启用匿名使用统计"开关，关闭后立即停止上报；
- 关闭动作本身允许上报一次 `telemetry_disabled`（只含版本与平台信息，用于估算关闭率；若评审认为不妥可改为静默关闭）；
- 提供公开的《隐私与统计说明》文档（见附录 A）。

## 4. 术语与口径定义

| 口径 | 定义 |
| :--- | :--- |
| 首次运行设备数 | `app_first_open` 事件的去重 `anonymous_id` 数 |
| 活跃设备数 | 指定时间窗内 `app_open` 事件的去重 `anonymous_id` 数 |
| 任务数 | `task_started` 事件数（按 `event_id` 去重后） |
| 成品数 | `task_success` 事件数（按 `task_id` 去重后） |
| 任务成功率 | `task_success` 去重 `task_id` 数 / `task_started` 去重 `task_id` 数 |
| 关闭率 | `telemetry_disabled` 去重 `anonymous_id` 数 / 首次运行设备数 |

注意：

- 用户删除本地配置、重装系统、换设备会产生新的 `anonymous_id`，设备数为近似值；
- 服务端时间一律以 UTC+8 入库与统计。

## 5. 客户端设计（PyQt5）

### 5.1 模块结构

```text
src/telemetry/
├── __init__.py
├── config.py          # 本地配置读写（anonymous_id、开关、首次启动标记）
├── client.py          # 事件队列 + 后台发送线程
├── events.py          # 事件类型常量与属性构造（bucket 计算）
└── consent.py         # 首次启动说明弹窗
```

### 5.2 本地配置

路径：

```text
~/.ab_video_processor/config.json
```

结构：

```json
{
  "anonymous_id": "uuid4",
  "telemetry_enabled": true,
  "telemetry_prompt_shown": true,
  "first_open_reported": false
}
```

要求：

- 仅保存以上非敏感字段，不得写入任何视频路径；
- 文件读写失败时静默降级为"不启用统计"，不影响启动。

### 5.3 首次启动流程

```text
启动
  -> 读取 config.json
  -> telemetry_prompt_shown == false
       -> 弹出说明弹窗（文案见附录 A）
       -> 用户选择 [允许匿名统计] / [关闭统计]
       -> 写入配置
  -> telemetry_enabled == true
       -> first_open_reported == false 时上报 app_first_open
       -> 上报 app_open
  -> 进入主界面
```

弹窗要求：非模态阻塞业务以外的强制干扰最小化；两个按钮视觉权重一致，不做诱导性默认勾选。

### 5.4 事件上报时机

| 事件 | 触发位置（对应现有代码） |
| :--- | :--- |
| `app_first_open` | 主窗口初始化完成、用户已同意后 |
| `app_open` | 每次主窗口初始化完成且已同意后 |
| `task_started` | `MainWindow.run_processing()` 中成功创建 `VideoProcessor` 之后 |
| `task_success` | `VideoProcessor.run()` 中 `self.finished.emit()` 之前，且输出文件已生成校验通过 |
| `task_failed` | `VideoProcessor.run()` 的 `except` 分支，错误归类后上报 |
| `telemetry_disabled` | 用户在设置中关闭开关时（仅一次，之后停止一切上报） |

注意：`task_started` / `task_success` / `task_failed` 通过同一个本地随机 `task_id` 串联，由 `MainWindow` 在创建任务时生成并传入 `VideoProcessor`。

### 5.5 发送机制

- 客户端内部使用 `queue.Queue`，事件先入队；
- 单个 daemon 后台线程消费队列并发送，超时 1 秒，失败最多重试 1 次，仍失败则丢弃；
- 主流程任何代码路径都不直接发起网络请求；
- 程序退出时不强制刷队列，未发出的事件直接放弃；
- `telemetry_enabled == false` 时事件直接不入队。

### 5.6 属性字段与区间桶

通用字段（所有事件）：

```json
{
  "event_id": "uuid4，幂等去重键",
  "event": "task_success",
  "anonymous_id": "uuid4",
  "app_version": "1.0.0",
  "app_build": "20260920",
  "platform": "windows | darwin | linux",
  "os_version_bucket": "win10 | win11 | macos | linux | other",
  "client_timestamp": "UTC+8 ISO8601"
}
```

任务事件 properties：

```json
{
  "task_id": "uuid4",
  "fps": 60,
  "use_gpu": false,
  "resolution_bucket": "<=720p | 1080p | 1440p | 2160p | other",
  "duration_bucket": "<1min | 1-3min | 3-10min | 10-30min | >30min",
  "processing_seconds_bucket": "<10s | 10-30s | 30-60s | 1-3min | 3-10min | >10min",
  "error_type": "video_probe_failed | ffmpeg_failed | nvenc_failed | output_write_failed | audio_merge_failed | unknown",
  "error_stage": "probe | resize | mix | encode | audio_merge | unknown"
}
```

约束：

- `error_type` / `error_stage` 只在 `task_failed` 中出现；
- 客户端负责错误归类，不向上传递原始异常字符串；
- `resolution_bucket` / `duration_bucket` 以视频 A 为基准。

## 6. 服务端设计

### 6.1 技术选型

```text
FastAPI + SQLite（一期）
部署：与将来 Web 平台同服务器，独立进程 / 独立端口
```

SQLite 文件独立存放：`telemetry-server/data/events.db`，便于备份与迁移 PostgreSQL。

### 6.2 接口

#### POST /api/events

请求头：`Content-Type: application/json`

请求体：见 5.6 通用字段 + properties。

响应：

```json
{ "ok": true }
```

行为：

- 200：接受（含"合法但被白名单过滤后落库"）；
- 202：合法但为重复 `event_id`，幂等忽略；
- 400：结构非法；
- 429：触发限流；
- 所有响应都不回显客户端提交的内容。

#### GET /api/health

返回 `{ "status": "ok" }`，用于运维探活。

### 6.3 服务端校验规则

1. 事件名白名单：`app_first_open`、`app_open`、`task_started`、`task_success`、`task_failed`、`telemetry_disabled`，其余丢弃（返回 200 但不落库，避免泄露校验细节）；
2. `event_id`、`anonymous_id` 必须是合法 UUID 格式，长度上限 64；
3. `properties` 仅保留白名单字段（5.6 所列），其余剔除；整体大小上限 2KB；
4. 字符串字段长度上限 64；
5. 限流：同一来源 IP 每分钟最多 60 次请求（内存滑窗即可）；
6. `event_id` 唯一约束，冲突返回 202；
7. `server_timestamp` 由服务端生成，UTC+8；`client_timestamp` 仅存档不参与统计。

### 6.4 数据表

```sql
CREATE TABLE IF NOT EXISTS telemetry_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    anonymous_id TEXT NOT NULL,
    event TEXT NOT NULL,
    app_version TEXT,
    app_build TEXT,
    platform TEXT,
    os_version_bucket TEXT,
    client_timestamp TEXT,
    server_timestamp TEXT NOT NULL,
    properties TEXT          -- JSON 字符串，仅存白名单字段
);

CREATE INDEX IF NOT EXISTS idx_events_event ON telemetry_events(event);
CREATE INDEX IF NOT EXISTS idx_events_anonymous_id ON telemetry_events(anonymous_id);
CREATE INDEX IF NOT EXISTS idx_events_server_timestamp ON telemetry_events(server_timestamp);
```

### 6.5 统计口径 SQL（交付物之一）

- 首次运行设备数：

```sql
SELECT COUNT(DISTINCT anonymous_id) FROM telemetry_events WHERE event = 'app_first_open';
```

- 指定日期活跃设备数：

```sql
SELECT COUNT(DISTINCT anonymous_id) FROM telemetry_events
WHERE event = 'app_open' AND date(server_timestamp) = date('now', 'localtime');
```

- 任务数 / 成品数 / 成功率：

```sql
SELECT
  (SELECT COUNT(DISTINCT json_extract(properties, '$.task_id')) FROM telemetry_events WHERE event = 'task_started') AS tasks,
  (SELECT COUNT(DISTINCT json_extract(properties, '$.task_id')) FROM telemetry_events WHERE event = 'task_success') AS outputs;
```

- 失败原因分布：

```sql
SELECT json_extract(properties, '$.error_type') AS error_type, COUNT(*) AS cnt
FROM telemetry_events WHERE event = 'task_failed'
GROUP BY error_type ORDER BY cnt DESC;
```

## 7. 打包与分发注意事项

- 客户端不内置任何管理密钥；埋点接口为公开端点，依赖服务端限流与白名单防护；
- `app_version` / `app_build` 在打包时写入常量，避免运行时推断；
- PyInstaller 打包需确认 daemon 线程与 `multiprocessing.freeze_support` 无冲突；
- 分发包内附《隐私与统计说明》（附录 A 内容）。

## 8. 验收标准

### 客户端

1. 首次启动出现说明弹窗，未选择前无任何网络请求；
2. 选择允许后，首次启动上报 `app_first_open` + `app_open`，二次启动只上报 `app_open`；
3. 选择关闭后，全生命周期无任何上报；
4. 设置中关闭开关后立即停止上报；
5. 完成一次 60fps 处理任务后，服务端可见同一 `task_id` 的 `task_started` 与 `task_success`；
6. 人为制造失败（如输入损坏视频），服务端可见 `task_failed` 且 `error_type` / `error_stage` 已归类、无路径泄露；
7. 断网状态下软件全流程功能正常，无报错弹窗、无明显卡顿；
8. 重复投递同一 `event_id`，服务端只落一条。

### 服务端

1. 非法事件名、非法 UUID、超大 properties 均被正确处理且不泄露内部细节；
2. 限流触发返回 429；
3. 重复 `event_id` 返回 202 且不重复计数；
4. 第 6.5 节 SQL 均可执行并得到正确结果；
5. 数据库中不出现路径、文件名、原始错误文本。

## 9. 里程碑

| 阶段 | 内容 | 产出 |
| :--- | :--- | :--- |
| M1 | 客户端 telemetry 模块 + 弹窗 + 设置开关 | `src/telemetry/`、UI 变更 |
| M2 | 服务端 FastAPI 接收服务 | `telemetry-server/` |
| M3 | 端到端联调 + 验收用例 | 测试记录 |
| M4 | 打包验证（Windows exe） | 分发包 + 隐私说明文档 |

## 10. 风险与开放问题

1. `telemetry_disabled` 上报是否保留：用于估算关闭率，但严格来说属于"用户关闭后仍上报一次"。倾向保留，事件中不含任何任务信息；评审可决定改为静默关闭；
2. 限流基于 IP，多人共享出口（公司 / 校园网）可能误伤，一期可接受；
3. SQLite 并发写入在事件量上来后可能成为瓶颈，预留迁移 PostgreSQL 的表结构兼容性；
4. 桌面软件"安装量"天然不可精确统计，对外表述统一为"首次运行设备数"。

---

## 附录 A：隐私与统计说明（随软件分发）

```text
隐私与统计说明

为改进软件稳定性与功能体验，本软件可选启用匿名使用统计。

统计内容仅包括：
- 软件版本、操作系统类型
- 启动次数
- 任务开始 / 成功 / 失败状态
- 非敏感处理参数（输出帧率、是否启用 GPU、视频分辨率区间、时长区间、失败环节归类）

不收集：
- 视频文件本体与视频内容
- 视频文件名、本地文件路径
- 用户账号、手机号、微信号等身份信息
- 硬件序列号、MAC 地址等设备指纹

你可以在首次启动说明中选择关闭，也可以随时在设置中关闭匿名统计。
```
