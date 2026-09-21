import os
import sys
import uuid
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (QApplication, QMainWindow, QPushButton, QFileDialog, QLabel,
                             QRadioButton, QVBoxLayout, QWidget, QProgressBar, QHBoxLayout,
                             QTextEdit, QFrame, QButtonGroup, QCheckBox, QScrollArea,
                             QComboBox, QDoubleSpinBox, QSizePolicy, QTabWidget, QLineEdit)
try:
    import resources
except ImportError:
    print("警告: 资源文件 'resources.py' 未找到。图标可能无法显示。")
    print("请使用 'pyrcc5 resources.qrc -o resources.py' 生成它。")

from pipeline import VideoProcessor
from config import ProcessingOptions, FILTER_STYLES, FX_STYLES
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
QComboBox, QDoubleSpinBox, QSpinBox {
    background: rgba(60, 60, 80, 0.9);
    color: #e0e0e0;
    border: 1px solid #555;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 13px;
    min-height: 18px;
}
QComboBox::drop-down {
    border: none;
    width: 22px;
}
QComboBox QAbstractItemView {
    background: #2a2a3a;
    color: #e0e0e0;
    selection-background-color: #4a90e2;
    selection-color: #ffffff;
}
QDoubleSpinBox::up-button, QSpinBox::up-button,
QDoubleSpinBox::down-button, QSpinBox::down-button {
    background: #3a3a55;
    border: none;
    width: 18px;
}
QDoubleSpinBox::up-button:hover, QSpinBox::up-button:hover,
QDoubleSpinBox::down-button:hover, QSpinBox::down-button:hover {
    background: #4a90e2;
}
QScrollArea {
    border: none;
    background: transparent;
}
QScrollBar:vertical {
    background: #2a2a3a;
    width: 10px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: #4a90e2;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
    background: none;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
}
QTabWidget::pane {
    border: 1px solid #444;
    border-radius: 4px;
    background: rgba(35, 35, 50, 0.6);
}
QTabBar::tab {
    background: #2a2a3a;
    color: #b0b0c0;
    padding: 6px 14px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    font-size: 13px;
}
QTabBar::tab:selected {
    background: #3d3d55;
    color: #fff;
    border-bottom: 2px solid #4a90e2;
}
QLineEdit, QTextEdit#caption_edit {
    background: rgba(60, 60, 80, 0.9);
    color: #e0e0e0;
    border: 1px solid #555;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 13px;
}
QLabel#param_label {
    font-size: 13px;
    color: #b0b0c0;
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
        self.resize(640, 780)
        self.setMinimumSize(560, 500)
        self.init_ui()
        sys.excepthook = self.except_hook
        self.telemetry_config = TelemetryConfig()
        self.telemetry = TelemetryClient(self.telemetry_config)
        self._telemetry_ui_ready = False
        self.telemetry_checkbox.setChecked(self.telemetry_config.enabled)
        self._telemetry_ui_ready = True
        QTimer.singleShot(0, self._init_telemetry_consent)

    def init_ui(self):
        # 主内容放入滚动区，窗口高度不足时可滚动，内容区域可自由压缩
        content = QWidget()
        main_layout = QVBoxLayout(content)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(16, 16, 16, 16)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setWidget(content)
        self.setCentralWidget(scroll_area)
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
        options_frame.setLayout(options_layout)
        main_layout.addWidget(options_frame)
        main_layout.addWidget(self._build_post_section())
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
        content.setLayout(main_layout)
        self.video_a_path = ""
        self.video_b_path = ""
        self.output_path = ""
        self.audio_file_path = ""
        self.caption_srt_path = ""
        self.temp_dir = os.path.join(os.path.expanduser("~"), ".video_temp_optimized")
        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir)

    def _build_post_section(self):
        """构建后期处理配置面板：两个标签页（画面与音频 / 包装）。"""
        frame = QFrame()
        layout = QVBoxLayout(frame)
        layout.setSpacing(8)
        title = QLabel("后期处理")
        title.setObjectName("section_title")
        layout.addWidget(title)
        tabs = QTabWidget()
        tabs.addTab(self._build_visual_tab(), "画面与音频")
        tabs.addTab(self._build_branding_tab(), "包装")
        layout.addWidget(tabs)
        frame.setLayout(layout)
        return frame

    def _build_visual_tab(self):
        """画面效果与音频配置页。"""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        rows = QWidget()
        rows_layout = QVBoxLayout(rows)
        rows_layout.setSpacing(10)
        rows_layout.setContentsMargins(4, 4, 4, 4)

        # ① 变速
        self.speed_check, speed_row = self._row_start("① 变速（倍速）")
        self.speed_random_check = QCheckBox("随机")
        self.speed_random_check.setChecked(True)
        self.speed_min_spin = self._spin(1.05, 1.0, 2.0, 0.05, "倍")
        self.speed_max_spin = self._spin(1.20, 1.0, 2.0, 0.05, "倍")
        speed_row.addWidget(QLabel("速度"))
        speed_row.addWidget(self.speed_min_spin)
        speed_row.addWidget(QLabel("~"))
        speed_row.addWidget(self.speed_max_spin)
        speed_row.addWidget(self.speed_random_check)
        self._row_end(rows_layout, speed_row)

        # ② 裁剪缩放
        self.zoom_check, zoom_row = self._row_start("② 画面放大")
        self.zoom_random_check = QCheckBox("随机")
        self.zoom_random_check.setChecked(True)
        self.zoom_min_spin = self._spin(110.0, 100.0, 200.0, 5.0, "%")
        self.zoom_max_spin = self._spin(120.0, 100.0, 200.0, 5.0, "%")
        zoom_row.addWidget(QLabel("幅度"))
        zoom_row.addWidget(self.zoom_min_spin)
        zoom_row.addWidget(QLabel("~"))
        zoom_row.addWidget(self.zoom_max_spin)
        zoom_row.addWidget(self.zoom_random_check)
        self._row_end(rows_layout, zoom_row)

        # ③ 镜像
        self.mirror_check, mirror_row = self._row_start("③ 镜像翻转（水平）")
        self._row_end(rows_layout, mirror_row)

        # ⑥ 滤镜
        self.filter_check, filter_row = self._row_start("⑥ 滤镜")
        self.filter_style_combo = QComboBox()
        self.filter_style_combo.addItems(["随机", "暖色", "冷色", "复古", "黑白", "明亮"])
        self.filter_strength_spin = self._spin(10.0, 0.0, 100.0, 1.0, "%")
        filter_row.addWidget(QLabel("风格"))
        filter_row.addWidget(self.filter_style_combo)
        filter_row.addWidget(QLabel("强度"))
        filter_row.addWidget(self.filter_strength_spin)
        self._row_end(rows_layout, filter_row)

        # ⑦ 画面特效
        self.fx_check, fx_row = self._row_start("⑦ 画面特效")
        self.fx_style_combo = QComboBox()
        self.fx_style_combo.addItems(["随机", "噪点", "暗角", "柔光", "漏光"])
        self.fx_strength_spin = self._spin(12.0, 0.0, 100.0, 1.0, "%")
        fx_row.addWidget(QLabel("类型"))
        fx_row.addWidget(self.fx_style_combo)
        fx_row.addWidget(QLabel("强度"))
        fx_row.addWidget(self.fx_strength_spin)
        self._row_end(rows_layout, fx_row)

        # ⑧ 贴纸
        self.sticker_check, sticker_row = self._row_start("⑧ 四角贴纸（随机样式与位置）")
        self._row_end(rows_layout, sticker_row)

        # ⑤ 音频：BGM / 配音
        self.audio_check = QCheckBox("⑤ 换 BGM / 配音")
        audio_row = QHBoxLayout()
        audio_row.setSpacing(8)
        audio_row.addWidget(self.audio_check)
        self.audio_mode_combo = QComboBox()
        self.audio_mode_combo.addItems(["BGM 替换原声", "原声 + BGM 混音", "配音替换原声"])
        self.audio_mode_combo.setEnabled(False)
        self.btn_audio_file = QPushButton("选择音频")
        self.btn_audio_file.setObjectName("select_button")
        self.btn_audio_file.setEnabled(False)
        self.btn_audio_file.clicked.connect(self.select_audio_file)
        self.audio_volume_spin = self._spin(30.0, 0.0, 100.0, 5.0, "%")
        self.audio_volume_spin.setEnabled(False)
        self.audio_volume_spin.setToolTip("BGM 音量（配音替换模式不生效）")
        self.label_audio_file = QLabel("未选择")
        self.label_audio_file.setObjectName("path_label")
        audio_row.addWidget(self.audio_mode_combo)
        audio_row.addWidget(self.btn_audio_file)
        audio_row.addWidget(self.label_audio_file, 1)
        audio_row.addWidget(QLabel("音量"))
        audio_row.addWidget(self.audio_volume_spin)
        self.audio_check.toggled.connect(self.on_audio_enabled)
        holder = QWidget()
        holder.setLayout(audio_row)
        rows_layout.addWidget(holder)

        rows.setLayout(rows_layout)
        scroll.setWidget(rows)
        scroll.setFixedHeight(260)
        return scroll

    def _build_branding_tab(self):
        """包装配置页：字幕条 / 花字 / 进度条 / 片头片尾。"""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        rows = QWidget()
        rows_layout = QVBoxLayout(rows)
        rows_layout.setSpacing(10)
        rows_layout.setContentsMargins(4, 4, 4, 4)

        # 字幕条
        self.caption_check, caption_row = self._row_start("④ 字幕条")
        self.btn_caption_srt = QPushButton("SRT")
        self.btn_caption_srt.setObjectName("select_button")
        self.btn_caption_srt.clicked.connect(self.select_caption_srt)
        self.label_caption_srt = QLabel("多行文本模式")
        self.label_caption_srt.setObjectName("path_label")
        caption_row.addWidget(self.btn_caption_srt)
        caption_row.addWidget(self.label_caption_srt, 1)
        self._row_end(rows_layout, caption_row)
        self.caption_edit = QTextEdit()
        self.caption_edit.setObjectName("caption_edit")
        self.caption_edit.setPlaceholderText("字幕文本，每行一条，均分内容时长")
        self.caption_edit.setFixedHeight(52)
        rows_layout.addWidget(self.caption_edit)

        # 花字
        self.fancy_check, fancy_row = self._row_start("④ 花字")
        self.fancy_edit = QLineEdit()
        self.fancy_edit.setPlaceholderText("花字内容，显示在画面上部")
        fancy_row.addWidget(self.fancy_edit, 1)
        self._row_end(rows_layout, fancy_row)

        # 进度条
        self.progress_check, progress_row = self._row_start("④ 进度条（底部）")
        self._row_end(rows_layout, progress_row)

        # 片头
        self.intro_check, intro_row = self._row_start("④ 片头")
        self.intro_edit = QLineEdit()
        self.intro_edit.setPlaceholderText("片头标题（留空则纯背景）")
        self.intro_edit.setFixedWidth(220)
        self.intro_dur_spin = self._spin(1.5, 0.5, 3.0, 0.1, "秒")
        intro_row.addWidget(self.intro_edit, 1)
        intro_row.addWidget(QLabel("时长"))
        intro_row.addWidget(self.intro_dur_spin)
        self._row_end(rows_layout, intro_row)

        # 片尾
        self.outro_check, outro_row = self._row_start("④ 片尾")
        self.outro_edit = QLineEdit()
        self.outro_edit.setPlaceholderText("片尾标题（留空则纯背景）")
        self.outro_edit.setFixedWidth(220)
        self.outro_dur_spin = self._spin(1.0, 0.5, 3.0, 0.1, "秒")
        outro_row.addWidget(self.outro_edit, 1)
        outro_row.addWidget(QLabel("时长"))
        outro_row.addWidget(self.outro_dur_spin)
        self._row_end(rows_layout, outro_row)

        rows.setLayout(rows_layout)
        scroll.setWidget(rows)
        scroll.setFixedHeight(260)
        return scroll

    def select_caption_srt(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择 SRT 字幕文件", "", "字幕文件 (*.srt)")
        if path:
            self.caption_srt_path = path
            self.label_caption_srt.setText(os.path.basename(path))
            self.label_caption_srt.setToolTip(path)
        else:
            self.caption_srt_path = ""
            self.label_caption_srt.setText("多行文本模式")

    def _row_start(self, text):
        check = QCheckBox(text)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(check)
        return check, row

    def _row_end(self, parent_layout, row):
        row.addStretch()
        holder = QWidget()
        holder.setLayout(row)
        parent_layout.addWidget(holder)

    def _spin(self, value, minimum, maximum, step, suffix=""):
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setSingleStep(step)
        spin.setDecimals(1)
        spin.setValue(value)
        if suffix:
            spin.setSuffix(suffix)
        spin.setFixedWidth(90)
        return spin

    def select_audio_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择 BGM / 配音文件", "",
                                              "音频文件 (*.mp3 *.wav *.m4a *.aac *.flac *.ogg)")
        if path:
            self.audio_file_path = path
            self.label_audio_file.setText(os.path.basename(path))
            self.label_audio_file.setToolTip(path)

    def on_audio_enabled(self, checked):
        self.audio_mode_combo.setEnabled(checked)
        self.btn_audio_file.setEnabled(checked)
        self.audio_volume_spin.setEnabled(checked)

    def build_options(self):
        """从 UI 收集 ProcessingOptions。"""
        style_map_f = {0: "random", 1: "warm", 2: "cool", 3: "vintage", 4: "mono", 5: "bright"}
        style_map_x = {0: "random", 1: "grain", 2: "vignette", 3: "bloom", 4: "leak"}
        return ProcessingOptions(
            speed_enabled=self.speed_check.isChecked(),
            speed_random=self.speed_random_check.isChecked(),
            speed_min=self.speed_min_spin.value(),
            speed_max=max(self.speed_min_spin.value(), self.speed_max_spin.value()),
            zoom_enabled=self.zoom_check.isChecked(),
            zoom_random=self.zoom_random_check.isChecked(),
            zoom_min=self.zoom_min_spin.value() / 100.0,
            zoom_max=max(self.zoom_min_spin.value(), self.zoom_max_spin.value()) / 100.0,
            mirror_enabled=self.mirror_check.isChecked(),
            filter_enabled=self.filter_check.isChecked(),
            filter_style=style_map_f[self.filter_style_combo.currentIndex()],
            filter_strength=self.filter_strength_spin.value() / 100.0,
            fx_enabled=self.fx_check.isChecked(),
            fx_style=style_map_x[self.fx_style_combo.currentIndex()],
            fx_strength=self.fx_strength_spin.value() / 100.0,
            sticker_enabled=self.sticker_check.isChecked(),
            audio_mode=({0: "replace_bgm", 1: "mix_bgm", 2: "replace_voice"}[self.audio_mode_combo.currentIndex()]
                        if self.audio_check.isChecked() else "original"),
            audio_file=getattr(self, "audio_file_path", ""),
            bgm_volume=self.audio_volume_spin.value() / 100.0,
            caption_enabled=self.caption_check.isChecked(),
            caption_text=self.caption_edit.toPlainText(),
            caption_srt=getattr(self, "caption_srt_path", ""),
            fancy_enabled=self.fancy_check.isChecked(),
            fancy_text=self.fancy_edit.text(),
            progress_enabled=self.progress_check.isChecked(),
            intro_enabled=self.intro_check.isChecked(),
            intro_text=self.intro_edit.text(),
            intro_duration=self.intro_dur_spin.value(),
            outro_enabled=self.outro_check.isChecked(),
            outro_text=self.outro_edit.text(),
            outro_duration=self.outro_dur_spin.value(),
        )

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
        options = self.build_options()
        if options.audio_mode != "original":
            if not options.audio_file:
                self.text_output.append("❌ 请先选择 BGM / 配音音频文件")
                self._reset_after_validation_error()
                return
            if not os.path.exists(options.audio_file):
                self.text_output.append(f"❌ 音频文件不存在: {options.audio_file}")
                self._reset_after_validation_error()
                return
        self.telemetry.track(telemetry_events.EVENT_TASK_STARTED, {
            "task_id": task_id,
            "fps": fps,
            "use_gpu": use_gpu,
            "features": options.enabled_features(),
        })
        self.processor = VideoProcessor(self.video_a_path, self.video_b_path, self.output_path, fps, self.temp_dir,
                                        options=options, use_gpu=use_gpu,
                                        telemetry=self.telemetry, task_id=task_id)
        self.processor.progress.connect(self.update_progress)
        self.processor.status.connect(self.append_text)
        self.processor.finished.connect(self.processing_finished)
        self.processor.error.connect(self.show_error)
        self.processor.start()

    def _reset_after_validation_error(self):
        self.progress_bar.setStyleSheet("QProgressBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #e74c3c, stop:1 #c0392b); border-radius: 5px; }")
        self.set_controls_enabled(True)

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
        for w in (self.speed_check, self.speed_random_check, self.speed_min_spin, self.speed_max_spin,
                  self.zoom_check, self.zoom_random_check, self.zoom_min_spin, self.zoom_max_spin,
                  self.mirror_check, self.filter_check, self.filter_style_combo, self.filter_strength_spin,
                  self.fx_check, self.fx_style_combo, self.fx_strength_spin, self.sticker_check,
                  self.audio_check, self.audio_mode_combo, self.btn_audio_file, self.audio_volume_spin,
                  self.caption_check, self.btn_caption_srt,
                  self.fancy_check, self.progress_check,
                  self.intro_check, self.outro_check, self.caption_edit, self.fancy_edit,
                  self.intro_edit, self.outro_edit, self.intro_dur_spin, self.outro_dur_spin):
            if w in (self.audio_mode_combo, self.btn_audio_file, self.audio_volume_spin):
                w.setEnabled(enabled and self.audio_check.isChecked())
            else:
                w.setEnabled(enabled)

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
