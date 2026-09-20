"""匿名使用统计模块。

合规红线（见 docs/PRD-telemetry.md）：
- 不收集文件路径、文件名、视频内容、硬件指纹、完整 traceback；
- 用户未同意前不上报任何事件；
- 埋点失败静默，不影响主功能。
"""

from .client import TelemetryClient
from .config import TelemetryConfig

__all__ = ["TelemetryClient", "TelemetryConfig"]
