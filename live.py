
from __future__ import annotations
import sys, time, os, glob, random
import threading, subprocess, json, tempfile, shutil
from concurrent.futures import ThreadPoolExecutor
import threading
from typing import List
import hik_capture  
from pathlib import Path
from collections import deque
from db import ensure_mongo_connected, load_camera_overrides
# at the very top of live.py
import os
print("[live] loaded from:", os.path.abspath(__file__))

# Qt Compatibility
# Qt Compatibility
PYQT6 = False
try:
    # Prefer PyQt5 first to match main_gui.py (avoid mixing)
    from PyQt5 import QtCore, QtGui, QtWidgets
    from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve, QTimer
except Exception:
    from PyQt6 import QtCore, QtGui, QtWidgets
    from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QTimer
    PYQT6 = True

try:
    from PyQt5.QtCore import pyqtSlot as _pyqtSlot
except Exception:
    from PyQt6.QtCore import pyqtSlot as _pyqtSlot
DEFAULT_RUNS_DIR = r"C:\Users\DELL\Desktop\inf"
INFERENCE_SCRIPT = str((Path(__file__).resolve().parent / "Inference.py").as_posix())
# ---- Alignment & scaling aliases (PyQt5/6 safe) ----
if PYQT6:
    AlignCenter  = Qt.AlignmentFlag.AlignCenter
    AlignRight   = Qt.AlignmentFlag.AlignRight
    AlignLeft    = Qt.AlignmentFlag.AlignLeft
    AlignVCenter = Qt.AlignmentFlag.AlignVCenter
    KeepAspect   = Qt.AspectRatioMode.KeepAspectRatio
    Smooth       = Qt.TransformationMode.SmoothTransformation
else:
    AlignCenter  = Qt.AlignCenter
    AlignRight   = Qt.AlignRight
    AlignLeft    = Qt.AlignLeft
    AlignVCenter = Qt.AlignVCenter
    KeepAspect   = Qt.KeepAspectRatio
    Smooth       = Qt.SmoothTransformation



# ----------------------------- Light Theme -----------------------------
LIGHT_QSS = """
* {
  font-family: "SF Pro Display", "Inter", "Segoe UI", "Helvetica Neue", Arial;
}
QMainWindow {
  background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
    stop:0 #f0f9ff, stop:0.3 #e0f2fe, stop:0.6 #ddd6fe, stop:1 #ede9fe);
}

#Sidebar {
  background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
    stop:0 rgba(255, 255, 255, 0.95), stop:1 rgba(249, 250, 251, 0.9));
  border-right: 2px solid rgba(139, 92, 246, 0.2);
  border-radius: 0px 24px 24px 0px;
}

#SummaryTitle {
  color: #7c3aed;
  font-weight: 900;
  font-size: 24px;
  letter-spacing: 2px;
}

#SummaryBox {
  background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
    stop:0 rgba(139, 92, 246, 0.08), stop:1 rgba(99, 102, 241, 0.05));
  border: 2px solid rgba(139, 92, 246, 0.25);
  border-radius: 16px;
  padding: 16px;
}

#SummaryBox QLabel {
  color: rgba(0, 0, 0, 0.9);
  font-weight: 700;
}

#BigStatus {
  border-radius: 20px;
  padding: 22px 0;
  color: #0f172a;
  font-size: 32px; font-weight: 900; letter-spacing: 6px;
  background: rgba(148,163,184,0.35);
  border: 3px dashed rgba(148,163,184,0.6);
}

.Card {
  background: rgba(255, 255, 255, 0.95);
  border: 2px solid rgba(139, 92, 246, 0.30);
  border-radius: 16px;
}

/* Explicit frames for clear separation */
.Card > QFrame, .Card {
  border-radius: 16px;
}

.Card[good="true"] {
  border: 3px solid rgba(34, 197, 94, 0.55);
  background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
    stop:0 rgba(34, 197, 94, 0.12), stop:1 rgba(22, 163, 74, 0.06));
}

.Card[ng="true"] {
  border: 3px solid rgba(239, 68, 68, 0.55);
  background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
    stop:0 rgba(239, 68, 68, 0.12), stop:1 rgba(220, 38, 38, 0.06));
}

.CardTitle {
  color: #7c3aed;
  font-weight: 800; font-size: 14px; letter-spacing: 1px;
}

.CardRight {
  color: rgba(0, 0, 0, 0.85);
  font-weight: 700; font-size: 13px;
}

.StatusLabel {
  color: white; font-weight: 900; font-size: 14px;
  padding: 10px 20px; border-radius: 12px; letter-spacing: 2px;
}
.StatusLabel[ok="true"] {
  background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #22c55e, stop:1 #16a34a);
  border: 2px solid rgba(34, 197, 94, 0.5);
}
.StatusLabel[ng="true"] {
  background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ef4444, stop:1 #dc2626);
  border: 2px solid rgba(239, 68, 68, 0.5);
}
.StatusLabel[na="true"] {
  background: rgba(148, 163, 184, 0.45);
  border: 2px solid rgba(148, 163, 184, 0.35);
  color: #0f172a;
}

.ImageBox {
  border: 3px dashed rgba(139, 92, 246, 0.35);
  border-radius: 14px;
  background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
    stop:0 rgba(241, 245, 249, 0.9), stop:1 rgba(226, 232, 240, 0.85));
  color: rgba(109, 40, 217, 0.8);
  font-weight: 600; font-size: 14px;
}

.SideBtn {
  background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
    stop:0 #8b5cf6, stop:0.5 #7c3aed, stop:1 #6366f1);
  color: white;
  border: 2px solid rgba(139, 92, 246, 0.5);
  border-radius: 12px; padding: 12px 16px;
  font-weight: 800; font-size: 13px; letter-spacing: 0.5px;
}
.SideBtn:hover {
  background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
    stop:0 #a78bfa, stop:0.5 #8b5cf6, stop:1 #7c3aed);
  border: 2px solid rgba(167, 139, 250, 0.7);
}
.SideBtn:pressed {
  background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
    stop:0 #6d28d9, stop:1 #5b21b6);
}

#SidebarLabel {
  color: rgba(2, 6, 23, 0.8);
  font-weight: 600; font-size: 13px; padding: 6px;
}
"""

