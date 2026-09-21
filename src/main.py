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

# ============ Web3 / Dark-Tech Design System ============
# 单一强调色（电青 mint），深空黑背景，中性冷灰，细边框卡片，胶囊按钮
# 形状规则：卡片与输入框 12px，主按钮与状态徽章全圆角

PALETTE = {
    "bg": "#0b0e14",
    "surface": "#11151d",
    "raised": "#1a2130",
    "input": "#151a24",
    "border": "#242d3d",
    "border_hover": "#33405a",
    "text": "#e6edf6",
    "muted": "#8b94a7",
    "accent": "#5eead4",
    "accent_hover": "#7df0dd",
    "accent_text": "#062420",
    "danger": "#f97066",
}

qss = f"""
QWidget {{
    background-color: {PALETTE['bg']};
    color: {PALETTE['text']};
    font-family: 'PingFang SC', 'Microsoft YaHei UI', 'Microsoft YaHei', 'Segoe UI', sans-serif;
    font-size: 13px;
}}
QMainWindow, QDialog {{ background-color: {PALETTE['bg']}; }}

/* ---------- 面板 / 卡片 ---------- */
QFrame#panel {{
    background-color: {PALETTE['surface']};
    border: 1px solid {PALETTE['border']};
    border-radius: 12px;
}}

/* ---------- 文本 ---------- */
QLabel {{ background: transparent; color: {PALETTE['text']}; }}
QLabel#panel_title {{
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 2px;
    color: {PALETTE['muted']};
}}
QLabel#field_label {{
    font-size: 13px;
    font-weight: 600;
    min-width: 64px;
}}
QLabel#path_label {{
    background-color: {PALETTE['input']};
    border: 1px solid {PALETTE['border']};
    border-radius: 8px;
    padding: 6px 10px;
    color: {PALETTE['muted']};
}}
QLabel#param_label {{ font-size: 12px; color: {PALETTE['muted']}; }}
QLabel#status_ready {{ color: {PALETTE['muted']}; font-size: 12px; }}
QLabel#status_done {{ color: {PALETTE['accent']}; font-size: 12px; font-weight: 600; }}
QLabel#status_error {{ color: {PALETTE['danger']}; font-size: 12px; font-weight: 600; }}

/* ---------- 按钮 ---------- */
QPushButton {{
    background-color: {PALETTE['raised']};
    color: {PALETTE['text']};
    border: 1px solid {PALETTE['border']};
    border-radius: 8px;
    padding: 7px 14px;
}}
QPushButton:hover {{ background-color: {PALETTE['border_hover']}; }}
QPushButton:pressed {{ background-color: {PALETTE['border']}; }}
QPushButton:disabled {{ color: {PALETTE['muted']}; background-color: {PALETTE['input']}; }}

QPushButton#run_button {{
    background-color: {PALETTE['accent']};
    color: {PALETTE['accent_text']};
    border: none;
    border-radius: 20px;
    padding: 10px 40px;
    font-size: 15px;
    font-weight: 700;
}}
QPushButton#run_button:hover {{ background-color: {PALETTE['accent_hover']}; }}
QPushButton#run_button:disabled {{
    background-color: {PALETTE['border']};
    color: {PALETTE['muted']};
}}

/* ---------- 复选 / 单选 ---------- */
QCheckBox, QRadioButton {{ spacing: 8px; color: {PALETTE['text']}; background: transparent; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {PALETTE['border_hover']};
    background-color: {PALETTE['input']};
}}
QCheckBox::indicator {{ border-radius: 5px; }}
QRadioButton::indicator {{ border-radius: 9px; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background-color: {PALETTE['accent']};
    border: 1px solid {PALETTE['accent']};
}}
QCheckBox:disabled, QRadioButton:disabled {{ color: {PALETTE['muted']}; }}

/* ---------- 输入控件 ---------- */
QLineEdit, QTextEdit, QComboBox, QDoubleSpinBox, QSpinBox {{
    background-color: {PALETTE['input']};
    color: {PALETTE['text']};
    border: 1px solid {PALETTE['border']};
    border-radius: 8px;
    padding: 6px 10px;
    selection-background-color: {PALETTE['accent']};
    selection-color: {PALETTE['accent_text']};
}}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus {{
    border: 1px solid {PALETTE['accent']};
}}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{
    background-color: {PALETTE['surface']};
    color: {PALETTE['text']};
    border: 1px solid {PALETTE['border']};
    selection-background-color: {PALETTE['raised']};
}}
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button,
QSpinBox::up-button, QSpinBox::down-button {{
    background-color: {PALETTE['raised']};
    border: none;
    width: 18px;
}}

/* ---------- 标签页 ---------- */
QTabWidget::pane {{
    border: 1px solid {PALETTE['border']};
    border-radius: 10px;
    background-color: {PALETTE['bg']};
    top: -1px;
}}
QTabBar::tab {{
    background-color: transparent;
    color: {PALETTE['muted']};
    padding: 8px 16px;
    font-size: 13px;
}}
QTabBar::tab:selected {{
    color: {PALETTE['text']};
    border-bottom: 2px solid {PALETTE['accent']};
}}
QTabBar::tab:hover {{ color: {PALETTE['text']}; }}

/* ---------- 进度条 ---------- */
QProgressBar {{
    background-color: {PALETTE['input']};
    border: 1px solid {PALETTE['border']};
    border-radius: 7px;
    height: 14px;
    text-align: center;
    font-size: 11px;
    color: {PALETTE['muted']};
}}
QProgressBar::chunk {{ background-color: {PALETTE['accent']}; border-radius: 6px; }}

/* ---------- 日志 ---------- */
QTextEdit#log_view {{
    font-family: 'JetBrains Mono', 'SF Mono', 'Cascadia Mono', 'Consolas', monospace;
    font-size: 12px;
    color: {PALETTE['muted']};
}}

/* ---------- 滚动条 ---------- */
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 4px 2px; }}
QScrollBar::handle:vertical {{
    background: {PALETTE['border']};
    border-radius: 4px;
    min-height: 32px;
}}
QScrollBar::handle:vertical:hover {{ background: {PALETTE['border_hover']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; background: none; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AB Video Processor")
        try:
            self.setWindowIcon(QIcon(":/logo.png"))
        except:
            print("图标资源 :logo.png 未找到，请检查resources.qrc和resources.py文件。")
        self.resize(700, 800)
        self.setMinimumSize(620, 540)
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
        main_layout.setSpacing(14)
        main_layout.setContentsMargins(20, 20, 20, 20)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setWidget(content)
        self.setCentralWidget(scroll_area)

        # ---------- 素材面板 ----------
        inputs_panel = QFrame()
        inputs_panel.setObjectName("panel")
        inputs_layout = QVBoxLayout(inputs_panel)
        inputs_layout.setSpacing(10)
        inputs_layout.setContentsMargins(16, 14, 16, 16)
        inputs_title = QLabel("素材输入")
        inputs_title.setObjectName("panel_title")
        inputs_layout.addWidget(inputs_title)

        self.label_a = QLabel("未选择")
        self.label_a.setObjectName("path_label")
        self.label_a.setWordWrap(True)
        self.btn_a = QPushButton("浏览")
        self.btn_a.clicked.connect(self.select_video_a)
        inputs_layout.addLayout(self._file_row("视频 A", "内容视频", self.label_a, self.btn_a))

        self.label_b = QLabel("未选择")
        self.label_b.setObjectName("path_label")
        self.label_b.setWordWrap(True)
        self.btn_b = QPushButton("浏览")
        self.btn_b.clicked.connect(self.select_video_b)
        inputs_layout.addLayout(self._file_row("视频 B", "填充素材", self.label_b, self.btn_b))

        self.label_output = QLabel("未选择")
        self.label_output.setObjectName("path_label")
        self.label_output.setWordWrap(True)
        self.btn_output = QPushButton("浏览")
        self.btn_output.clicked.connect(self.select_output_path)
        inputs_layout.addLayout(self._file_row("输出", "保存为 .mp4", self.label_output, self.btn_output))
        main_layout.addWidget(inputs_panel)

        # ---------- 处理选项面板 ----------
        options_frame = QFrame()
        options_frame.setObjectName("panel")
        options_layout = QVBoxLayout(options_frame)
        options_layout.setSpacing(10)
        options_layout.setContentsMargins(16, 14, 16, 16)
        options_title = QLabel("处理选项")
        options_title.setObjectName("panel_title")
        options_layout.addWidget(options_title)

        fps_row = QHBoxLayout()
        fps_row.setSpacing(16)
        fps_label = QLabel("处理强度")
        fps_label.setObjectName("field_label")
        fps_row.addWidget(fps_label)
        self.radio_60 = QRadioButton("50% · 60fps")
        self.radio_120 = QRadioButton("75% · 120fps")
        self.radio_240 = QRadioButton("87.5% · 240fps")
        self.radio_60.setChecked(True)
        fps_button_group = QButtonGroup(self)
        fps_button_group.addButton(self.radio_60)
        fps_button_group.addButton(self.radio_120)
        fps_button_group.addButton(self.radio_240)
        fps_row.addWidget(self.radio_60)
        fps_row.addWidget(self.radio_120)
        fps_row.addWidget(self.radio_240)
        fps_row.addStretch()
        options_layout.addLayout(fps_row)

        options_layout.addWidget(self._build_post_section())

        self.gpu_checkbox = QCheckBox("启用 GPU 加速（需要 NVIDIA 显卡和驱动）")
        self.gpu_checkbox.setChecked(False)
        options_layout.addWidget(self.gpu_checkbox)
        self.telemetry_checkbox = QCheckBox("启用匿名使用统计（不收集视频内容与文件路径）")
        self.telemetry_checkbox.setChecked(False)
        self.telemetry_checkbox.toggled.connect(self.on_telemetry_toggled)
        options_layout.addWidget(self.telemetry_checkbox)
        main_layout.addWidget(options_frame)

        # ---------- 运行按钮 ----------
        self.btn_run = QPushButton("开始处理")
        self.btn_run.setObjectName("run_button")
        self.btn_run.clicked.connect(self.run_processing)
        self.btn_run.setEnabled(False)
        main_layout.addWidget(self.btn_run, alignment=Qt.AlignCenter)

        # ---------- 任务状态面板 ----------
        status_panel = QFrame()
        status_panel.setObjectName("panel")
        status_layout = QVBoxLayout(status_panel)
        status_layout.setSpacing(10)
        status_layout.setContentsMargins(16, 14, 16, 16)
        status_title = QLabel("任务状态")
        status_title.setObjectName("panel_title")
        status_layout.addWidget(status_title)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        status_layout.addWidget(self.progress_bar)
        self.status_label = QLabel("待开始")
        self.status_label.setObjectName("status_ready")
        status_layout.addWidget(self.status_label)
        self.text_output = QTextEdit()
        self.text_output.setObjectName("log_view")
        self.text_output.setReadOnly(True)
        self.text_output.setMinimumHeight(140)
        status_layout.addWidget(self.text_output)
        main_layout.addWidget(status_panel)
        content.setLayout(main_layout)
        self.video_a_path = ""
        self.video_b_path = ""
        self.output_path = ""
        self.audio_file_path = ""
        self.caption_srt_path = ""
        self.temp_dir = os.path.join(os.path.expanduser("~"), ".video_temp_optimized")
        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir)

    def _file_row(self, name, hint, path_label, btn):
        """素材/输出文件选择行：左侧字段名（悬停显示说明），右侧路径与浏览按钮。"""
        row = QHBoxLayout()
        row.setSpacing(10)
        label = QLabel(name)
        label.setObjectName("field_label")
        label.setToolTip(hint)
        row.addWidget(label)
        row.addWidget(path_label, 1)
        row.addWidget(btn)
        return row

    def _build_post_section(self):
        """后期处理配置面板：两个标签页（画面与音频 / 包装）。"""
        tabs = QTabWidget()
        tabs.addTab(self._build_visual_tab(), "画面与音频")
        tabs.addTab(self._build_branding_tab(), "包装")
        return tabs

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
        scroll.setMinimumHeight(230)
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
        self.btn_caption_srt.clicked.connect(self.select_caption_srt)
        self.label_caption_srt = QLabel("多行文本模式")
        self.label_caption_srt.setObjectName("path_label")
        caption_row.addWidget(self.btn_caption_srt)
        caption_row.addWidget(self.label_caption_srt, 1)
        self._row_end(rows_layout, caption_row)
        self.caption_edit = QTextEdit()
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
        scroll.setMinimumHeight(230)
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
            self.append_text("已启用 GPU 加速模式。")
        else:
            self.append_text("使用 CPU 模式处理。")
        self._set_status("处理中", "status_ready")
        task_id = str(uuid.uuid4())
        options = self.build_options()
        if options.audio_mode != "original":
            if not options.audio_file:
                self.append_text("[错误] 请先选择 BGM / 配音音频文件")
                self._reset_after_validation_error()
                return
            if not os.path.exists(options.audio_file):
                self.append_text(f"[错误] 音频文件不存在: {options.audio_file}")
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
        self.progress_bar.setStyleSheet("QProgressBar::chunk { background-color: #f97066; border-radius: 6px; }")
        self._set_status("校验失败", "status_error")
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
        self._set_status("处理完成", "status_done")
        self.append_text("处理完成")

    def show_error(self, message):
        self.set_controls_enabled(True)
        self._set_status("处理失败", "status_error")
        self.append_text(f"[错误] {message}")
        self.progress_bar.setStyleSheet("QProgressBar::chunk { background-color: #f97066; border-radius: 6px; }")

    def _set_status(self, text, object_name):
        self.status_label.setText(text)
        self.status_label.setObjectName(object_name)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

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
