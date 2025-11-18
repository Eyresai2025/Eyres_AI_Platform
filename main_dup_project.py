from typing import Iterable, List
import sys, os, importlib
from pathlib import Path

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt, QEvent, QTimer, QEasingCurve, QRect, QPoint
from PyQt5.QtGui import QPalette, QColor, QPixmap, QPainter, QPen, QFont, QFontMetrics
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QStackedWidget, QFrame, QMessageBox, QSizePolicy, QSplitter
)
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt, QEvent, QTimer, QEasingCurve, QRect, QPoint, QSize
from PyQt5.QtGui import QPalette, QColor, QPixmap, QPainter, QPen, QFont, QFontMetrics, QIcon

from toasts import ToastManager
from app_prefs import AppPrefs
# from project_manager import (
#     ProjectDialog,
#     InspectionProject,
#     load_last_project,
#     load_project_from_folder,
#     save_last_project_path,
# )
from login_window import LoginWindow




# ============================= Helpers =============================

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

def _find_icon(filename: str) -> Path | None:
    """
    Return full path to an icon inside Media/, or None if not found.
    Example filenames you can create in Media:
      - sidebar_capture.png
      - sidebar_annotation.png
      - sidebar_augment.png
      - sidebar_training.png
      - sidebar_roi.png
    """
    media = _app_base_dir() / "Media"
    p = media / filename
    return p if p.is_file() else None



# ============================= UI Bits =============================

class ToolButton(QPushButton):
    def __init__(self, text: str,
                 icon_path: Path | None = None,
                 tooltip: str | None = None):
        super().__init__(text)

        self.full_text = text          # remember label
        self._compact = False          # current mode

        if tooltip:
            self.setToolTip(tooltip)

        self.setFixedHeight(46)
        self.setCursor(Qt.PointingHandCursor)

        # not checkable → no persistent selected state
        self.setCheckable(False)

        if icon_path is not None:
            self.setIcon(QIcon(str(icon_path)))
            self.setIconSize(QSize(20, 20))

        self._apply_style()            # start in expanded mode

    # -------- public API to toggle compact/expanded --------
    def set_compact(self, compact: bool):
        if self._compact == compact:
            return
        self._compact = compact
        self._apply_style()

    # -------- internal: apply the right stylesheet/text ----
    def _apply_style(self):
        if self._compact:
            # icon-only, centered (collapsed sidebar)
            super().setText("")  # hide label
            self.setStyleSheet("""
                QPushButton {
                    background-color: #343a40;
                    color: #f8f9fa;
                    border: 0px solid transparent;
                    border-radius: 16px;
                    padding: 0;                  /* no horizontal text padding */
                    font-size: 13px;
                    font-weight: 600;
                }
                QPushButton::menu-indicator { width: 0px; }
                QPushButton:hover  { background-color: #495057; }
                QPushButton:pressed { background-color: #495057; color: #f8f9fa; }
            """)
        else:
            # icon + text, left aligned (expanded sidebar)
            super().setText(self.full_text)
            self.setStyleSheet("""
                QPushButton {
                    background-color: #343a40;
                    color: #f8f9fa;
                    border: 0px solid transparent;
                    border-radius: 16px;
                    padding: 0 16px;
                    font-size: 13px;
                    font-weight: 600;
                    text-align: left;
                }
                QPushButton::menu-indicator { width: 0px; }
                QPushButton:hover  { background-color: #495057; }
                QPushButton:pressed { background-color: #495057; color: #f8f9fa; }
            """)

