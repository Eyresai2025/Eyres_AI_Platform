
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


def _app_base_dir() -> Path:
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def _find_logo() -> Path | None:
    media = _app_base_dir() / "Media"
    if not media.exists():
        return None
    for name in ("LOGO-02.png", "logo.png", "Logo.png", "logo@2x.png"):
        p = media / name
        if p.is_file():
            return p
    for ext in ("*.png", "*.jpg", "*.jpeg", "*.bmp", "*.gif", "*.webp"):
        files = list(media.glob(ext))
        if files:
            return files[0]
    return None

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
    

LIVE_QSS = """
QMainWindow {
  background-color: #020617;
}

/* LEFT SIDEBAR */
#Sidebar {
  background-color: #020617;
  border-right: 1px solid #111827;
}

/* MAIN GRID BACKDROP */
#GridHost {
  background-color: #020617;
}

/* ===== INSPECTION SUMMARY LABEL ===== */
#SummaryHeader {
  color: #9ca3af;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.20em;
  text-transform: uppercase;
  padding-top: 4px;
  padding-bottom: 4px;
}

/* ===== BIG STATUS PILL ===== */
#BigStatus {
  border-radius: 16px;
  padding: 6px 16px;
  font-size: 14px;
  font-weight: 900;
  letter-spacing: 2px;
  text-transform: uppercase;
  text-align: center;
  margin: 0px;
  min-height: 32px;
  min-width: 140px;
}

/* neutral (no result yet) */
#BigStatus[mode="neutral"] {
  background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                            stop:0 #6b7280, stop:1 #4b5563);
  border: 2px solid #9ca3af;
  color: #e5e7eb;
}

/* GOOD pill */
#BigStatus[mode="good"] {
  background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                            stop:0 #22c55e, stop:0.5 #16a34a, stop:1 #15803d);
  border: 2px solid #22c55e;
  color: #ffffff;
}

/* NG pill */
#BigStatus[mode="ng"] {
  background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                            stop:0 #ef4444, stop:0.5 #dc2626, stop:1 #b91c1c);
  border: 2px solid #ef4444;
  color: #ffffff;
}

/* ===================== SUMMARY TILES (GOOD / BAD / RR / TOTAL) ===================== */

#SummaryContainer {
  background: transparent;
  border: none;
}

/* each tile frame */
QFrame#SummaryTile {
  background-color: #020617;
  border-radius: 12px;
  border: 1px solid #1e293b;
  padding: 4px 10px 8px 10px;
  margin-bottom: 6px;
}

/* colored top line per tile */
#SummaryLineGood {
  background-color: #16a34a;      /* green */
  border-radius: 2px;
}
#SummaryLineBad {
  background-color: #dc2626;      /* red */
  border-radius: 2px;
}
#SummaryLineRR {
  background-color: #eab308;      /* yellow */
  border-radius: 2px;
}
#SummaryLineTotal {
  background-color: #6b7280;      /* grey */
  border-radius: 2px;
}

/* label + value inside each tile */
#SummaryName {
  color: #e5e7eb;
  font-weight: 600;
  font-size: 11px;
}

#SummaryValue {
  color: #f9fafb;
  font-weight: 800;
  font-size: 15px;   /* bigger numbers */
  font-family: "Consolas","SF Mono","Roboto Mono",monospace;
}

/* ===== RESET + BYPASS AREA ===== */
#ResetButton {
  background-color: #fef2f2;
  border: 1px solid #ef4444;
  border-radius: 6px;
  color: #b91c1c;
  font-weight: 600;
  font-size: 11px;
  padding: 4px 6px;
}
#ResetButton:hover {
  background-color: #fee2e2;
}

/* ===== SMALL INFO CARDS (UPTIME / CYCLE / INSPECTION) ===== */
#InfoCard {
    background-color: #020617;
    border-radius: 8px;
    border: 1px solid #1f2937;
    padding: 4px 8px;
}
#InfoLabel {
  color: #9ca3af;
  font-size: 11px;
  font-weight: 600;
}
#InfoValue {
  color: #e5e7eb;
  font-size: 13px;
  font-weight: 700;
}

/* ==== CAMERA CARDS ==== */
#Card {
  background-color: #020617;
  border-radius: 18px;
  border: 1px solid #1e293b;  /* neutral border */
}
#Card > QFrame, #Card {
  border-radius: 18px;
}
/* GOOD card = green border */
#Card[good="true"] {
  border: 2px solid #22c55e;
}
/* NG card = red border */
#Card[ng="true"] {
  border: 2px solid #ef4444;
}

/* Camera title + NG count */
#CardTitle {
  color: #e5e7eb;
  font-weight: 600;
  font-size: 12px;
}
#CardRight {
  color: #fca5a5;  /* red-ish NG counter */
  font-weight: 600;
  font-size: 11px;
}

/* Status chip */
#StatusLabel {
  padding: 4px 10px;
  border-radius: 10px;
  font-size: 10px;
  font-weight: 700;
}
#StatusLabel[ok="true"] {
  background-color: rgba(22, 163, 74, 0.18);
  border: 1px solid #22c55e;
  color: #bbf7d0;
}
#StatusLabel[ng="true"] {
  background-color: rgba(220, 38, 38, 0.18);
  border: 1px solid #ef4444;
  color: #fecaca;
}
#StatusLabel[na="true"] {
  background-color: rgba(30, 64, 175, 0.18);
  border: 1px solid #1d4ed8;
  color: #bfdbfe;
}

/* Image box */
#ImageBox {
  border-radius: 14px;
  border: 1px dashed #1e293b;
  background-color: #020617;
  color: #6b7280;
  font-size: 12px;
  font-weight: 500;
}

/* Bottom row text */
#BottomRow {
  color: #6b7280;
  font-size: 11px;
}
"""



