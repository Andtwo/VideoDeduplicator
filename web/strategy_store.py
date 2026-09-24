"""持久化内容处理策略版本，并维护当前启用版本。"""
import copy
import json
import os
import threading
import time
import uuid
from pathlib import Path

from web.strategy import DEFAULT_CONFIG, generate_strategy, validate_strategy_config

MAX_NAME_LENGTH = 60
MAX_DESCRIPTION_LENGTH = 300


class StrategyConflictError(ValueError):
    """客户端编辑的配置已过期。"""


class StrategyStore:
    def __init__(self, path):
        self.path = Path(path)
        self._lock = threading.RLock()
        self._ensure_store()

    def _default_data(self):
        now = time.time()
        version = {
            "id": uuid.uuid4().hex,
            "name": "默认随机策略",
            "version": 1,
            "description": "兼容原有服务端随机处理逻辑",
            "config": validate_strategy_config(DEFAULT_CONFIG),
            "created_at": now,
        }
        return {"active_id": version["id"], "versions": [version]}

    def _ensure_store(self):
        with self._lock:
            if not self.path.exists():
                self._write(self._default_data())
                return
            self._read()

    def _read(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            versions = data["versions"]
            if not isinstance(versions, list) or not versions:
                raise ValueError
            if data.get("active_id") not in {item["id"] for item in versions}:
                raise ValueError
            changed = False
            for item in versions:
                normalized = validate_strategy_config(item["config"])
                if normalized != item["config"]:
                    item["config"] = normalized
                    changed = True
            if changed:
                self._write(data)
            return data
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"策略版本文件损坏: {self.path}") from exc

    def _write(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, self.path)

    def list_versions(self):
        with self._lock:
            data = self._read()
            versions = copy.deepcopy(data["versions"])
            versions.sort(key=lambda item: item["created_at"], reverse=True)
            for item in versions:
                item["active"] = item["id"] == data["active_id"]
            return versions

    def active_version(self):
        with self._lock:
            data = self._read()
            version = next(item for item in data["versions"] if item["id"] == data["active_id"])
            result = copy.deepcopy(version)
            result["active"] = True
            return result

    def create_version(self, name, description, config):
        name = str(name or "").strip()
        description = str(description or "").strip()
        if not name or len(name) > MAX_NAME_LENGTH:
            raise ValueError(f"策略名称长度必须为 1-{MAX_NAME_LENGTH} 个字符")
        if len(description) > MAX_DESCRIPTION_LENGTH:
            raise ValueError(f"策略说明不能超过 {MAX_DESCRIPTION_LENGTH} 个字符")
        normalized = validate_strategy_config(config)
        with self._lock:
            data = self._read()
            number = max((item["version"] for item in data["versions"] if item["name"] == name), default=0) + 1
            version = {
                "id": uuid.uuid4().hex,
                "name": name,
                "version": number,
                "description": description,
                "config": normalized,
                "created_at": time.time(),
            }
            data["versions"].append(version)
            self._write(data)
            return copy.deepcopy(version)

    def update_version(self, version_id, name, description, config, expected_revision=None):
        name = str(name or "").strip()
        if not name or len(name) > MAX_NAME_LENGTH:
            raise ValueError(f"策略名称长度必须为 1-{MAX_NAME_LENGTH} 个字符")
        description = str(description or "").strip()
        if len(description) > MAX_DESCRIPTION_LENGTH:
            raise ValueError(f"策略说明不能超过 {MAX_DESCRIPTION_LENGTH} 个字符")
        normalized = validate_strategy_config(config)
        with self._lock:
            data = self._read()
            version = next((v for v in data["versions"] if v["id"] == version_id), None)
            if version is None:
                raise KeyError(version_id)
            revision = version.get("revision", 0)
            if type(expected_revision) is not int or expected_revision != revision:
                raise StrategyConflictError("该策略已被更新，请重新加载所选版本后再保存")
            if any(v["id"] != version_id and v["name"] == name and v["version"] == version["version"] for v in data["versions"]):
                raise ValueError("该名称下已存在相同版本号，请使用其他名称")
            version.update(name=name, description=description, config=normalized,
                           updated_at=time.time(), revision=revision + 1)
            self._write(data)
            return copy.deepcopy(version)

    def delete_versions(self, version_ids):
        if not isinstance(version_ids, list) or not version_ids or any(not isinstance(v, str) for v in version_ids):
            raise ValueError("请选择要删除的策略版本")
        ids = set(version_ids)
        with self._lock:
            data = self._read()
            if data["active_id"] in ids:
                raise ValueError("当前启用的策略版本不能删除")
            if ids - {v["id"] for v in data["versions"]}:
                raise KeyError("策略版本不存在")
            data["versions"] = [v for v in data["versions"] if v["id"] not in ids]
            self._write(data)

    def activate(self, version_id):
        with self._lock:
            data = self._read()
            version = next((item for item in data["versions"] if item["id"] == version_id), None)
            if not version:
                raise KeyError(version_id)
            data["active_id"] = version_id
            self._write(data)
            result = copy.deepcopy(version)
            result["active"] = True
            return result

    def delete(self, version_id):
        with self._lock:
            data = self._read()
            if data["active_id"] == version_id:
                raise ValueError("当前启用的策略版本不能删除")
            remaining = [item for item in data["versions"] if item["id"] != version_id]
            if len(remaining) == len(data["versions"]):
                raise KeyError(version_id)
            data["versions"] = remaining
            self._write(data)

    def snapshot_for_task(self, has_audio_file=False, has_video_b=False, title="", rng=None):
        version = self.active_version()
        strategy = generate_strategy(
            has_audio_file=has_audio_file,
            has_video_b=has_video_b,
            title=title,
            rng=rng,
            config=version["config"],
        )
        strategy["strategy_version_id"] = version["id"]
        strategy["strategy_name"] = version["name"]
        strategy["strategy_version"] = version["version"]
        return strategy
