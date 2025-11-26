from typing import Iterable, List
import sys, os, importlib
from pathlib import Path

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt, QEvent, QTimer, QEasingCurve, QRect, QPoint, QSize
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QStackedWidget, QFrame, QMessageBox, QSizePolicy, QSplitter
)
from PyQt5.QtGui import QPalette, QColor, QPixmap, QPainter, QPen, QFont, QFontMetrics, QIcon

from toasts import ToastManager
from app_prefs import AppPrefs
from login_window import LoginWindow
from dashboard_page import DashboardPage
from machine_page import MachinePage       
from project_page import ProjectPage 
from utils.project_paths import get_project_folder


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

def _find_logo_ico() -> Path | None:
    media = _app_base_dir() / "Media"
    if not media.exists():
        return None

    # try some common names first
    for name in ("app.ico", "Logo.ico", "LOGO.ico", "app.ico", "EyResAI.ico"):
        p = media / name
        if p.is_file():
            return p

    # otherwise, first any .ico in Media
    files = list(media.glob("*.ico"))
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

def _get_app_icon() -> QIcon | None:
    """
    Return the app icon from Media/app.ico (or the first .ico we find),
    or None if nothing exists.
    """
    # Try explicit app.ico
    icon_path = _app_base_dir() / "Media" / "app.ico"
    if icon_path.is_file():
        return QIcon(str(icon_path))

    # Fallback to whatever _find_logo_ico() finds
    ico = _find_logo_ico()
    if ico is not None:
        return QIcon(str(ico))

    return None