LIVE_QSS += """
/* CARD CONTAINER */
#Card {
  background-color: #020617;
  border-radius: 18px;
  border: 1px solid #1e293b;  /* neutral border */
}

/* Glow can stay, but keep shadow subtle */
#Card > QFrame, #Card {
  border-radius: 18px;
}

/* GOOD card = green border */
#Card[good="true"] {
  border: 2px solid #22c55e;
}

/* NG card = red border */
#Card[ng="true"] {
  border: 2px solid #ef4444;
}

/* Camera title + NG count */
#CardTitle {
  color: #e5e7eb;
  font-weight: 600;
  font-size: 12px;
}
#CardRight {
  color: #fca5a5;  /* red-ish NG counter */
  font-weight: 600;
  font-size: 11px;
}

/* Status chip */
#StatusLabel {
  padding: 4px 10px;
  border-radius: 10px;
  font-size: 10px;
  font-weight: 700;
}
#StatusLabel[ok="true"] {
  background-color: rgba(22, 163, 74, 0.18);
  border: 1px solid #22c55e;
  color: #bbf7d0;
}
#StatusLabel[ng="true"] {
  background-color: rgba(220, 38, 38, 0.18);
  border: 1px solid #ef4444;
  color: #fecaca;
}
#StatusLabel[na="true"] {
  background-color: rgba(30, 64, 175, 0.18);
  border: 1px solid #1d4ed8;
  color: #bfdbfe;
}

/* Image box */
#ImageBox {
  border-radius: 14px;
  border: 1px dashed #1e293b;
  background-color: #020617;
  color: #6b7280;
  font-size: 12px;
  font-weight: 500;
}

/* Bottom row text */
#BottomRow {
  color: #6b7280;
  font-size: 11px;
}
"""

