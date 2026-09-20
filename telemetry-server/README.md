# AB Video Processor Telemetry Server

匿名使用统计接收服务，配套 PRD：`docs/PRD-telemetry.md`。

## 快速开始

```bash
cd telemetry-server
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py             # 默认监听 127.0.0.1:8765
```

生产部署建议放在 Nginx 后面，并通过环境变量配置：

```bash
export TELEMETRY_DB=/var/lib/ab-telemetry/events.db
export TELEMETRY_STATS_TOKEN=换成随机长字符串
uvicorn main:app --host 127.0.0.1 --port 8765
```

## 接口

| 接口 | 说明 |
| :--- | :--- |
| `POST /api/events` | 事件接收，白名单校验 + 字段过滤 + IP 限流（60 次/分钟）+ `event_id` 幂等去重 |
| `GET /api/health` | 探活 |
| `GET /api/stats` | 基础统计，需请求头 `X-Stats-Token` |

## 行为说明

- 事件名不在白名单：返回 200 但不落库（避免泄露校验细节）；
- `event_id` 重复：返回 202，不重复计数；
- 非法 UUID / 结构不合法：返回 400；
- 触发限流：返回 429；
- 服务端不记录客户端 IP，`server_timestamp` 统一 UTC+8。

## 客户端配置

部署后把 `src/telemetry/client.py` 中的 `DEFAULT_ENDPOINT` 改成实际地址，例如：

```python
DEFAULT_ENDPOINT = "https://your-domain.com/api/events"
```

## 常用统计 SQL

```bash
sqlite3 data/events.db
```

```sql
-- 首次运行设备数（≈ UV 累计）
SELECT COUNT(DISTINCT anonymous_id) FROM telemetry_events WHERE event = 'app_first_open';

-- 当日活跃设备数（UTC+8 入库）
SELECT COUNT(DISTINCT anonymous_id) FROM telemetry_events
WHERE event = 'app_open' AND date(server_timestamp) = date('now', 'localtime');

-- 任务成功率
SELECT
  (SELECT COUNT(DISTINCT json_extract(properties, '$.task_id')) FROM telemetry_events WHERE event = 'task_started') AS tasks,
  (SELECT COUNT(DISTINCT json_extract(properties, '$.task_id')) FROM telemetry_events WHERE event = 'task_success') AS outputs;

-- 失败原因分布
SELECT json_extract(properties, '$.error_type'), COUNT(*)
FROM telemetry_events WHERE event = 'task_failed' GROUP BY 1 ORDER BY 2 DESC;
```