# ----------------------------- Card Widget -----------------------------
class CardWidget(QtWidgets.QFrame):
    def __init__(self, cam_id: int, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setProperty("good", False)
        self.setProperty("ng", False)
        self.setMinimumWidth(260)

        if PYQT6:
            self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        else:
            self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.setLineWidth(2)

        self.cam_id = cam_id
        self.ng_count = 0
        self._pixmap: QtGui.QPixmap | None = None

        shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 10)
        shadow.setColor(QtGui.QColor(139, 92, 246, 60))
        self.setGraphicsEffect(shadow)

        root = QtWidgets.QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(16, 16, 16, 16)

        # Top bar
        top = QtWidgets.QHBoxLayout()
        self.title = QtWidgets.QLabel(f"📷 Camera {cam_id}")
        self.title.setObjectName("CardTitle")
        self.right = QtWidgets.QLabel("❌ 0")
        self.right.setObjectName("CardRight")
        top.addWidget(self.title)
        top.addStretch(1)
        top.addWidget(self.right)

        # Status chip
        self.status = QtWidgets.QLabel("N/A")
        self.status.setObjectName("StatusLabel")
        self.status.setAlignment(AlignCenter)
        self.status.setProperty("na", True)
        self.status.setProperty("ok", False)
        self.status.setProperty("ng", False)

        # Image box
        self.image = QtWidgets.QLabel("📸 Placeholder")
        self.image.setObjectName("ImageBox")
        self.image.setAlignment(AlignCenter)
        self.image.setMinimumHeight(200)

        # Bottom row
        bottom = QtWidgets.QHBoxLayout()
        self.b1 = QtWidgets.QLabel("⏱️ —")
        self.b2 = QtWidgets.QLabel("🎯 —")
        self.score = QtWidgets.QLabel("📊 Score: 0")
        for w in (self.b1, self.b2, self.score):
            w.setObjectName("BottomRow")
        bottom.addWidget(self.b1, 1)
        bottom.addWidget(self.b2, 1)
        bottom.addWidget(self.score, 1)

        root.addLayout(top)
        root.addWidget(self.status)
        root.addWidget(self.image, 1)
        root.addLayout(bottom)

        self._pulse_anim = QPropertyAnimation(self, b"geometry")
        self._pulse_anim.setDuration(200)
        self._pulse_anim.setEasingCurve(QEasingCurve.Type.OutCubic if PYQT6 else QEasingCurve.OutCubic)

    def set_image(self, path: str):
        pm = QtGui.QPixmap(path)
        if pm.isNull():
            self.image.setText("⚠️ Could not load image")
            self.image.setPixmap(QtGui.QPixmap())
            return
        self._pixmap = pm
        self._rescale_pixmap()
        self._animate_success()

    def set_good(self):
        self.setProperty("good", True)
        self.setProperty("ng", False)
        self.style().unpolish(self); self.style().polish(self)
        self.status.setText("✓ GOOD")
        self.status.setProperty("ok", True)
        self.status.setProperty("ng", False)
        self.status.setProperty("na", False)
        self.status.style().unpolish(self.status); self.status.style().polish(self.status)
        shadow = self.graphicsEffect()
        if shadow: shadow.setColor(QtGui.QColor(34, 197, 94, 100))

    def set_ng(self):
        self.setProperty("good", False)
        self.setProperty("ng", True)
        self.style().unpolish(self); self.style().polish(self)
        self.status.setText("✗ NG")
        self.status.setProperty("ok", False)
        self.status.setProperty("ng", True)
        self.status.setProperty("na", False)
        self.status.style().unpolish(self.status); self.status.style().polish(self.status)
        self.ng_count += 1
        self.right.setText(f"❌ {self.ng_count}")
        shadow = self.graphicsEffect()
        if shadow: shadow.setColor(QtGui.QColor(239, 68, 68, 100))

    def clear(self):
        self._pixmap = None
        self.image.setText("📸 Placeholder")
        self.image.setPixmap(QtGui.QPixmap())
        self.ng_count = 0
        self.right.setText("❌ 0")
        self.setProperty("good", False)
        self.setProperty("ng", False)
        self.style().unpolish(self); self.style().polish(self)
        self.status.setText("N/A")
        self.status.setProperty("ok", False)
        self.status.setProperty("ng", False)
        self.status.setProperty("na", True)
        self.status.style().unpolish(self.status); self.status.style().polish(self.status)
        shadow = self.graphicsEffect()
        if shadow: shadow.setColor(QtGui.QColor(139, 92, 246, 60))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._rescale_pixmap()

    def _rescale_pixmap(self):
        if not self._pixmap or self._pixmap.isNull():
            return
        pm = self._pixmap.scaled(self.image.size(), KeepAspect, Smooth)
        self.image.setPixmap(pm)
        self.image.setText("")

    def _animate_success(self):
        start = self.geometry()
        scaled = QtCore.QRect(start)
        scaled.setWidth(int(start.width() * 1.02))
        scaled.setHeight(int(start.height() * 1.02))
        scaled.moveCenter(start.center())
        self._pulse_anim.setStartValue(start)
        self._pulse_anim.setKeyValueAt(0.5, scaled)
        self._pulse_anim.setEndValue(start)
        self._pulse_anim.start()
