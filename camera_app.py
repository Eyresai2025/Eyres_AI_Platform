from __future__ import annotations
import os, sys, time, ctypes, traceback
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
from collections import defaultdict
from toasts import ToastManager
import numpy as np
import cv2
from PyQt5 import QtCore, QtGui, QtWidgets
from pathlib import Path
from typing import Optional, Iterable

def _app_base_dir() -> Path:
    """
    Root folder of the app (PyInstaller-safe).
    - From source: folder of the current .py
    - From PyInstaller EXE: the temporary _MEIPASS dir
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent

def _media_dirs() -> list[Path]:
    """
    Candidate media directories next to the app.
    Supports both 'Media' and 'media' names.
    """
    base = _app_base_dir()
    return [base / "Media", base / "media"]

def _find_first_in_media(patterns: Iterable[str]) -> Optional[Path]:
    """
    Return the first existing file in any media directory that matches
    one of the provided filenames/globs. Exact filename wins over glob.
    """
    for mdir in _media_dirs():
        if not mdir.exists():
            continue
        # exact name first
        for name in patterns:
            p = mdir / name
            if p.is_file():
                return p
        # then globs (e.g., 'camera*.png')
        for name in patterns:
            for g in (mdir.glob(name) if any(ch in name for ch in "*?[]") else []):
                if g.is_file():
                    return g
    return None

# ---------- Optional icons (dynamic) ----------
_area_path = _find_first_in_media([
    "camera (1).png",          # your current filename
    "camera_1.png",
    "camera-1.png",
    "camera*.png",             # any camera*.png as fallback
    "*.png", "*.svg", "*.ico"  # last resorts
])
_line_path = _find_first_in_media([
    "camera.png",
    "camera-plain.png",
    "camera2.png",
    "camera*.png",
    "*.png", "*.svg", "*.ico"
])

# Keep public names as strings (or empty) because StepMode checks with os.path.exists
AREA_ICON_PATH = str(_area_path) if _area_path else ""
LINE_ICON_PATH = str(_line_path) if _line_path else ""


# ---------- Help ----------
HELP_HTML = """
<div id="helpRoot">
  <div class="hero">
    <div>
      <h1>Camera Capture — Quick Help</h1>
      <p class="subtitle">A simple, one-page flow to grab images from your Lucid cameras.</p>
    </div>
  </div>

  <div class="card">
    <h2>What this app does</h2>
    <ul class="bullets">
      <li>🔍 <b>Finds your cameras</b> and lets you pick one or many.</li>
      <li>⚙️ Uses <b>safe defaults</b> so you don’t have to tune settings every time.</li>
      <li>🧮 Captures a <b>fixed number of images</b> from each selected camera.</li>
      <li>💾 Saves everything in a <b>date-stamped folder</b>, one folder per camera.</li>
      <li>📈 Shows a <b>progress bar</b> and a clear <b>status log</b>.</li>
      <li>🖼️ Gives a quick <b>preview grid</b> so you can check results fast.</li>
    </ul>
  </div>

  <div class="card">
    <h2>How to use (60-second guide)</h2>
    <ol class="steps">
      <li>🧭 <b>Choose Mode</b> — <i>Area Scan</i> (normal photos) or <i>Line Scan</i> (moving belt/roller).</li>
      <li>🎛️ <b>Select Cameras</b> — Press <b>Refresh</b>, tick the ones you need, or use <b>Select all cameras</b>.</li>
      <li>🔢 <b>Images per camera</b> — Pick how many pictures to take from each camera (e.g., 10).</li>
      <li>📂 <b>Save Location</b> — Choose where to store the session.</li>
      <li>▶️ <b>Capture</b> — Start; watch the progress and read the short log lines below.</li>
      <li>👀 <b>Preview</b> — Check sample images from every camera, then press <b>Finish</b> to start fresh.</li>
    </ol>
  </div>

  <div class="card">
    <h2>Where are my images?</h2>
    <pre class="folder">
{your_folder}/capture_{mode}_{YYYYMMDD_HHMMSS}/
  ├─ {SERIAL_1}/  image_001.jpg, image_002.jpg, ...
  └─ {SERIAL_2}/  image_001.jpg, image_002.jpg, ...
    </pre>
  </div>

  <div class="card tips">
    <h2>Quick tips</h2>
    <ul class="bullets">
      <li>🧪 <b>Line Scan</b> needs a working trigger from your machine (wired to <i>Line0</i>).</li>
      <li>🌗 Too dark or too bright? Reduce/increase exposure in code later — for now, just confirm wiring and lighting.</li>
      <li>🛠️ No cameras listed? Check power/network, then press <b>Refresh Devices</b>.</li>
    </ul>
    <div class="shortcuts">⌨️ <b>Shortcuts:</b> F1 = Help • Alt+→ = Next • Alt+← = Back</div>
  </div>