LIVE_QSS += """
/* ===== METRIC CARDS (Good/Bad/RR/Total) ===== */
#MetricCard {
  background-color: #0b1120;
  border-radius: 10px;
  border: 1px solid #1f2933;
  padding: 4px 10px;
  margin-bottom: 4px;
}

/* coloured top border like your reference image */
#MetricCard[type="good"] {
  border-top: 3px solid #22c55e;
}
#MetricCard[type="bad"] {
  border-top: 3px solid #ef4444;
}
#MetricCard[type="rr"] {
  border-top: 3px solid #eab308;
}
#MetricCard[type="total"] {
  border-top: 3px solid #eab308;
}

/* re-tune summary labels for card style */
#SummaryKey {
  color: #9ca3af;
  font-weight: 600;
  font-size: 10px;
}
#SummaryVal {
  color: #f9fafb;
  font-weight: 800;
  font-size: 14px;
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
        self.title = QtWidgets.QLabel(f"Camera {cam_id}")
        self.title.setObjectName("CardTitle")
        self.right = QtWidgets.QLabel("0")
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
        # root.addWidget(self.status)
        self.status.hide()  # keep the object but never show it

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
        self.status.setText("GOOD")
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


# ----------------------------- Simple Toggle Switch -----------------------------
class ToggleSwitch(QtWidgets.QCheckBox):
    """Small pill-style on/off switch used for Rejection Bypass."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setChecked(False)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(40, 22)  # pill size
        self.setText("")           # no checkbox text

    def paintEvent(self, event):
        radius = self.height() // 2
        center = self.rect().center()

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        # Background
        if self.isChecked():
            bg = QtGui.QColor("#22c55e")   # green
        else:
            bg = QtGui.QColor("#4b5563")   # grey

        painter.setPen(QtGui.QPen(bg))
        painter.setBrush(bg)
        painter.drawRoundedRect(2, 2, self.width() - 4, self.height() - 4, radius, radius)

        # Handle
        handle_r = radius - 3
        if self.isChecked():
            cx = self.width() - radius
        else:
            cx = radius
        cy = center.y()

        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QtGui.QColor("#f9fafb"))
        painter.drawEllipse(QtCore.QPointF(cx, cy), handle_r, handle_r)
        painter.end()



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

