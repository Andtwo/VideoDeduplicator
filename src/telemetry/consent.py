"""首次启动统计说明弹窗。

两个按钮视觉权重一致，不做默认勾选诱导；
用户做出选择前不上报任何事件。
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QHBoxLayout, QPushButton

CONSENT_TEXT = (
    "为改进软件稳定性与功能体验，本软件可选启用匿名使用统计。\n\n"
    "统计内容仅包括：软件版本、操作系统类型、启动次数、"
    "任务开始 / 成功 / 失败状态，以及非敏感处理参数"
    "（输出帧率、是否启用 GPU、视频分辨率区间、时长区间、失败环节归类）。\n\n"
    "不收集：视频文件与视频内容、文件名、本地文件路径、"
    "账号与联系方式、硬件序列号与 MAC 地址等设备指纹。\n\n"
    "你也可以随时在设置中关闭匿名统计。"
)


class ConsentDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("隐私与统计说明")
        self.setModal(True)
        self.setMinimumWidth(460)
        self._accepted = False

        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        label = QLabel(CONSENT_TEXT)
        label.setWordWrap(True)
        label.setObjectName("consent_text")
        layout.addWidget(label)

        buttons = QHBoxLayout()
        buttons.addStretch()
        btn_accept = QPushButton("允许匿名统计")
        btn_accept.clicked.connect(self._on_accept)
        btn_decline = QPushButton("关闭统计")
        btn_decline.clicked.connect(self._on_decline)
        buttons.addWidget(btn_accept)
        buttons.addWidget(btn_decline)
        layout.addLayout(buttons)

        self.setLayout(layout)

    def _on_accept(self):
        self._accepted = True
        self.accept()

    def _on_decline(self):
        self._accepted = False
        self.accept()

    @property
    def accepted_telemetry(self):
        """用户是否允许匿名统计（区别于对话框本身的 accept/reject）。"""
        return self._accepted


def ask_consent(parent=None):
    """弹出说明弹窗，返回用户是否允许匿名统计。"""
    dialog = ConsentDialog(parent)
    dialog.exec_()
    return dialog.accepted_telemetry
