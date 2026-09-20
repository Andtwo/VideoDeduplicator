"""事件队列 + 后台发送线程。

- 事件先入队，daemon 线程消费发送，主流程不直接发起网络请求；
- 超时 1 秒，失败最多重试 1 次，仍失败则丢弃；
- 程序退出时不强制刷队列；
- 未启用统计时事件直接不入队；
- 使用标准库 urllib，不新增第三方依赖。
"""

import json
import os
import queue
import sys
import threading
import urllib.request
import uuid
from datetime import datetime, timezone, timedelta

from . import events as ev

# 部署埋点服务端后改成实际地址；本地调试可用环境变量 AB_TELEMETRY_ENDPOINT 覆盖
DEFAULT_ENDPOINT = "https://telemetry.example.com/api/events"

APP_VERSION = "1.0.0"
APP_BUILD = "20260920"

_TIMEOUT = 1.0
_MAX_RETRY = 1
_TZ_CN = timezone(timedelta(hours=8))


class TelemetryClient:
    def __init__(self, config, endpoint=DEFAULT_ENDPOINT,
                 app_version=APP_VERSION, app_build=APP_BUILD):
        self._config = config
        self._endpoint = os.environ.get("AB_TELEMETRY_ENDPOINT", endpoint)
        self._app_version = app_version
        self._app_build = app_build
        self._queue = queue.Queue(maxsize=200)
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    @property
    def enabled(self):
        return self._config.enabled

    def set_enabled(self, enabled):
        self._config.set_enabled(enabled)

    def track(self, event, properties=None):
        """尽力而为地上报事件，任何情况下都不抛异常、不阻塞。"""
        try:
            if not self._config.enabled:
                return
            if event not in ev.ALLOWED_EVENTS:
                return
            payload = {
                "event_id": str(uuid.uuid4()),
                "event": event,
                "anonymous_id": self._config.anonymous_id,
                "app_version": self._app_version,
                "app_build": self._app_build,
                "platform": sys.platform,
                "os_version_bucket": ev.os_version_bucket(sys.platform),
                "client_timestamp": datetime.now(_TZ_CN).isoformat(),
                "properties": properties or {},
            }
            self._queue.put_nowait(payload)
        except Exception:
            pass

    def _worker(self):
        while True:
            try:
                payload = self._queue.get()
            except Exception:
                continue
            try:
                self._send(payload)
            except Exception:
                pass
            finally:
                try:
                    self._queue.task_done()
                except Exception:
                    pass

    def _send(self, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        for _ in range(_MAX_RETRY + 1):
            try:
                req = urllib.request.Request(
                    self._endpoint,
                    data=body,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=_TIMEOUT):
                    return
            except Exception:
                continue