# ----------------------------- Main Window -----------------------------
class MainWindow(QtWidgets.QMainWindow):
    # ==== signals (must be class attributes for PyQt) ====
    infer_result = QtCore.pyqtSignal(int, str, bool, str)

    def _make_info_card(self, title_text: str, value_text: str = "—"):
        """Small info row card: title on left, value on right."""
        card = QtWidgets.QFrame()
        card.setObjectName("InfoCard")
        lay = QtWidgets.QHBoxLayout(card)
        lay.setContentsMargins(8, 2, 8, 2)
        lay.setSpacing(4)

        key = QtWidgets.QLabel(title_text)
        val = QtWidgets.QLabel(value_text)

        # bump font size a little
        key_font = key.font()
        key_font.setPointSize(key_font.pointSize() + 1)
        key.setFont(key_font)

        val_font = val.font()
        val_font.setPointSize(val_font.pointSize() + 1)
        val.setFont(val_font)

        key.setStyleSheet("color:#9ca3af; font-weight:600;")
        val.setStyleSheet("color:#f9fafb; font-weight:600;")

        val.setAlignment(AlignRight | AlignVCenter)

        lay.addWidget(key, 1)
        lay.addWidget(val, 0)
        return card, val

    def __init__(self, mvs_overrides: dict[int, dict] | None = None):
        super().__init__()
        self.setWindowTitle("LIVE UI ")

        screen = QtWidgets.QApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            w = min(1300, avail.width())
            h = min(700,  avail.height())
        else:
            w, h = 1366, 768

        self.setMinimumSize(w, h)
        self.resize(w, h)
        self.cycle_count = 0
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
        self._last_is_ng: bool | None = None  # None = no result yet
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
        root.setSpacing(0)
        self.setCentralWidget(central)

        # ---- sidebar ----
        self.sidebar = QtWidgets.QFrame()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(280)

        side = QtWidgets.QVBoxLayout(self.sidebar)
        side.setContentsMargins(16, 16, 16, 16)
        side.setSpacing(14)

        # ============ LOGO HEADER ============
        self.logoLabel = QtWidgets.QLabel()
        self.logoLabel.setObjectName("LiveLogo")
        self.logoLabel.setAlignment(AlignCenter)

        logo_path = _find_logo()
        if logo_path is not None:
            pm = QtGui.QPixmap(str(logo_path))
            if not pm.isNull():
                pm = pm.scaled(220, 80, KeepAspect, Smooth)
                self.logoLabel.setPixmap(pm)
            else:
                self.logoLabel.setText("EyRes.AI")
        else:
            self.logoLabel.setText("EyRes.AI")

        self.logoLabel.setStyleSheet("""
            QLabel#LiveLogo {
                color:#e5e7eb;
                font-size:18px;
                font-weight:800;
            }
        """)
        side.addWidget(self.logoLabel)
        side.addSpacing(8)

        # ===== NEW: "Inspection Summary" label =====
        self.summaryHeader = QtWidgets.QLabel("INSPECTION SUMMARY")
        self.summaryHeader.setObjectName("SummaryHeader")
        side.addWidget(self.summaryHeader)

        # ============ INSPECTION SUMMARY – 4 SMALL TILES (UNCHANGED STYLE) ============
        self.summaryBox = QtWidgets.QWidget(objectName="SummaryContainer")
        summary_layout = QtWidgets.QVBoxLayout(self.summaryBox)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        summary_layout.setSpacing(6)

        def make_tile(title: str, line_obj_name: str, value_label: QtWidgets.QLabel):
            tile = QtWidgets.QFrame()
            tile.setObjectName("SummaryTile")
            v = QtWidgets.QVBoxLayout(tile)
            v.setContentsMargins(6, 6, 6, 6)
            v.setSpacing(4)

            # colored line on top
            line = QtWidgets.QFrame()
            line.setObjectName(line_obj_name)
            if PYQT6:
                line.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
            else:
                line.setFrameShape(QtWidgets.QFrame.NoFrame)
            line.setFixedHeight(3)
            v.addWidget(line)

            # name + value row
            row = QtWidgets.QHBoxLayout()
            name_lbl = QtWidgets.QLabel(title)
            name_lbl.setObjectName("SummaryName")

            value_label.setObjectName("SummaryValue")
            value_label.setAlignment(AlignRight | AlignVCenter)

            row.addWidget(name_lbl)
            row.addStretch(1)
            row.addWidget(value_label)
            v.addLayout(row)

            summary_layout.addWidget(tile)

        # value labels
        self.lblGoodVal  = QtWidgets.QLabel("0")
        self.lblBadVal   = QtWidgets.QLabel("0")
        self.lblRatioVal = QtWidgets.QLabel("0.00%")
        self.lblTotalVal = QtWidgets.QLabel("0")

        make_tile("Good (G)",        "SummaryLineGood",  self.lblGoodVal)
        make_tile("Bad (NG)",        "SummaryLineBad",   self.lblBadVal)
        make_tile("Rej. Ratio (RR)", "SummaryLineRR",    self.lblRatioVal)
        make_tile("Total",           "SummaryLineTotal", self.lblTotalVal)

        side.addWidget(self.summaryBox)
        side.addSpacing(6)

        # ============ Reset button ============
        self.btnReset = QtWidgets.QPushButton("Reset Counts / Images")
        self.btnReset.setObjectName("ResetButton")
        self.btnReset.clicked.connect(self._reset_all)
        side.addWidget(self.btnReset)

        # ============ Rejection Bypass (toggle switch) ============
        bypassRow = QtWidgets.QHBoxLayout()
        self.lblBypass = QtWidgets.QLabel("Rejection Bypass")
        self.lblBypass.setStyleSheet("color:#e5e7eb; font-size:11px; font-weight:600;")
        self.toggleBypass = ToggleSwitch()

        bypassRow.addWidget(self.lblBypass)
        bypassRow.addStretch(1)
        bypassRow.addWidget(self.toggleBypass)

        side.addLayout(bypassRow)
        side.addSpacing(6)

        side.addSpacing(8)

        # ============ Small info cards: Uptime / Cycle / Inspection ============
        self.uptimeCard, self.lblUptimeVal = self._make_info_card("Uptime", "00:00:00")
        self.cycleCard,  self.lblCycleVal  = self._make_info_card("Cycle", "0")
        self.inspCard,   self.lblInspVal   = self._make_info_card("Inspection", "idle")

        side.addWidget(self.uptimeCard)
        side.addWidget(self.cycleCard)
        side.addWidget(self.inspCard)

        side.addStretch(1)

        # ============ BIG GOOD/NG PILL (UPDATED PILL STYLE) ============
        self.bigStatus = QtWidgets.QLabel("—")
        self.bigStatus.setObjectName("BigStatus")
        self.bigStatus.setAlignment(AlignCenter)
        self.bigStatus.setProperty("mode", "neutral")

        # --- pill dimensions - make wider to fit "GOOD" text ---
        pill_h = 32  # Slightly taller for better appearance
        pill_w = 140  # Fixed width that fits both "GOOD" and "NG" comfortably

        self.bigStatus.setFixedSize(pill_w, pill_h)
        self.bigStatus.setSizePolicy(
            QtWidgets.QSizePolicy.Fixed,
            QtWidgets.QSizePolicy.Fixed
        )

        # Enhanced pill styling - removed text-shadow
        self.bigStatus.setStyleSheet("""
            QLabel#BigStatus {
                border-radius: 16px;  /* Half of height for perfect pill shape */
                padding: 6px 16px;
                font-size: 14px;
                font-weight: 900;
                letter-spacing: 2px;
                text-transform: uppercase;
                text-align: center;
                margin: 0px;
            }
            
            /* neutral (no result yet) */
            QLabel#BigStatus[mode="neutral"] {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                          stop:0 #6b7280, stop:1 #4b5563);
                border: 2px solid #9ca3af;
                color: #e5e7eb;
            }

            /* GOOD pill - Enhanced green gradient */
            QLabel#BigStatus[mode="good"] {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                          stop:0 #22c55e, stop:0.5 #16a34a, stop:1 #15803d);
                border: 2px solid #22c55e;
                color: #ffffff;
            }

            /* NG pill - Enhanced red gradient */
            QLabel#BigStatus[mode="ng"] {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                          stop:0 #ef4444, stop:0.5 #dc2626, stop:1 #b91c1c);
                border: 2px solid #ef4444;
                color: #ffffff;
            }
        """)

        # add centered at bottom of sidebar
        side.addWidget(self.bigStatus, 0, AlignCenter)

        # ---- grid host (camera cards) ----
        self.gridHost = QtWidgets.QWidget()
        self.gridHost.setObjectName("GridHost")
        self.grid = QtWidgets.QGridLayout(self.gridHost)
        self.grid.setHorizontalSpacing(16)
        self.grid.setVerticalSpacing(16)
        self.grid.setContentsMargins(16, 16, 16, 16)
    
        # add sidebar + grid to root layout
        root.addWidget(self.sidebar)
        root.addWidget(self.gridHost, 1)

        self.cards: list[CardWidget] = []
        self.apply_theme()

        # Uptime timer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)

    def apply_theme(self):
        # Apply live UI theme
        self.setStyleSheet(LIVE_QSS)
        self._update_big_status()


    def _prompt_cameras(self, initial: bool = False):
        settings = QtCore.QSettings("Live_ui", "layout")
        prev = int(settings.value("num_cameras", 8))
        num, ok = QtWidgets.QInputDialog.getInt(
            self, "Camera Configuration",
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
        self._last_is_ng = None  
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
        """
        Update the big GOOD / NG pill at the bottom-left.
        Only text + 'mode' property change; QSS handles colors.
        """
        if self._last_is_ng is None:
            self.bigStatus.setText("—")
            self.bigStatus.setProperty("mode", "neutral")
        elif self._last_is_ng:
            self.bigStatus.setText("NG")
            self.bigStatus.setProperty("mode", "ng")
        else:
            self.bigStatus.setText("GOOD")
            self.bigStatus.setProperty("mode", "good")

        self.bigStatus.style().unpolish(self.bigStatus)
        self.bigStatus.style().polish(self.bigStatus)
        self.bigStatus.update()




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
            c.clear()            
            c.set_image(img_path)  

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
    def _ensure_yolo(self, weights: str):
        """
        Lazily create a UnifiedYOLOInferencer and cache it on self.
        Reuse the same model for all images to keep live latency low.
        """
        # If already loaded with same weights, reuse
        if getattr(self, "_yolo_infer", None) is not None and getattr(self, "_yolo_weights", None) == weights:
            return

        import Inference as infer

        # Prefer whatever device is in config; let Inference decide if None
        device = self._infer_cfg.get("device") or None

        # allow_cpu_fallback=True so it still works on machines without CUDA
        self._yolo_infer = infer.UnifiedYOLOInferencer(
            weights=weights,
            device=device,
            allow_cpu_fallback=True
        )
        self._yolo_weights = weights

    def _yolo_predict_and_save(self, image_path: str, out_dir: str):
        """
        Use cached YOLO model to run on a single image and save an overlay.
        Returns: (overlay_path, is_ng, score_text)
        """
        import os
        import cv2
        import Inference as infer  # to access draw_vis

        img = cv2.imread(image_path)
        if img is None:
            raise RuntimeError(f"Cannot read image: {image_path}")

        # Run YOLO (uses the cached self._yolo_infer)
        dets, _ = self._yolo_infer.predict_image(img)

        # Draw overlay
        vis = infer.draw_vis(img, dets)

        # Save under out_dir/images
        img_out_dir = os.path.join(out_dir, "images")
        os.makedirs(img_out_dir, exist_ok=True)
        save_p = os.path.join(img_out_dir, os.path.basename(image_path))
        cv2.imwrite(save_p, vis)

        # Simple NG logic: any detection => NG
        is_ng = len(dets) > 0

        # Build a human-readable score text for the UI
        if dets:
            top = max(dets, key=lambda d: d.get("conf", 0.0))
            cls_name = str(top.get("name", top.get("cls", "?")))
            conf = float(top.get("conf", 0.0))
            score_text = f"{cls_name} {conf:.2f}"
        else:
            score_text = "GOOD"

        return save_p, is_ng, score_text

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
        self._last_is_ng = bool(is_ng)
        self.has_results = True
        self._refresh_summary()

        # mark this inference complete and trigger the next one
        self._inflight = False
        QtCore.QTimer.singleShot(0, self._kick_next_inference)

        
    def _prompt_infer_options(self) -> bool:
        # 1) backend choice
        backend, ok = QtWidgets.QInputDialog.getItem(
            self, "Select Backend", "Inference backend:",
            ["yolo", "detectron"], 0, False
        )
        
        # Ensure main window gets focus back
        self.raise_()
        self.activateWindow()
        
        if not ok:
            return False

        # 2) weights path
        weights, ok = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select Weights File", "", "Model files (*.pt *.pth);;All files (*)"
        )
        
        # Ensure main window gets focus back
        self.raise_()
        self.activateWindow()
        
        if not ok or not weights:
            return False

        # 3) detectron num_classes (YOLO ignores)
        num_classes = None
        if backend == "detectron":
            num_classes, ok = QtWidgets.QInputDialog.getInt(
                self, "Detectron Classes", "Number of classes:", 5, 1, 999, 1
            )
            
            # Ensure main window gets focus back
            self.raise_()
            self.activateWindow()
            
            if not ok:
                return False

        # CUDA default (no UI). Inference.py already falls back if needed.
        self._infer_cfg["backend"] = backend
        self._infer_cfg["weights"] = weights
        self._infer_cfg["num_classes"] = num_classes
        self._infer_cfg["device"] = "cuda"  
        return True
        
    @QtCore.pyqtSlot(int)
    def _on_cycle_tick(self, n: int):
        self.cycle_count = n
        self.lblCycleVal.setText(str(n))
        
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
        self._infer_cfg["device"] = "cuda"  
        return True



    def _start_live_flow(self):
        # Ensure window is visible and focused FIRST
        self.showMaximized()
        self.raise_()
        self.activateWindow()
        
        # Small delay to ensure window is ready
        QtCore.QTimer.singleShot(50, self._start_live_flow_actual)

    def _start_live_flow_actual(self):
        """Actual live flow implementation with window focus management"""
        # Get connected cameras first
        try:
            devs = hik_capture.list_devices()
        except Exception as e:
            print("[live] list_devices error:", e)
            devs = []

        if not devs:
            # NEW: fall back to local folder mode
            QtWidgets.QMessageBox.information(
                self, "No Cameras Detected",
                "No Hikrobot cameras detected.\n\n"
                "Switching to local folder mode (select model + image folder)."
            )
            # Ensure window stays focused after dialog
            self.raise_()
            self.activateWindow()
            self._start_folder_mode()
            return

        # (existing camera logic stays same below here)
        n_max = min(8, len(devs))

        # --- SINGLE combined dialog ---
        dlg = LiveConfigDialog(max_cams=n_max, parent=self)
        
        # Ensure the dialog doesn't minimize the main window
        dlg.setWindowModality(QtCore.Qt.ApplicationModal)
        
        result = dlg.exec() if PYQT6 else dlg.exec_()
        
        # Ensure main window gets focus back after dialog closes
        self.raise_()
        self.activateWindow()
        
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

        # Sidebar – don't leave inspection blank
        self.lblInspVal.setText(backend.upper())

        # Pick the first N camera indices
        cam_indices = [d.index for d in devs[:num_cams]]

        # Capture output dir
        base_dir = os.path.dirname(os.path.abspath(__file__))
        out_dir  = os.path.join(base_dir, "captures")
        os.makedirs(out_dir, exist_ok=True)

        # Continuous mode: frames=0  -> CaptureWorker loop forever
        self._make_capture_bridge(cam_indices, frames=0, out_dir=out_dir, mirror=False)

        # Show final message and ensure window stays focused
        QtWidgets.QMessageBox.information(
            self, "Capture",
            f"Starting continuous capture from {num_cams} camera(s) with {backend.upper()}.\n"
            f"Press Ctrl+C or close the window to stop."
        )
        self.raise_()
        self.activateWindow()



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

    def _start_folder_mode(self):
        # Ensure window is visible and focused FIRST
        self.showMaximized()
        self.raise_()
        self.activateWindow()
        
        # Small delay to ensure window is ready
        QtCore.QTimer.singleShot(50, self._start_folder_mode_actual)

    def _start_folder_mode_actual(self):
        """Actual folder mode implementation with window focus management"""
        """
        Offline mode: ask for backend/weights and an image folder,
        then run inference on those images and show them in the cards.
        No cameras needed.
        """
        # 1) Ask backend + weights + (optional) num_classes
        if not self._prompt_infer_options():
            return

        # 2) Ask for folder containing images
        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select Image Folder", ""
        )
        
        # Ensure main window gets focus back after file dialog
        self.raise_()
        self.activateWindow()
        
        if not folder:
            return

        exts = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp")
        image_paths = []
        for root, _, files in os.walk(folder):
            for f in files:
                if os.path.splitext(f)[1].lower() in exts:
                    image_paths.append(os.path.join(root, f))

        if not image_paths:
            QtWidgets.QMessageBox.warning(
                self, "No Images",
                "No image files were found in the selected folder."
            )
            # Ensure window stays focused after dialog
            self.raise_()
            self.activateWindow()
            return

        # 3) Build ONLY ONE card in folder mode
        num_cards = 1
        self._build_cards(num_cards)
        self.has_results = True
        self._refresh_summary()

        # Map all "fake cam indices" to that single card (index 0)
        self._dev_map = {idx: 0 for idx in range(len(image_paths))}

        # 4) Fill inference queue
        self._pending.clear()
        self._inflight = False
        for idx, path in enumerate(image_paths):
            self._pending.append((idx, path))

        # 5) Kick off sequential inference
        self.lblInspVal.setText("FOLDER MODE")
        self._kick_next_inference()

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

        self.lblInspVal.setText(backend.upper())


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
        self.lblUptimeVal.setText(f"{hh:02d}:{mm:02d}:{ss:02d}")


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