class PathwayIndicator(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(64)
        self.setObjectName("PathwayBg")
        self.setStyleSheet("""
            QWidget#PathwayBg { background-color:#495057; border:none; border-bottom:1px solid #6c757d; }
        """)
        self._spec = [
            ("1. Image Capturing", "#0d6efd", "Connect/preview cameras and record images"),
            ("2. Annotation Tool", "#c83a93", "Draw boxes/masks to label data"),
            ("3. Augmentation",   "#ffc107", "Create augmented variants of images"),
            ("4. Training",       "#28a745", "Set hyperparams and start training"),
        ]
        self._active = 1
        self._completed = {0}
        self._labels: List[QLabel] = []
        for text, _, tip in self._spec:
            lab = QLabel(text, self)
            lab.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
            lab.setToolTip(tip)
            lab.setStyleSheet("color:#fff; font-weight:600; font-size:10px; background:transparent;")
            self._labels.append(lab)
        self._margin_left, self._margin_right = 70, 70
        self._circle_d, self._line_y, self._label_gap = 24, 28, 5

    def set_states(self, completed: Iterable[int], active: int):
        self._completed = set(completed)
        self._active = max(0, min(active, len(self._spec)-1))
        self.update()
        self._position_labels()

    def _centers(self) -> List[QPoint]:
        n = len(self._spec)
        w = max(1, self.width() - self._margin_left - self._margin_right)
        xs = [self._margin_left + int(i * (w / (n - 1))) for i in range(n)]
        return [QPoint(x, self._line_y) for x in xs]

    def _position_labels(self):
        centers = self._centers()
        if not centers:
            return
        w = self.width()
        maxw = 140
        for i, lab in enumerate(self._labels):
            cx = centers[i].x()
            half_avail = max(1, min(cx, w - cx))
            lab_w = min(maxw, 2 * half_avail - 6)
            lab_w = max(70, lab_w)
            x = int(cx - lab_w // 2)
            y = self._line_y + (self._circle_d // 2) + self._label_gap
            lab.setGeometry(QRect(x, y, lab_w, 24))
            fm = QFontMetrics(lab.font())
            if fm.horizontalAdvance(lab.text()) > lab_w * 2:
                lab.setText(fm.elidedText(lab.text(), Qt.ElideRight, lab_w))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._position_labels()

    def paintEvent(self, e):
        super().paintEvent(e)
        centers = self._centers()
        if not centers:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        base_pen = QPen(QColor("#d2d6db")); base_pen.setWidth(3)
        p.setPen(base_pen)
        p.drawLine(QPoint(self._margin_left, self._line_y),
                   QPoint(self.width() - self._margin_right, self._line_y))
        active_color = QColor(self._spec[self._active][1])
        prog_pen = QPen(active_color); prog_pen.setWidth(5)
        p.setPen(prog_pen)
        p.drawLine(QPoint(self._margin_left, self._line_y), centers[self._active])
        r = self._circle_d // 2
        for i, c in enumerate(centers):
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#ffffff"))
            p.drawEllipse(c, r + 2, r + 2)
            p.setBrush(QColor(self._spec[i][1]))
            p.drawEllipse(c, r, r)
            if i in self._completed:
                pen = QPen(Qt.white); pen.setWidth(2)
                p.setPen(pen); p.setBrush(Qt.NoBrush)
                p.drawLine(c.x()-6, c.y()+1, c.x()-2, c.y()+6)
                p.drawLine(c.x()-2, c.y()+6, c.x()+6, c.y()-5)
            else:
                p.setPen(Qt.white)
                f = QFont(self.font()); f.setBold(True); p.setFont(f)
                rect = QRect(c.x()-r, c.y()-r, self._circle_d, self._circle_d)
                p.drawText(rect, Qt.AlignCenter, str(i+1))


class CameraPlaceholderWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.camera_widget = None
        self.is_loaded = False
        self._project_root = None 
        v = QVBoxLayout(self); v.setAlignment(Qt.AlignCenter)
        self.loading_label = QLabel("Loading Camera Application...")
        self.loading_label.setStyleSheet("color:#adb5bd; font-size:18px; font-style:italic;")
        v.addWidget(self.loading_label)
        self.load_button = QPushButton("Launch Camera App")
        self.load_button.setStyleSheet("""
            QPushButton { background-color:#007bff; color:#fff; border:none; padding:15px 30px;
                          font-size:16px; font-weight:700; border-radius:8px; }
            QPushButton:hover { background-color:#0056b3; }
        """)
        self.load_button.clicked.connect(self.load_camera_app)
        self.load_button.hide()
        v.addWidget(self.load_button)

    def set_project_root(self, root):
        from pathlib import Path
        if root is None:
            self._project_root = None
        else:
            self._project_root = Path(root)

        # if camera widget already exists, push it
        if self.camera_widget and hasattr(self.camera_widget, "set_project_root"):
            self.camera_widget.set_project_root(self._project_root)


    def load_camera_app(self):
        try:
            sys.path.append(os.path.dirname(__file__))
            try:
                from camera_app import CameraWidget
                self.camera_widget = CameraWidget(self)
            except ImportError as e:
                self.loading_label.setText("❌ Camera app not available")
                self.load_button.show()
                QMessageBox.critical(
                    self, "Import Error",
                    f"Cannot import camera application:\n{str(e)}"
                )
                return

            # NEW: pass current project root to CameraWidget if supported
            if self._project_root is not None and hasattr(self.camera_widget, "set_project_root"):
                self.camera_widget.set_project_root(self._project_root)

            self.loading_label.hide()
            self.load_button.hide()
            self.layout().addWidget(self.camera_widget)
            self.is_loaded = True

            if hasattr(self.camera_widget, 'initialize_camera'):
                self.camera_widget.initialize_camera()

        except Exception as e:
            self.loading_label.setText(f"❌ Error loading camera: {str(e)}")
            self.load_button.show()
            QMessageBox.critical(
                self, "Loading Error",
                f"Failed to load camera application:\n{str(e)}"
            )


    def activate(self):
        if not self.is_loaded:
            self.load_camera_app()


class AnnotationPlaceholderWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.annotation_widget = None
        self.is_loaded = False
        layout = QVBoxLayout(self); layout.setContentsMargins(0,0,0,0); layout.setSpacing(0)
        self.loading_label = QLabel("Loading Annotation Tool...")
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_label.setStyleSheet("color:#adb5bd; font-size:18px; font-style:italic; padding:20px;")
        layout.addWidget(self.loading_label)
        self.load_button = QPushButton("✏️ Launch Annotation Tool")
        self.load_button.setStyleSheet("""
            QPushButton { background:#28a745; color:#fff; border:none; padding:15px 30px;
                          font-size:16px; font-weight:700; border-radius:8px; }
            QPushButton:hover { background:#218838; }
        """)
        self.load_button.clicked.connect(self.load_annotation_tool)
        self.load_button.hide()
        layout.addWidget(self.load_button, 0, Qt.AlignCenter)

    def load_annotation_tool(self):
        try:
            sys.path.append(os.path.dirname(__file__))
            try:
                from annotation_tool import AnnotationTool
                self.annotation_widget = AnnotationTool()
            except ImportError as e:
                self.loading_label.setText("❌ Annotation tool not available")
                self.load_button.show()
                QMessageBox.critical(self, "Import Error", f"Cannot import annotation tool:\n{str(e)}")
                return
            self.loading_label.hide(); self.load_button.hide()
            self.layout().addWidget(self.annotation_widget)
            self.is_loaded = True
            if hasattr(self.annotation_widget, 'initialize_tool'):
                self.annotation_widget.initialize_tool()
        except Exception as e:
            self.loading_label.setText(f"❌ Error loading annotation tool: {str(e)}")
            self.load_button.show()
            QMessageBox.critical(self, "Loading Error", f"Failed to load annotation tool:\n{str(e)}")

    def activate(self):
        if not self.is_loaded:
            self.load_annotation_tool()

    def deactivate(self): pass


class AugmentationPlaceholderWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._aug_window = None
        self._embedded = None
        self.is_loaded = False
        self.setObjectName("AugmentationHost")
        v = QtWidgets.QVBoxLayout(self); v.setContentsMargins(0,0,0,0); v.setSpacing(0)
        self._loading_box = QtWidgets.QWidget()
        lbx = QtWidgets.QVBoxLayout(self._loading_box); lbx.setContentsMargins(0,40,0,0); lbx.setSpacing(10)
        self.loading_label = QtWidgets.QLabel("Loading Augmentation Tool...")
        self.loading_label.setAlignment(QtCore.Qt.AlignCenter)
        self.loading_label.setStyleSheet("color:#adb5bd; font-size:16px; font-style:italic;")
        self.load_button = QtWidgets.QPushButton("Launch Augmentation Tool")
        self.load_button.setFixedHeight(38)
        self.load_button.setCursor(QtCore.Qt.PointingHandCursor)
        self.load_button.setStyleSheet("""
            QPushButton { background:#ffc107; color:#000; border:none; border-radius:8px; font-weight:700; padding:8px 18px; }
            QPushButton:hover { background:#e0a800; }
        """)
        self.load_button.clicked.connect(self.load_augmentation_tool)
        lbx.addWidget(self.loading_label, 0, QtCore.Qt.AlignCenter)
        lbx.addWidget(self.load_button, 0, QtCore.Qt.AlignCenter)
        v.addWidget(self._loading_box)

    def activate(self):
        if not self.is_loaded:
            self.load_augmentation_tool()

    def deactivate(self): pass

    def load_augmentation_tool(self):
        try:
            # Make sure current folder is on sys.path
            here = os.path.dirname(__file__)
            if here not in sys.path:
                sys.path.append(here)

            # ---- Import like annotation_tool does ----
            try:
                from augmentation_tool import AugmentationWizard  # main class name
            except ImportError as e:
                self.loading_label.setText("❌ Augmentation tool not available")
                self.load_button.show()
                QtWidgets.QMessageBox.critical(
                    self,
                    "Import Error",
                    f"Cannot import augmentation tool:\n{str(e)}"
                )
                return

            # Instantiate the tool (handle both with/without parent kwarg)
            try:
                aug_obj = AugmentationWizard(parent=None)
            except TypeError:
                aug_obj = AugmentationWizard()

            central = None
            if hasattr(aug_obj, "centralWidget") and callable(getattr(aug_obj, "centralWidget")):
                try:
                    central = aug_obj.centralWidget()
                except Exception:
                    central = None

            # --- Same embedding logic as before ---
            if central is not None and isinstance(aug_obj, QtWidgets.QMainWindow):
                self._aug_window = aug_obj
                self._aug_window.hide()
                if central is None:
                    central = QtWidgets.QWidget()
                    self._aug_window.setCentralWidget(central)

                self._embedded = central
                self._embedded.setParent(self)

                if self._aug_window.styleSheet():
                    self._embedded.setStyleSheet(self._aug_window.styleSheet())

                if hasattr(self._aug_window, "initialize_tool"):
                    try:
                        self._aug_window.initialize_tool()
                    except Exception as e:
                        print(f"[AugHost] initialize_tool error: {e}")

            else:
                if isinstance(aug_obj, QtWidgets.QWidget):
                    self._embedded = aug_obj
                    self._embedded.setParent(self)
                    if hasattr(self._embedded, "initialize_tool"):
                        try:
                            self._embedded.initialize_tool()
                        except Exception as e:
                            print(f"[AugHost] initialize_tool error: {e}")
                else:
                    raise TypeError("Loaded tool is neither QMainWindow nor QWidget")

            # Replace loading box with embedded tool
            host_layout = self.layout()
            host_layout.removeWidget(self._loading_box)
            self._loading_box.hide()
            self._loading_box.setParent(None)

            host_layout.addWidget(self._embedded)
            self._embedded.setSizePolicy(
                QtWidgets.QSizePolicy.Expanding,
                QtWidgets.QSizePolicy.Expanding
            )
            self.is_loaded = True

        except Exception as e:
            print(f"❌ Failed to load augmentation tool: {e}")
            self.loading_label.setText(f"❌ Error loading augmentation tool:\n{str(e)}")
            self.load_button.show()
            QtWidgets.QMessageBox.critical(
                self,
                "Loading Error",
                f"Failed to load augmentation tool:\n{str(e)}"
            )


    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        if self._embedded:
            self._embedded.resize(self.size())


class TrainingPlaceholderWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._train_window = None
        self._embedded = None
        self.is_loaded = False
        self.setObjectName("TrainingHost")
        v = QtWidgets.QVBoxLayout(self); v.setContentsMargins(0,0,0,0); v.setSpacing(0)
        self._loading_box = QtWidgets.QWidget()
        lbx = QtWidgets.QVBoxLayout(self._loading_box); lbx.setContentsMargins(0,40,0,0); lbx.setSpacing(10)
        self.loading_label = QtWidgets.QLabel("Loading Training Tool...")
        self.loading_label.setAlignment(QtCore.Qt.AlignCenter)
        self.loading_label.setStyleSheet("color:#adb5bd; font-size:16px; font-style:italic;")
        self.load_button = QtWidgets.QPushButton("Launch Training Tool")
        self.load_button.setFixedHeight(38)
        self.load_button.setCursor(QtCore.Qt.PointingHandCursor)
        self.load_button.setStyleSheet("""
            QPushButton { background:#28a745; color:#fff; border:none; border-radius:8px; font-weight:700; padding:8px 18px; }
            QPushButton:hover { background:#218838; }
        """)
        self.load_button.clicked.connect(self.load_training_tool)
        lbx.addWidget(self.loading_label, 0, QtCore.Qt.AlignCenter)
        lbx.addWidget(self.load_button, 0, QtCore.Qt.AlignCenter)
        v.addWidget(self._loading_box)

    def activate(self):
        if not self.is_loaded:
            self.load_training_tool()

    def deactivate(self): pass

    def load_training_tool(self):
        try:
            # Ensure our folder is in sys.path
            here = os.path.dirname(__file__)
            if here not in sys.path:
                sys.path.append(here)

            # Direct import of your class
            try:
                from training_tool import TrainingWindow
            except ImportError as e:
                self.loading_label.setText("❌ Training tool not available")
                self.load_button.show()
                QtWidgets.QMessageBox.critical(
                    self,
                    "Import Error",
                    f"Cannot import training tool:\n{str(e)}"
                )
                return

            # Instantiate the training window (handle parent / no-parent)
            try:
                obj = TrainingWindow(parent=None)
            except TypeError:
                obj = TrainingWindow()

            central = None
            if isinstance(obj, QtWidgets.QMainWindow) and hasattr(obj, "centralWidget"):
                central = obj.centralWidget() if callable(obj.centralWidget) else None
                self._train_window = obj
                self._train_window.hide()

                if central is None:
                    central = QtWidgets.QWidget()
                    self._train_window.setCentralWidget(central)

                self._embedded = central
                self._embedded.setParent(self)
                self._embedded.setPalette(self._train_window.palette())

                if self._train_window.styleSheet():
                    self._embedded.setStyleSheet(self._train_window.styleSheet())

                if hasattr(self._train_window, "initialize_tool"):
                    try:
                        self._train_window.initialize_tool()
                    except Exception as e:
                        print(f"[TrainHost] initialize_tool error: {e}")

            elif isinstance(obj, QtWidgets.QWidget):
                self._embedded = obj
                self._embedded.setParent(self)
                if hasattr(self._embedded, "initialize_tool"):
                    try:
                        self._embedded.initialize_tool()
                    except Exception as e:
                        print(f"[TrainHost] initialize_tool error: {e}")
            else:
                raise TypeError("Loaded training tool is neither QMainWindow nor QWidget")

            # Swap loading UI → embedded training UI
            host_layout = self.layout()
            host_layout.removeWidget(self._loading_box)
            self._loading_box.hide()
            self._loading_box.setParent(None)

            host_layout.addWidget(self._embedded)
            self._embedded.setSizePolicy(
                QtWidgets.QSizePolicy.Expanding,
                QtWidgets.QSizePolicy.Expanding
            )

            # solid bg behind training
            self.setAutoFillBackground(True)
            self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
            pal = self.palette()
            pal.setColor(QtGui.QPalette.Window, QtGui.QColor("#0f1419"))
            self.setPalette(pal)
            self._embedded.setAutoFillBackground(False)
            self._embedded.setAttribute(QtCore.Qt.WA_StyledBackground, False)

            self.is_loaded = True

        except Exception as e:
            print(f"❌ Failed to load training tool: {e}")
            self.loading_label.setText(f"❌ Error loading training tool:\n{str(e)}")
            self.load_button.show()
            QtWidgets.QMessageBox.critical(
                self,
                "Loading Error",
                f"Failed to load training tool:\n{str(e)}"
            )


    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        if self._embedded:
            self._embedded.resize(self.size())


class AspectLogoLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._orig = QPixmap()
        self.setAlignment(Qt.AlignCenter)

    def setPixmap(self, pm: QPixmap):
        self._orig = pm
        super().setPixmap(pm)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if not self._orig.isNull():
            scaled = self._orig.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            super().setPixmap(scaled)


# ============================= ROI Host =============================

# Fallback QSS to mimic your standalone ROI dark theme
_ROI_DEFAULT_QSS = """
QWidget#ROIHost, QWidget#ROI_ROOT { background:#0f1419; }
QFrame, QGroupBox, QWidget[role="panel"] {
    background:#151a20; border:1px solid #2a2f36; border-radius:8px;
}
QLabel { color:#e9ecef; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit,
QListView, QTreeView, QTableView {
    background:#0b1220; color:#e9ecef; border:1px solid #2a3340;
    padding:6px 8px; border-radius:6px; selection-background-color:#0d6efd;
    selection-color:#000;
}
QPushButton {
    background:#233044; color:#e9ecef; border:1px solid #2e3a4a; border-radius:8px; padding:8px 12px;
}
QPushButton:hover { background:#2a3a50; }
QPushButton:pressed { background:#1f2a3c; }

QTabWidget::pane { border:1px solid #2a2f36; }
QTabBar::tab { background:#1a2028; color:#e9ecef; padding:6px 10px;
               border:1px solid #2a2f36; border-bottom:none; }
QTabBar::tab:selected { background:#0f1419; }

QMenuBar, QMenu { background:#151a20; color:#e9ecef; }
QMenu::item:selected { background:#223048; }

QScrollArea, QScrollArea > QWidget > QWidget { background:transparent; }

QScrollBar:vertical { background:#0f1419; width:10px; }
QScrollBar::handle:vertical { background:#2a2f36; min-height:20px; border-radius:5px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0px; }

QScrollBar:horizontal { background:#0f1419; height:10px; }
QScrollBar::handle:horizontal { background:#2a2f36; min-width:20px; border-radius:5px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width:0px; }
"""

def _make_roi_dark_palette() -> QPalette:
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor("#0f1419"))
    pal.setColor(QPalette.Base, QColor("#0f1419"))
    pal.setColor(QPalette.AlternateBase, QColor("#151a20"))
    pal.setColor(QPalette.Button, QColor("#233044"))
    pal.setColor(QPalette.ButtonText, Qt.white)
    pal.setColor(QPalette.Text, Qt.white)
    pal.setColor(QPalette.WindowText, Qt.white)
    pal.setColor(QPalette.Highlight, QColor("#0d6efd"))
    pal.setColor(QPalette.HighlightedText, Qt.black)
    return pal


class ROIPlaceholderWidget(QtWidgets.QWidget):
    """
    Embeds ROI from ROI.py/roi_tool.py and **fences** it from the app's global palette.
    Uses ROI's own stylesheet if exported as ROI_QSS or get_stylesheet(); otherwise uses a dark fallback.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._roi_window = None
        self._embedded = None
        self._roi_mod = None
        self.is_loaded = False

        self.setObjectName("ROIHost")
        self.setAutoFillBackground(True)
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)

        v = QtWidgets.QVBoxLayout(self); v.setContentsMargins(0,0,0,0); v.setSpacing(0)

        self._loading_box = QtWidgets.QWidget()
        lbx = QtWidgets.QVBoxLayout(self._loading_box); lbx.setContentsMargins(0,40,0,0); lbx.setSpacing(12)
        title = QtWidgets.QLabel("Measurements · ROI")
        title.setAlignment(QtCore.Qt.AlignCenter)
        title.setStyleSheet("color:#e9ecef; font-weight:800; font-size:18px;")
        self.loading_label = QtWidgets.QLabel("Load your ROI tool or paste code here.")
        self.loading_label.setAlignment(QtCore.Qt.AlignCenter)
        self.loading_label.setStyleSheet("color:#adb5bd; font-size:14px;")
        self.load_button = QtWidgets.QPushButton("Launch ROI Tool (auto-import ROI.py)")
        self.load_button.setFixedHeight(38)
        self.load_button.setCursor(QtCore.Qt.PointingHandCursor)
        self.load_button.setStyleSheet("""
            QPushButton { background:#17a2b8; color:#fff; border:none; border-radius:8px; font-weight:700; padding:8px 18px; }
            QPushButton:hover { background:#138496; }
        """)
        self.load_button.clicked.connect(self.load_roi_tool)
        hint = QtWidgets.QLabel("Tip: expose ROI_QSS or get_stylesheet() in ROI.py for a perfect theme match.")
        hint.setAlignment(QtCore.Qt.AlignCenter)
        hint.setStyleSheet("color:#94a3b8; font-size:12px; padding:0 16px;")

        for w in (title, self.loading_label, self.load_button, hint):
            lbx.addWidget(w, 0, QtCore.Qt.AlignCenter)
        v.addWidget(self._loading_box)

    # --- fencing & theming
    def _apply_roi_theme(self):
        """Stop app palette bleed and apply ROI-specific theme to the subtree."""
        # root id to scope QSS
        self._embedded.setObjectName("ROI_ROOT")

        # 1) Apply a local **dark** palette only inside ROI subtree (no app-wide side effects)
        roi_pal = _make_roi_dark_palette()
        for w in [self, self._embedded] + self._embedded.findChildren(QtWidgets.QWidget):
            w.setPalette(roi_pal)
            w.setAttribute(QtCore.Qt.WA_StyledBackground, True)

        # 2) Use ROI's stylesheet if available, else fallback
        qss = None
        if self._roi_mod is not None:
            if hasattr(self._roi_mod, "ROI_QSS"):
                qss = getattr(self._roi_mod, "ROI_QSS")
            elif hasattr(self._roi_mod, "get_stylesheet") and callable(getattr(self._roi_mod, "get_stylesheet")):
                try: qss = self._roi_mod.get_stylesheet()
                except Exception: qss = None
        if not qss:
            qss = _ROI_DEFAULT_QSS
        self._embedded.setStyleSheet(qss)

    def activate(self):
        if not self.is_loaded:
            try:
                self.load_roi_tool(auto=True)
            except Exception:
                pass

    def deactivate(self): pass

    def load_roi_tool(self, auto=False):
        try:
            here = os.path.dirname(__file__)
            if here not in sys.path:
                sys.path.append(here)

            # ----- Direct imports instead of importlib loop -----
            try:
                from ROI import ROIWindow
                import ROI as roi_mod
            except ImportError:
                try:
                    from roi_tool import ROIWindow
                    import roi_tool as roi_mod
                except ImportError as e:
                    # Neither ROI nor roi_tool could be imported
                    raise ImportError(f"Could not import ROI.py (or roi_tool.py) from {here}") from e

            self._roi_mod = roi_mod

            # Instantiate ROIWindow (handle parent / no-parent)
            try:
                obj = ROIWindow(parent=None)
            except TypeError:
                obj = ROIWindow()

            # ---- Same embedding logic as before ----
            if isinstance(obj, QtWidgets.QMainWindow) and hasattr(obj, "centralWidget"):
                central = obj.centralWidget() if callable(obj.centralWidget) else None
                self._roi_window = obj
                self._roi_window.hide()

                if central is None:
                    central = QtWidgets.QWidget()
                    self._roi_window.setCentralWidget(central)

                self._embedded = central
                if self._roi_window.styleSheet():  # preserve ROI's own QSS if window provided one
                    self._embedded.setStyleSheet(self._roi_window.styleSheet())

            elif isinstance(obj, QtWidgets.QWidget):
                self._embedded = obj
            else:
                raise TypeError("Loaded ROI tool is neither QMainWindow nor QWidget")

            # swap loading UI
            host = self.layout()
            host.removeWidget(self._loading_box)
            self._loading_box.hide()
            self._loading_box.setParent(None)
            host.addWidget(self._embedded)
            self._embedded.setSizePolicy(
                QtWidgets.QSizePolicy.Expanding,
                QtWidgets.QSizePolicy.Expanding
            )

            # <<< key: fence + theme >>>
            self._apply_roi_theme()

            self.is_loaded = True

        except Exception as e:
            if not auto:
                print(f"❌ Failed to load ROI tool: {e}")
                self.loading_label.setText(f"❌ Error loading ROI tool:\n{str(e)}")
                self.load_button.show()
                QtWidgets.QMessageBox.critical(
                    self,
                    "Loading Error",
                    f"Failed to load ROI tool:\n{str(e)}"
                )



# ============================= Main Window =============================

class MainWindow(QMainWindow):
    def _get_sidebar_width(self) -> int:
        sizes = self.splitter.sizes() if hasattr(self, "splitter") else []
        return sizes[0] if sizes else 0

    def _set_sidebar_width(self, w: int) -> None:
        if not hasattr(self, "splitter"):
            return
        sizes = self.splitter.sizes()
        if not sizes or len(sizes) < 2:
            self.splitter.setSizes([w, max(0, self.width() - w)])
            return
        total = sum(sizes) or max(1, self.width())
        self.splitter.setSizes([w, max(0, total - w)])

    sidebarWidth = QtCore.pyqtProperty(int, fget=_get_sidebar_width, fset=_set_sidebar_width)
        
    def _set_sidebar_compact(self, compact: bool):
        # nav buttons
        for b in getattr(self, "nav_buttons", []):
            b.set_compact(compact)
        # ROI button
        if hasattr(self, "btn_roi") and self.btn_roi is not None:
            self.btn_roi.set_compact(compact)


    def __init__(self):
        super().__init__()
        self.prefs = AppPrefs()
        # self._current_project: InspectionProject | None = None
        self.setWindowTitle("AI Model Training Suite")
        self.setMinimumSize(1100, 700)  # or any size you like
        self.setGeometry(80, 80, 1200, 800)
        self._collapsed_width = 72
        self._anim_ms = 160
        self._auto_collapse_ms = 280
        self._build()
        self._restore_window_session()
        # select last tool (or default to 0 = camera)
        last_idx = max(0, min(self.prefs.get_last_tool_index(0), 4))
        self.switch_tool(last_idx, _from_restore=True)
        try:
            self.toast_info(f"Restored last session: {self._tool_name(last_idx)}", 1400)
        except Exception:
            pass

        # # try restore last project
        # try:
        #     last_path = load_last_project()
        #     if last_path:
        #         proj = load_project_from_folder(last_path)
        #     else:
        #         proj = None
        # except Exception:
        #     proj = None

        # if proj:
        #     self._set_project(proj)
        # else:
        #     # show dialog on first launch
        #     QtCore.QTimer.singleShot(0, self._select_project_dialog)
        # last_idx = max(0, min(self.prefs.get_last_tool_index(0), 4))
        # self.switch_tool(last_idx, _from_restore=True)
        # try:
        #     self.toast_info(f"Restored last session: {self._tool_name(last_idx)}", 1400)
        # except Exception:
        #     pass
    
    # # --- Project helpers ---
    # def current_project(self) -> InspectionProject | None:
    #     """Return the current InspectionProject object or None."""
    #     return self._current_project

    # def current_project_root(self):
    #     """Return Path of current project root or None."""
    #     return self._current_project.root if self._current_project else None
    
    # def _set_project(self, proj: InspectionProject):
    #     self._current_project = proj
    #     self.lbl_project.setText(f"Project: {proj.name}  —  {proj.root}")
    #     save_last_project_path(proj.root)

    #     # propagate to pages that care
    #     if hasattr(self.page_capture, "set_project_root"):
    #         self.page_capture.set_project_root(proj.root)
    #     if hasattr(self.page_annot, "set_project_root"):
    #         self.page_annot.set_project_root(proj.root)
    #     if hasattr(self.page_aug, "set_project_root"):
    #         self.page_aug.set_project_root(proj.root)
    #     if hasattr(self.page_train, "set_project_root"):
    #         self.page_train.set_project_root(proj.root)
    #     if hasattr(self.page_roi, "set_project_root"):
    #         self.page_roi.set_project_root(proj.root)

    # def _select_project_dialog(self):
    #     dlg = ProjectDialog(self)
    #     proj = dlg.exec_and_get()
    #     if proj is None:
    #         # user cancelled – keep current project if any
    #         if not self._current_project:
    #             self.toast_warn("No project selected. Image capturing will be disabled.")
    #         return
    #     self._set_project(proj)
    #     self.toast_success(f"Project selected: {proj.name}")



    def _restore_sidebar(self):
        try: w = max(160, self.prefs.get_sidebar_width(220))
        except Exception: w = 260
        self.splitter.setSizes([w, max(600, self.width() - w)])
        self._expanded_width = w

    def _on_splitter_moved(self, pos: int, index: int):
        try:
            sizes = self.splitter.sizes()
            if sizes and len(sizes) >= 2 and sizes[0] > self._collapsed_width + 2:
                self._expanded_width = sizes[0]
                self.prefs.set_sidebar_width(self._expanded_width)
                self.prefs.save()
        except Exception:
            pass

    def _animate_to(self, target_w: int):
        if not hasattr(self, "_anim"):
            self._anim = QtCore.QPropertyAnimation(self, b"sidebarWidth", self)
        self._anim.stop()
        self._anim.setDuration(self._anim_ms)
        self._anim.setStartValue(self._get_sidebar_width())
        self._anim.setEndValue(target_w)
        self._anim.setEasingCurve(QEasingCurve.InOutQuad)
        self._anim.start()

    def _expand_sidebar(self):
        self._hover_timer.stop()
        w = max(180, getattr(self, "_expanded_width", self.prefs.get_sidebar_width(260)))
        self._animate_to(w)
        self._set_sidebar_compact(False)

    def _collapse_sidebar(self):
        self._animate_to(self._collapsed_width)
        self._set_sidebar_compact(True) 

    def eventFilter(self, obj, ev):
        if obj is self.side:
            if ev.type() == QEvent.Enter: self._expand_sidebar()
            elif ev.type() == QEvent.Leave: self._hover_timer.start(self._auto_collapse_ms)
        return super().eventFilter(obj, ev)

    def _build(self):

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # # --- Project bar at top ---
        # proj_bar = QFrame()
        # proj_bar.setStyleSheet("QFrame { background:#161a1d; border-bottom:1px solid #2b2f33; }")
        # hb = QHBoxLayout(proj_bar)
        # hb.setContentsMargins(10, 6, 10, 6)

        # self.lbl_project = QLabel("Project: (none)")
        # self.lbl_project.setStyleSheet("color:#e9ecef; font-weight:600;")
        # hb.addWidget(self.lbl_project)

        # hb.addStretch(1)

        # self.btn_change_project = QPushButton("Change Project…")
        # self.btn_change_project.setFixedHeight(26)
        # self.btn_change_project.setStyleSheet("""
        #     QPushButton {
        #         background:#0d6efd; color:#fff; border:none; padding:4px 10px;
        #         border-radius:6px; font-size:12px; font-weight:600;
        #     }
        #     QPushButton:hover { background:#0b5ed7; }
        # """)
        # self.btn_change_project.clicked.connect(self._select_project_dialog)
        # hb.addWidget(self.btn_change_project)

        # root.addWidget(proj_bar)

        # --- Splitter ---
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(6)
        self.splitter.setStyleSheet(
            "QSplitter::handle { background:#3a3f44; } "
            "QSplitter::handle:hover { background:#4b5156; }"
        )
        root.addWidget(self.splitter, 1)

        # ================== Sidebar ==================
        self.side = QFrame()
        self.side.setObjectName("Sidebar")
        self.side.setMinimumWidth(120)
        self.side.setMaximumWidth(320)
        self.side.setStyleSheet(
            "QFrame#Sidebar{background-color:#2b2f33; border-right:1px solid #3a3f44;}"
        )
        self.side.setMouseTracking(True)
        self.side.installEventFilter(self)
        sv = QVBoxLayout(self.side)
        sv.setContentsMargins(0, 0, 0, 0)
        sv.setSpacing(0)

        # --- Logo header ---
        header = QFrame()
        header.setFixedHeight(110)
        hv = QHBoxLayout(header)
        hv.setContentsMargins(12, 8, 12, 8)
        hv.setSpacing(0)

        logo_label = AspectLogoLabel()
        logo_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        logo_file = _find_logo()
        if logo_file is not None:
            pm = QPixmap(str(logo_file))
            if not pm.isNull():
                logo_label.setPixmap(pm)
            else:
                logo_label.setStyleSheet("background:#2b2f33; border-radius:8px;")
        else:
            logo_label.setStyleSheet("background:#2b2f33; border-radius:8px;")
        hv.addWidget(logo_label)
        sv.addWidget(header)

        # --- Navigation buttons ---
        nav = QFrame()
        nv = QVBoxLayout(nav)
        nv.setContentsMargins(8, 24, 8, 24)
        nv.setSpacing(10)

        # common pill-style button look (like first screenshot)
        sidebar_btn_style = """
            QPushButton {
                background-color: #343a40;
                color: #f8f9fa;
                border: 0px solid transparent;
                border-radius: 14px;
                padding: 0 16px;
                font-size: 13px;
                font-weight: 600;
                text-align: left;
            }
            QPushButton::menu-indicator { width: 0px; }
            QPushButton:hover {
                background-color: #495057;
            }
            QPushButton:pressed {
                background-color: #0d6efd;
                color: #ffffff;
            }
        """

        # icons live in Media/
        media_dir = _app_base_dir() / "Media"

        # text, index, tooltip, icon filename
        self._buttons_cfg = [
            ("  Image Capturing",  0,
                "Open the camera workspace: connect devices, preview, and record.",
                "sidebar_capture.png"),
            ("  Annotation Tool",  1,
                "Label images (boxes/masks). Saves annotations for training.",
                "sidebar_annotation.png"),
            ("  Augmentation Tool", 2,
                "Generate augmented variants of images for robust training.",
                "sidebar_augment.png"),
            ("  Model Training",   3,
                "Configure hyperparameters and run model training.",
                "sidebar_training.png"),
        ]

        self.nav_buttons = []
        for text, idx, tip, icon_name in self._buttons_cfg:
            icon_path = media_dir / icon_name
            btn = ToolButton(
                text,
                icon_path=icon_path if icon_path.is_file() else None,
                tooltip=tip,
            )
            btn.clicked.connect(lambda _, i=idx: self.switch_tool(i))
            nv.addWidget(btn)
            self.nav_buttons.append(btn)

        # --- Measurements / ROI section ---
        nv.addSpacing(12)
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setStyleSheet("color:#3a3f44;")
        nv.addWidget(line)

        section = QLabel("MEASUREMENTS")
        section.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        section.setStyleSheet(
            "color:#94a3b8; font-size:11px; font-weight:800; "
            "margin:10px 12px 2px 12px; letter-spacing:1px;"
        )
        nv.addWidget(section)

        # keep a reference so we can toggle compact/expanded
        roi_icon_path = media_dir / "sidebar_roi.png"
        self.btn_roi = ToolButton(
            "  ROI",
            icon_path=roi_icon_path if roi_icon_path.is_file() else None,
            tooltip="Region of Interest & Measurements",
        )
        self.btn_roi.clicked.connect(lambda _: self.switch_tool(4))
        nv.addWidget(self.btn_roi)

        nv.addStretch(1)
        sv.addWidget(nav, 1)


        # ================== Main area ==================
        self.main_frame = QFrame()
        self.main_frame.setStyleSheet("QFrame{background:#1f2327;}")
        mv = QVBoxLayout(self.main_frame)
        mv.setContentsMargins(0, 0, 0, 0)
        mv.setSpacing(0)

        self.pathway = PathwayIndicator()
        mv.addWidget(self.pathway)

        self.stack = QStackedWidget()
        self.stack.setStyleSheet("QStackedWidget{background:#23282d;}")
        self.page_capture = CameraPlaceholderWidget(self)
        self.page_annot   = AnnotationPlaceholderWidget(self)
        self.page_aug     = AugmentationPlaceholderWidget(self)
        self.page_train   = TrainingPlaceholderWidget()
        self.page_train.setObjectName("TrainingHostPage")
        self.page_train.setAutoFillBackground(True)
        self.page_train.setStyleSheet("#TrainingHostPage { background: #0f1419; }")
        self.page_roi     = ROIPlaceholderWidget(self)

        for w in (self.page_capture, self.page_annot, self.page_aug, self.page_train, self.page_roi):
            self.stack.addWidget(w)
        mv.addWidget(self.stack, 1)

        self.splitter.addWidget(self.side)
        self.splitter.addWidget(self.main_frame)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self._restore_sidebar()
        self._set_sidebar_compact(self._get_sidebar_width() <= self._collapsed_width + 4)
        # Toasts
        self.toast_mgr = ToastManager.install(self)
        self.toast_info    = lambda msg, ms=2500: self.toast_mgr.show(msg, "info",    ms)
        self.toast_success = lambda msg, ms=2500: self.toast_mgr.show(msg, "success", ms)
        self.toast_warn    = lambda msg, ms=2500: self.toast_mgr.show(msg, "warning", ms)
        self.toast_error   = lambda msg, ms=2500: self.toast_mgr.show(msg, "error",   ms)

        self.pathway.set_states(completed=[0], active=1)
        self.toast_success("Welcome to AI Model Training Suite", 1200)

        self.splitter.splitterMoved.connect(self._on_splitter_moved)
        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.timeout.connect(self._collapse_sidebar)


    def _restore_window_session(self):
            try:
                geo = self.prefs.get_geometry()
                if not geo.isEmpty():
                    # This may try to apply an old (too-small) size
                    self.restoreGeometry(geo)

                    # If restored size ended up smaller than what the layout wants,
                    # grow it to at least the minimum size. Growing is safe and
                    # won't trigger the QWindowsWindow::setGeometry warning.
                    minw, minh = self.minimumSize().width(), self.minimumSize().height()
                    curw, curh = self.width(), self.height()

                    needs_fix = (curw < minw) or (curh < minh)
                    if needs_fix:
                        self.resize(max(curw, minw), max(curh, minh))
                        # Overwrite the old bad geometry so next launch is clean
                        self.prefs.set_geometry(self.saveGeometry())

                st = self.prefs.get_win_state()
                if not st.isEmpty():
                    self.restoreState(st)

                if self.prefs.get_maximized(False):
                    self.showMaximized()

            except Exception:
                # If anything goes wrong, just fall back to default geometry
                pass


    def _save_window_session(self):
        try:
            self.prefs.set_geometry(self.saveGeometry())
            self.prefs.set_win_state(self.saveState())
            self.prefs.set_maximized(self.isMaximized())
            self.prefs.save()
        except Exception:
            pass

    def _tool_name(self, idx: int) -> str:
        return {
            0: "Image Capturing", 1: "Annotation Tool", 2: "Augmentation Tool",
            3: "Model Training", 4: "ROI (Measurements)",
        }.get(idx, f"Tool {idx}")

    def switch_tool(self, index: int, _from_restore: bool=False):
        self.stack.setCurrentIndex(index)
        if index == 0:
            self.page_capture.activate()
            if not _from_restore: self.toast_info("Opening Camera Workspace…")
        elif index == 1:
            self.page_annot.activate()
            if not _from_restore: self.toast_success("Annotation Tool ready.")
        elif index == 2:
            self.page_aug.activate()
            if not _from_restore: self.toast_info("Loading Augmentation Tool…")
        elif index == 3:
            self.page_train.activate()
            if not _from_restore: self.toast_warn("Training feature is in preview.")
        elif index == 4:
            self.page_roi.activate()
            if not _from_restore: self.toast_info("Measurements · ROI")

        self.pathway.set_states(completed=list(range(min(index, 4))), active=min(index, 3))
        if not _from_restore:
            self.prefs.set_last_tool_index(index); self.prefs.save()

    def closeEvent(self, e):
        self._save_window_session()
        super().closeEvent(e)


# ============================= App Theme =============================

def apply_dark_theme(app: QApplication):
    app.setStyle("Fusion")
    dark = QPalette()
    dark.setColor(QPalette.Window, QColor(31, 35, 39))
    dark.setColor(QPalette.WindowText, Qt.white)
    dark.setColor(QPalette.Base, QColor(26, 29, 33))
    dark.setColor(QPalette.AlternateBase, QColor(39, 43, 47))
    dark.setColor(QPalette.ToolTipBase, Qt.white)
    dark.setColor(QPalette.ToolTipText, Qt.white)
    dark.setColor(QPalette.Text, Qt.white)
    dark.setColor(QPalette.Button, QColor(43, 47, 51))
    dark.setColor(QPalette.ButtonText, Qt.white)
    dark.setColor(QPalette.BrightText, QColor(220, 53, 69))
    dark.setColor(QPalette.Highlight, QColor(13, 110, 253))
    dark.setColor(QPalette.HighlightedText, Qt.black)
    app.setPalette(dark)  # ROI subtree overrides this locally
    app.setStyleSheet("""
        QMessageBox { background-color:#343a40; color:#fff; }
        QMessageBox QLabel { color:#fff; }
        QMessageBox QPushButton {
            background-color:#495057; color:#fff; border:1px solid #6c757d;
            padding:8px 15px; border-radius:4px; font-weight:700;
        }
        QMessageBox QPushButton:hover { background-color:#6c757d; }
        QToolTip { background:#ffffff; color:#212529; border-radius:6px; font-size:12px; }
    """)


# ============================= Entrypoint =============================
def after_login(user):
    main_window = MainWindow()
    main_window.show()

def main():
    app = QApplication(sys.argv)
    apply_dark_theme(app)

    login = LoginWindow(on_login_success=after_login)
    login.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