#-----------------------------------CAM-------------------------------------------------------
class CaptureWorker(QtCore.QObject):
    frameCaptured = QtCore.pyqtSignal(int, int, str)  # cam_index, frame_idx, path
    finished      = QtCore.pyqtSignal()
    error         = QtCore.pyqtSignal(str)
    cycleTick     = QtCore.pyqtSignal(int)            # <--- NEW

    def __init__(
        self,
        cam_indices: List[int],
        frames: int,
        out_dir: str,
        exposure_us=None,
        gain_db=None,
        mirror=False,
        exposure_map: dict[int, float] | None = None,
        gain_map: dict[int, float] | None = None,
    ):
        super().__init__()
        self.cam_indices = cam_indices
        self.frames      = frames            # >0 => finite, <=0 => continuous
        self.out_dir     = out_dir

        # 🔹 default values (if nothing specific in the map)
        self.exposure_us = exposure_us
        self.gain_db     = gain_db

        # 🔹 per-camera overrides (index -> value)
        self.exposure_map: dict[int, float] = exposure_map or {}
        self.gain_map: dict[int, float]     = gain_map or {}

        self.mirror      = mirror
        self._running    = True
        self._cycle      = 0                 # <--- NEW


    @QtCore.pyqtSlot()
    def stop(self):
        """Ask the worker loop to stop."""
        self._running = False

    @QtCore.pyqtSlot()
    def run(self):
        try:
            def _cb(cam_idx, frame_i, path):
                self.frameCaptured.emit(int(cam_idx), int(frame_i), str(path))

            def _exp_for(idx: int):
                # per-camera exposure; fall back to global exposure_us
                return self.exposure_map.get(idx, self.exposure_us)

            def _gain_for(idx: int):
                # per-camera gain; fall back to global gain_db
                return self.gain_map.get(idx, self.gain_db)

            # ----- FINITE MODE -----
            if self.frames and self.frames > 0:
                if not self._running:
                    return

                # capture 'frames' images per camera with its own exp/gain
                for cam_idx in self.cam_indices:
                    hik_capture.capture_multi(
                        indices=[cam_idx],
                        frames=self.frames,
                        base_out=self.out_dir,
                        mirror=self.mirror,
                        exposure_us=_exp_for(cam_idx),
                        gain_db=_gain_for(cam_idx),
                        progress_cb=_cb,
                    )

                self._cycle += 1
                self.cycleTick.emit(self._cycle)
                self.finished.emit()
                return

            # ----- CONTINUOUS MODE (frames <= 0) -----
            while self._running:
                self._cycle += 1
                # each loop = one "cycle": 1 frame per camera
                for cam_idx in self.cam_indices:
                    hik_capture.capture_multi(
                        indices=[cam_idx],
                        frames=1,              # 1 frame per cam per cycle
                        base_out=self.out_dir,
                        mirror=self.mirror,
                        exposure_us=_exp_for(cam_idx),
                        gain_db=_gain_for(cam_idx),
                        progress_cb=_cb,
                    )
                self.cycleTick.emit(self._cycle)

            # when stop() called, loop exits:
            self.finished.emit()

        except Exception as e:
            self.error.emit(str(e))