# ============================= UI Bits =============================
class ToolButton(QPushButton):
    def __init__(self, text: str,
                 icon_path: Path | None = None,
                 tooltip: str | None = None):
        super().__init__(text)

        self.full_text = text          # remember label
        self._compact = False          # current mode

        self.setCheckable(True)
        self.setAutoExclusive(True)
        if tooltip:
            self.setToolTip(tooltip)

        self.setFixedHeight(34)
        self.setCursor(Qt.PointingHandCursor)

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
            super().setText("")
            self.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #f8f9fa;
                    border: 0px solid transparent;
                    border-radius: 0px;
                    padding: 0;
                    margin: 0;
                    font-size: 13px;
                    font-weight: 600;
                }
                QPushButton:checked {
                    background-color: #0d6efd;
                    color: #ffffff;
                }
                QPushButton::menu-indicator { width: 0px; }
                QPushButton:hover  { background-color: #3b4045; }
                QPushButton:pressed { background-color: #3b4045; color: #f8f9fa; }
            """)
        else:
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
                QPushButton:checked {
                    background-color: #0d6efd;
                    color: #ffffff;
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

    def load_camera_app(self):
        try:
            sys.path.append(os.path.dirname(__file__))
            try:
                from camera_app import CameraWidget
                # --- get active project info from MainWindow / ProjectPage ---
                project_name = None
                project_root = None

                mw = self.window()  # MainWindow
                if mw is not None and hasattr(mw, "get_active_project_info"):
                    try:
                        info = mw.get_active_project_info()
                        if info:
                            project_name, project_root = info
                    except Exception as e:
                        print("[CameraPlaceholderWidget] active project fetch failed:", e)

                self.camera_widget = CameraWidget(
                    parent=self,
                    project_name=project_name,
                    project_root=project_root,
                )
            except ImportError as e:
                self.loading_label.setText("❌ Camera app not available")
                self.load_button.show()
                QMessageBox.critical(
                    self, "Import Error",
                    f"Cannot import camera application:\n{str(e)}"
                )
                return


            self.loading_label.hide()
            self.load_button.hide()
            self.layout().addWidget(self.camera_widget)
            self.is_loaded = True

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
        self._orig_full = QPixmap()
        self._orig_compact = QPixmap()
        self._current_mode = "full"  # 'full' or 'compact'
        self._last_size = QSize()
        self.setAlignment(Qt.AlignCenter)

    def setPixmaps(self, full_pm: QPixmap, compact_pm: QPixmap = None):
        self._orig_full = full_pm
        self._orig_compact = compact_pm if compact_pm else full_pm
        self._current_mode = "full"
        self._last_size = QSize()
        super().setPixmap(full_pm)

    def set_mode(self, mode: str):
        """Set display mode: 'full' or 'compact'"""
        if self._current_mode == mode:
            return
        self._current_mode = mode
        self._last_size = QSize()  # Force rescale
        self._update_pixmap()

    def _update_pixmap(self):
        if self._current_mode == "full" and not self._orig_full.isNull():
            super().setPixmap(self._orig_full)
        elif self._current_mode == "compact" and not self._orig_compact.isNull():
            super().setPixmap(self._orig_compact)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if (self._current_mode == "full" and self._orig_full.isNull()) or \
           (self._current_mode == "compact" and self._orig_compact.isNull()):
            return

        # avoid re-scaling on every tiny animation step
        if self.size() == self._last_size:
            return
        self._last_size = self.size()

        source = self._orig_full if self._current_mode == "full" else self._orig_compact
        scaled = source.scaled(
            self.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        QLabel.setPixmap(self, scaled)

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


class PLCPlaceholderWidget(QtWidgets.QWidget):
    """
    Embeds ModernPLCWindow from PLC_GUI.py into the main stack.
    We reuse its central widget and stylesheet so it looks the same.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._plc_window = None
        self._embedded = None
        self.is_loaded = False

        self.setObjectName("PLC_HOST")
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        self._loading_box = QtWidgets.QWidget()
        lbx = QtWidgets.QVBoxLayout(self._loading_box)
        lbx.setContentsMargins(0, 40, 0, 0)
        lbx.setSpacing(10)

        title = QtWidgets.QLabel("PLC UI · Live Monitoring")
        title.setAlignment(QtCore.Qt.AlignCenter)
        title.setStyleSheet("color:#e9ecef; font-weight:800; font-size:18px;")

        self.loading_label = QtWidgets.QLabel("Launch PLC Live UI")
        self.loading_label.setAlignment(QtCore.Qt.AlignCenter)
        self.loading_label.setStyleSheet("color:#adb5bd; font-size:14px;")

        self.load_button = QtWidgets.QPushButton("Launch PLC LIVE")
        self.load_button.setFixedHeight(38)
        self.load_button.setCursor(QtCore.Qt.PointingHandCursor)
        self.load_button.setStyleSheet("""
            QPushButton {
                background:#0d9488;
                color:#fff;
                border:none;
                border-radius:8px;
                font-weight:700;
                padding:8px 18px;
            }
            QPushButton:hover { background:#0f766e; }
        """)
        self.load_button.clicked.connect(self.load_plc_ui)

        for w in (title, self.loading_label, self.load_button):
            lbx.addWidget(w, 0, QtCore.Qt.AlignCenter)

        v.addWidget(self._loading_box)

    def activate(self):
        """Called when sidebar PLC LIVE button is clicked."""
        if not self.is_loaded:
            self.load_plc_ui()

    def deactivate(self):
        pass

    def load_plc_ui(self):
        try:
            here = os.path.dirname(__file__)
            if here not in sys.path:
                sys.path.append(here)

            from PLC_GUI import ModernPLCWindow
        except Exception as e:
            self.loading_label.setText("❌ PLC GUI not available")
            QtWidgets.QMessageBox.critical(
                self, "Import Error", f"Cannot import PLC_GUI:\n{e}"
            )
            self.load_button.show()
            return

        try:
            plc_obj = ModernPLCWindow()
        except TypeError:
            plc_obj = ModernPLCWindow()

        # If it is a QMainWindow, embed its central widget
        if isinstance(plc_obj, QtWidgets.QMainWindow):
            central = plc_obj.centralWidget() if callable(plc_obj.centralWidget) else None
            self._plc_window = plc_obj
            self._plc_window.hide()

            if central is None:
                central = QtWidgets.QWidget()
                self._plc_window.setCentralWidget(central)

            self._embedded = central
            self._embedded.setParent(self)

            if self._plc_window.styleSheet():
                self._embedded.setStyleSheet(self._plc_window.styleSheet())

        elif isinstance(plc_obj, QtWidgets.QWidget):
            self._embedded = plc_obj
            self._embedded.setParent(self)
        else:
            QtWidgets.QMessageBox.critical(
                self, "Type Error", "Loaded PLC GUI is neither QMainWindow nor QWidget"
            )
            return

        # swap loading box with embedded PLC UI
        host = self.layout()
        host.removeWidget(self._loading_box)
        self._loading_box.hide()
        self._loading_box.setParent(None)

        host.addWidget(self._embedded)
        self._embedded.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Expanding
        )

        self.is_loaded = True

# ============================= Main Window =============================

class MainWindow(QMainWindow):
    def _get_sidebar_width(self) -> int:
        sizes = self.splitter.sizes() if hasattr(self, "splitter") else []
        return sizes[0] if sizes else 0
    
    def get_active_project_info(self):
        try:
            if hasattr(self.page_projects, "selected_project"):
                p = self.page_projects.selected_project
                if p:
                    folder = p.get("folder_path")
                    if not folder:
                        folder = str(get_project_folder(p.get("name")))
                    return p.get("name"), folder
        except Exception as e:
            print("[MainWindow] get_active_project_info error:", e)

        return (None, None)



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
        
        # PLC LIVE button
        if hasattr(self, "btn_plc") and self.btn_plc is not None:
            self.btn_plc.set_compact(compact)

        # header height (logo area)
        if hasattr(self, "header_frame"):
            self.header_frame.setFixedHeight(80 if compact else 110)

        # nav layout margins tighter when collapsed
        if hasattr(self, "nav_layout"):
            if compact:
                self.nav_layout.setContentsMargins(4, 16, 4, 16)
            else:
                self.nav_layout.setContentsMargins(8, 24, 8, 24)

        # hide MEASUREMENTS label + line when collapsed
        if hasattr(self, "measure_label"):
            self.measure_label.setVisible(not compact)
        if hasattr(self, "measure_line"):
            self.measure_line.setVisible(not compact)
        if hasattr(self, "plc_label"):
            self.plc_label.setVisible(not compact)

        # Smooth logo transition with a small delay
        if hasattr(self, "logo_label"):
            QtCore.QTimer.singleShot(50, lambda: self._update_logo_for_state(compact))

        # Logout button text
        if hasattr(self, "btn_logout"):
            if compact:
                self.btn_logout.setText("")        
            else:
                self.btn_logout.setText("  Logout")

    def _update_logo_for_state(self, compact: bool):
        """Update logo with smooth transition"""
        if hasattr(self, "logo_label") and hasattr(self.logo_label, "set_mode"):
            self.logo_label.set_mode("compact" if compact else "full")
            
        if compact and getattr(self, "logo_pixmap_compact", None) is not None:
            self.logo_label.setPixmap(self.logo_pixmap_compact)
        elif (not compact) and getattr(self, "logo_pixmap_full", None) is not None:
            self.logo_label.setPixmap(self.logo_pixmap_full)


    def __init__(self, user=None):
        super().__init__()
        app_icon = _get_app_icon()
        if app_icon is not None:
            self.setWindowIcon(app_icon)
        self.current_user = user or {}
        self.prefs = AppPrefs()
        self.setWindowTitle("AI Model Training Suite")
        self.setMinimumSize(1100, 700)  # or any size you like
        self.setGeometry(80, 80, 1200, 800)
        self._collapsed_width = 56
        self._anim_ms = 300
        self._auto_collapse_ms = 500
        self._live_window = None 
        self._build()
        self._restore_window_session()
        self.switch_tool(0, _from_restore=True)
        try:
            self.toast_info("Welcome back · Dashboard", 1400)
        except Exception:
            pass

    def _restore_sidebar(self):
        try: 
            w = max(220, self.prefs.get_sidebar_width(220))  
        except Exception: 
            w = 260
        
        # Set sidebar to expanded width
        total_width = max(1200, self.width())  
        self.splitter.setSizes([w, total_width - w])
        self._expanded_width = w
        
        # Explicitly set expanded state
        self._set_sidebar_compact(False)

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
        # Only collapse if sidebar is currently expanded
        if self._get_sidebar_width() > self._collapsed_width + 20:
            self._animate_to(self._collapsed_width)
            self._set_sidebar_compact(True)

    def eventFilter(self, obj, ev):
        if obj is self.side:
            if ev.type() == QEvent.Enter: 
                self._expand_sidebar()
            elif ev.type() == QEvent.Leave: 
                # Only start collapse timer if sidebar is currently expanded
                if self._get_sidebar_width() > self._collapsed_width + 20:
                    self._hover_timer.start(self._auto_collapse_ms)
        return super().eventFilter(obj, ev)

    def _build(self):

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # --- Splitter ---
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(3)
        self.splitter.setStyleSheet(
            "QSplitter::handle { background:#0d6efd; } "
            "QSplitter::handle:hover { background:#0d6efd; }"
        )
        root.addWidget(self.splitter, 1)

        # ================== Sidebar ==================
        self.side = QFrame()
        self.side.setObjectName("Sidebar")
        self.side.setMinimumWidth(60)
        self.side.setMaximumWidth(320)
        self.side.setStyleSheet(
            "QFrame#Sidebar{background-color:#2b2f33; border-right:0px solid transparent;}"
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

        # In your _build method, replace the logo section with:
        logo_label = AspectLogoLabel()
        logo_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        logo_file_png = _find_logo()
        logo_file_ico = _find_logo_ico()

        full_pm = QPixmap()
        compact_pm = QPixmap()

        if logo_file_png is not None:
            full_pm = QPixmap(str(logo_file_png))
            
        if logo_file_ico is not None:
            compact_pm = QPixmap(str(logo_file_ico))
        else:
            # Fallback: create compact version from full logo
            if not full_pm.isNull():
                compact_pm = full_pm.scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        if not full_pm.isNull():
            logo_label.setPixmaps(full_pm, compact_pm)
        else:
            logo_label.setStyleSheet("background:#2b2f33; border-radius:8px;")

        hv.addWidget(logo_label)
        sv.addWidget(header)
        self.logo_label = logo_label

        # keep refs for collapse/expand behaviour
        self.header_frame = header
        self.logo_label = logo_label

        # --- Navigation buttons ---
        nav = QFrame()
        nv = QVBoxLayout(nav)
        nv.setContentsMargins(8, 20, 8, 0)
        nv.setSpacing(6)
        self.nav_layout = nv

        # keep list of all nav buttons
        self.nav_buttons = []

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

        # Dashboard button
        dash_icon_path = media_dir / "sidebar_dashboard.png"
        self.btn_dashboard = ToolButton(
            "  Dashboard",
            icon_path=dash_icon_path if dash_icon_path.is_file() else None,
            tooltip="Overview dashboard.",
        )
        self.btn_dashboard.clicked.connect(lambda _: self.switch_tool(0))
        nv.addWidget(self.btn_dashboard)
        self.nav_buttons.append(self.btn_dashboard)

        # NEW: Machines button
        machines_icon_path = media_dir / "sidebar_machines.png"
        self.btn_machines = ToolButton(
            "  Machines",
            icon_path=machines_icon_path if machines_icon_path.is_file() else None,
            tooltip="Manage machines.",
        )
        self.btn_machines.clicked.connect(lambda _: self.switch_tool(1))
        nv.addWidget(self.btn_machines)
        self.nav_buttons.append(self.btn_machines)

        # NEW: Projects button
        projects_icon_path = media_dir / "sidebar_projects.png"
        self.btn_projects = ToolButton(
            "  Projects",
            icon_path=projects_icon_path if projects_icon_path.is_file() else None,
            tooltip="Manage projects.",
        )
        self.btn_projects.clicked.connect(lambda _: self.switch_tool(2))
        nv.addWidget(self.btn_projects)
        self.nav_buttons.append(self.btn_projects)

        # text, index, tooltip, icon filename for PIPELINE tools
        # indices now start from 3
        self._buttons_cfg = [
            ("  Image Capturing",  3,
                "Open the camera workspace: connect devices, preview, and record.",
                "sidebar_capture.png"),
            ("  Annotation Tool",  4,
                "Label images (boxes/masks). Saves annotations for training.",
                "sidebar_annotation.png"),
            ("  Augmentation Tool", 5,
                "Generate augmented variants of images for robust training.",
                "sidebar_augment.png"),
            ("  Model Training",   6,
                "Configure hyperparameters and run model training.",
                "sidebar_training.png"),
        ]


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

         # --- NEW: Live button (just below Model Training) ---
        live_icon_path = media_dir / "sidebar_live.png"   # optional icon file
        self.btn_live = ToolButton(
            "  Live",
            icon_path=live_icon_path if live_icon_path.is_file() else None,
            tooltip="Start live pipeline (configure later)",
        )
        self.btn_live.clicked.connect(self._on_live_clicked)   # your existing handler
        nv.addWidget(self.btn_live)
        self.nav_buttons.append(self.btn_live)


        # --- Measurements / ROI section ---
        nv.addSpacing(12)
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setStyleSheet("background-color:#0d6efd; color:#0d6efd; min-height:1px;")
        nv.addWidget(line)

        section = QLabel("MEASUREMENTS")
        section.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        section.setStyleSheet(
            "color:#94a3b8; font-size:11px; font-weight:800; "
            "margin:10px 12px 2px 12px; letter-spacing:1px;"
        )
        nv.addWidget(section)
        self.measure_line = line
        self.measure_label = section

        # keep a reference so we can toggle compact/expanded
        roi_icon_path = media_dir / "sidebar_roi.png"
        self.btn_roi = ToolButton(
            "  ROI",
            icon_path=roi_icon_path if roi_icon_path.is_file() else None,
            tooltip="Region of Interest & Measurements",
        )
        self.btn_roi.clicked.connect(lambda _: self.switch_tool(7))
        nv.addWidget(self.btn_roi)          # <- add this
        self.nav_buttons.append(self.btn_roi)

        # --- PLC UI section (under ROI) ---
        nv.addSpacing(8)

        self.plc_label = QLabel("PLC UI")
        self.plc_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.plc_label.setStyleSheet(
            "color:#94a3b8; font-size:11px; font-weight:800; "
            "margin:6px 12px 2px 12px; letter-spacing:1px;"
        )
        nv.addWidget(self.plc_label)

        plc_icon_path = media_dir / "sidebar_plc.png"
        self.btn_plc = ToolButton(
            "  PLC LIVE",
            icon_path=plc_icon_path if plc_icon_path.is_file() else None,
            tooltip="PLC UI · Live Monitoring",
        )
        self.btn_plc.clicked.connect(lambda _: self.switch_tool(8))   # <-- use your PLC page index
        nv.addWidget(self.btn_plc)
        self.nav_buttons.append(self.btn_plc)


        # map stack index -> corresponding nav button
        self._tool_button_map = {
            0: self.btn_dashboard,
            1: self.btn_machines,
            2: self.btn_projects,
            3: self.nav_buttons[3],   # Image Capturing
            4: self.nav_buttons[4],   # Annotation
            5: self.nav_buttons[5],   # Augmentation
            6: self.nav_buttons[6],   # Model Training
            7: self.btn_roi,          # ROI
            8: self.btn_plc,     # PLC LIVE
        }


        nv.addSpacing(10) 
        nv.addStretch(1)
        # --------- NEW: Logout button at bottom ----------
        logout_icon_path = media_dir / "sidebar_logout.png"
        self.btn_logout = QPushButton("  Logout")
        self.btn_logout.setCursor(Qt.PointingHandCursor)
        self.btn_logout.setFixedHeight(40)
        self.btn_logout.setStyleSheet("""
            QPushButton {
                background-color:#dc3545;
                color:#ffffff;
                border:0px;
                border-radius:16px;
                padding:0 16px;
                font-size:13px;
                font-weight:600;
                text-align:left;
            }
            QPushButton:hover  { background-color:#c82333; }
            QPushButton:pressed{ background-color:#bd2130; }
        """)

        if logout_icon_path.is_file():
            self.btn_logout.setIcon(QIcon(str(logout_icon_path)))
            self.btn_logout.setIconSize(QSize(18, 18))

        self.btn_logout.clicked.connect(self._on_logout_clicked)
        nv.addWidget(self.btn_logout)
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
        if isinstance(self.current_user, dict):
            username = self.current_user.get("username") or self.current_user.get("name")
        else:
            username = str(self.current_user) if self.current_user else None
        self.page_dashboard = DashboardPage(username=username)
        self.page_machines  = MachinePage()
        self.page_projects  = ProjectPage()

        self.page_capture = CameraPlaceholderWidget(self)
        self.page_annot   = AnnotationPlaceholderWidget(self)
        self.page_aug     = AugmentationPlaceholderWidget(self)
        self.page_train   = TrainingPlaceholderWidget()
        self.page_train.setObjectName("TrainingHostPage")
        self.page_train.setAutoFillBackground(True)
        self.page_train.setStyleSheet("#TrainingHostPage { background: #0f1419; }")
        self.page_roi     = ROIPlaceholderWidget(self)
        self.page_plc     = PLCPlaceholderWidget(self)


        # index mapping:
        # 0 = dashboard, 1 = machines, 2 = projects,
        # 3 = image capture, 4 = annotation, 5 = augmentation,
        # 6 = training, 7 = ROI
        for w in (
            self.page_dashboard,
            self.page_machines,
            self.page_projects,
            self.page_capture,
            self.page_annot,
            self.page_aug,
            self.page_train,
            self.page_roi,
            self.page_plc,
        ):
            self.stack.addWidget(w)
        mv.addWidget(self.stack, 1)


        self.splitter.addWidget(self.side)
        self.splitter.addWidget(self.main_frame)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
            
        # RESTORE SIDEBAR WITH EXPANDED STATE
        self._restore_sidebar()
            
        # FORCE EXPANDED MODE ON STARTUP
        self._set_sidebar_compact(False)
            
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
    
    def _confirm_cameras_connected(self) -> bool:
        """
        Show a nice yes/no popup asking if cameras are connected.
        Returns True if user clicks Yes, False otherwise.
        """
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle("Camera Check")

        box.setText(
            "Are your cameras powered ON and connected?\n\n"
            "Click 'Yes' to start the Live pipeline,\n"
            "or 'No' to cancel."
        )

        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.setDefaultButton(QMessageBox.Yes)

        # Dark-theme styling
        box.setStyleSheet("""
            QMessageBox {
                background-color: #111111;
            }
            QLabel {
                color: #EEEEEE;
                font-size: 12pt;
            }
            QPushButton {
                min-width: 90px;
                padding: 6px 14px;
                border-radius: 6px;
                background-color: #2E86FF;
                color: white;
            }
            QPushButton:hover {
                background-color: #4095FF;
            }
            QPushButton:pressed {
                background-color: #245FCC;
            }
        """)

        result = box.exec_()   # PyQt5
        return result == QMessageBox.Yes
 
    def _on_live_clicked(self):
        """
        Open the Live pipeline window (from live.py).

        - If user says cameras are connected -> camera live mode
        - If user says NO -> local folder inference mode
        """
        try:
            # ensure current folder is on sys.path
            here = os.path.dirname(__file__)
            if here not in sys.path:
                sys.path.append(here)

            from live import MainWindow as LiveWindow
        except Exception as e:
            QMessageBox.critical(
                self,
                "Live Error",
                f"Cannot import live pipeline:\n{e}",
            )
            return

        if self._live_window is None:
            try:
                self._live_window = LiveWindow()
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Live Error",
                    f"Failed to create live window:\n{e}",
                )
                self._live_window = None
                return

        # Set window properties BEFORE showing
        self._live_window.setMinimumSize(1366, 768)
        self._live_window.resize(1300, 700)
        
        # Show and activate the window FIRST
        self._live_window.showMaximized()
        self._live_window.raise_()
        self._live_window.activateWindow()
        
        # Force the window to stay on top during configuration
        self._live_window.setWindowFlags(self._live_window.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
        self._live_window.show()

        # Small delay to ensure window is fully visible
        QtCore.QTimer.singleShot(100, self._start_live_config)

    def _start_live_config(self):
        """Start the configuration after the window is fully visible"""
        if not hasattr(self, '_live_window') or self._live_window is None:
            return
            
        # ---- NEW: ask which mode to use ----
        reply = QMessageBox.question(
            self._live_window,
            "Start Live",
            "Are Hikrobot cameras connected?\n\n"
            "Yes  → use cameras\n"
            "No   → run on local image folder",
            QMessageBox.Yes | QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            # camera mode (this will itself fall back to folder-mode
            # if no devices are actually found)
            self._live_window._start_live_flow()
        else:
            # offline folder mode
            self._live_window._start_folder_mode()

        # Remove the always-on-top flag after configuration
        self._live_window.setWindowFlags(self._live_window.windowFlags() & ~QtCore.Qt.WindowStaysOnTopHint)
        self._live_window.show()

        # optional toast
        if hasattr(self, "toast_info"):
            try:
                self.toast_info("Opening Live pipeline…", 1800)
            except Exception:
                pass

    
    def _on_logout_clicked(self):
        """
        Logout: close this main window and show the login screen again.
        """
        from login_window import LoginWindow  # already imported at top

        app = QApplication.instance()

        # create a fresh login window
        login = LoginWindow(on_login_success=after_login)

        login.show()

        # close current main window
        self.close()

    def _restore_window_session(self):
            try:
                geo = self.prefs.get_geometry()
                if not geo.isEmpty():
                    # This may try to apply an old (too-small) size
                    self.restoreGeometry(geo)
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
            0: "Dashboard",
            1: "Machines",
            2: "Projects",
            3: "Image Capturing",
            4: "Annotation Tool",
            5: "Augmentation Tool",
            6: "Model Training",
            7: "ROI (Measurements)",
            8: "PLC Live UI",
        }.get(idx, f"Tool {idx}")


    def switch_tool(self, index: int, _from_restore: bool = False):
        self.stack.setCurrentIndex(index)

        # --- Dashboard / Machines / Projects (no pathway) ---
        if index == 0:
            if not _from_restore:
                self.toast_info("Dashboard")
            self.page_dashboard.refresh_counts()
            self.pathway.hide()

        elif index == 1:
            if not _from_restore:
                self.toast_info("Machines")
            self.pathway.hide()

        elif index == 2:
            if not _from_restore:
                self.toast_info("Projects")
            self.pathway.hide()

        # --- Pipeline tools (show pathway) ---
        elif index == 3:
            self.page_capture.activate()
            if not _from_restore:
                self.toast_info("Opening Camera Workspace…")
            self.pathway.show()

        elif index == 4:
            self.page_annot.activate()
            if not _from_restore:
                self.toast_success("Annotation Tool ready.")
            self.pathway.show()

        elif index == 5:
            self.page_aug.activate()
            if not _from_restore:
                self.toast_info("Loading Augmentation Tool…")
            self.pathway.show()

        elif index == 6:
            self.page_train.activate()
            if not _from_restore:
                self.toast_warn("Training feature is in preview.")
            self.pathway.show()

        elif index == 7:
            self.page_roi.activate()
            if not _from_restore:
                self.toast_info("Measurements · ROI")
            self.pathway.show()

        elif index == 8:
            self.page_plc.activate()
            if not _from_restore:
                self.toast_info("PLC Live UI")
            self.pathway.hide() 

        # Update pathway only for pipeline pages (3..7)
        if 3 <= index <= 7:
            # map 3..7 -> steps 0..3 (ROI shares last step)
            step = min(max(index - 3, 0), 3)
            self.pathway.set_states(
                completed=list(range(step)),
                active=step
            )

        for b in self.nav_buttons:
            b.setChecked(False)

        btn = getattr(self, "_tool_button_map", {}).get(index)
        if btn is not None:
            btn.setChecked(True)


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
    main_window = MainWindow(user=user)
    main_window.show()

def main():
    app = QApplication(sys.argv)
    apply_dark_theme(app)

    login = LoginWindow(on_login_success=after_login)
    login.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
