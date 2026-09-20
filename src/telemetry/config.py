"""本地配置读写：anonymous_id、统计开关、首次启动标记。

配置只保存非敏感字段，任何读写失败都静默降级为"不启用统计"。
"""

import json
import os
import uuid

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".ab_video_processor")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

_DEFAULTS = {
    "anonymous_id": "",
    "telemetry_enabled": False,
    "telemetry_prompt_shown": False,
    "first_open_reported": False,
}


class TelemetryConfig:
    def __init__(self, path=CONFIG_PATH):
        self._path = path
        self._data = dict(_DEFAULTS)
        self._load()
        if not self._data.get("anonymous_id"):
            self._data["anonymous_id"] = str(uuid.uuid4())
            self._save()

    def _load(self):
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                for key in _DEFAULTS:
                    if key in data:
                        self._data[key] = data[key]
        except Exception:
            pass

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    @property
    def anonymous_id(self):
        return self._data["anonymous_id"]

    @property
    def enabled(self):
        return bool(self._data.get("telemetry_enabled"))

    @property
    def prompt_shown(self):
        return bool(self._data.get("telemetry_prompt_shown"))

    @property
    def first_open_reported(self):
        return bool(self._data.get("first_open_reported"))

    def set_enabled(self, enabled):
        self._data["telemetry_enabled"] = bool(enabled)
        self._save()

    def mark_prompt_shown(self):
        self._data["telemetry_prompt_shown"] = True
        self._save()

    def mark_first_open_reported(self):
        self._data["first_open_reported"] = True
        self._save()