# ----------------------------- Main Window -----------------------------
class LiveConfigDialog(QtWidgets.QDialog):
    def __init__(self, max_cams: int, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Live Capture Configuration")
        self.setModal(True)

        layout = QtWidgets.QVBoxLayout(self)

        form = QtWidgets.QFormLayout()
        form.setLabelAlignment(AlignRight | AlignVCenter)

        # --- Backend ---
        self.combo_backend = QtWidgets.QComboBox()
        self.combo_backend.addItems(["yolo", "detectron"])
        form.addRow("Inference backend:", self.combo_backend)

        # --- Weights path ---
        w_layout = QtWidgets.QHBoxLayout()
        self.ed_weights = QtWidgets.QLineEdit()
        self.ed_weights.setPlaceholderText("Select weights file (.pt / .pth)")
        btn_browse = QtWidgets.QPushButton("Browse…")
        w_layout.addWidget(self.ed_weights, 1)
        w_layout.addWidget(btn_browse)
        form.addRow("Weights file:", w_layout)

        # --- Num cameras (also how many cards) ---
        self.spin_cams = QtWidgets.QSpinBox()
        self.spin_cams.setRange(1, max_cams)
        self.spin_cams.setValue(min(4, max_cams))
        form.addRow("How many cameras:", self.spin_cams)

        # --- Detectron num_classes (only visible for Detectron) ---
        self.lbl_classes = QtWidgets.QLabel("Detectron num_classes:")
        self.spin_classes = QtWidgets.QSpinBox()
        self.spin_classes.setRange(1, 1000)
        self.spin_classes.setValue(5)
        form.addRow(self.lbl_classes, self.spin_classes)

        layout.addLayout(form)

        # Buttons
        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        layout.addWidget(btn_box)

        # Connections
        btn_browse.clicked.connect(self._on_browse)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        self.combo_backend.currentTextChanged.connect(self._on_backend_changed)

        # Initial state
        self._on_backend_changed(self.combo_backend.currentText())

    def _on_backend_changed(self, text: str):
        """Show num_classes only for Detectron."""
        is_detectron = (text.lower() == "detectron")
        self.lbl_classes.setVisible(is_detectron)
        self.spin_classes.setVisible(is_detectron)

    def _on_browse(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select Weights File", "",
            "Model files (*.pt *.pth);;All files (*)"
        )
        if path:
            self.ed_weights.setText(path)

    def accept(self):
        # Basic validation
        if not self.ed_weights.text().strip():
            QtWidgets.QMessageBox.warning(self, "Missing Weights",
                                          "Please select a weights file.")
            return
        super().accept()

    def get_values(self) -> dict:
        backend = self.combo_backend.currentText().lower()
        return {
            "backend": backend,
            "weights": self.ed_weights.text().strip(),
            "num_cams": self.spin_cams.value(),
            "num_classes": self.spin_classes.value() if backend == "detectron" else None,
        }

class MainWindow(QtWidgets.QMainWindow):
  # ==== signals (must be class attributes for PyQt) ====
    infer_result = QtCore.pyqtSignal(int, str, bool, str)  # cam_index, overlay_path, is_ng, score_text

    def __init__(self, mvs_overrides: dict[int, dict] | None = None):
        super().__init__()
        self.setWindowTitle(" ⚡ LIVE UI ")
        self.resize(1440, 900)
        self.cycle_count = 0

        # 🔹 MVS overrides coming from MongoDB (index -> {"ExposureTime": ..., "Gain": ...})
        self._mvs_overrides: dict[int, dict] = mvs_overrides or {}


        # ---- inference/session config ----
        self._infer_cfg = {
            "backend": None,       # "yolo" | "detectron"
            "weights": None,
            "num_classes": None,   # detectron only
            "device": None,        # optional
            "out_dir": None,       # temp per run
        }
        self._infer_pool = ThreadPoolExecutor(max_workers=2)

        # ---- state & maps ----
        self.good = 0
        self.bad = 0
        self.start_time = time.time()
        self.has_results = False
        self.cards: list[CardWidget] = []
        self._dev_map: dict[int, int] = {}   # cam index -> card index
        self.num_cams = 0
        self.num_frames = 0
        self._pending = deque()   # holds tuples (cam_index, img_path)
        self._inflight = False    # True when one inference is running
        self._infer_pool = ThreadPoolExecutor(max_workers=2)
        self.infer_result.connect(self._apply_infer_result)


        # ---- root containers ----
        central = QtWidgets.QWidget()
        root = QtWidgets.QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        self.setCentralWidget(central)

        # ---- sidebar ----
        self.sidebar = QtWidgets.QFrame(objectName="Sidebar")
        self.sidebar.setFixedWidth(280)
        side = QtWidgets.QVBoxLayout(self.sidebar)
        side.setContentsMargins(16, 16, 16, 16)
        side.setSpacing(14)

        self.summaryTitle = QtWidgets.QLabel("⚡ SUMMARY", objectName="SummaryTitle")
        side.addWidget(self.summaryTitle)

        # summary box (left-aligned key : value)
        self.summaryBox = QtWidgets.QWidget(objectName="SummaryBox")
        grid = QtWidgets.QGridLayout(self.summaryBox)
        grid.setContentsMargins(7, 7, 7, 7)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)

        def make_row(row_idx: int, key_text: str, value_label: QtWidgets.QLabel):
            key = QtWidgets.QLabel(key_text)
            key.setObjectName("SummaryKey")
            key.setAlignment(AlignLeft | AlignVCenter)      # <-- flush-left key

            colon = QtWidgets.QLabel(":")
            colon.setObjectName("SummaryColon")
            colon.setAlignment(AlignLeft | AlignVCenter)    # <-- left-align colon too

            value_label.setObjectName("SummaryVal")
            value_label.setAlignment(AlignLeft | AlignVCenter)  # <-- flush-left value
            value_label.setStyleSheet('font-family: "Consolas","SF Mono","Roboto Mono",monospace;')

            grid.addWidget(key,   row_idx, 0)
            grid.addWidget(colon, row_idx, 1)
            grid.addWidget(value_label, row_idx, 2)

        self.lblGoodVal  = QtWidgets.QLabel("0")
        self.lblBadVal   = QtWidgets.QLabel("0")
        self.lblRatioVal = QtWidgets.QLabel("0.00%")
        self.lblTotalVal = QtWidgets.QLabel("0")

        make_row(0, "Good",     self.lblGoodVal)
        make_row(1, "Bad",      self.lblBadVal)
        make_row(2, "NG Ratio", self.lblRatioVal)
        make_row(3, "Total",    self.lblTotalVal)

        side.addWidget(self.summaryBox)

        # Buttons


        self.btnReset = QtWidgets.QPushButton("🔄 Reset Counts & Images")
        self.btnReset.setObjectName("SideBtn")
        self.btnReset.clicked.connect(self._reset_all)

        # add buttons to the sidebar (not to a non-existent 'sb')
        side.addWidget(self.btnReset)

        # Stats
        self.lblUptime = QtWidgets.QLabel("⏱️ Uptime: 00:00:00")
        self.lblCycle  = QtWidgets.QLabel("⚡ Cycle: 0")
        self.lblInsp   = QtWidgets.QLabel("🔍 Inspection: idle")

        for w in (self.lblUptime, self.lblCycle, self.lblInsp):
            w.setObjectName("SidebarLabel")
            side.addWidget(w)

        # Camera count (1–8)
        # self.btnCaptureMore = QtWidgets.QPushButton("📸 Capture More")
        # self.btnCaptureMore.setObjectName("SideBtn")
        # self.btnCaptureMore.clicked.connect(self.start_capture_and_infer_flow)
        # side.addWidget(self.btnCaptureMore)


        side.addStretch(1)

        # Big status (neutral until results exist)
        self.bigStatus = QtWidgets.QLabel("—")
        self.bigStatus.setObjectName("BigStatus")
        self.bigStatus.setAlignment(AlignCenter)
        side.addWidget(self.bigStatus)

        # Grid
        self.gridHost = QtWidgets.QWidget()
        self.grid = QtWidgets.QGridLayout(self.gridHost)
        self.grid.setHorizontalSpacing(24)
        self.grid.setVerticalSpacing(24)
        self.grid.setContentsMargins(24, 24, 24, 24)

        root.addWidget(self.sidebar)
        root.addWidget(self.gridHost, 1)

        self.cards: list[CardWidget] = []
        self.apply_theme()
       # self._prompt_cameras(initial=True)

        # Uptime timer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)

    def apply_theme(self):
        self.setStyleSheet(LIGHT_QSS)
        self._update_big_status()

    def _prompt_cameras(self, initial: bool = False):
        settings = QtCore.QSettings("Live_ui", "layout")
        prev = int(settings.value("num_cameras", 8))
        num, ok = QtWidgets.QInputDialog.getInt(
            self, "🎛️ Camera Configuration",
            "How many camera cards to display?",
            prev, 1, 8, 1   # <-- up to 8
        )
        if not ok and initial:
            num = max(1, min(prev, 8))
        elif not ok:
            return
        settings.setValue("num_cameras", num)
        self._build_cards(num)

    def _build_cards(self, n: int):
        for i in reversed(range(self.grid.count())):
            item = self.grid.itemAt(i)
            w = item.widget()
            if w: w.setParent(None)
        self.cards.clear()

        # 4 columns when >4, else n columns
        cols = 4 if n > 4 else n
        row = col = 0
        for cam_id in range(1, n + 1):
            card = CardWidget(cam_id)
            self.grid.addWidget(card, row, col, 1, 1)
            self.cards.append(card)
            col += 1
            if col >= cols:
                col = 0
                row += 1

        # Reset summary since layout changed
        self._reset_counters(soft=True)

    def _reset_counters(self, soft: bool = False):
        # soft=True doesn't prompt; it just clears numbers and status
        self.good = 0
        self.bad = 0
        if not soft:
            for c in self.cards: c.clear()
        self.has_results = False
        self._refresh_summary()

    # ---- summary & status ----
    def _refresh_summary(self):
        total = self.good + self.bad
        ratio = (self.bad / total * 100.0) if total else 0.0

        self.lblGoodVal.setText(str(self.good))
        self.lblBadVal.setText(str(self.bad))
        self.lblRatioVal.setText(f"{ratio:.2f}%")   # change to f"{int(ratio)}" if you want just "0"
        self.lblTotalVal.setText(str(total))

        self._update_big_status()


    def _update_big_status(self):
        if not self.has_results:
            # neutral placeholder before any upload
            self.bigStatus.setText("—")
            self.bigStatus.setStyleSheet(
                "#BigStatus { background: rgba(148,163,184,0.35); "
                "border: 3px dashed rgba(148,163,184,0.6); color: #0f172a; "
                "border-radius: 20px; padding: 10px 0; font-size: 10px; "
                "font-weight: 900; letter-spacing: 6px; }"
            )
            return

        if self.bad == 0:
            self.bigStatus.setText("✓ GOOD")
            self.bigStatus.setStyleSheet(
                "#BigStatus { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, "
                "stop:0 #22c55e, stop:1 #16a34a); "
                "border: 3px solid rgba(34, 197, 94, 0.6); color: white; "
                "border-radius: 20px; padding: 10px 0; font-size: 10px; "
                "font-weight: 900; letter-spacing: 6px; }"
            )
        else:
            self.bigStatus.setText("✗ NG")
            self.bigStatus.setStyleSheet(
                "#BigStatus { "
                "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ef4444, stop:1 #dc2626); "
                "border: 2px solid rgba(239, 68, 68, 0.6); color: white; "
                "border-radius: 14px; padding: 10px 0; "
                "font-size: 10px; font-weight: 800; letter-spacing: 2px; "
                "}"
            )

    # ---- actions ----
    def _reset_all(self):
        reply = QtWidgets.QMessageBox.question(
            self, "🔄 Reset Confirmation",
            "Reset all counts and clear images?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
            if PYQT6 else
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        if reply == (QtWidgets.QMessageBox.StandardButton.Yes if PYQT6 else QtWidgets.QMessageBox.Yes):
            for c in self.cards: c.clear()
            self._reset_counters(soft=True)

    def _put_image(self):
        img_path = self._find_test_image()
        if not img_path:
            QtWidgets.QMessageBox.warning(
                self, "Image not found",
                "Place at least one image in a folder named 'test_image' next to this script."
            )
            return

        # 1) load same test image to all placeholders
        for c in self.cards:
            c.clear()              # ensure neutral before placing
            c.set_image(img_path)  # only sets image, leaves status as N/A

        # 2) testing purpose: assign some GOOD, some NG
        n = len(self.cards)
        idxs = list(range(n))
        random.shuffle(idxs)

        # split roughly half NG, half GOOD; ensure at least one of each if n>=2
        ng_count_target = max(1, n // 2) if n >= 2 else (1 if n == 1 else 0)
        ng_idxs = set(idxs[:ng_count_target])

        self.good = 0
        self.bad = 0
        for i, c in enumerate(self.cards):
            if i in ng_idxs:
                c.set_ng(); self.bad += 1
            else:
                c.set_good(); self.good += 1

        self.has_results = True
        self._refresh_summary()

    # ---- helpers ----
    def _find_test_image(self) -> str | None:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        test_dir = os.path.join(base_dir, "test_image")
        exts = ["*.png", "*.jpg", "*.jpeg", "*.bmp", "*.gif", "*.tif", "*.tiff", "*.webp"]
        candidates = []
        if os.path.isdir(test_dir):
            for ext in exts:
                candidates.extend(glob.glob(os.path.join(test_dir, ext)))
        # also allow a single file like test_image.png in base_dir
        for ext in [".png",".jpg",".jpeg",".bmp",".gif",".tif",".tiff",".webp"]:
            p = os.path.join(base_dir, f"test_image{ext}")
            if os.path.isfile(p): candidates.append(p)
        return candidates[0] if candidates else None
      
    def start_capture_flow(self):
        # 1) Ask for number of cameras
        devs = hik_capture.list_devices()
        if not devs:
            QtWidgets.QMessageBox.critical(self, "No Cameras", "No Hikrobot cameras detected.")
            return

        n_max = min(8, len(devs))
        num, ok = QtWidgets.QInputDialog.getInt(
            self, "Select Cameras", f"How many cameras? (Available: {len(devs)})",
            min(1, n_max), 1, n_max, 1
        )
        if not ok:
            return

        # auto-pick first N device indices
        cam_indices = [d.index for d in devs[:num]]

        # 2) Ask frames per camera
        frames, ok2 = QtWidgets.QInputDialog.getInt(
            self, "Frames", "Frames per camera:", 5, 1, 9999, 1
        )
        if not ok2:
            return

        # 3) Prepare UI grid for 'num' cameras
        self._build_cards(num)
        self.has_results = True
        self._refresh_summary()  # keeps counts neutral

        # 4) Choose output base dir (next to live.py: captures/)
        base_dir = os.path.dirname(os.path.abspath(__file__))
        out_dir = os.path.join(base_dir, "captures")

        # 5) Launch worker thread
        self._cap_thread = QtCore.QThread(self)
        self._cap_worker = CaptureWorker(cam_indices, frames, out_dir, mirror=False)
        self._cap_worker.moveToThread(self._cap_thread)
        self._cap_thread.started.connect(self._cap_worker.run)
        self._cap_worker.frameCaptured.connect(self._on_frame_captured_and_enqueue)
        self._cap_worker.error.connect(self._on_capture_error)
        self._cap_worker.finished.connect(self._on_capture_finished)
        self._cap_worker.finished.connect(self._cap_thread.quit)
        self._cap_worker.finished.connect(self._cap_worker.deleteLater)
        self._cap_thread.finished.connect(self._cap_thread.deleteLater)
        self._cap_thread.start()
        QtWidgets.QMessageBox.information(self, "Capture", f"Capturing {frames} frame(s) from {num} camera(s).")

    @_pyqtSlot(int, int, str)  # cam_index, frame_index, img_path
    def _on_frame_captured_and_infer(self, cam_index: int, frame_index: int, img_path: str):
        if not img_path or not os.path.isfile(img_path):
            print("[infer] error: bad image path:", img_path)
            return
        if not self._infer_cfg.get("backend") or not self._infer_cfg.get("weights"):
            QtWidgets.QMessageBox.critical(self, "Inference Not Configured",
                "Backend/weights missing. Click Start Live again.")
            return
          
    @QtCore.pyqtSlot(int, int, str)  # cam_index, frame_idx, img_path
    def _on_frame_captured_and_enqueue(self, cam_index: int, frame_idx: int, img_path: str):
        if not img_path or not os.path.isfile(img_path):
            print("[capture] bad path:", img_path)
            return

        # DO NOT show raw image now – let inference decide what to show
        # Just queue for inference
        self._pending.append((cam_index, img_path))

        # Immediately try to start inference (if none currently running)
        self._kick_next_inference()



    def _on_capture_error(self, msg: str):
        QtWidgets.QMessageBox.critical(self, "Capture Error", msg)

    @QtCore.pyqtSlot()
    def _on_capture_finished(self):
        # start sequential inference over the queued images
        self._kick_next_inference()
        
    @QtCore.pyqtSlot(int, str, bool, str)
    def _apply_infer_result(self, cam_index: int, overlay_path: str, is_ng: bool, score_text: str):
        card_idx = self._dev_map.get(cam_index, 0) if hasattr(self, "_dev_map") else cam_index
        card_idx = max(0, min(card_idx, len(self.cards) - 1))
        card = self.cards[card_idx] if self.cards else None
        if card:
            # show overlay image (final)
            card.set_image(overlay_path)
            if is_ng:
                card.set_ng(); self.bad += 1
            else:
                card.set_good(); self.good += 1
            try:
                card.score.setText(f"📊 Score: {score_text}")
            except Exception:
                pass

        self.has_results = True
        self._refresh_summary()

        # mark this inference complete and trigger the next one
        self._inflight = False
        QtCore.QTimer.singleShot(0, self._kick_next_inference)

        
    def _prompt_infer_options(self) -> bool:
        # 1) backend
        backend, ok = QtWidgets.QInputDialog.getItem(
            self, "Choose Backend", "Inference engine:", ["YOLO", "Detectron"], 0, False
        )
        if not ok:
            return False

        # 2) weights
        wpath, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select Weight File", "", "All Files (*.*)"
        )
        if not wpath:
            return False

        num_classes = None
        if backend.lower() == "detectron":
            nc, ok2 = QtWidgets.QInputDialog.getInt(
                self, "Detectron Classes", "Number of classes (NUM_CLASSES):", 5, 1, 100, 1
            )
            if not ok2: return False
            num_classes = nc

        self._infer_cfg["backend"] = backend.lower()
        self._infer_cfg["weights"] = wpath
        self._infer_cfg["num_classes"] = num_classes
        # optional: device (leave None to let inference.py decide or set "cuda"/"cpu")
        self._infer_cfg["device"] = None
        # make a fresh temp out dir per run
        self._infer_cfg["out_dir"] = tempfile.mkdtemp(prefix="live_infer_")
        return True
    
    @QtCore.pyqtSlot(int)
    def _on_cycle_tick(self, n: int):
        self.cycle_count = n
        self.lblCycle.setText(f"⚡ Cycle: {n}")
        
    def _stop_capture_thread(self):
        """Gracefully stop the capture worker when closing the window."""
        # Ask the worker to stop its loop
        if hasattr(self, "_cap_worker") and self._cap_worker is not None:
            try:
                self._cap_worker.stop()
            except Exception as e:
                print("[live] error while stopping worker:", e)

        # Stop the thread itself
        if hasattr(self, "_cap_thread") and self._cap_thread is not None:
            self._cap_thread.quit()
            self._cap_thread.wait(2000)

    def closeEvent(self, event):
        """Stop capture and join the worker thread when the window closes."""
        self._stop_capture_thread()
        super().closeEvent(event)


    # def start_capture_and_infer_flow(self):
    #     # 1) how many cameras?
    #     devs = hik_capture.list_devices()
    #     if not devs:
    #         QtWidgets.QMessageBox.critical(self, "No Cameras", "No Hikrobot cameras detected.")
    #         return
    #     n_max = min(8, len(devs))
    #     num, ok = QtWidgets.QInputDialog.getInt(
    #         self, "Cameras", f"How many cameras? (available: {len(devs)})", min(1, n_max), 1, n_max, 1
    #     )
    #     if not ok: return
    #     cam_indices = [d.index for d in devs[:num]]  # cards = cameras

    #     # 2) frames per camera
    #     frames, ok2 = QtWidgets.QInputDialog.getInt(
    #         self, "Frames", "Images per camera:", 5, 1, 9999, 1
    #     )
    #     if not ok2: return

    #     # 3) inference options
    #     if not self._prompt_infer_options():
    #         return

    #     # 4) build UI cards = number of cameras
    #     self._build_cards(num)
    #     self.has_results = True
    #     self._refresh_summary()

    #     # 5) map MVS index to displayed position
    #     self._dev_map = {d.index: i for i, d in enumerate(devs[:num])}

    #     # 6) base capture dir
    #     base_dir = os.path.dirname(os.path.abspath(__file__))
    #     self._capture_out = os.path.join(base_dir, "captures")
    #     os.makedirs(self._capture_out, exist_ok=True)

    #     # 7) start capture worker (frames will call back per-image)
    #     self._cap_thread = QtCore.QThread(self)
    #     self._cap_worker = CaptureWorker(cam_indices, frames, self._capture_out, mirror=False)
    #     self._cap_worker.moveToThread(self._cap_thread)
    #     self._cap_thread.started.connect(self._cap_worker.run)
    #     self._cap_worker.frameCaptured.connect(self._on_frame_captured_and_enqueue)
    #     self._cap_worker.error.connect(self._on_capture_error)
    #     self._cap_worker.finished.connect(self._on_capture_finished)
    #     self._cap_worker.finished.connect(self._cap_thread.quit)
    #     self._cap_worker.finished.connect(self._cap_worker.deleteLater)
    #     self._cap_thread.finished.connect(self._cap_thread.deleteLater)
    #     self._cap_thread.start()
    #     QtWidgets.QMessageBox.information(
    #         self, "Capture", f"Capturing {frames} image(s) from {num} camera(s)…\n"
    #                         f"Engine: {self._infer_cfg['backend'].upper()}"
    #     )
        
    def _infer_one_and_update(self, cam_index: int, image_path: str):
        try:
            backend = self._infer_cfg["backend"]
            weights = self._infer_cfg["weights"]
            out_dir = self._infer_cfg["out_dir"]
            num_classes = self._infer_cfg["num_classes"]

            overlay_path, is_ng, score_txt = self._run_inference_on_image(
                backend=backend, weights=weights, image_path=image_path,
                out_dir=out_dir, num_classes=num_classes
            )

            # update UI on main thread
            def _apply():
                pos = self._dev_map.get(cam_index, 0)
                if 0 <= pos < len(self.cards):
                    card = self.cards[pos]
                    if overlay_path and os.path.isfile(overlay_path):
                        card.set_image(overlay_path)
                    else:
                        card.set_image(image_path)  # fallback
                    # mark status
                    if is_ng:
                        self.bad += 1; card.set_ng()
                    else:
                        self.good += 1; card.set_good()
                    self._refresh_summary()
            QtCore.QTimer.singleShot(0, _apply)
        except Exception as e:
            print(f"[infer] error: {e}")
            
    def _run_inference_on_image(self, backend: str, weights: str, image_path: str,
                                out_dir: str, num_classes: int | None):
        """
        Live-fast path:
        - YOLO: reuse a single GPU model instance, no JSON/CSV, return overlay path.
        - Detectron path remains as-is (if you use it live, consider a similar cache).
        """
        overlay = None
        is_ng = False
        score_text = "—"

        try:
            if backend == "yolo":
                # 1) Build once + keep on GPU
                self._ensure_yolo(weights)
                # 2) Predict + save overlay only (fast)
                overlay, is_ng, score_text = self._yolo_predict_and_save(image_path, out_dir)
            else:
                # (optional) keep your detectron code path; consider caching like YOLO
                import Inference as infer
                res = infer.detectron_infer(weights=weights, source=image_path, out_dir=out_dir,
                                            num_classes=(num_classes or 1))
                # fall back to discovering overlay; but detectron path is usually slower
                stem = os.path.splitext(os.path.basename(image_path))[0]
                candidates = [os.path.join(out_dir, "images", stem + ext) for ext in (".jpg",".png",".jpeg",".bmp")]
                overlay = next((p for p in candidates if os.path.isfile(p)), None)
        except Exception as e:
            print("[live fast] inference error:", e)

        return overlay, is_ng, score_text



    def _ask_backend_and_weights(self) -> bool:
        # 1) backend choice
        backend, ok = QtWidgets.QInputDialog.getItem(
            self, "Select Backend", "Inference backend:",
            ["yolo", "detectron"], 0, False
        )
        if not ok:
            return False

        # 2) weights path
        weights, ok = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select Weights File", "", "Model files (*.pt *.pth);;All files (*)"
        )
        if not ok or not weights:
            return False

        # 3) detectron num_classes (YOLO ignores)
        num_classes = None
        if backend == "detectron":
            num_classes, ok = QtWidgets.QInputDialog.getInt(
                self, "Detectron Classes", "Number of classes:", 5, 1, 999, 1
            )
            if not ok:
                return False

        # CUDA default (no UI). Inference.py already falls back if needed.
        self._infer_cfg["backend"] = backend
        self._infer_cfg["weights"] = weights
        self._infer_cfg["num_classes"] = num_classes
        self._infer_cfg["device"] = "cuda"   # <—— default; Inference.py handles fallback
        return True



    def _start_live_flow(self):
        # Get connected cameras first
        devs = hik_capture.list_devices()
        if not devs:
            QtWidgets.QMessageBox.critical(self, "No Cameras", "No Hikrobot cameras detected.")
            return

        n_max = min(8, len(devs))

        # --- SINGLE combined dialog ---
        dlg = LiveConfigDialog(max_cams=n_max, parent=self)
        result = dlg.exec() if PYQT6 else dlg.exec_()
        if result != QtWidgets.QDialog.Accepted:
            return

        cfg = dlg.get_values()
        backend      = cfg["backend"]        # "yolo" or "detectron"
        weights      = cfg["weights"]
        num_cams     = cfg["num_cams"]
        num_classes  = cfg["num_classes"]    # None for YOLO

        # Save inference config
        self._infer_cfg["backend"]     = backend
        self._infer_cfg["weights"]     = weights
        self._infer_cfg["num_classes"] = num_classes
        self._infer_cfg["device"]      = "cuda"  # Inference.py will fallback if needed
        self._infer_cfg["out_dir"]     = tempfile.mkdtemp(prefix="live_infer_")

        # Sidebar – don’t leave inspection blank
        self.lblInsp.setText(f"🔍 Inspection: {backend.upper()}")

        # Pick the first N camera indices
        cam_indices = [d.index for d in devs[:num_cams]]

        # Capture output dir
        base_dir = os.path.dirname(os.path.abspath(__file__))
        out_dir  = os.path.join(base_dir, "captures")
        os.makedirs(out_dir, exist_ok=True)

        # Continuous mode: frames=0  -> CaptureWorker loop forever
        self._make_capture_bridge(cam_indices, frames=0, out_dir=out_dir, mirror=False)

        QtWidgets.QMessageBox.information(
            self, "Capture",
            f"Starting continuous capture from {num_cams} camera(s) with {backend.upper()}.\n"
            f"Press Ctrl+C or close the window to stop."
        )



    # def _capture_more_flow(self):
    #     """
    #     Reuse current config; ask only for additional frames and start capture again.
    #     """
    #     if not self._infer_cfg.get("backend") or not self._infer_cfg.get("weights"):
    #         QtWidgets.QMessageBox.warning(self, "Not Configured",
    #                                       "Start a run first to set backend and weights.")
    #         return

    #     num_frames, ok = QtWidgets.QInputDialog.getInt(
    #         self, "Frames per Camera", "Enter number of images to capture per camera:",
    #         3, 1, 10000, 1
    #     )
    #     if not ok:
    #         return

    #     self.num_frames = num_frames
    #     if not self._dev_map or self.num_cams <= 0:
    #         # fallback if cards were cleared
    #         self.num_cams = max(1, len(self.cards))
    #         self._dev_map = {i: i for i in range(self.num_cams)}

    #     self.btnStart.setEnabled(False)
    #     self.btnCaptureMore.setEnabled(False)
    #     self._start_capture_async(self.num_cams, self.num_frames)
        
    def _make_capture_bridge(self, cam_indices, frames, out_dir, mirror=False):
        """
        Build cards, prepare cam->card map, and spin the CaptureWorker thread.
        If frames <= 0: continuous mode (infinite loop).
        """
        # UI grid & summary
        self._build_cards(len(cam_indices))
        self.has_results = True
        self._refresh_summary()

        # map each camera index to its card position
        self._dev_map = {cam_idx: i for i, cam_idx in enumerate(cam_indices)}
        self.num_cams = len(cam_indices)
        self.num_frames = frames if frames is not None else 0

        # 🔹 build per-camera exp/gain maps from Mongo overrides (if available)
        exp_map: dict[int, float] = {}
        gain_map: dict[int, float] = {}
        for cam_idx in cam_indices:
            ov = self._mvs_overrides.get(cam_idx) if hasattr(self, "_mvs_overrides") else None
            if not ov:
                continue
            if "ExposureTime" in ov:
                exp_map[cam_idx] = float(ov["ExposureTime"])
            if "Gain" in ov:
                gain_map[cam_idx] = float(ov["Gain"])

        # thread + worker
        self._cap_thread = QtCore.QThread(self)
        self._cap_worker = CaptureWorker(
            cam_indices,
            frames,
            out_dir,
            mirror=mirror,
            exposure_map=exp_map,
            gain_map=gain_map,
        )
        self._cap_worker.moveToThread(self._cap_thread)

        self._cap_thread.started.connect(self._cap_worker.run)
        self._cap_worker.frameCaptured.connect(self._on_frame_captured_and_enqueue)
        self._cap_worker.error.connect(self._on_capture_error)
        self._cap_worker.cycleTick.connect(self._on_cycle_tick)   # NEW

        # finished is only used in finite mode; in continuous mode it never fires
        self._cap_worker.finished.connect(self._on_capture_finished)
        self._cap_worker.finished.connect(self._cap_thread.quit)
        self._cap_worker.finished.connect(self._cap_worker.deleteLater)
        self._cap_thread.finished.connect(self._cap_thread.deleteLater)

        self._cap_thread.start()


    def _kick_next_inference(self):
        """Start next pending image (if any) and nothing currently running."""
        if not self._infer_cfg.get("out_dir"):
            self._infer_cfg["out_dir"] = tempfile.mkdtemp(prefix="live_infer_")
        os.makedirs(self._infer_cfg["out_dir"], exist_ok=True)
        if self._inflight:
            return
        if not self._pending:
            # nothing left
            return

        cam_index, img_path = self._pending.popleft()

        # safety: inference config must be present
        if not self._infer_cfg.get("backend") or not self._infer_cfg.get("weights"):
            QtWidgets.QMessageBox.critical(self, "Inference Not Configured",
                "Backend/weights missing. Click Start Live again.")
            return

        backend     = self._infer_cfg["backend"]
        weights     = self._infer_cfg["weights"]
        out_dir     = self._infer_cfg["out_dir"]
        num_classes = self._infer_cfg.get("num_classes")

        self._inflight = True
        fut = self._infer_pool.submit(
            self._run_inference_on_image, backend, weights, img_path, out_dir, num_classes
        )

        def _done(f):
            try:
                overlay, is_ng, score_text = f.result()
            except Exception as e:
                print("[infer] worker error:", e)
                overlay, is_ng, score_text = None, False, "—"
            # emit back to UI thread
            self.infer_result.emit(cam_index, overlay or img_path, is_ng, score_text)

        fut.add_done_callback(_done)
        
    def start_from_config(self, devs, cfg: dict):
        """
        Start capture + inference using a pre-filled config dict:
        cfg = {
            'backend': 'yolo' or 'detectron',
            'weights': 'path/to/weights',
            'num_cams': int,
            'num_classes': int or None,
            # optional: 'frames_per_cam': int (if >0, finite; if missing/<=0, continuous)
        }
        """
        backend      = cfg["backend"]
        weights      = cfg["weights"]
        num_cams     = cfg["num_cams"]
        num_classes  = cfg.get("num_classes")
        frames       = cfg.get("frames_per_cam", 0)   # 0 => continuous

        # Save inference config
        self._infer_cfg["backend"]     = backend
        self._infer_cfg["weights"]     = weights
        self._infer_cfg["num_classes"] = num_classes  # None for YOLO
        self._infer_cfg["device"]      = "cuda"
        self._infer_cfg["out_dir"]     = tempfile.mkdtemp(prefix="live_infer_")

        self.lblInsp.setText(f"🔍 Inspection: {backend.upper()}")

        # Pick first N devices
        cam_indices = [d.index for d in devs[:num_cams]]

        base_dir = os.path.dirname(os.path.abspath(__file__))
        out_dir  = os.path.join(base_dir, "captures")
        os.makedirs(out_dir, exist_ok=True)

        # Build cards = num_cams and start CaptureWorker
        self._make_capture_bridge(cam_indices, frames, out_dir, mirror=False)

        QtWidgets.QMessageBox.information(
            self, "Capture",
            f"{'Continuous' if frames <= 0 else f'{frames} frame(s) per camera'} "
            f"from {num_cams} camera(s) with {backend.upper()}."
        )


    # ---- misc ----
    def _tick(self):
        sec = int(time.time() - self.start_time)
        hh = sec // 3600
        mm = (sec % 3600) // 60
        ss = sec % 60
        self.lblUptime.setText(f"⏱️ Uptime: {hh:02d}:{mm:02d}:{ss:02d}")

    def showEvent(self, event):
        super().showEvent(event)
        self.setWindowOpacity(0)
        self._fade_in = QPropertyAnimation(self, b"windowOpacity")
        self._fade_in.setDuration(600)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)
        self._fade_in.setEasingCurve(QEasingCurve.Type.OutCubic if PYQT6 else QEasingCurve.OutCubic)
        self._fade_in.start()

# ----------------------------- Entrypoint -----------------------------
# ----------------------------- Entrypoint -----------------------------
if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    app.setOrganizationName("Live_ui")
    app.setApplicationName("Live Inspection UI")

    font = app.font()
    font.setPointSize(10)
    font.setFamily("SF Pro Display")
    app.setFont(font)

    # 🔹 1) Check MongoDB connection
    if not ensure_mongo_connected():
        QtWidgets.QMessageBox.critical(
            None,
            "MongoDB connection failed",
            "Could not connect to MongoDB at:\n"
            "  mongodb://localhost:27017/\n\n"
            "Database: SmartQC+P\n\n"
            "Please start MongoDB service and try again."
        )
        sys.exit(1)

    # 🔹 2) Load overrides from DB (arena ignored here; use mvs for Hik)
    try:
        arena_overrides, mvs_overrides = load_camera_overrides()
    except Exception as e:
        QtWidgets.QMessageBox.critical(
            None,
            "MongoDB error",
            f"Failed to load camera overrides from MongoDB:\n{e}"
        )
        sys.exit(1)

    w = MainWindow(mvs_overrides=mvs_overrides)
    w.show()
    sys.exit(app.exec() if PYQT6 else app.exec_())