</div>
"""

class SimpleHelpDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Help")
        self.resize(780, 560)

        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(14, 14, 14, 14)

        card = QtWidgets.QFrame()
        card.setObjectName("helpCard")
        lay = QtWidgets.QVBoxLayout(card)
        lay.setContentsMargins(18, 18, 18, 18)

        txt = QtWidgets.QTextBrowser()
        txt.setObjectName("helpText")
        txt.setOpenExternalLinks(True)
        txt.setHtml(HELP_HTML)

        lay.addWidget(txt)
        v.addWidget(card, 1)

        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        btns.rejected.connect(self.reject)
        v.addWidget(btns, 0, QtCore.Qt.AlignRight)

# ---------- Arena SDK guard ----------
ARENA_OK = True
try:
    from arena_api.system import system
    from arena_api.buffer import BufferFactory
except Exception as e:
    ARENA_OK = False
    ARENA_IMPORT_ERR = str(e)

# ---------- Arena helpers ----------
@dataclass
class CamInfo:
    index: int
    model: str
    serial: str

def list_cameras() -> List[CamInfo]:
    if not ARENA_OK:
        raise RuntimeError(f"arena_api not available: {ARENA_IMPORT_ERR}")
    devices = system.create_device()
    out = []
    for i, dev in enumerate(devices):
        model = dev.nodemap.get_node("DeviceModelName").value
        serial = dev.nodemap.get_node("DeviceSerialNumber").value
        out.append(CamInfo(i, model, serial))
    return out

def _set_nm_value(nm, name: str, value):
    node = nm.get_node(name)
    if not getattr(node, "is_writable", False):
        return
    last = None
    seq = [value]
    if isinstance(value, bool):
        seq += [1 if value else 0, "true" if value else "false"]
    if isinstance(value, (int, float)):
        seq += [str(value)]
    for c in seq:
        try:
            node.value = c
            return
        except Exception as e:
            last = e
    raise RuntimeError(f"Failed to set node '{name}' to {value!r}: {last}")

def _set_tl_value(tl, name: str, value):
    try:
        node = tl[name]
    except Exception:
        return
    last = None
    seq = [value]
    if isinstance(value, bool):
        seq += [1 if value else 0, "true" if value else "false"]
    if isinstance(value, (int, float)):
        seq += [str(value)]
    for c in seq:
        try:
            node.value = c
            return
        except Exception as e:
            last = e
    raise RuntimeError(f"Failed to set TL node '{name}' to {value!r}: {last}")

def _safe_stop(dev):
    try:
        dev.stop_stream()
    except Exception:
        pass

def setup_area_camera(dev):
    nm = dev.nodemap
    _safe_stop(dev)
    _set_nm_value(nm, "TriggerMode", "Off")
    _set_nm_value(nm, "ExposureAuto", "Off")
    _set_nm_value(nm, "Width",  int(min(nm.get_node("WidthMax").value, 2048)))
    _set_nm_value(nm, "Height", int(min(nm.get_node("HeightMax").value, 1536)))
    _set_nm_value(nm, "PixelFormat", "Mono8")
    _set_nm_value(nm, "ExposureTime", 1500.0)
    tl = dev.tl_stream_nodemap
    _set_tl_value(tl, "StreamAutoNegotiatePacketSize", True)
    _set_tl_value(tl, "StreamPacketResendEnable", True)
    dev.start_stream()

def setup_line_camera(dev):
    nm = dev.nodemap
    _safe_stop(dev)
    _set_nm_value(nm, "Height", 770)
    _set_nm_value(nm, "Width", 2048)
    _set_nm_value(nm, "PixelFormat", "Mono8")
    _set_nm_value(nm, "ExposureTime", 1700.0)
    try:
        _set_nm_value(nm, "TriggerSelector", "FrameStart")
        _set_nm_value(nm, "TriggerMode", "On")
        _set_nm_value(nm, "TriggerSource", "Line0")
        _set_nm_value(nm, "TriggerActivation", "FallingEdge")
    except Exception:
        pass
    tl = dev.tl_stream_nodemap
    _set_tl_value(tl, "StreamAutoNegotiatePacketSize", True)
    _set_tl_value(tl, "StreamPacketResendEnable", True)
    dev.start_stream()

def _read_nodes_safe(nm, names):
    out = {}
    for n in names:
        try:
            out[n] = str(nm.get_node(n).value)
        except Exception:
            out[n] = "<N/A>"
    return out

def _read_tl_nodes_safe(tl, names):
    out = {}
    for n in names:
        try:
            out[n] = str(tl[n].value)
        except Exception:
            out[n] = "<N/A>"
    return out

def arena_grab_gray(dev) -> Optional[np.ndarray]:
    try:
        buf = dev.get_buffer()
        item = BufferFactory.copy(buf)
        w, h = item.width, item.height
        raw_type = ctypes.c_ubyte * (w * h)
        raw = raw_type.from_address(ctypes.addressof(item.pbytes))
        img = np.ctypeslib.as_array(raw).reshape((h, w)).copy()
        dev.requeue_buffer(buf)
        return img
    except Exception:
        return None

# ---------- Worker ----------
class CaptureWorker(QtCore.QThread):
    progress = QtCore.pyqtSignal(int, int)
    status = QtCore.pyqtSignal(str)
    finished_ok = QtCore.pyqtSignal(list)
    failed = QtCore.pyqtSignal(str)

    def __init__(self, mode: str, serials: List[str], n_images: int, base_dir: str):
        super().__init__()
        self.mode = mode
        self.serials = serials
        self.n_images = max(1, int(n_images))
        self.base_dir = base_dir
        self._stop = False

    def stop(self): self._stop = True

    def run(self):
        if not ARENA_OK:
            self.failed.emit(f"arena_api not available: {ARENA_IMPORT_ERR}")
            return
        try:
            devices = system.create_device()
            ser2dev = {}
            for dev in devices:
                s = dev.nodemap.get_node("DeviceSerialNumber").value
                if s in self.serials:
                    ser2dev[s] = dev
            if not ser2dev:
                self.failed.emit("No matching cameras found.")
                return

            for s, d in ser2dev.items():
                self.status.emit(f"Configuring {s} as {self.mode} scan ...")
                (setup_area_camera if self.mode == "area" else setup_line_camera)(d)
                nm, tl = d.nodemap, d.tl_stream_nodemap
                core = ["Width", "Height", "PixelFormat", "ExposureTime", "TriggerMode", "ExposureAuto",
                        "TriggerSelector", "TriggerSource", "TriggerActivation"]
                tlk = ["StreamAutoNegotiatePacketSize", "StreamPacketResendEnable"]
                nmv = _read_nodes_safe(nm, core)
                tlv = _read_tl_nodes_safe(tl, tlk)
                self.status.emit(f"[{s}] === Applied Camera Settings ===")
                for k in core: self.status.emit(f"[{s}] {k}: {nmv.get(k, '<N/A>')}")
                for k in tlk:  self.status.emit(f"[{s}] {k}: {tlv.get(k, '<N/A>')}")
                self.status.emit(f"[{s}] ===============================")

            total = self.n_images * len(ser2dev)
            saved, done = [], 0
            ts = time.strftime("%Y%m%d_%H%M%S")
            root_out = os.path.join(self.base_dir, f"capture_{self.mode}_{ts}")
            os.makedirs(root_out, exist_ok=True)

            for serial, dev in ser2dev.items():
                cam_dir = os.path.join(root_out, serial)
                os.makedirs(cam_dir, exist_ok=True)
                for i in range(self.n_images):
                    if self._stop: break
                    self.status.emit(f"[{serial}] Capturing {i+1}/{self.n_images}…")
                    img = arena_grab_gray(dev) or arena_grab_gray(dev)
                    if img is None:
                        self.status.emit(f"[{serial}] Skipped (no frame)")
                        done += 1; self.progress.emit(done, total); continue
                    fp = os.path.join(cam_dir, f"{serial}_{int(time.time()*1000)}_{i+1:03d}.jpg")
                    cv2.imwrite(fp, img); saved.append(fp)
                    done += 1; self.progress.emit(done, total)

            for _, dev in ser2dev.items():
                _safe_stop(dev)
            self.finished_ok.emit(saved)
        except Exception:
            self.failed.emit(traceback.format_exc())

# ---------- Preview helpers ----------
def _group_by_camdir(paths: List[str]) -> Dict[str, List[str]]:
    g = defaultdict(list)
    for p in paths:
        g[os.path.dirname(p)].append(p)
    for k in g:
        g[k].sort(key=lambda x: os.path.getmtime(x), reverse=True)
    return g

def _pick_previews_by_rule(paths: List[str]) -> List[Tuple[str, str]]:
    groups = _group_by_camdir(paths)
    cams = sorted(groups.keys())
    out: List[Tuple[str, str]] = []
    if not cams: return out
    if len(cams) == 1:
        out += [(p, os.path.basename(cams[0])) for p in groups[cams[0]][:4]]
    elif len(cams) == 2:
        for c in cams: out += [(p, os.path.basename(c)) for p in groups[c][:2]]
    else:
        for c in cams: out.append((groups[c][0], os.path.basename(c)))
    return out

# ---------- Small utilities for labels (prevents strips) ----------
def _make_title(text: str) -> QtWidgets.QLabel:
    lbl = QtWidgets.QLabel(text)
    lbl.setObjectName("pageTitle")
    lbl.setFrameShape(QtWidgets.QFrame.NoFrame)
    lbl.setAutoFillBackground(False)
    lbl.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
    return lbl

def _make_subtitle(text: str) -> QtWidgets.QLabel:
    lbl = QtWidgets.QLabel(text)
    lbl.setObjectName("pageSubtitle")
    lbl.setFrameShape(QtWidgets.QFrame.NoFrame)
    lbl.setAutoFillBackground(False)
    lbl.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
    return lbl

# ---------- Widgets ----------
class StepIndicator(QtWidgets.QWidget):
    def __init__(self, number:int, title:str, parent=None):
        super().__init__(parent)
        self.number=number; self.is_active=False; self.is_complete=False
        self.setFixedHeight(52)
        h=QtWidgets.QHBoxLayout(self); h.setContentsMargins(16,10,16,10)
        self.circle=QtWidgets.QLabel(str(number)); self.circle.setObjectName("stepCircle")
        self.circle.setFixedSize(30,30); self.circle.setAlignment(QtCore.Qt.AlignCenter)
        self.title_label=QtWidgets.QLabel(title); self.title_label.setObjectName("stepTitle")
        h.addWidget(self.circle); h.addWidget(self.title_label); h.addStretch()
        self._update()
    def set_active(self,a): self.is_active=a; self._update()
    def set_complete(self,c): self.is_complete=c; self._update()
    def _update(self):
        if self.is_active:
            self.circle.setStyleSheet("QLabel#stepCircle{background:#0ea5e9;color:#000;border-radius:15px;font-weight:700;}")
            self.title_label.setStyleSheet("color:#e6e6e6;font-weight:600;")
        elif self.is_complete:
            self.circle.setStyleSheet("QLabel#stepCircle{background:#10b981;color:#000;border-radius:15px;font-weight:700;}")
            self.title_label.setStyleSheet("color:#a3a3a3;")
        else:
            self.circle.setStyleSheet("QLabel#stepCircle{background:#111;color:#666;border:1px solid #2a2a2a;border-radius:15px;}")
            self.title_label.setStyleSheet("color:#8a8a8a;")
    def mousePressEvent(self, e): self.parent().parent().parent()._on_step_clicked(self.number-1)

class StepMode(QtWidgets.QWidget):
    changed = QtCore.pyqtSignal()
    def __init__(self, area_icon_path=None, line_icon_path=None, icon_size=64):
        super().__init__()
        self.area_icon_path=area_icon_path; self.line_icon_path=line_icon_path; self.icon_size=icon_size
        v=QtWidgets.QVBoxLayout(self); v.setContentsMargins(32,24,32,24); v.setSpacing(16)

        title=_make_title("Select Capture Mode")
        title.setObjectName("modeTitle")              
        title.setStyleSheet("font-size: 22px; font-weight: 700; color:#27b6f3;")
        subtitle=_make_subtitle("Choose between area scan or line scan")

        row=QtWidgets.QWidget(); row.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        hl=QtWidgets.QHBoxLayout(row); hl.setSpacing(20)

        self.area_card=self._card("Area Scan","Standard 2D imaging\nIdeal for static objects", self.area_icon_path)
        self.area=QtWidgets.QRadioButton(); self.area.setChecked(True)
        self.area.toggled.connect(self.changed.emit); self.area.toggled.connect(self._refresh_cards)
        self.area_card.layout().addWidget(self.area, 0, QtCore.Qt.AlignCenter)

        self.line_card=self._card("Line Scan","Continuous scanning\nFor moving objects", self.line_icon_path)
        self.line=QtWidgets.QRadioButton(); self.line.toggled.connect(self.changed.emit); self.line.toggled.connect(self._refresh_cards)
        self.line_card.layout().addWidget(self.line, 0, QtCore.Qt.AlignCenter)

        hl.addWidget(self.area_card); hl.addWidget(self.line_card)
        v.addWidget(title); v.addWidget(subtitle); v.addWidget(row); v.addStretch(1)
        self._refresh_cards()
    def _icon(self, path):
        lbl=QtWidgets.QLabel(); lbl.setAlignment(QtCore.Qt.AlignCenter)
        if path and os.path.exists(path):
            pm=QtGui.QPixmap(path)
            if not pm.isNull():
                pm=pm.scaled(self.icon_size,self.icon_size,QtCore.Qt.KeepAspectRatio,QtCore.Qt.SmoothTransformation)
                lbl.setPixmap(pm); return lbl
        lbl.setFixedHeight(self.icon_size); return lbl
    def _card(self, title, desc, icon_path):
        w=QtWidgets.QWidget(); w.setObjectName("modeCard"); w.setFixedSize(300,220)
        w.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        l=QtWidgets.QVBoxLayout(w); l.setContentsMargins(18,18,18,18); l.setSpacing(10)
        t=QtWidgets.QLabel(title); t.setObjectName("cardTitle"); t.setAlignment(QtCore.Qt.AlignCenter)
        d=QtWidgets.QLabel(desc);  d.setObjectName("cardDesc");  d.setAlignment(QtCore.Qt.AlignCenter); d.setWordWrap(True)
        l.addWidget(self._icon(icon_path)); l.addWidget(t); l.addWidget(d); l.addStretch()
        return w
    def _refresh_cards(self):
        sel = "QWidget#modeCard{background:transparent;border:2px solid #0ea5e9;border-radius:12px;}"
        norm= "QWidget#modeCard{background:transparent;border:1px solid #242424;border-radius:12px;}"
        self.area_card.setStyleSheet(sel if self.area.isChecked() else norm)
        self.line_card.setStyleSheet(sel if self.line.isChecked() else norm)
    def value(self)->str: return "area" if self.area.isChecked() else "line"

class StepDevices(QtWidgets.QWidget):
    changed = QtCore.pyqtSignal()
    def __init__(self):
        super().__init__()
        v=QtWidgets.QVBoxLayout(self); v.setContentsMargins(32,24,32,24); v.setSpacing(14)
        title=_make_title("Select Cameras")
        subtitle=_make_subtitle("Choose one or more cameras")
        top=QtWidgets.QWidget(); ht=QtWidgets.QHBoxLayout(top); ht.setContentsMargins(0,0,0,0)
        self.count_lbl=QtWidgets.QLabel("0 devices found"); self.count_lbl.setObjectName("deviceCount")
        self.refresh=QtWidgets.QPushButton("Refresh Devices"); self.refresh.setObjectName("primaryButton"); self.refresh.clicked.connect(self.refresh_devices)
        ht.addWidget(self.count_lbl); ht.addStretch(); ht.addWidget(self.refresh)
        self.list=QtWidgets.QListWidget(); self.list.setObjectName("deviceList")
        self.list.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
        self.list.itemSelectionChanged.connect(self._on_sel); self.list.itemSelectionChanged.connect(self.changed.emit)
        bottom=QtWidgets.QWidget(); hb=QtWidgets.QHBoxLayout(bottom); hb.setContentsMargins(0,0,0,0)
        self.select_all=QtWidgets.QCheckBox("Select all cameras"); self.select_all.setTristate(True)
        self.select_all.setObjectName("selectAll"); self.select_all.stateChanged.connect(self._toggle_all)
        hb.addWidget(self.select_all); hb.addStretch()
        v.addWidget(title); v.addWidget(subtitle); v.addWidget(top); v.addWidget(self.list,1); v.addWidget(bottom)
        self.refresh_devices()
    def _counts(self):
        t=self.list.count(); s=len(self.list.selectedItems())
        self.count_lbl.setText(f"{t} device{'s' if t!=1 else ''} found • {s} selected")
    def _sync_all(self):
        t=self.list.count(); s=len(self.list.selectedItems())
        if t==0 or s==0: self.select_all.setCheckState(QtCore.Qt.Unchecked)
        elif s==t: self.select_all.setCheckState(QtCore.Qt.Checked)
        else: self.select_all.setCheckState(QtCore.Qt.PartiallyChecked)
    def _on_sel(self): self._counts(); self._sync_all()
    def _toggle_all(self, state:int):
        if state==QtCore.Qt.PartiallyChecked: return
        block=self.list.blockSignals(True)
        try:
            self.list.selectAll() if state==QtCore.Qt.Checked else self.list.clearSelection()
        finally:
            self.list.blockSignals(block)
        self.changed.emit(); self._counts(); self._sync_all()
    def refresh_devices(self):
        self.list.clear()
        try: cams=list_cameras()
        except Exception as e:
            cams=[]; QtWidgets.QMessageBox.critical(self,"Arena Error",str(e))
        for c in cams:
            it=QtWidgets.QListWidgetItem(f"📹  {c.model}  •  S/N: {c.serial}")
            it.setData(QtCore.Qt.UserRole, c.serial)
            it.setIcon(QtGui.QIcon.fromTheme("camera"))
            self.list.addItem(it)
        if self.select_all.checkState()==QtCore.Qt.Checked and self.list.count()>0: self.list.selectAll()
        self._counts(); self._sync_all()
    def selected_serials(self)->List[str]: return [i.data(QtCore.Qt.UserRole) for i in self.list.selectedItems()]

class StepCount(QtWidgets.QWidget):
    changed = QtCore.pyqtSignal()
    def __init__(self):
        super().__init__()
        v=QtWidgets.QVBoxLayout(self); v.setContentsMargins(32,24,32,24); v.setSpacing(14)
        title=_make_title("Images Per Camera")
        subtitle=_make_subtitle("Specify how many images to capture")
        form=QtWidgets.QWidget(); form.setObjectName("formContainer"); form.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        f=QtWidgets.QFormLayout(form); f.setContentsMargins(18,18,18,18); f.setLabelAlignment(QtCore.Qt.AlignRight)
        self.spin=QtWidgets.QSpinBox(); self.spin.setObjectName("imageCountSpin"); self.spin.setRange(1,10000); self.spin.setValue(10); self.spin.setMinimumWidth(160)
        self.spin.valueChanged.connect(self.changed.emit)
        f.addRow("Image Count:", self.spin)
        info=QtWidgets.QLabel("💡 Total images = count × number of cameras"); info.setObjectName("infoLabel")
        v.addWidget(title); v.addWidget(subtitle); v.addWidget(form); v.addWidget(info); v.addStretch(1)
    def value(self)->int: return self.spin.value()

class StepFolder(QtWidgets.QWidget):
    changed = QtCore.pyqtSignal()
    def __init__(self):
        super().__init__()
        v=QtWidgets.QVBoxLayout(self); v.setContentsMargins(32,24,32,24); v.setSpacing(14)
        title=_make_title("Save Location")
        subtitle=_make_subtitle("Choose where to save captured images")
        box=QtWidgets.QWidget(); box.setObjectName("formContainer"); box.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        bx=QtWidgets.QVBoxLayout(box); bx.setContentsMargins(18,18,18,18)
        lbl=QtWidgets.QLabel("Output Directory:"); lbl.setObjectName("formLabel")
        row=QtWidgets.QHBoxLayout(); row.setSpacing(10)
        self.edit=QtWidgets.QLineEdit(os.path.abspath("captures")); self.edit.setObjectName("pathEdit")
        btn=QtWidgets.QPushButton("📁 Browse"); btn.setObjectName("secondaryButton"); btn.clicked.connect(self._choose)
        row.addWidget(self.edit,1); row.addWidget(btn)
        bx.addWidget(lbl); bx.addLayout(row)
        v.addWidget(title); v.addWidget(subtitle); v.addWidget(box); v.addStretch(1)
        self.edit.textChanged.connect(self.changed.emit)
    def _choose(self):
        d=QtWidgets.QFileDialog.getExistingDirectory(self,"Select Folder",self.edit.text())
        if d: self.edit.setText(d)
    def value(self)->str: return self.edit.text().strip()

class StepCapture(QtWidgets.QWidget):
    def __init__(self, start_cb, stop_cb):
        super().__init__()
        self._start_cb=start_cb; self._stop_cb=stop_cb
        v=QtWidgets.QVBoxLayout(self); v.setContentsMargins(32,24,32,24); v.setSpacing(12)
        title=_make_title("Capturing Images")
        subtitle=_make_subtitle("Acquisition in progress…")
        box=QtWidgets.QWidget(); box.setObjectName("progressContainer"); box.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        bx=QtWidgets.QVBoxLayout(box); bx.setContentsMargins(14,14,14,14)
        self.pbar=QtWidgets.QProgressBar(); self.pbar.setObjectName("modernProgress"); self.pbar.setMinimumHeight(24)
        bx.addWidget(self.pbar)
        loglbl=QtWidgets.QLabel("📋 Capture Log"); loglbl.setObjectName("sectionLabel")
        self.log=QtWidgets.QPlainTextEdit(); self.log.setObjectName("captureLog"); self.log.setReadOnly(True)
        v.addWidget(title); v.addWidget(subtitle); v.addWidget(box); v.addWidget(loglbl); v.addWidget(self.log,1)
    @QtCore.pyqtSlot(int,int)
    def on_progress(self, d:int, t:int): self.pbar.setValue(int(100*d/max(1,t)))
    @QtCore.pyqtSlot(str)
    def on_status(self, msg:str): self.log.appendPlainText(msg)
    @QtCore.pyqtSlot(str)
    def on_failed(self, err:str): QtWidgets.QMessageBox.critical(self,"Capture Failed",err)
    def start(self): self.pbar.setValue(0); self.log.clear(); self._start_cb()
    def stop(self): self._stop_cb()

class StepPreview(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        v=QtWidgets.QVBoxLayout(self); v.setContentsMargins(32,24,32,24); v.setSpacing(12)
        title=_make_title("Image Preview")
        subtitle=_make_subtitle("Review captured images")
        self.scroll=QtWidgets.QScrollArea(); self.scroll.setObjectName("previewScroll"); self.scroll.setWidgetResizable(True)
        self.gallery=QtWidgets.QWidget(); self.grid=QtWidgets.QGridLayout(self.gallery); self.grid.setSpacing(12); self.grid.setContentsMargins(8,8,8,8)
        self.scroll.setWidget(self.gallery)
        v.addWidget(title); v.addWidget(subtitle); v.addWidget(self.scroll,1)
    def _clear(self):
        while self.grid.count():
            it=self.grid.takeAt(0); w=it.widget()
            if w: w.deleteLater()
    def set_paths(self, paths:List[str]):
        self._clear(); picks=_pick_previews_by_rule(paths); r=c=0
        for p, cam in picks:
            card=QtWidgets.QWidget(); card.setObjectName("previewCard"); card.setAttribute(QtCore.Qt.WA_StyledBackground, True)
            cl=QtWidgets.QVBoxLayout(card); cl.setContentsMargins(10,10,10,10)
            img=QtWidgets.QLabel(); img.setAlignment(QtCore.Qt.AlignCenter)
            pm=QtGui.QPixmap(p)
            if not pm.isNull(): pm=pm.scaled(360,270,QtCore.Qt.KeepAspectRatio,QtCore.Qt.SmoothTransformation)
            img.setPixmap(pm)
            cap=QtWidgets.QLabel(f"📷 {cam}"); cap.setObjectName("previewCamera")
            name=QtWidgets.QLabel(os.path.basename(p)); name.setObjectName("previewFilename")
            cl.addWidget(img); cl.addWidget(cap); cl.addWidget(name)
            self.grid.addWidget(card, r, c); c+=1
            if c>=2: c=0; r+=1

# ---------- Main ----------
class CameraWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._toasts = ToastManager.install(self)
        self._worker: Optional[CaptureWorker] = None
        self._saved_paths: List[str] = []

        root=QtWidgets.QHBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(0)

        # Sidebar (slimmer + visible right divider)
        sidebar=QtWidgets.QWidget(); sidebar.setObjectName("sidebar"); sidebar.setFixedWidth(230)
        sidebar.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Expanding)
        sidebar.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        sl=QtWidgets.QVBoxLayout(sidebar); sl.setContentsMargins(0,0,0,0); sl.setSpacing(0)
        steps=QtWidgets.QWidget(); col=QtWidgets.QVBoxLayout(steps); col.setContentsMargins(8,16,8,16)
        self.step_indicators=[]
        for i, t in enumerate(["Mode","Cameras","Images","Location","Capture","Preview"]):
            ind=StepIndicator(i+1, t); self.step_indicators.append(ind); col.addWidget(ind)
        sl.addWidget(steps); sl.addStretch()
        root.addWidget(sidebar)
        sep = QtWidgets.QWidget()
        sep.setObjectName("sidebarSeparator")
        sep.setFixedWidth(1)
        root.addWidget(sep)

        # Main area
        main=QtWidgets.QWidget(); main.setObjectName("mainContainer")
        main.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        ml=QtWidgets.QVBoxLayout(main); ml.setContentsMargins(0,0,0,0); ml.setSpacing(0)

        top=QtWidgets.QWidget(); top.setObjectName("topBar"); top.setFixedHeight(44)
        top.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        tl=QtWidgets.QHBoxLayout(top); tl.setContentsMargins(12,6,12,6); tl.addStretch()
        self.btn_help=QtWidgets.QToolButton(); self.btn_help.setObjectName("helpButton"); self.btn_help.setAutoRaise(True)
        self.btn_help.setToolTip("Help (F1)")
        self.btn_help.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_MessageBoxQuestion))
        self.btn_help.setIconSize(QtCore.QSize(20,20)); self.btn_help.setFixedSize(34,34)
        self.btn_help.clicked.connect(self._show_help)
        QtWidgets.QShortcut(QtGui.QKeySequence.HelpContents, self, activated=self._show_help)
        tl.addWidget(self.btn_help, 0, QtCore.Qt.AlignRight)

        self.stack=QtWidgets.QStackedWidget(); self.stack.setObjectName("contentStack")
        self.stack.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.step_mode   = StepMode(AREA_ICON_PATH, LINE_ICON_PATH, icon_size=56)
        self.step_devs   = StepDevices()
        self.step_devs.refresh.clicked.connect(lambda: self._toast("Scanning for cameras…", "info", 1500))
        self.step_devs.refresh.clicked.connect(
            lambda: QtCore.QTimer.singleShot(
                500,
                lambda: self._toast(self.step_devs.count_lbl.text(), "info", 1800)
            )
        )
        self.step_count  = StepCount()
        self.step_folder = StepFolder()
        self.step_capture= StepCapture(self._start_capture, self._stop_capture)
        self.step_preview= StepPreview()
        for w in [self.step_mode,self.step_devs,self.step_count,self.step_folder,self.step_capture,self.step_preview]:
            self.stack.addWidget(w)

        ml.addWidget(top); ml.addWidget(self.stack,1)

        nav=QtWidgets.QWidget(); nav.setObjectName("navBar"); nav.setFixedHeight(64)
        nav.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        nl=QtWidgets.QHBoxLayout(nav); nl.setContentsMargins(16,10,16,10)
        self.btn_back=QtWidgets.QPushButton("← Back"); self.btn_back.setObjectName("navButton"); self.btn_back.setFixedHeight(40); self.btn_back.setFixedWidth(110)
        self.btn_next=QtWidgets.QPushButton("Next →"); self.btn_next.setObjectName("primaryNavButton"); self.btn_next.setFixedHeight(40); self.btn_next.setFixedWidth(110)
        self.btn_back.clicked.connect(self._go_back); self.btn_next.clicked.connect(self._go_next)
        nl.addStretch(); nl.addWidget(self.btn_back); nl.addWidget(self.btn_next)
        ml.addWidget(nav)

        root.addWidget(main,1)

        # Style
        self._apply_flat_black_qss()

        # validations
        self.step_mode.changed.connect(self._update_nav)
        self.step_devs.changed.connect(self._update_nav)
        self.step_count.changed.connect(self._update_nav)
        self.step_folder.changed.connect(self._update_nav)
        self._update_nav()

    def _toast(self, text: str, kind: str = "info", dur_ms: int = 2500):
        mgr = ToastManager.instance()
        if mgr:
            mgr.show(text, kind=kind, duration_ms=dur_ms)

    def _wire_milestone_toasts(self):
        """Show small toasts for notable status messages coming from the worker."""
        if not self._worker:
            return

        def maybe_toast(msg: str):
            m = msg.lower()
            if "=== applied camera settings" in m:
                self._toast("Camera settings applied.", "success", 1600)
            if "skipped (no frame)" in m:
                self._toast("A frame was skipped.", "warning", 1800)

        self._worker.status.connect(maybe_toast)

    # ---- flow helpers ----
    def current_step(self)->int: return self.stack.currentIndex()
    def _on_step_clicked(self, idx:int):
        cur=self.current_step()
        if idx==cur: return
        if idx>cur and not self._validate(cur): return
        if idx>=5 and not self._saved_paths:
            # QtWidgets.QMessageBox.information(self,"Info","Complete a capture before viewing preview.")
            self._toast("Complete a capture before viewing preview.", "warning", 2500)
            return
        self.stack.setCurrentIndex(idx); self._update_nav()
    def _go_back(self):
        i=self.current_step()
        if i>0: self.stack.setCurrentIndex(i-1); self._update_nav()
    def _restart_app_soft(self):
        try:
            self._stop_capture()
            if self._worker:
                try:
                    self._worker.progress.disconnect(self.step_capture.on_progress)
                    self._worker.status.disconnect(self.step_capture.on_status)
                    self._worker.failed.disconnect(self.step_capture.on_failed)
                    self._worker.finished_ok.disconnect(self._on_capture_done)
                except Exception: pass
                self._worker=None
        except Exception: pass
        self._saved_paths=[]
        try: self.step_preview._clear()
        except Exception: pass
        try: self.step_mode.area.setChecked(True); self.step_mode._refresh_cards()
        except Exception: pass
        try: self.step_devs.refresh_devices(); self.step_devs.list.clearSelection()
        except Exception: pass
        try: self.step_count.spin.setValue(10)
        except Exception: pass
        try: self.step_folder.edit.setText(os.path.abspath("captures"))
        except Exception: pass
        try: self.step_capture.pbar.setValue(0); self.step_capture.log.clear()
        except Exception: pass
        self.stack.setCurrentIndex(0); self._update_nav()
        self._toast("Ready for a new session.", "success", 2000)
    def _go_next(self):
        i=self.current_step()
        if not self._validate(i): return
        if i==3:
            self.stack.setCurrentIndex(4); self._update_nav(); QtCore.QTimer.singleShot(100, self.step_capture.start); return
        if i<5: self.stack.setCurrentIndex(i+1); self._update_nav()
        else: self._restart_app_soft()
    def _validate(self, idx:int)->bool:
        if idx==1:
            ok=len(self.step_devs.selected_serials())>0
            if not ok:
                self._toast("Please select at least one camera.", "warning", 2500)
            return ok
        if idx==2:
            ok=self.step_count.value()>=1
            if not ok: 
                self._toast("Image count must be ≥ 1.", "warning", 2500)
            return ok
        if idx==3:
            ok=bool(self.step_folder.value())
            if not ok: 
                self._toast("Choose a valid save folder.", "warning", 2500)
            return ok
        return True
    def _update_nav(self):
        i=self.current_step()
        for idx, ind in enumerate(self.step_indicators):
            ind.set_active(idx==i); ind.set_complete(idx<i or (idx==5 and self._saved_paths))
        self.btn_back.setEnabled(i>0 and i<4)
        if i==4:
            self.btn_next.setEnabled(False); self.btn_next.setText("Capturing...")
        elif i==5:
            self.btn_next.setEnabled(True); self.btn_next.setText("Finish")
        else:
            self.btn_next.setEnabled(self._validate(i)); self.btn_next.setText("Next →")
    def _start_capture(self):
        mode=self.step_mode.value(); serials=self.step_devs.selected_serials(); n=self.step_count.value(); base=self.step_folder.value()
        self._saved_paths=[]
        self._worker=CaptureWorker(mode, serials, n, base)
        self._worker.progress.connect(self.step_capture.on_progress)
        self._worker.status.connect(self.step_capture.on_status)
        self._worker.failed.connect(self.step_capture.on_failed)
        self._worker.finished_ok.connect(self._on_capture_done)
        cams = len(serials)
        self._toast(f"Starting capture: {n} image(s) × {cams} camera(s)…", "info", 2500)
        self._worker.failed.connect(lambda err: self._toast("Capture failed — see log.", "error", 4000))
        self._wire_milestone_toasts()
        self._worker.start()
    def _stop_capture(self):
        try:
            if self._worker and self._worker.isRunning():
                self._worker.stop(); self._worker.wait(2000)
        except Exception: pass
    def _on_capture_done(self, paths:List[str]):
        self._saved_paths=paths or []
        count = len(self._saved_paths)
        self._toast(f"Capture complete — saved {count} file(s).", "success", 3000)
        self.step_preview.set_paths(self._saved_paths)
        self.stack.setCurrentIndex(5); self._update_nav()
    def _show_help(self): SimpleHelpDialog(self).exec_()

    # ---------- Style ----------
    def _apply_flat_black_qss(self):
        self.setStyleSheet("""
        * { font-family: 'Segoe UI', Arial, sans-serif; font-size: 14px; }
        QMainWindow, QWidget { background:#000; color:#e5e5e5; }

        /* Sidebar: thin delimiter line on the right */
        QWidget#sidebar { background:#000; border-right: 1px solid #1e1e1e; }

        QWidget#mainContainer { background:#000; }
        QStackedWidget#contentStack { background:#000; }
        QWidget#topBar, QWidget#navBar { background:#000; border:none; }

        /* Make common widgets transparent (prevents grey strips) */
        QLabel, QGroupBox, QFrame, QTextBrowser, QScrollArea, QAbstractScrollArea,
        QRadioButton, QCheckBox, QToolButton, QPlainTextEdit, QListWidget,
        QProgressBar, QLineEdit, QSpinBox, QPushButton { background: transparent; }

       QWidget#sidebarSeparator {
        background: #2a2a2a;   /* medium grey line */
        min-width: 1px;
        max-width: 1px;
        }


        /* (Optional) make all titles/subtitles transparent to kill strips */
        QLabel#pageTitle, QLabel#pageSubtitle {
            background: transparent;
            border: none;
        }


        /* Help dialog */
        QFrame#helpCard { background:#000; border:1px solid #222; border-radius:10px; }
        QTextBrowser#helpText { color:#e5e5e5; border:none; }

        /* Titles/subtitles explicitly transparent */
        QLabel#pageTitle, QLabel#pageSubtitle { background: transparent; border: none; }
        QLabel#pageTitle    { color:#fff; font-size:26px; font-weight:700; }
        QLabel#pageSubtitle { color:#9e9e9e; }

        QLabel#deviceCount  { color:#9e9e9e; }
        QLabel#sectionLabel { color:#d0d0d0; font-weight:600; }
        QLabel#formLabel    { color:#d0d0d0; }
        QLabel#infoLabel    { color:#a0a0a0; font-size:12px; padding:8px;
                              background:#0a0a0a; border:1px solid #222; border-radius:6px; }

        /* Mode cards */
        QWidget#modeCard { border:1px solid #242424; border-radius:12px; }
        QWidget#modeCard:hover { border-color:#303030; }
        QLabel#cardTitle { color:#f1f1f1; font-size:18px; font-weight:700; }
        QLabel#cardDesc  { color:#a8a8a8; font-size:13px; }

        QRadioButton { color:#e5e5e5; }
        QRadioButton::indicator { width:18px; height:18px; border-radius:9px; border:1px solid #333; background:#111; }
        QRadioButton::indicator:checked { background:#0ea5e9; border:1px solid #0ea5e9; }

        /* Device list */
        QListWidget#deviceList { border:1px solid #1f1f1f; border-radius:8px; }
        QListWidget#deviceList::item { background:#0a0a0a; border:1px solid #171717; border-radius:6px; padding:14px; margin:4px; }
        QListWidget#deviceList::item:hover { background:#111; border-color:#222; }
        QListWidget#deviceList::item:selected { background:#111; border:1px solid #0ea5e9; color:#fff; }

        QCheckBox#selectAll { color:#dcdcdc; font-weight:600; }
        QCheckBox#selectAll::indicator { width:16px; height:16px; border:1px solid #333; background:#0a0a0a; border-radius:3px; }
        QCheckBox#selectAll::indicator:checked { background:#0ea5e9; border:1px solid #0ea5e9; }
        QCheckBox#selectAll::indicator:indeterminate { background:#666; }

        /* Forms */
        QWidget#formContainer { border:1px solid #1f1f1f; border-radius:10px; }
        QLineEdit#pathEdit, QSpinBox#imageCountSpin {
            background:#0a0a0a; border:1px solid #222; border-radius:8px; padding:10px 12px; color:#f1f1f1;
        }
        QLineEdit#pathEdit:focus, QSpinBox#imageCountSpin:focus { border:1px solid #0ea5e9; background:#0d0d0d; }
        QSpinBox#imageCountSpin::up-button, QSpinBox#imageCountSpin::down-button { background:#1a1a1a; border:none; border-radius:4px; width:18px; }

        /* Progress/Log */
        QWidget#progressContainer { border:1px solid #1f1f1f; border-radius:10px; }
        QProgressBar#modernProgress { background:#0a0a0a; border:1px solid #222; border-radius:12px; text-align:center; color:#e5e5e5; font-weight:600; }
        QProgressBar#modernProgress::chunk { background:#0ea5e9; border-radius:12px; }
        QPlainTextEdit#captureLog { background:#0a0a0a; border:1px solid #1f1f1f; border-radius:8px; padding:12px; color:#dcdcdc; font-family:Consolas,Monaco,'Courier New'; font-size:12px; }

        /* Preview */
        QScrollArea#previewScroll { border:none; }
        QWidget#previewCard { background:#0a0a0a; border:1px solid #1f1f1f; border-radius:10px; }
        QWidget#previewCard:hover { border-color:#2a2a2a; }
        QLabel#previewCamera { color:#0ea5e9; font-weight:600; font-size:13px; }
        QLabel#previewFilename { color:#9a9a9a; font-size:11px; font-family:Consolas; }

        /* Buttons */
        QPushButton#primaryButton, QPushButton#primaryNavButton {
            background:#0ea5e9; color:#000; border:none; border-radius:8px; padding:10px 18px; font-weight:700;
        }
        QPushButton#primaryButton:hover, QPushButton#primaryNavButton:hover { background:#27b6f3; }
        QPushButton#primaryButton:pressed, QPushButton#primaryNavButton:pressed { background:#0894cf; }
        QPushButton#secondaryButton { background:#111; color:#e5e5e5; border:1px solid #2a2a2a; border-radius:8px; padding:10px 18px; font-weight:600; }
        QPushButton#secondaryButton:hover { background:#151515; border-color:#3a3a3a; }
        QPushButton#navButton { background:#111; color:#dcdcdc; border:1px solid #2a2a2a; border-radius:8px; font-weight:600; }
        QPushButton#navButton:hover { background:#151515; border-color:#3a3a3a; }

        /* Help button */
        QToolButton#helpButton { background:#0ea5e9; border:none; border-radius:17px; }
        QToolButton#helpButton:hover { background:#27b6f3; }
        QToolButton#helpButton:pressed { background:#0894cf; }

        /* Scrollbars */
        QScrollBar:vertical { background:#0a0a0a; width:12px; border:none; }
        QScrollBar::handle:vertical { background:#2a2a2a; min-height:30px; border-radius:6px; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
        QScrollBar:horizontal { background:#0a0a0a; height:12px; border:none; }
        QScrollBar::handle:horizontal { background:#2a2a2a; min-width:30px; border-radius:6px; }
        """)

# ---------- App palette/style ----------
def _apply_dark_fusion(app: QtWidgets.QApplication):
    # Force Fusion style to avoid Windows theme painting artifacts
    app.setStyle("Fusion")
    pal = QtGui.QPalette()
    # Base colors
    base = QtGui.QColor(0, 0, 0)
    mid  = QtGui.QColor(10,10,10)
    text = QtGui.QColor(229,229,229)
    pal.setColor(QtGui.QPalette.Window, base)
    pal.setColor(QtGui.QPalette.Base, mid)
    pal.setColor(QtGui.QPalette.AlternateBase, base)
    pal.setColor(QtGui.QPalette.ToolTipBase, base)
    pal.setColor(QtGui.QPalette.ToolTipText, text)
    pal.setColor(QtGui.QPalette.Text, text)
    pal.setColor(QtGui.QPalette.Button, base)
    pal.setColor(QtGui.QPalette.ButtonText, text)
    pal.setColor(QtGui.QPalette.Highlight, QtGui.QColor(14,165,233))
    pal.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor(0,0,0))
    app.setPalette(pal)

# ---------- Entrypoint ----------
def main():
    QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)
    QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
    app = QtWidgets.QApplication(sys.argv)
    _apply_dark_fusion(app)  # <- important to kill the grey strips from OS theme
    win = CameraWidget()
    win.setWindowTitle("Camera Acquisition — Flat Black")
    win.resize(1280, 800)
    win.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
