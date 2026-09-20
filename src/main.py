import os
import sys
import uuid
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (QApplication, QMainWindow, QPushButton, QFileDialog, QLabel,
                             QRadioButton, QVBoxLayout, QWidget, QProgressBar, QHBoxLayout,
                             QTextEdit, QFrame, QButtonGroup, QCheckBox)
try:
    import resources
except ImportError:
    print("警告: 资源文件 'resources.py' 未找到。图标可能无法显示。")
    print("请使用 'pyrcc5 resources.qrc -o resources.py' 生成它。")

from pipeline import VideoProcessor
from telemetry import TelemetryClient, TelemetryConfig
from telemetry import consent as telemetry_consent
from telemetry import events as telemetry_events

qss = """
QWidget {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1e1e2f, stop:1 #141422);
    color: #e0e0e0;
}
QFrame {
    background: rgba(40, 40, 60, 0.9);
    border: none;
    border-radius: 10px;
    padding: 15px;
    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.3);
}
QLabel#section_title {
    font-size: 14px;
    font-weight: 600;
    color: #ffffff;
}
QLabel#path_label {
    background: rgba(60, 60, 80, 0.8);
    border: 1px solid #555;
    border-radius: 5px;
    padding: 8px;
    font-size: 14px;
    color: #e0e0e0;
}
QPushButton#select_button {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4a90e2, stop:1 #357abd);
    color: white;
    border: none;
    padding: 8px 15px;
    font-size: 14px;
    border-radius: 5px;
    transition: all 0.3s;
}
QPushButton#select_button:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #5aa1f2, stop:1 #4688d1);
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
}
QRadioButton, QCheckBox {
    font-size: 14px;
    color: #e0e0e0;
}
QRadioButton::indicator, QCheckBox::indicator {
    width: 20px;
    height: 20px;
    border-radius: 5px;
    border: 2px solid #ffd700;
    background: #2a2a3a;
}
QRadioButton::indicator {
    border-radius: 10px;
}
QRadioButton::indicator:checked, QCheckBox::indicator:checked {
    background: #ffd700;
    border: 2px solid #ffd700;
}
QRadioButton::indicator:hover, QCheckBox::indicator {
    border: 2px solid #ffea00;
}
QPushButton#run_button {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ff7e5f, stop:1 #feb47b);
    color: white;
    border: none;
    padding: 12px 25px;
    font-size: 16px;
    font-weight: bold;
    border-radius: 8px;
    transition: all 0.3s;
}
QPushButton#run_button:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ff926f, stop:1 #ffc48b);
    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.3);
}
QPushButton#run_button:disabled {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #999, stop:1 #777);
    color: #ccc;
}
QProgressBar {
    background: rgba(40, 40, 60, 0.8);
    border-radius: 5px;
    text-align: center;
    font-size: 14px;
    color: #ffffff;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4a90e2, stop:1 #357abd);
    border-radius: 5px;
}
QTextEdit {
    background: rgba(30, 30, 50, 0.9);
    border: 1px solid #555;
    border-radius: 5px;
    font-size: 12px;
    color: #d0d0d0;
}
QTextEdit::verticalScrollBar {
    background: #2a2a3a;
    width: 10px;
    margin: 0px;
}
QTextEdit::verticalScrollBar::handle {
    background: #4a90e2;
    border-radius: 5px;
}
QTextEdit::verticalScrollBar::add-line, QTextEdit::verticalScrollBar::sub-line {
    background: none;
}
QLabel {
    background: transparent;
}
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AB Video Processor")
        try:
            self.setWindowIcon(QIcon(":/logo.png"))
        except:
            print("图标资源 :logo.png 未找到，请检查resources.qrc和resources.py文件。")
        self.setGeometry(100, 100, 600, 850)
        self.init_ui()
        sys.excepthook = self.except_hook
        self.telemetry_config = TelemetryConfig()
        self.telemetry = TelemetryClient(self.telemetry_config)
        self._telemetry_ui_ready = False
        self.telemetry_checkbox.setChecked(self.telemetry_config.enabled)
        self._telemetry_ui_ready = True
        QTimer.singleShot(0, self._init_telemetry_consent)

    def init_ui(self):
        container = QWidget()
        self.setCentralWidget(container)
        main_layout = QVBoxLayout()
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(20, 20, 20, 20)
        video_a_frame = QFrame()
        video_a_layout = QHBoxLayout()
        video_a_layout.setSpacing(10)
        video_a_title = QLabel("视频A（内容视频）")
        video_a_title.setObjectName("section_title")
        self.label_a = QLabel("未选择")
        self.label_a.setObjectName("path_label")
        self.label_a.setWordWrap(True)
        self.btn_a = QPushButton("选择")
        self.btn_a.setObjectName("select_button")
        self.btn_a.clicked.connect(self.select_video_a)
        video_a_layout.addWidget(video_a_title)
        video_a_layout.addWidget(self.label_a, 1)
        video_a_layout.addWidget(self.btn_a)
        video_a_frame.setLayout(video_a_layout)
        main_layout.addWidget(video_a_frame)
        video_b_frame = QFrame()
        video_b_layout = QHBoxLayout()
        video_b_layout.setSpacing(10)
        video_b_title = QLabel("视频B（填充素材）")
        video_b_title.setObjectName("section_title")
        self.label_b = QLabel("未选择")
        self.label_b.setObjectName("path_label")
        self.label_b.setWordWrap(True)
        self.btn_b = QPushButton("选择")
        self.btn_b.setObjectName("select_button")
        self.btn_b.clicked.connect(self.select_video_b)
        video_b_layout.addWidget(video_b_title)
        video_b_layout.addWidget(self.label_b, 1)
        video_b_layout.addWidget(self.btn_b)
        video_b_frame.setLayout(video_b_layout)
        main_layout.addWidget(video_b_frame)
        output_frame = QFrame()
        output_layout = QHBoxLayout()
        output_layout.setSpacing(10)
        output_title = QLabel("输出路径")
        output_title.setObjectName("section_title")
        self.label_output = QLabel("未选择")
        self.label_output.setObjectName("path_label")
        self.label_output.setWordWrap(True)
        self.btn_output = QPushButton("选择")
        self.btn_output.setObjectName("select_button")
        self.btn_output.clicked.connect(self.select_output_path)
        output_layout.addWidget(output_title)
        output_layout.addWidget(self.label_output, 1)
        output_layout.addWidget(self.btn_output)
        output_frame.setLayout(output_layout)
        main_layout.addWidget(output_frame)
        options_frame = QFrame()
        options_layout = QVBoxLayout()
        options_layout.setSpacing(15)
        fps_title = QLabel("处理强度")
        fps_title.setObjectName("section_title")
        options_layout.addWidget(fps_title)
        self.radio_60 = QRadioButton("50%（60fps）")
        self.radio_120 = QRadioButton("75%（120fps）")
        self.radio_240 = QRadioButton("87.5%（240fps）")
        self.radio_60.setChecked(True)
        fps_button_group = QButtonGroup(self)
        fps_button_group.addButton(self.radio_60)
        fps_button_group.addButton(self.radio_120)
        fps_button_group.addButton(self.radio_240)
        fps_options_layout = QHBoxLayout()
        fps_options_layout.addWidget(self.radio_60)
        fps_options_layout.addWidget(self.radio_120)
        fps_options_layout.addWidget(self.radio_240)
        fps_options_layout.addStretch()
        options_layout.addLayout(fps_options_layout)
        gpu_title = QLabel("性能选项")
        options_layout.addWidget(gpu_title)
        self.gpu_checkbox = QCheckBox("启用GPU加速（需要NVIDIA显卡和驱动）")
        self.gpu_checkbox.setChecked(False)
        options_layout.addWidget(self.gpu_checkbox)
        telemetry_title = QLabel("隐私与统计")
        telemetry_title.setObjectName("section_title")
        options_layout.addWidget(telemetry_title)
        self.telemetry_checkbox = QCheckBox("启用匿名使用统计（不收集视频内容与文件路径）")
        self.telemetry_checkbox.setChecked(False)
        self.telemetry_checkbox.toggled.connect(self.on_telemetry_toggled)
        options_layout.addWidget(self.telemetry_checkbox)
        options_frame.setLayout(options_layout)
        main_layout.addWidget(options_frame)
        self.btn_run = QPushButton("运行")
        self.btn_run.setObjectName("run_button")
        self.btn_run.setMinimumWidth(200)
        self.btn_run.clicked.connect(self.run_processing)
        self.btn_run.setEnabled(False)
        main_layout.addWidget(self.btn_run, alignment=Qt.AlignCenter)
        progress_log_frame = QFrame()
        progress_log_layout = QVBoxLayout()
        progress_log_layout.setSpacing(10)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        progress_log_layout.addWidget(self.progress_bar)
        self.text_output = QTextEdit()
        self.text_output.setReadOnly(True)
        progress_log_layout.addWidget(self.text_output)
        progress_log_frame.setLayout(progress_log_layout)
        main_layout.addWidget(progress_log_frame)
        container.setLayout(main_layout)
        self.video_a_path = ""
        self.video_b_path = ""
        self.output_path = ""
        self.temp_dir = os.path.join(os.path.expanduser("~"), ".video_temp_optimized")
        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir)

    def select_video_a(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择视频A", "", "视频文件 (*.mp4 *.avi *.mov)")
        if path:
            self.video_a_path = path
            self.label_a.setText(path)
            self.check_run_enable()

    def select_video_b(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择视频B", "", "视频文件 (*.mp4 *.avi *.mov)")
        if path:
            self.video_b_path = path
            self.label_b.setText(path)
            self.check_run_enable()

    def select_output_path(self):
        path, _ = QFileDialog.getSaveFileName(self, "选择输出路径", "C.mp4", "视频文件 (*.mp4)")
        if path:
            self.output_path = path
            self.label_output.setText(path)
            self.check_run_enable()

    def check_run_enable(self):
        if self.video_a_path and self.video_b_path and self.output_path:
            self.btn_run.setEnabled(True)
        else:
            self.btn_run.setEnabled(False)

    def _init_telemetry_consent(self):
        """首次启动弹出统计说明，用户选择前不上报任何事件。"""
        try:
            if not self.telemetry_config.prompt_shown:
                accepted = telemetry_consent.ask_consent(self)
                self.telemetry_config.mark_prompt_shown()
                self.telemetry_config.set_enabled(accepted)
                self._telemetry_ui_ready = False
                self.telemetry_checkbox.setChecked(accepted)
                self._telemetry_ui_ready = True
            if self.telemetry_config.enabled:
                if not self.telemetry_config.first_open_reported:
                    self.telemetry.track(telemetry_events.EVENT_APP_FIRST_OPEN)
                    self.telemetry_config.mark_first_open_reported()
                self.telemetry.track(telemetry_events.EVENT_APP_OPEN)
        except Exception:
            pass

    def on_telemetry_toggled(self, checked):
        if not getattr(self, "_telemetry_ui_ready", False):
            return
        try:
            if checked:
                self.telemetry.set_enabled(True)
            else:
                # 关闭前上报最后一次（仅版本/平台信息），随后停止一切上报
                self.telemetry.track(telemetry_events.EVENT_TELEMETRY_DISABLED)
                self.telemetry.set_enabled(False)
        except Exception:
            pass

    def run_processing(self):
        if self.radio_60.isChecked():
            fps = 60
        elif self.radio_120.isChecked():
            fps = 120
        else:
            fps = 240
        use_gpu = self.gpu_checkbox.isChecked()
        self.set_controls_enabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("")
        self.text_output.clear()
        if use_gpu:
            self.append_text("已启用GPU加速模式。")
        else:
            self.append_text("使用CPU模式处理。")
        task_id = str(uuid.uuid4())
        self.telemetry.track(telemetry_events.EVENT_TASK_STARTED, {
            "task_id": task_id,
            "fps": fps,
            "use_gpu": use_gpu,
        })
        self.processor = VideoProcessor(self.video_a_path, self.video_b_path, self.output_path, fps, self.temp_dir, use_gpu,
                                        telemetry=self.telemetry, task_id=task_id)
        self.processor.progress.connect(self.update_progress)
        self.processor.status.connect(self.append_text)
        self.processor.finished.connect(self.processing_finished)
        self.processor.error.connect(self.show_error)
        self.processor.start()

    def set_controls_enabled(self, enabled):
        self.btn_a.setEnabled(enabled)
        self.btn_b.setEnabled(enabled)
        self.btn_output.setEnabled(enabled)
        is_ready = bool(enabled and self.video_a_path and self.video_b_path and self.output_path)
        self.btn_run.setEnabled(is_ready)
        self.radio_60.setEnabled(enabled)
        self.radio_120.setEnabled(enabled)
        self.radio_240.setEnabled(enabled)
        self.gpu_checkbox.setEnabled(enabled)
        self.telemetry_checkbox.setEnabled(enabled)

    def update_progress(self, value):
        self.progress_bar.setValue(value)

    def append_text(self, text):
        self.text_output.append(f"• {text}")
        self.text_output.verticalScrollBar().setValue(self.text_output.verticalScrollBar().maximum())

    def processing_finished(self):
        self.set_controls_enabled(True)
        self.append_text("处理完成！")

    def show_error(self, message):
        self.set_controls_enabled(True)
        self.text_output.append(f"❌ {message}")
        self.progress_bar.setStyleSheet("QProgressBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #e74c3c, stop:1 #c0392b); border-radius: 5px; }")

    def closeEvent(self, event):
        import shutil
        if os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir, ignore_errors=True)
            except Exception as e:
                print(f"退出时清理临时文件失败: {e}")
        super().closeEvent(event)

    def except_hook(self, exc_type, exc_value, exc_traceback):
        import traceback
        error_msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        if hasattr(self, 'text_output'):
            self.show_error(f"发生未捕获的异常：\n{error_msg}")
            self.setWindowTitle("AB Video Processor - 发生严重错误")
        sys.__excepthook__(exc_type, exc_value, exc_traceback)


if __name__ == "__main__":
    if sys.platform.startswith('win'):
        from multiprocessing import freeze_support
        freeze_support()
    app = QApplication(sys.argv)
    app.setStyleSheet(qss)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
