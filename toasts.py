# toasts.py
from PyQt5 import QtCore, QtGui, QtWidgets

_KIND_COLORS = {
    "info":    ("#0d6efd", "#1f2937"),  
    "success": ("#198754", "#1f2937"),
    "warning": ("#b78103", "#1f2937"),
    "error":   ("#dc3545", "#1f2937"),
}

class Toast(QtWidgets.QFrame):
    """White rounded toast with no dark halo; antialiased custom paint."""
    closed = QtCore.pyqtSignal()

    def __init__(self, text, kind="info", duration_ms=2500, parent=None):
        # Use translucent window, but paint the white card ourselves
        super().__init__(parent, QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setAttribute(QtCore.Qt.WA_StyledBackground, False)
        self.setObjectName("ToastFrame")

        self._radius = 12
        self._accent, self._text_color = _KIND_COLORS.get(kind, _KIND_COLORS["info"])

        # Content
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 10, 10)
        lay.setSpacing(10)

        dot = QtWidgets.QLabel("●")
        dot.setStyleSheet(f"color:{self._accent}; font-size:14px;")
        lay.addWidget(dot, 0, QtCore.Qt.AlignTop)

        lbl = QtWidgets.QLabel(text)
        lbl.setObjectName("ToastText")
        lbl.setWordWrap(True)
        # readable font & size
        f = lbl.font()
        f.setFamily("Segoe UI")             # fallback to your OS font
        f.setPointSize(10)                  # ≈ 13px
        lbl.setFont(f)
        lbl.setStyleSheet(f"color:{self._text_color};")
        lay.addWidget(lbl, 1)

        btn = QtWidgets.QPushButton("✕")
        btn.setObjectName("CloseBtn")
        btn.setFixedSize(22, 22)
        bf = btn.font(); bf.setPointSize(11)  # ≈ 15px
        btn.setFont(bf)
        btn.setStyleSheet(f"""
            QPushButton#CloseBtn {{
                background: transparent; color: {self._text_color};
                border: none; font-weight: 700;
            }}
            QPushButton#CloseBtn:hover {{ color: #000; }}
        """)
        btn.clicked.connect(self._close_now)
        lay.addWidget(btn, 0, QtCore.Qt.AlignTop)

        self.setAutoFillBackground(False)
        self.setStyleSheet("""
        #ToastFrame { background: transparent; }
        #ToastFrame QLabel, #ToastFrame QPushButton { background: transparent; }
        """)

        for w in (self,):
            w.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)

        for w in (dot, lbl, btn):
            w.setAutoFillBackground(False)
            w.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)

        # Re-apply per-widget styles with explicit transparent bg
        dot.setStyleSheet(f"color:{self._accent}; font-size:14px; background: transparent;")
        lbl.setStyleSheet(f"color:{self._text_color}; background: transparent;")

        # Opacity fade
        self._opacity = QtWidgets.QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)
        self._fade = QtCore.QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade.setDuration(200)

        self._life_timer = QtCore.QTimer(self, interval=max(800, duration_ms), singleShot=True)
        self._life_timer.timeout.connect(self.hide_smooth)

    def show_smooth(self):
        self._fade.stop()
        self._opacity.setOpacity(0.0)
        self.show(); self.raise_()
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()
        self._life_timer.start()

    @QtCore.pyqtSlot()
    def hide_smooth(self):
        self._fade.stop()
        self._fade.setStartValue(self._opacity.opacity())
        self._fade.setEndValue(0.0)
        self._fade.finished.connect(self._on_faded_out)
        self._fade.start()

    def _on_faded_out(self):
        self._fade.finished.disconnect(self._on_faded_out)
        self.hide()
        self.closed.emit()

    def _close_now(self):
        self._life_timer.stop()
        self.hide_smooth()

    def paintEvent(self, ev):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)

        r = self._radius
        rect = self.rect().adjusted(0, 0, -1, -1)          
        rectf = QtCore.QRectF(rect)                

        # White rounded card
        path = QtGui.QPainterPath()
        path.addRoundedRect(rectf, float(r), float(r))
        p.fillPath(path, QtGui.QColor("#ffffff"))

        # Subtle border
        pen = QtGui.QPen(QtGui.QColor(0, 0, 0, 30))
        p.setPen(pen)
        p.drawPath(path)

        # Left accent strip (rounded with the card)
        strip_w = 6
        strip_rectf = QtCore.QRectF(0.0, 0.0, float(strip_w), float(rectf.height()))
        strip_full = QtGui.QPainterPath()
        strip_full.addRoundedRect(rectf, float(r), float(r))
        strip_slice = QtGui.QPainterPath()
        strip_slice.addRect(strip_rectf)
        strip_path = strip_full.intersected(strip_slice)
        p.fillPath(strip_path, QtGui.QColor(self._accent))



class ToastManager(QtCore.QObject):
    """Bottom-right stacked toasts on a host widget (e.g., your QMainWindow)."""
    _instance = None

    def __init__(self, host: QtWidgets.QWidget):
        super().__init__(host)
        self.host = host
        self.toasts = []
        host.installEventFilter(self)

    @classmethod
    def install(cls, host):
        mgr = cls(host)
        cls._instance = mgr
        return mgr

    @classmethod
    def instance(cls):
        return cls._instance

    def show(self, text, kind="info", duration_ms=2500):
        t = Toast(text, kind, duration_ms, parent=self.host)
        t.closed.connect(lambda: self._remove(t))
        t.resize(self._preferred_size(t))
        t.show_smooth()
        self.toasts.append(t)
        self._reposition()

    def _remove(self, t):
        if t in self.toasts:
            self.toasts.remove(t)
        self._reposition()

    def _preferred_size(self, toast: Toast):
        w = min(360, max(280, int(self.host.width() * 0.28)))
        toast.resize(w, toast.sizeHint().height())
        return toast.size()

    def _reposition(self):
        margin = 16

        # Host's top-left in global screen coordinates
        host_top_left = self.host.mapToGlobal(QtCore.QPoint(0, 0))
        host_w = self.host.width()
        host_h = self.host.height()

        y = host_top_left.y() + host_h - margin
        for t in reversed(self.toasts):
            sz = self._preferred_size(t)
            x = host_top_left.x() + host_w - sz.width() - margin
            y -= sz.height()
            t.move(x, y)           # global coords now ✔
            y -= 8  

    def eventFilter(self, obj, ev):
        if obj is self.host and ev.type() in (QtCore.QEvent.Resize, QtCore.QEvent.Move, QtCore.QEvent.Show):
            self._reposition()
        return super().eventFilter(obj, ev)
