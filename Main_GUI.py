from typing import Iterable, List
import sys, os, importlib
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QStackedWidget, QFrame, QMessageBox,QSizePolicy
)
from PyQt5.QtCore import Qt, QSize, QRect, QPoint
from PyQt5.QtGui import (
    QIcon, QPalette, QColor, QPainter, QPen, QFont, QFontMetrics,QPixmap
)
from PyQt5 import QtCore, QtGui, QtWidgets

# ---------- Sidebar Button ----------
class ToolButton(QPushButton):
    def __init__(self, text, icon_path=None,tooltip=None):
        super().__init__(text)
        if tooltip:
            self.setToolTip(tooltip)
        self.setFixedHeight(50)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("""
            QPushButton {
                background-color: #495057;     /* dark grey for sidebar buttons */
                color: white;
                border: none;
                text-align: center;
                padding: 0 12px; 
                font-size: 14px;
                font-weight: bold;
                border-radius: 8px;
                margin: 6px 10px;
            }
            QPushButton:hover {
                background-color: #6c757d;
                border-left: 4px solid #0d6efd;
            }
            QPushButton:pressed { background-color: #0d6efd; }
        """)
# ---------- Full-width Pathway Indicator (compact) ----------
class PathwayIndicator(QWidget):
    """
    Compact full-width pathway:
      • baseline spans the entire widget width (with safe side margins)
      • progress line up to active step
      • smaller circles, tighter spacing
      • labels centered under circles, constrained width to prevent overlap
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(74)   # ↓ was 84
        self.setObjectName("PathwayBg")
        self.setStyleSheet("""
            QWidget#PathwayBg {
                background-color: #495057;
                border: none;
                border-bottom: 1px solid #6c757d;
            }
        """)

        self._spec = [
            ("1. Image Capturing", "#0d6efd", "Connect/preview cameras and record images"),
            ("2. Annotation Tool", "#c83a93", "Draw boxes/masks to label data"),
            ("3. Augmentation",   "#ffc107", "Create augmented variants of images"),
            ("4. Training",       "#28a745", "Set hyperparams and start training"),
        ]
        self._active = 1           # 0-based
        self._completed = {0}

        # Labels (slightly smaller font)
        self._label_widgets: List[QLabel] = []
        for text, _,tip in self._spec:
            lab = QLabel(text, self)
            lab.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
            lab.setWordWrap(False)
            lab.setToolTip(tip)
            lab.setStyleSheet(
                "color:#ffffff; font-weight:600; font-size:10px; background:transparent;"
            )  # ↓ was 11px
            self._label_widgets.append(lab)

        # Geometry (more compact)
        self._margin_left  = 70
        self._margin_right = 70
        self._circle_d = 24        # ↓ was 26
        self._line_y = 28          # ↓ was 32
        self._label_gap = 5        # ↓ was 6

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
        maxw = 140  # keep compact; adjust if you want wider labels
        for i, lab in enumerate(self._label_widgets):
            cx = centers[i].x()
            # Max half-width available on both sides if we keep the label centered
            half_avail = max(1, min(cx, w - cx))
            lab_w = min(maxw, 2 * half_avail - 6)   
            lab_w = max(70, lab_w)                  
            x = int(cx - lab_w // 2)                
            y = self._line_y + (self._circle_d // 2) + self._label_gap
            lab.setGeometry(QRect(x, y, lab_w, 24))
            lab.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
            # Optional: elide if still too long for two short lines
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

        # Baseline
        base_pen = QPen(QColor("#d2d6db")); base_pen.setWidth(3)
        p.setPen(base_pen)
        p.drawLine(QPoint(self._margin_left, self._line_y),
                   QPoint(self.width()-self._margin_right, self._line_y))

        # Progress
        active_color = QColor(self._spec[self._active][1])
        prog_pen = QPen(active_color); prog_pen.setWidth(5)
        p.setPen(prog_pen)
        p.drawLine(QPoint(self._margin_left, self._line_y), centers[self._active])

        # Circles + check/number
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
                f = QFont(self.font()); f.setBold(True)
                p.setFont(f)
                rect = QRect(c.x()-r, c.y()-r, self._circle_d, self._circle_d)
                p.drawText(rect, Qt.AlignCenter, str(i+1))


class CameraPlaceholderWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.camera_widget = None
        self.is_loaded = False
        
        v = QVBoxLayout(self)
        v.setAlignment(Qt.AlignCenter)
        
        # Loading message
        self.loading_label = QLabel("Loading Camera Application...")
        self.loading_label.setStyleSheet("color:#adb5bd; font-size:18px; font-style:italic;")
        v.addWidget(self.loading_label)
        
        # Load button as fallback
        self.load_button = QPushButton("Launch Camera App")
        self.load_button.setStyleSheet("""
            QPushButton {
                background-color: #007bff;
                color: white;
                border: none;
                padding: 15px 30px;
                font-size: 16px;
                font-weight: bold;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
        """)
        self.load_button.clicked.connect(self.load_camera_app)
        self.load_button.hide()
        v.addWidget(self.load_button)

    def load_camera_app(self):
        """Dynamically load the camera application"""
        try:
            # Import the camera application
            sys.path.append(os.path.dirname(__file__))
            
            try:
                from camera_app import CameraWidget
                self.camera_widget = CameraWidget(self)
            except ImportError as e:
                self.loading_label.setText("❌ Camera app not available")
                self.load_button.show()
                QMessageBox.critical(self, "Import Error", 
                                   f"Cannot import camera application:\n{str(e)}")
                return
            
            # Remove placeholder content
            self.loading_label.hide()
            self.load_button.hide()
            
            # Add camera widget to layout
            layout = self.layout()
            layout.addWidget(self.camera_widget)
            self.is_loaded = True
            
            # Initialize camera if needed
            if hasattr(self.camera_widget, 'initialize_camera'):
                self.camera_widget.initialize_camera()
                
        except Exception as e:
            self.loading_label.setText(f"❌ Error loading camera: {str(e)}")
            self.load_button.show()
            QMessageBox.critical(self, "Loading Error", 
                               f"Failed to load camera application:\n{str(e)}")

    def activate(self):
        """Called when this tool becomes active"""
        if not self.is_loaded:
            self.load_camera_app()
# ---------- Annotation Tool Integration ----------
class AnnotationPlaceholderWidget(QWidget):
    """Placeholder widget that loads the annotation tool when activated"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.annotation_widget = None
        self.is_loaded = False
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Loading message
        self.loading_label = QLabel("Loading Annotation Tool...")
        self.loading_label.setStyleSheet("""
            QLabel {
                color: #adb5bd;
                font-size: 18px;
                font-style: italic;
                padding: 20px;
            }
        """)
        self.loading_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.loading_label)
        
        # Load button as fallback
        self.load_button = QPushButton("✏️ Launch Annotation Tool")
        self.load_button.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                border: none;
                padding: 15px 30px;
                font-size: 16px;
                font-weight: bold;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
        """)
        self.load_button.clicked.connect(self.load_annotation_tool)
        self.load_button.hide()
        layout.addWidget(self.load_button, 0, Qt.AlignCenter)

    def load_annotation_tool(self):
        """Dynamically load the annotation tool"""
        try:
            # Import the annotation tool
            sys.path.append(os.path.dirname(__file__))
            
            # Try to import the annotation module
            try:
                from annotation_tool import AnnotationTool
                self.annotation_widget = AnnotationTool()
            except ImportError as e:
                self.loading_label.setText("❌ Annotation tool not available")
                self.load_button.show()
                QMessageBox.critical(self, "Import Error", 
                                   f"Cannot import annotation tool:\n{str(e)}")
                return
            
            # Remove placeholder content
            self.loading_label.hide()
            self.load_button.hide()
            
            # Add annotation widget to layout
            layout = self.layout()
            layout.addWidget(self.annotation_widget)
            self.is_loaded = True
            
            # Initialize annotation tool if needed
            if hasattr(self.annotation_widget, 'initialize_tool'):
                self.annotation_widget.initialize_tool()
                
        except Exception as e:
            self.loading_label.setText(f"❌ Error loading annotation tool: {str(e)}")
            self.load_button.show()
            QMessageBox.critical(self, "Loading Error", 
                               f"Failed to load annotation tool:\n{str(e)}")

    def activate(self):
        """Called when this tool becomes active"""
        if not self.is_loaded:
            self.load_annotation_tool()

    def deactivate(self):
        """Called when this tool becomes inactive"""
        pass

# ---------- Augmentation Tool Integration ----------
class AugmentationPlaceholderWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self._aug_window = None       # If QMainWindow, we keep it hidden here
        self._embedded = None         # The widget actually embedded into this host
        self.is_loaded = False

        # Host layout (fill fully; no margins)
        self.setObjectName("AugmentationHost")
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # Lightweight loading UI
        self._loading_box = QtWidgets.QWidget()
        lbx = QtWidgets.QVBoxLayout(self._loading_box)
        lbx.setContentsMargins(0, 40, 0, 0)
        lbx.setSpacing(10)

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

    # Called by MainWindow.switch_tool
    def activate(self):
        if not self.is_loaded:
            self.load_augmentation_tool()
        else:
            print("Augmentation tool already loaded")

    def deactivate(self):
        pass

    # --- Core loader ---
    def load_augmentation_tool(self):
        """Import augmentation_tool, locate the class, instantiate it, and embed it."""
        try:
            # Ensure local import path
            here = os.path.dirname(__file__)
            if here not in sys.path:
                sys.path.append(here)

            mod = importlib.import_module("augmentation_tool")

            # Accept any of these names (first one found wins)
            candidate_names = [
                "AugmentationTool",      # old expectation
                "AugmentationWizard",    # your current class
                "MainWindow",            # optional fallback
            ]

            ToolClass = None
            for name in candidate_names:
                if hasattr(mod, name):
                    ToolClass = getattr(mod, name)
                    break

            if ToolClass is None:
                raise ImportError(
                    "Could not find any of: "
                    + ", ".join(f"augmentation_tool.{n}" for n in candidate_names)
                )

            # Instantiate: try with parent, then without (your class has no parent arg)
            try:
                aug_obj = ToolClass(parent=None)
            except TypeError:
                aug_obj = ToolClass()

            # If it’s a QMainWindow, try to embed its central widget
            central = None
            if hasattr(aug_obj, "centralWidget") and callable(getattr(aug_obj, "centralWidget")):
                try:
                    central = aug_obj.centralWidget()
                except Exception:
                    central = None

            if central is not None and isinstance(aug_obj, QtWidgets.QMainWindow):
                # keep a ref so it isn't GC'ed
                self._aug_window = aug_obj
                self._aug_window.hide()

                if central is None:
                    central = QtWidgets.QWidget()
                    self._aug_window.setCentralWidget(central)

                self._embedded = central
                self._embedded.setParent(self)
                self._embedded.setContentsMargins(0, 0, 0, 0)

                # copy palette/stylesheet for visual parity
                self._embedded.setPalette(self._aug_window.palette())
                if self._aug_window.styleSheet():
                    self._embedded.setStyleSheet(self._aug_window.styleSheet())

                # optional initialization hook
                if hasattr(self._aug_window, "initialize_tool"):
                    try:
                        self._aug_window.initialize_tool()
                    except Exception as e:
                        print(f"[AugHost] initialize_tool error: {e}")

            else:
                # If it’s already a QWidget (panel-style), embed directly
                if isinstance(aug_obj, QtWidgets.QWidget):
                    self._embedded = aug_obj
                    self._embedded.setParent(self)
                    self._embedded.setContentsMargins(0, 0, 0, 0)

                    if hasattr(self._embedded, "initialize_tool"):
                        try:
                            self._embedded.initialize_tool()
                        except Exception as e:
                            print(f"[AugHost] initialize_tool error: {e}")
                else:
                    raise TypeError("Loaded tool is neither QMainWindow nor QWidget")

            # Swap loading box for embedded widget
            host_layout = self.layout()
            host_layout.removeWidget(self._loading_box)
            self._loading_box.hide()
            self._loading_box.setParent(None)
            host_layout.addWidget(self._embedded)

            self._embedded.setSizePolicy(
                QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
            )

            self.is_loaded = True

        except Exception as e:
            print(f"❌ Failed to load augmentation tool: {e}")
            self.loading_label.setText(f"❌ Error loading augmentation tool:\n{str(e)}")
            self.load_button.show()
            QtWidgets.QMessageBox.critical(
                self, "Loading Error", f"Failed to load augmentation tool:\n{str(e)}"
            )


    # Keep child filling nicely if parent resizes
    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        if self._embedded:
            self._embedded.resize(self.size())

    def activate(self):
        """Called when this tool becomes active"""
        if not self.is_loaded:
            self.load_augmentation_tool()
        else:
            print("✅ Augmentation tool already loaded")

    def deactivate(self):
        """Called when this tool becomes inactive"""
        pass

class TrainingPlaceholderWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self); v.setAlignment(Qt.AlignCenter)
        lab = QLabel("🔄 Loading Training Tool...")
        lab.setStyleSheet("color:#adb5bd; font-size:18px; font-style:italic;")
        v.addWidget(lab)

class AspectLogoLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._orig = QPixmap()
        self.setAlignment(Qt.AlignCenter)

    def setPixmap(self, pm: QPixmap):   # store original
        self._orig = pm
        super().setPixmap(pm)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if not self._orig.isNull():
            scaled = self._orig.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            super().setPixmap(scaled)


# ---------- Main Window ----------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Model Training Suite")
        self.setGeometry(80, 80, 1200, 800)
        self._build()

    def _build(self):
        central = QWidget(); self.setCentralWidget(central)
        main = QHBoxLayout(central); main.setContentsMargins(0,0,0,0); main.setSpacing(0)

        # ===== Sidebar (dark grey) =====
        side = QFrame()
        side.setFixedWidth(260)
        side.setStyleSheet("QFrame{background-color:#2b2f33; border-right:1px solid #3a3f44;}")
        sv = QVBoxLayout(side); sv.setContentsMargins(0,0,0,0); sv.setSpacing(0)

        # --- Header box with ONLY logo ---
        header = QFrame()
        header.setFixedHeight(110)
        # header.setStyleSheet("QFrame{background:#3a4146; border-bottom:2px solid #0d6efd;}")
        hv = QHBoxLayout(header)
        hv.setContentsMargins(12, 8, 12, 8)   # inner padding around logo
        hv.setSpacing(0)

        logo_label = AspectLogoLabel()
        logo_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        logo_path = r"E:\Office\Desktop\My files\project files\AI pipline\Media\LOGO-02.png"
        pm = QPixmap(logo_path)
        if not pm.isNull():
            logo_label.setPixmap(pm)          # AspectLogoLabel keeps aspect ratio
        else:
            logo_label.setStyleSheet("background:#2b2f33; border-radius:8px;")

        hv.addWidget(logo_label)              # center-fill logo
        sv.addWidget(header)


        # --- Navigation buttons ---
        nav = QFrame()
        nv = QVBoxLayout(nav)
        nv.setContentsMargins(4, 18, 4, 18)
        nv.setSpacing(6)

        buttons = [
            ("  Image Capturing ", 0, "Open the camera workspace: connect devices, preview, and record."),
            ("  Annotation Tool ", 1, "Label images (boxes/masks). Saves annotations for training."),
            ("  Augmentation Tool ", 2, "Generate augmented variants of images for robust training."),
            ("  Model Training ", 3, "Configure hyperparameters and run model training."),
        ]
        for text, idx, tip in buttons:
            b = ToolButton(text, tooltip=tip)
            b.clicked.connect(lambda _, i=idx: self.switch_tool(i))
            nv.addWidget(b)


        nv.addStretch(1)
        sv.addWidget(nav, 1)

        # Add sidebar to main layout
        main.addWidget(side)

        # ===== Main area (darker) =====
        frame = QFrame()
        frame.setStyleSheet("QFrame{background:#1f2327;}")
        mv = QVBoxLayout(frame); mv.setContentsMargins(0,0,0,0); mv.setSpacing(0)

        self.pathway = PathwayIndicator()
        mv.addWidget(self.pathway)

        self.stack = QStackedWidget()
        self.stack.setStyleSheet("QStackedWidget{background:#23282d;}")
        # Create tool pages with dynamic loading capability
        self.page_capture = CameraPlaceholderWidget(self)
        self.page_annot   = AnnotationPlaceholderWidget(self)
        self.page_aug     = AugmentationPlaceholderWidget(self)
        self.page_train   = TrainingPlaceholderWidget()

        for w in [self.page_capture, self.page_annot, self.page_aug, self.page_train]:
            self.stack.addWidget(w)
        mv.addWidget(self.stack, 1)

        main.addWidget(frame, 1)

        # initial: step 2 active, step 1 completed
        self.pathway.set_states(completed=[0], active=1)


    def switch_tool(self, index: int):
        self.stack.setCurrentIndex(index)
        
        # Activate dynamic loading for specific tools
        if index == 0:  # Image Capturing
            self.page_capture.activate()
        elif index == 1:  # Annotation Tool
            self.page_annot.activate()
        elif index == 2:  # Augmentation Tool
            self.page_aug.activate()
        # Add similar activation for other tools if needed
        
        # auto-progress example
        self.pathway.set_states(completed=list(range(index)), active=min(index, 3))

# ---------- Global dark palette ----------
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
    app.setPalette(dark)
    
    # Additional styling for message boxes
    app.setStyleSheet("""
        QMessageBox {
            background-color: #343a40;
            color: white;
        }
        QMessageBox QLabel {
            color: white;
        }
        QMessageBox QPushButton {
            background-color: #495057;
            color: white;
            border: 1px solid #6c757d;
            padding: 8px 15px;
            border-radius: 4px;
            font-weight: bold;
        }
        QMessageBox QPushButton:hover {
            background-color: #6c757d;
        }
        QToolTip {
            background-color: #ffffff;
            color: #212529;
            border-radius: 6px;
            font-size: 12px;
        }
    """)

def main():
    app = QApplication(sys.argv)
    apply_dark_theme(app)
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()