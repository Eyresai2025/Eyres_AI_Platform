from __future__ import annotations
import sys, os
from typing import List, Tuple
from PyQt5 import QtCore, QtGui, QtWidgets
import shutil
from pathlib import Path

# ---------------- Dependency helper: PyYAML on demand ----------------
def require_yaml(parent: QtWidgets.QWidget | None = None):
    """
    Ensure PyYAML is available. If not installed, ask the user to install it,
    try to install via pip, then import again. Raises ImportError if still missing.
    """
    try:
        import yaml  # type: ignore
        return yaml
    except Exception:
        # Ask user if we should install
        ans = QtWidgets.QMessageBox.question(
            parent,
            "Missing dependency",
            "PyYAML is required but not installed.\n\n"
            "Install it now via pip?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        if ans == QtWidgets.QMessageBox.Yes:
            try:
                import subprocess
                # Use -m pip to install for the same interpreter
                subprocess.check_call([sys.executable, "-m", "pip", "install", "pyyaml"])
                import yaml  # type: ignore
                QtWidgets.QMessageBox.information(parent, "Installed", "PyYAML installed successfully.")
                return yaml
            except Exception as e:
                QtWidgets.QMessageBox.critical(parent, "Install failed",
                                               f"Could not install PyYAML automatically.\n\nError:\n{e}\n\n"
                                               f"You can install it manually:\n"
                                               f"{sys.executable} -m pip install pyyaml")
                raise ImportError("PyYAML not available and automatic install failed.") from e
        else:
            raise ImportError("PyYAML not available and user declined installation.")

# --- Dynamic path helpers (PyInstaller-friendly) ---
def app_base_dir() -> Path:
    """Root folder of the app (PyInstaller-safe)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent

def candidate_dirs() -> list[Path]:
    """Places to search for shipped assets/models/datasets next to the app."""
    base = app_base_dir()
    return [
        base,
        base / "assets",
        base / "Assets",
        base / "models",
        base / "Models",
        base / "weights",
        base / "Weights",
        base / "data",
        base / "Data",
        base.parent / "assets",
        base.parent / "models",
        base.parent / "data",
    ]

def find_first_file(*names_or_relpaths: str) -> Path | None:
    """Find the first existing file in candidate dirs."""
    for folder in candidate_dirs():
        for name in names_or_relpaths:
            p = (folder / name)
            if p.is_file():
                return p
    return None

def fwd(p: Path | str) -> str:
    """Normalize to forward slashes (Ultralytics-friendly on Windows too)."""
    return str(p).replace("\\", "/")

# ---------- ultra-short help ----------
HELP_HTML = """
<div id="helpRoot">
  <h1>Two-Step Wizard</h1>
  <ol>
    <li><b>Model</b> — Pick exactly one (YOLO 1 / YOLO 2 / Detectron 1 / Detectron 2)</li>
    <li><b>Train</b> — Use the sidebar: Dataset → Segmentation → Detection → Hyperparams → Run</li>
  </ol>
  <p>Training is CPU-only. Segmentation runs before Detection.</p>
</div>
"""

# --------------------------------------Helpers---------------------------------
class SimpleHelpDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Help")
        self.resize(560, 360)
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(14, 14, 14, 14)
        frame = QtWidgets.QFrame()
        frame.setObjectName("helpCard")
        flay = QtWidgets.QVBoxLayout(frame)
        txt = QtWidgets.QTextBrowser()
        txt.setObjectName("helpText")
        txt.setOpenExternalLinks(True)
        txt.setHtml(HELP_HTML)
        flay.addWidget(txt)
        v.addWidget(frame, 1)
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        btns.rejected.connect(self.reject)
        v.addWidget(btns, 0, QtCore.Qt.AlignRight)

# ================================== new index button ==========================================
class DatasetMergeDialog(QtWidgets.QDialog):
    """
    Simple dialog to run the user's 3-step dataset merge:
      1) merge classes into base data.yaml (nc + names)
      2) rewrite class ids in update labels (in place)
      3) copy updated images/labels into base/train and base/test
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Merge / Update Dataset")
        self.resize(720, 520)
        self.out_base_yaml = ""  # set after successful run

        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(10)

        # --- sections ---
        self.base_yaml = self._file_row("Base data.yaml")
        self.update_yaml = self._file_row("Update data.yaml")

        # Update/train+test images & labels (sources to copy FROM)
        self.src_train_images = self._folder_row("Update train/images")
        self.src_train_labels = self._folder_row("Update train/labels")
        self.src_test_images  = self._folder_row("Update test/images")
        self.src_test_labels  = self._folder_row("Update test/labels")

        # Destination in base (copy TO)
        self.dst_train_images = self._folder_row("Base train/images (dest)")
        self.dst_train_labels = self._folder_row("Base train/labels (dest)")
        self.dst_test_images  = self._folder_row("Base test/images (dest)")
        self.dst_test_labels  = self._folder_row("Base test/labels (dest)")

        form = QtWidgets.QFormLayout()
        form.setLabelAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        form.setFormAlignment(QtCore.Qt.AlignVCenter)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)

        for lbl, row in [
            self.base_yaml, self.update_yaml,
            self.src_train_images, self.src_train_labels,
            self.src_test_images,  self.src_test_labels,
            self.dst_train_images, self.dst_train_labels,
            self.dst_test_images,  self.dst_test_labels,
        ]:
            form.addRow(lbl, row)

        card = QtWidgets.QFrame()
        card.setObjectName("card")
        card.setLayout(form)
        card.setStyleSheet("""
            QFrame#card {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(30,41,59,0.55), stop:1 rgba(15,23,42,0.55));
                border:1px solid #334155; border-radius:12px;
            }
        """)
        v.addWidget(card, 1)

        # --- run/cancel buttons ---
        btns = QtWidgets.QDialogButtonBox()
        self.run_btn = btns.addButton("Run merge", QtWidgets.QDialogButtonBox.AcceptRole)
        self.cancel_btn = btns.addButton(QtWidgets.QDialogButtonBox.Cancel)
        self.run_btn.clicked.connect(self._run_merge)
        self.cancel_btn.clicked.connect(self.reject)
        v.addWidget(btns)

    # ---------- chip label + browse rows ----------
    def _chip(self, text: str) -> QtWidgets.QLabel:
        lb = QtWidgets.QLabel(text)
        lb.setAlignment(QtCore.Qt.AlignCenter)
        lb.setStyleSheet("""
            color:#ffffff; font-weight:600; font-size:14px;
            background: rgba(148,163,184,0.18);
            border:1px solid rgba(148,163,184,0.35);
            border-radius:10px; padding:4px 10px; min-height:32px;
        """)
        return lb

    def _file_row(self, label_text: str):
        label = self._chip(label_text)
        edit  = QtWidgets.QLineEdit(); edit.setMinimumHeight(34); edit.setStyleSheet("color:#ffffff;")
        btn   = QtWidgets.QToolButton(); btn.setText("Browse…"); btn.setMinimumHeight(32)
        def pick():
            fn, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select file", os.path.expanduser("~"), "YAML Files (*.yaml *.yml);;All Files (*.*)")
            if fn: edit.setText(fn)
        btn.clicked.connect(pick)
        row = QtWidgets.QHBoxLayout(); row.setSpacing(8); row.setContentsMargins(0,0,0,0)
        row.addWidget(edit, 1); row.addWidget(btn, 0)
        w = QtWidgets.QWidget(); w.setLayout(row)
        return label, w

    def _folder_row(self, label_text: str):
        label = self._chip(label_text)
        edit  = QtWidgets.QLineEdit(); edit.setMinimumHeight(34); edit.setStyleSheet("color:#ffffff;")
        btn   = QtWidgets.QToolButton(); btn.setText("Browse…"); btn.setMinimumHeight(32)
        def pick():
            dn = QtWidgets.QFileDialog.getExistingDirectory(self, "Select folder", os.path.expanduser("~"))
            if dn: edit.setText(dn)
        btn.clicked.connect(pick)
        row = QtWidgets.QHBoxLayout(); row.setSpacing(8); row.setContentsMargins(0,0,0,0)
        row.addWidget(edit, 1); row.addWidget(btn, 0)
        w = QtWidgets.QWidget(); w.setLayout(row)
        return label, w

    # helpers to read QLineEdit values
    def _val(self, row_widget: QtWidgets.QWidget) -> str:
        le = row_widget.findChild(QtWidgets.QLineEdit)
        return (le.text() or "").strip() if le else ""

    # ---------- run merge ----------
    def _run_merge(self):
        yaml = require_yaml(self)
        import shutil as _shutil

        base_yaml_path   = self._val(self.base_yaml[1])
        update_yaml_path = self._val(self.update_yaml[1])

        src_train_images = self._val(self.src_train_images[1])
        src_train_labels = self._val(self.src_train_labels[1])
        src_test_images  = self._val(self.src_test_images[1])
        src_test_labels  = self._val(self.src_test_labels[1])

        dst_train_images = self._val(self.dst_train_images[1])
        dst_train_labels = self._val(self.dst_train_labels[1])
        dst_test_images  = self._val(self.dst_test_images[1])
        dst_test_labels  = self._val(self.dst_test_labels[1])

        # derive update label dirs explicitly
        update_train_dir = src_train_labels
        update_test_dir  = src_test_labels

        # --- validate ---
        required = [
            base_yaml_path, update_yaml_path,
            src_train_images, src_train_labels, src_test_images, src_test_labels,
            dst_train_images, dst_train_labels, dst_test_images, dst_test_labels
        ]
        if not all(required):
            QtWidgets.QMessageBox.warning(self, "Missing", "Please fill all paths.")
            return
        for p in [base_yaml_path, update_yaml_path]:
            if not os.path.isfile(p):
                QtWidgets.QMessageBox.warning(self, "Not found", f"File not found:\n{p}")
                return
        for d in [src_train_images, src_train_labels, src_test_images, src_test_labels,
                  dst_train_images, dst_train_labels, dst_test_images, dst_test_labels]:
            if not os.path.isdir(d):
                QtWidgets.QMessageBox.warning(self, "Not a folder", f"Folder not found:\n{d}")
                return

        try:
            # ===== STEP 1: MERGE CLASSES =====
            with open(base_yaml_path, "r", encoding="utf-8") as f:
                base_data = yaml.safe_load(f) or {}
            with open(update_yaml_path, "r", encoding="utf-8") as f:
                update_data = yaml.safe_load(f) or {}

            base_data.setdefault("names", [])
            update_names = update_data.get("names", [])
            for cls in update_names:
                if cls not in base_data["names"]:
                    base_data["names"].append(cls)
            base_data["nc"] = len(base_data["names"])

            class InlineList(list): pass
            def represent_inline_list(dumper, data):
                return dumper.represent_sequence('tag:yaml.org,2002:seq', data, flow_style=True)
            yaml.add_representer(InlineList, represent_inline_list)
            base_data['names'] = InlineList(base_data['names'])

            with open(base_yaml_path, 'w', encoding="utf-8") as f:
                yaml.safe_dump(base_data, f, default_flow_style=False, sort_keys=False)

            # ===== STEP 2: UPDATE LABELS (IN PLACE) =====
            update_to_final_map = {i: base_data['names'].index(cls) for i, cls in enumerate(update_names)}

            def update_labels_in_place(folder, mapping):
                files = [f for f in os.listdir(folder) if f.endswith('.txt')]
                for item in files:
                    fp = os.path.join(folder, item)
                    rows = []
                    with open(fp, 'r', encoding="utf-8") as myfile:
                        for line in myfile:
                            s = line.strip()
                            if s:
                                parts = s.split(" ")
                                rows.append(parts)
                    for r in rows:
                        old = r[0]
                        if old.isdigit():
                            r[0] = str(mapping.get(int(old), int(old)))
                    with open(fp, 'w', encoding="utf-8") as wf:
                        for r in rows:
                            wf.write(" ".join(r) + "\n")

            update_labels_in_place(update_train_dir, update_to_final_map)
            update_labels_in_place(update_test_dir,  update_to_final_map)

            # ===== STEP 3: COPY FILES =====
            for d in [dst_train_images, dst_train_labels, dst_test_images, dst_test_labels]:
                os.makedirs(d, exist_ok=True)

            def copy_files(src, dst):
                for file in os.listdir(src):
                    s = os.path.join(src, file)
                    d = os.path.join(dst, file)
                    if os.path.isfile(s):
                        _shutil.copy2(s, d)

            copy_files(src_train_images, dst_train_images)
            copy_files(src_train_labels, dst_train_labels)
            copy_files(src_test_images,  dst_test_images)
            copy_files(src_test_labels,  dst_test_labels)

            # success
            self.out_base_yaml = base_yaml_path
            self.accept()

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Merge failed", str(e))

# ================================== Step indicator ==========================================
class StepIndicator(QtWidgets.QWidget):
    def __init__(self, number: int, title: str, parent=None):
        super().__init__(parent)
        self.number = number
        self.is_active = False
        self.is_complete = False
        self.setFixedHeight(56)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)

        self.circle = QtWidgets.QLabel(str(number))
        self.circle.setFixedSize(32, 32)
        self.circle.setAlignment(QtCore.Qt.AlignCenter)
        self.circle.setObjectName("stepCircle")

        self.title_label = QtWidgets.QLabel(title)
        self.title_label.setObjectName("stepTitle")
        self.title_label.setAutoFillBackground(False)

        layout.addWidget(self.circle)
        layout.addWidget(self.title_label)
        layout.addStretch()
        self._update_style()

    def set_active(self, active: bool):
        self.is_active = active
        self._update_style()

    def set_complete(self, complete: bool):
        self.is_complete = complete
        self._update_style()

    def _update_style(self):
        if self.is_active:
            self.circle.setStyleSheet("""
                QLabel#stepCircle {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 #0ea5e9, stop:1 #0284c7);
                    color: white; border-radius: 16px; font-weight: 600;
                }""")
            self.title_label.setStyleSheet("color: #e2e8f0; font-weight: 600;")
        elif self.is_complete:
            self.circle.setStyleSheet("""
                QLabel#stepCircle {
                    background: #10b981; color: white; border-radius: 16px; font-weight: 600;
                }""")
            self.title_label.setStyleSheet("color: #94a3b8;")
        else:
            self.circle.setStyleSheet("""
                QLabel#stepCircle {
                    background: #334155; color: #64748b; border-radius: 16px; font-weight: 600;
                }""")
            self.title_label.setStyleSheet("color: #64748b;")

# ================================== Pages ====================================================
class StepModel(QtWidgets.QWidget):
    changed = QtCore.pyqtSignal()
    card_selected = QtCore.pyqtSignal(str)

    def __init__(self):
        super().__init__()
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(32, 32, 32, 32)
        v.setSpacing(24)

        title = QtWidgets.QLabel("Select Model")
        title.setObjectName("pageTitle")
        title.setAutoFillBackground(False)
        title.setStyleSheet("""
            background: transparent;
            font-size: 26px;
            color: #27b6f3;
            font-weight: 700;
        """)
        subtitle = QtWidgets.QLabel("Choose one model to proceed")
        subtitle.setObjectName("pageSubtitle")
        subtitle.setAutoFillBackground(False)
        subtitle.setStyleSheet("background: transparent;font-size: 13px;")

        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(20)

        self._cards: List[Tuple[QtWidgets.QWidget, QtWidgets.QRadioButton, str]] = []

        def key_for(label_text: str) -> str:
            return {"YOLO Segmentation": "seg",
                    "YOLO Detection": "det",
                    "Detectron 1": "d1",
                    "Detectron 2": "d2"}[label_text]

        def add_card(r, c, label_text: str):
            card = QtWidgets.QWidget()
            card.setObjectName("modeCard")
            card.setFixedSize(280, 120)
            card.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))

            lay = QtWidgets.QVBoxLayout(card)
            lay.setContentsMargins(24, 16, 24, 16)
            lay.setSpacing(8)

            title_lbl = QtWidgets.QLabel(label_text)
            title_lbl.setObjectName("cardTitle")
            title_lbl.setAlignment(QtCore.Qt.AlignCenter)
            title_lbl.setStyleSheet("color: #27b6f3; font-weight: 600;")

            rb = QtWidgets.QRadioButton()
            rb.toggled.connect(self.changed.emit)
            rb.toggled.connect(self._update_card_styles)

            lay.addWidget(title_lbl)
            lay.addStretch()
            lay.addWidget(rb, 0, QtCore.Qt.AlignCenter)

            def on_card_clicked():
                rb.setChecked(True)
                self._update_card_styles()
                self.card_selected.emit(key_for(label_text))

            def _make_click_handler(callback):
                def handler(ev):
                    if ev.button() == QtCore.Qt.LeftButton:
                        callback()
                        ev.accept()
                    else:
                        ev.ignore()
                return handler

            card.mouseReleaseEvent = _make_click_handler(on_card_clicked)  # type: ignore

            grid.addWidget(card, r, c)
            self._cards.append((card, rb, label_text))

        # ADD THE CARDS
        add_card(0, 0, "YOLO Segmentation")
        add_card(0, 1, "YOLO Detection")
        add_card(1, 0, "Detectron 1")
        add_card(1, 1, "Detectron 2")

        # Default selection
        self._cards[0][1].setChecked(True)
        self._update_card_styles()

        # Put widgets on the page
        v.addWidget(title)
        v.addWidget(subtitle)
        v.addSpacing(8)
        v.addLayout(grid)
        v.addStretch(1)

    def _update_card_styles(self):
        for card, rb, _ in self._cards:
            if rb.isChecked():
                card.setStyleSheet("""
                    QWidget#modeCard {
                        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                            stop:0 rgba(14, 165, 233, 0.15), stop:1 rgba(14, 165, 233, 0.05));
                        border: 2px solid #0ea5e9; border-radius: 12px;
                    }""")
            else:
                card.setStyleSheet("""
                    QWidget#modeCard {
                        background: rgba(51,65,85,0.3);
                        border: 2px solid #334155; border-radius: 12px;
                    }""")

    def value(self) -> str:
        for _, rb, name in self._cards:
            if rb.isChecked():
                if name == "YOLO Segmentation": return "seg"
                if name == "YOLO Detection":     return "det"
                if name == "Detectron 1":        return "d1"
                if name == "Detectron 2":        return "d2"
        return "seg"

# ------------------------------ Train Config Page -------------------------------------------
class StepTrain(QtWidgets.QWidget):
    changed = QtCore.pyqtSignal()

    # Try common filenames first; fall back to empty if not found
    DEFAULT_SEG_PATH = fwd(find_first_file(
        "yolo11s-seg.pt", "yolo11s-seg/yolo11s-seg.pt", "seg.pt"
    ) or Path(""))

    DEFAULT_DET_PATH = fwd(find_first_file(
        "yolo11n.pt", "yolo11n/yolo11n.pt", "det.pt"
    ) or Path(""))

    def __init__(self, mode: str = "seg"):
        super().__init__()
        self.mode = mode  # "seg" | "det" | "d1" | "d2"

        # Root split: sidebar (left) + content (right)
        root = QtWidgets.QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ===== Left sidebar (Train sections) =====
        self.side = QtWidgets.QFrame()
        self.side.setObjectName("trainSidebar")
        self.side.setFixedWidth(240)
        sideLay = QtWidgets.QVBoxLayout(self.side)
        sideLay.setContentsMargins(12, 16, 12, 16)
        sideLay.setSpacing(8)

        title = QtWidgets.QLabel("Train")
        title.setObjectName("trainTitle")
        sideLay.addWidget(title)

        self.nav = QtWidgets.QListWidget()
        self.nav.setObjectName("trainNav")
        self.nav.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        for label in ["Dataset", "Segmentation", "Detection", "Hyperparams", "Run"]:
            self.nav.addItem(label)
        self.nav.setCurrentRow(0)
        self.nav.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.nav.setFocusPolicy(QtCore.Qt.NoFocus)
        sideLay.addWidget(self.nav, 1)

        hint = QtWidgets.QLabel("Work top-to-bottom.\nSegmentation runs first.")
        hint.setObjectName("trainHint")
        sideLay.addWidget(hint)

        root.addWidget(self.side)

        # ===== Right content stack =====
        content = QtWidgets.QFrame()
        content.setObjectName("trainContent")
        cLay = QtWidgets.QVBoxLayout(content)
        cLay.setContentsMargins(24, 20, 24, 20)
        cLay.setSpacing(12)

        # Header
        hdr = QtWidgets.QHBoxLayout()
        hdr.setSpacing(8)
        hdr_lbl = QtWidgets.QLabel("Training Configuration")
        hdr_lbl.setObjectName("pageTitle")
        hdr.addWidget(hdr_lbl)
        hdr.addStretch(1)
        cLay.addLayout(hdr)

        # Stacked pages
        self.stack = QtWidgets.QStackedWidget()
        cLay.addWidget(self.stack, 1)

        # Build pages
        self._build_page_dataset()
        self._build_page_seg()
        self._build_page_det()
        self._build_page_hparams()
        self._build_page_run()

        # Wire nav
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)

        root.addWidget(content, 1)

        # style
        self._apply_local_qss()

        # enable/disable states for weight editors initially
        self.seg_default_rb.toggled.connect(self._update_states)
        self.det_default_rb.toggled.connect(self._update_states)
        self._update_states()

        # jump sidebar to relevant page based on initial mode
        self._jump_to_mode(mode)

    def set_mode(self, mode: str):
        """Call this when leaving the first screen to lock which training will run."""
        self.mode = mode
        self._jump_to_mode(mode)

    def _jump_to_mode(self, mode: str):
        # Unhide both first
        for row in (1, 2):
            it = self.nav.item(row)
            if it:
                it.setHidden(False)

        # Hide the unused one
        if mode == "seg":
            it = self.nav.item(2)
            if it:
                it.setHidden(True)   # hide Detection
        elif mode == "det":
            it = self.nav.item(1)
            if it:
                it.setHidden(True)   # hide Segmentation

        # Always land on Dataset
        self.nav.setCurrentRow(0)

    # ===== Page builders =====
    def _card(self) -> QtWidgets.QFrame:
        f = QtWidgets.QFrame()
        f.setObjectName("card")
        return f
    def _equalize_label_widths(self, labels: list[QtWidgets.QLabel]):
        w = max(l.sizeHint().width() for l in labels)
        for l in labels:
            l.setMinimumWidth(w)
            l.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Preferred)
    def _equalize_label_sizes(self, labels: list[QtWidgets.QLabel]):
        w = max(l.sizeHint().width() for l in labels)
        h = max(l.sizeHint().height() for l in labels)
        for l in labels:
            l.setWordWrap(False)
            l.setMinimumSize(w, h)
            l.setMaximumHeight(h)
            l.setFixedHeight(h)
            l.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)

    def _open_merge_dialog(self):
        dlg = DatasetMergeDialog(self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            if dlg.out_base_yaml:
                self.data_edit.setText(dlg.out_base_yaml)
            QtWidgets.QMessageBox.information(self, "Done", "Dataset merged and files copied successfully.")

    def _build_page_dataset(self):
        chip_css = """
    color:#ffffff; font-weight:600; font-size:16px;
    background: rgba(148, 163, 184, 0.18);
    border: 1px solid rgba(148, 163, 184, 0.35);
    border-radius: 10px;
    padding: 4px 10px;
    min-height: 36px;
"""
        card = self._card()
        lay = QtWidgets.QFormLayout(card)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(12)
        lay.setLabelAlignment(QtCore.Qt.AlignVCenter)
        lay.setFormAlignment(QtCore.Qt.AlignVCenter)

        # ---- Ultralytics version (label chip + compact combo) ----
        self.ver_combo = QtWidgets.QComboBox()
        self.ver_combo.addItems(["8", "10", "11", "12"])
        self.ver_combo.setCurrentText("11")
        self.ver_combo.setToolTip("Informational: ensure your Python env has this Ultralytics major installed.")
        self.ver_combo.setStyleSheet("")
        self.ver_combo.setMinimumHeight(34)

        ver_label = QtWidgets.QLabel("Ultralytics version:")
        ver_label.setStyleSheet(chip_css)
        ver_label.setAlignment(QtCore.Qt.AlignCenter)

        # ---- data.yaml (label chip + compact input) ----
        self.data_edit = QtWidgets.QLineEdit()
        self.data_edit.setPlaceholderText(r"Path to data.yaml")
        self.data_edit.setMinimumHeight(40)
        self.data_edit.setStyleSheet("""
            QLineEdit {
                color:#ffffff;
                font-size:16px;
                padding: 8px 12px;
            }
            QLineEdit::placeholder { color: rgba(255,255,255,0.7); }
        """)

        self.btn_browse_data = QtWidgets.QToolButton()
        self.btn_browse_data.setText("Browse…")
        self.btn_browse_data.clicked.connect(self._browse_data_yaml)
        self.btn_browse_data.setMinimumHeight(34)

        hl = QtWidgets.QHBoxLayout()
        hl.setSpacing(8)
        hl.addWidget(self.data_edit, 1)
        hl.addWidget(self.btn_browse_data, 0)

        data_label = QtWidgets.QLabel("data.yaml:")
        data_label.setStyleSheet(chip_css)
        data_label.setAlignment(QtCore.Qt.AlignCenter)

        QtCore.QTimer.singleShot(0, lambda: self._equalize_label_sizes([ver_label, data_label]))

        lay.addRow(ver_label, self.ver_combo)
        lay.addRow(data_label, self._wrap(hl))

        merge_btn = QtWidgets.QPushButton("Merge / Update dataset…")
        merge_btn.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        merge_btn.setMinimumHeight(40)
        merge_btn.setStyleSheet("""
            QPushButton {
                color: white; font-weight: 700;
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #0ea5e9, stop:1 #0284c7);
                border:none; border-radius:10px; padding:8px 14px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #0284c7, stop:1 #0369a1);
            }
        """)
        merge_btn.clicked.connect(self._open_merge_dialog)

        left_wrap = QtWidgets.QWidget()
        lw = QtWidgets.QHBoxLayout(left_wrap)
        lw.setContentsMargins(0, 8, 0, 0)
        lw.setSpacing(0)
        lw.addWidget(merge_btn, 0, QtCore.Qt.AlignLeft)

        row = lay.rowCount()
        lay.setWidget(row, QtWidgets.QFormLayout.LabelRole, left_wrap)
        lay.setWidget(row, QtWidgets.QFormLayout.FieldRole, QtWidgets.QWidget())

        self.stack.addWidget(card)

    def _build_page_seg(self):
        card = self._card()
        grid = QtWidgets.QGridLayout(card)
        grid.setContentsMargins(16, 16, 16, 16)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)

        title = QtWidgets.QLabel("Segmentation (YOLO 1)")
        title.setStyleSheet("color:#e5eefb; font-weight:700;")
        grid.addWidget(title, 0, 0, 1, 4)

        rb_css = """
        QRadioButton {
            color:#e6edf7; font-size:15px; font-weight:600;
            padding:6px 10px; border-radius:8px;
        }
        QRadioButton::indicator { width:18px; height:18px; }
        QRadioButton:hover { background: rgba(148,163,184,0.14); }
        QRadioButton:checked {
            background: rgba(14,165,233,0.18);
            border:1px solid rgba(14,165,233,0.45);
        }
        """

        self.seg_default_rb = QtWidgets.QRadioButton("Use default")
        self.seg_custom_rb  = QtWidgets.QRadioButton("Use custom last.pt")
        self.seg_default_rb.setChecked(True)
        self.seg_default_rb.setStyleSheet(rb_css)
        self.seg_custom_rb.setStyleSheet(rb_css)

        grid.addWidget(self.seg_default_rb, 1, 0)
        grid.addWidget(self.seg_custom_rb,  1, 1)

        self.seg_path_edit = QtWidgets.QLineEdit(self.DEFAULT_SEG_PATH)
        self.seg_browse = QtWidgets.QToolButton()
        self.seg_browse.setText("Browse…")
        self.seg_browse.clicked.connect(lambda: self._browse_path(self.seg_path_edit))

        hp = QtWidgets.QHBoxLayout()
        hp.setContentsMargins(0,0,0,0)
        hp.setSpacing(8)
        hp.addWidget(self.seg_path_edit)
        hp.addWidget(self.seg_browse)

        self.seg_weights_container = QtWidgets.QWidget()
        row = QtWidgets.QHBoxLayout(self.seg_weights_container)
        row.setContentsMargins(0,0,0,0)
        row.setSpacing(8)
        seg_wlbl = QtWidgets.QLabel("Weights path:")
        seg_wlbl.setStyleSheet("color:#ffffff; font-weight:600;")
        row.addWidget(seg_wlbl)
        row.addLayout(hp)

        grid.addWidget(self.seg_weights_container, 2, 0, 1, 4)

        info = QtWidgets.QLabel("Tip: leave default if you want to start from provided seg weights.")
        info.setStyleSheet("color:#9fb6d6;")
        grid.addWidget(info, 3, 0, 1, 4)

        self.seg_default_rb.toggled.connect(self._update_states)
        self.seg_custom_rb.toggled.connect(self._update_states)

        self.stack.addWidget(card)

    def _build_page_det(self):
        card = self._card()
        grid = QtWidgets.QGridLayout(card)
        grid.setContentsMargins(16, 16, 16, 16)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)

        title = QtWidgets.QLabel("Defect Detection (YOLO 2)")
        title.setStyleSheet("color:#e5eefb; font-weight:700;")
        grid.addWidget(title, 0, 0, 1, 4)

        rb_css = """
        QRadioButton {
            color:#e6edf7; font-size:15px; font-weight:600;
            padding:6px 10px; border-radius:8px;
        }
        QRadioButton::indicator { width:18px; height:18px; }
        QRadioButton:hover { background: rgba(148,163,184,0.14); }
        QRadioButton:checked {
            background: rgba(14,165,233,0.18);
            border:1px solid rgba(14,165,233,0.45);
        }
        """

        self.det_default_rb = QtWidgets.QRadioButton("Use default")
        self.det_custom_rb  = QtWidgets.QRadioButton("Use custom last.pt")
        self.det_default_rb.setChecked(True)
        self.det_default_rb.setStyleSheet(rb_css)
        self.det_custom_rb.setStyleSheet(rb_css)

        grid.addWidget(self.det_default_rb, 1, 0)
        grid.addWidget(self.det_custom_rb,  1, 1)

        self.det_path_edit = QtWidgets.QLineEdit(self.DEFAULT_DET_PATH)
        self.det_browse = QtWidgets.QToolButton()
        self.det_browse.setText("Browse…")
        self.det_browse.clicked.connect(lambda: self._browse_path(self.det_path_edit))

        hp = QtWidgets.QHBoxLayout()
        hp.setContentsMargins(0,0,0,0)
        hp.setSpacing(8)
        hp.addWidget(self.det_path_edit)
        hp.addWidget(self.det_browse)

        self.det_weights_container = QtWidgets.QWidget()
        row = QtWidgets.QHBoxLayout(self.det_weights_container)
        row.setContentsMargins(0,0,0,0)
        row.setSpacing(8)
        det_wlbl = QtWidgets.QLabel("Weights path:")
        det_wlbl.setStyleSheet("color:#ffffff; font-weight:600;")
        row.addWidget(det_wlbl)
        row.addLayout(hp)

        grid.addWidget(self.det_weights_container, 2, 0, 1, 4)

        info = QtWidgets.QLabel("Tip: leave default if you want to start from provided detection weights.")
        info.setStyleSheet("color:#9fb6d6;")
        grid.addWidget(info, 3, 0, 1, 4)

        self.det_default_rb.toggled.connect(self._update_states)
        self.det_custom_rb.toggled.connect(self._update_states)

        self.stack.addWidget(card)

    def _build_page_hparams(self):
        card = self._card()
        grid = QtWidgets.QGridLayout(card)
        grid.setContentsMargins(16, 16, 16, 16)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(12)

        self._hparam_labels = []

        chip_css = """
            color:#ffffff; font-weight:600; font-size:16px;
            background: rgba(148, 163, 184, 0.18);
            border: 1px solid rgba(148, 163, 184, 0.35);
            border-radius: 10px;
            padding: 4px 10px;
            min-height: 36px;
        """

        def mk_lbl(t):
            lb = QtWidgets.QLabel(t)
            lb.setAlignment(QtCore.Qt.AlignCenter)
            lb.setStyleSheet(chip_css)
            self._hparam_labels.append(lb)
            return lb

        self.device_combo = QtWidgets.QComboBox()
        self._populate_device_combo()

        self.epochs = QtWidgets.QSpinBox(); self.epochs.setRange(1, 5000); self.epochs.setValue(400)
        self.imgsz  = QtWidgets.QSpinBox(); self.imgsz.setRange(32, 4096); self.imgsz.setSingleStep(32); self.imgsz.setValue(1024)
        self.opt    = QtWidgets.QComboBox(); self.opt.addItems(["Adam", "SGD", "AdamW"]); self.opt.setCurrentText("Adam")
        self.batch  = QtWidgets.QSpinBox(); self.batch.setRange(1, 512); self.batch.setValue(16)
        self.project= QtWidgets.QLineEdit("runs")
        self.lr0    = QtWidgets.QDoubleSpinBox(); self.lr0.setDecimals(6); self.lr0.setRange(1e-6, 1.0); self.lr0.setSingleStep(0.0001); self.lr0.setValue(0.0001)

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 2)
        grid.setColumnStretch(2, 1)
        grid.setColumnStretch(3, 2)

        grid.addWidget(mk_lbl("device"), 0, 0); grid.addWidget(self.device_combo, 0, 1)
        grid.addWidget(mk_lbl("epochs"), 0, 2); grid.addWidget(self.epochs,      0, 3)
        grid.addWidget(mk_lbl("imgsz"),  1, 0); grid.addWidget(self.imgsz,       1, 1)
        grid.addWidget(mk_lbl("optimizer"), 1, 2); grid.addWidget(self.opt,      1, 3)
        grid.addWidget(mk_lbl("batch"),  2, 0); grid.addWidget(self.batch,       2, 1)
        grid.addWidget(mk_lbl("project"),2, 2); grid.addWidget(self.project,     2, 3)
        grid.addWidget(mk_lbl("lr0"),    3, 0); grid.addWidget(self.lr0,         3, 1)

        QtCore.QTimer.singleShot(0, lambda: self._equalize_label_sizes(self._hparam_labels))

        self.stack.addWidget(card)

    def _build_page_run(self):
        card = self._card()
        v = QtWidgets.QVBoxLayout(card)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(10)

        self.console = QtWidgets.QPlainTextEdit()
        self.console.setObjectName("console")
        self.console.setReadOnly(True)
        self.console.setPlaceholderText("Console output will appear here…")

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(10)
        self.btn_build = QtWidgets.QPushButton("Build Commands")
        self.btn_build.setObjectName("navButton")
        self.btn_build.setFixedHeight(44)
        self.btn_build.setMinimumWidth(140)
        self.btn_build.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))

        self.btn_start = QtWidgets.QPushButton("Start Training")
        self.btn_start.setObjectName("primaryNavButton")
        self.btn_start.setFixedHeight(44)
        self.btn_start.setMinimumWidth(160)
        self.btn_start.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))

        self.btn_build.clicked.connect(self._on_build)
        self.btn_start.clicked.connect(self._on_start)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_build)
        btn_row.addWidget(self.btn_start)

        v.addWidget(self.console, 1)
        v.addLayout(btn_row)

        self.stack.addWidget(card)

    # ===== helpers =====
    def _apply_local_qss(self):
        self.setStyleSheet("""
        QLabel#trainTitle { color:#f1f5f9; font-size:18px; font-weight:800; letter-spacing:-0.2px; }
        QLabel#trainHint { color:#96a7c2; font-size:12px; }
        QListWidget#trainNav {
            background: rgba(15,23,42,0.5);
            border:1px solid #334155; border-radius:10px; color:#dbe7ff;
        }
        QListWidget#trainNav::item { padding:10px 12px; }
        QListWidget#trainNav::item:selected {
            background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #0ea5e9, stop:1 #0284c7);
            color:white; border-radius:6px;
        }
        QFrame#trainSidebar {
            background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #1e293b, stop:1 #0f172a);
            border-right: 1px solid #334155;
        }
        QFrame#trainContent { background:#0f1419; }

        QFrame#card {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                      stop:0 rgba(30,41,59,0.55), stop:1 rgba(15,23,42,0.55));
            border:1px solid #334155; border-radius:12px;
        }

        QLabel#chip {
            color:#e6faff; background:#0ea5e922; border:1px solid #0ea5e9;
            border-radius:11px; padding:1px 10px; font-weight:700; font-size:12px;
        }

       QLineEdit, QComboBox {
            background: rgba(15,23,42,0.8);
            border:2px solid #334155;
            border-radius:8px;
            padding:10px 14px;
            color:#f1f5f9;
        }
        QToolButton { background: rgba(14,165,233,0.1); color:#d6f1ff; border:1px solid #0ea5e9; border-radius:8px; padding:8px 12px; }
        QToolButton:hover { background: rgba(14,165,233,0.2); }
        QLineEdit:focus, QComboBox:focus { border-color:#0ea5e9; }

        QPlainTextEdit#console { background: #0b1220; border:1px solid #223; border-radius:10px; color:#e5e7eb; font-family: Consolas, 'Fira Code', monospace; font-size: 12px; padding: 8px; }
        /* Uniform control heights */
        QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QToolButton {
            min-height: 10px;
            padding: 8px 12px;
        }
        QLabel#trainTitle { }
        """)

    def _wrap(self, layout: QtWidgets.QLayout) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget(); w.setLayout(layout); return w

    def _browse_data_yaml(self):
        fn, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select data.yaml", os.path.expanduser("~"), "YAML Files (*.yaml *.yml)")
        if fn:
            self.data_edit.setText(fn)

    def _browse_path(self, editor: QtWidgets.QLineEdit):
        fn, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select weights (.pt)", os.path.expanduser("~"), "PyTorch Weights (*.pt)")
        if fn:
            editor.setText(fn)

    def _update_states(self):
        self.seg_path_edit.setEnabled(self.seg_custom_rb.isChecked())
        self.seg_browse.setEnabled(self.seg_custom_rb.isChecked())
        self.det_path_edit.setEnabled(self.det_custom_rb.isChecked())
        self.det_browse.setEnabled(self.det_custom_rb.isChecked())

        if hasattr(self, "seg_weights_container"):
            self.seg_weights_container.setVisible(self.seg_custom_rb.isChecked())

        if hasattr(self, "det_weights_container"):
            self.det_weights_container.setVisible(self.det_custom_rb.isChecked())

    # ===== command builders & runners =====
    def _populate_device_combo(self):
        import shutil as _shutil, subprocess

        opts = ["cpu"]
        cuda_ok = False
        gpu_names = []

        try:
            import torch  # noqa
            try:
                if torch.cuda.is_available():  # type: ignore[attr-defined]
                    cuda_ok = True
                    n = torch.cuda.device_count()  # type: ignore[attr-defined]
                    opts.append("cuda")
                    for i in range(n):
                        opts.append(f"cuda:{i}")
                        try:
                            gpu_names.append(torch.cuda.get_device_name(i))  # type: ignore[attr-defined]
                        except Exception:
                            gpu_names.append(f"GPU {i}")
            except Exception:
                pass
        except ImportError:
            pass

        if not cuda_ok and _shutil.which("nvidia-smi"):
            try:
                out = subprocess.run(
                    ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                    capture_output=True, text=True, timeout=2
                ).stdout.strip()
                if out:
                    gpu_names = [ln.strip() for ln in out.splitlines() if ln.strip()]
            except Exception:
                pass

        self.device_combo.clear()
        self.device_combo.addItems(opts)

        if cuda_ok:
            self.device_combo.setToolTip("CUDA available: " + ", ".join(gpu_names))
            self.device_combo.setCurrentText("cuda")
        else:
            tip = "No CUDA available. "
            if gpu_names:
                tip += "NVIDIA driver detected: " + ", ".join(gpu_names) + ". Install CUDA-enabled PyTorch."
            else:
                tip += "No NVIDIA GPU/driver detected or PyTorch not installed."
            self.device_combo.setToolTip(tip)

    def _quote(self, s: str) -> str:
        return s

    def _normpath(self, p: str) -> str:
        return p.replace("\\", "/")

    def _get_seg_weights(self) -> str:
        return self.seg_path_edit.text().strip() if self.seg_custom_rb.isChecked() else self.DEFAULT_SEG_PATH

    def _get_det_weights(self) -> str:
        return self.det_path_edit.text().strip() if self.det_custom_rb.isChecked() else self.DEFAULT_DET_PATH

    # ---------- data.yaml preflight with YAML dependency handled ----------
    def _fix_and_stage_data_yaml(self, data_yaml_path: str) -> str:
        """
        Load data.yaml, resolve/repair paths (train/val[/test]), and write a temp
        YAML next to the original (in a .cache_wizard folder) that Ultralytics will consume.
        Returns the path to the temp YAML.
        """
        yaml = require_yaml(self)

        src = Path(data_yaml_path).resolve()
        if not src.is_file():
            raise FileNotFoundError(f"data.yaml not found: {src}")

        with open(src, "r", encoding="utf-8") as f:
            data = (yaml.safe_load(f) or {})

        base = src.parent

        dataset_root = data.get("path", "")
        train = data.get("train", "")
        val   = data.get("val", "")
        test  = data.get("test", "")

        def _abs(candidate: str) -> Path:
            c = str(candidate or "").strip()
            if not c:
                return Path("")
            p = Path(c)
            return p if p.is_absolute() else (base / p)

        path_hint = _abs(dataset_root) if dataset_root else base

        def _resolve_dir(p: str | Path) -> Path:
            if not p:
                return Path("")
            p = Path(p)
            if not p.is_absolute():
                p = (path_hint / p) if dataset_root else (base / p)
            if p.is_dir():
                return p
            # fallback guesses
            for guess in [p.parent, base / p.name, path_hint / p.name]:
                if guess.is_dir():
                    return guess
            return p

        train_dir = _resolve_dir(train)
        val_dir   = _resolve_dir(val)
        test_dir  = _resolve_dir(test) if test else Path("")

        def _ensure_dir(label: str, p: Path) -> Path:
            if p and p.is_dir():
                return p
            dn = QtWidgets.QFileDialog.getExistingDirectory(self, f"Select {label}", str(base))
            if not dn:
                raise FileNotFoundError(f"{label} not found and no folder selected.")
            return Path(dn)

        train_dir = _ensure_dir("train images folder", train_dir)
        val_dir   = _ensure_dir("val images folder",   val_dir)
        if test:
            test_dir = _ensure_dir("test images folder", test_dir)

        fixed = dict(data)
        fixed.pop("path", None)
        fixed["train"] = fwd(train_dir)
        fixed["val"]   = fwd(val_dir)
        if test:
            fixed["test"]  = fwd(test_dir)

        cache_dir = base / ".cache_wizard"
        cache_dir.mkdir(exist_ok=True)
        out = cache_dir / f"{src.stem}_fixed.yaml"

        with open(out, "w", encoding="utf-8") as f:
            yaml.safe_dump(fixed, f, sort_keys=False)

        return fwd(out)

    def _yolo_bin(self) -> str:
        """Return the YOLO runner (CLI if on PATH, else module form)."""
        return "yolo" if shutil.which("yolo") else f"{sys.executable} -m ultralytics"

    def build_commands(self) -> tuple[str, list]:
        """
        Returns:
            info (str): info banner
            cmds (list): list of tuples (program, args_list)
        """
        data_yaml = (self.data_edit.text() or "").strip()
        if not data_yaml or not os.path.isfile(data_yaml):
            raise ValueError("Please choose a valid data.yaml (Dataset → Browse…).")

        ver = self.ver_combo.currentText()
        info = f"[info] Requested Ultralytics major version: {ver} (ensure your environment has this installed)"

        if self.mode == "seg":
            weights = self._get_seg_weights()
        elif self.mode == "det":
            weights = self._get_det_weights()
        else:
            raise ValueError("Detectron training not implemented in this screen yet.")

        # Helpful, explicit error if weights are missing
        if not weights or not os.path.isfile(weights):
            raise FileNotFoundError(
                "Weights not found. Either select a custom .pt file or place a default\n"
                "model in one of these folders next to the app: models/, weights/, assets/."
            )

        # Fix/normalize YAML splits and stage a temp copy for training
        fixed_yaml = self._fix_and_stage_data_yaml(data_yaml)

        # program to run
        if shutil.which("yolo"):
            program = "yolo"
            prefix = []  # call `yolo` directly
        else:
            program = sys.executable
            prefix = ["-m", "ultralytics"]

        if self.mode == "seg":
            args = prefix + self._build_args("segment", weights.replace("\\", "/"), fixed_yaml)
        else:
            args = prefix + self._build_args("detect",  weights.replace("\\", "/"), fixed_yaml)

        return info, [(program, args)]

    def _build_args(self, task: str, w: str, y: str) -> list:
        """Return argv for yolo: ['train','segment','model=...','data=...','epochs=...']"""
        device_val = self.device_combo.currentText().strip() if hasattr(self, "device_combo") else "cpu"
        return [
            "train", task,
            f"model={w}",
            f"data={y}",
            f"epochs={self.epochs.value()}",
            f"imgsz={self.imgsz.value()}",
            f"optimizer={self.opt.currentText()}",
            f"device={device_val}",
            "patience=0",
            f"batch={self.batch.value()}",
            f"project={self.project.text().strip()}",
            f"lr0={self.lr0.value()}",
        ]

    def _fmt_cmd(self, program: str, args: list[str]) -> str:
        return program + " " + " ".join(args)

    def _on_build(self):
        try:
            info, cmds = self.build_commands()
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Build error", str(e))
            return
        self.console.appendPlainText("\n=== Built Command(s) ===")
        self.console.appendPlainText(info)
        for program, args in cmds:
            self.console.appendPlainText(self._fmt_cmd(program, args))
        self.nav.setCurrentRow(4)

    def _on_start(self):
        try:
            info, cmds = self.build_commands()
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Cannot start", str(e))
            return
        dev_txt = getattr(self, "device_combo", None)
        self.console.appendPlainText(f"\n=== Starting Training ({(dev_txt.currentText() if dev_txt else 'cpu').upper()}) ===")
        self.console.appendPlainText(info)
        for program, args in cmds:
            self.console.appendPlainText(self._fmt_cmd(program, args))
        self.nav.setCurrentRow(4)
        self._run_commands_sequential(cmds)

    def _pipe(self, data: QtCore.QByteArray):
        """Append process output to the console safely."""
        try:
            text = bytes(data).decode("utf-8", errors="ignore")
            if text:
                self.console.appendPlainText(text.rstrip())
                vsb = self.console.verticalScrollBar()
                if vsb:
                    vsb.setValue(vsb.maximum())
        except Exception:
            pass

    def _run_commands_sequential(self, commands: list):
        if hasattr(self, "btn_start"): self.btn_start.setEnabled(False)
        if hasattr(self, "btn_build"): self.btn_build.setEnabled(False)
        self._proc = QtCore.QProcess(self)
        self._proc.setProcessChannelMode(QtCore.QProcess.MergedChannels)
        self._proc.readyRead.connect(lambda: self._pipe(self._proc.readAll()))
        self._proc.finished.connect(self._next_or_done)
        self._cmds = commands
        self._idx  = -1
        self._next_or_done()

    def _next_or_done(self):
        self._idx += 1
        if self._idx >= len(self._cmds):
            self.console.appendPlainText("\n=== All trainings finished ===")
            if hasattr(self, "btn_start"): self.btn_start.setEnabled(True)
            if hasattr(self, "btn_build"): self.btn_build.setEnabled(True)
            return

        program, args = self._cmds[self._idx]
        self._proc.start(program, args)
        self.console.appendPlainText(f"\n[Running {self._idx+1}/{len(self._cmds)}] -> {program} " + " ".join(args))

# ================================== Main Window =============================================
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Training Wizard")
        self.resize(1180, 760)

        central = QtWidgets.QWidget(); central.setObjectName("centralWidget")
        root = QtWidgets.QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Sidebar (global steps)
        sidebar_container = QtWidgets.QWidget()
        sidebar_container.setObjectName("sidebar")
        sidebar_container.setFixedWidth(280)
        sidebar_layout = QtWidgets.QVBoxLayout(sidebar_container)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        header = QtWidgets.QWidget()
        header.setObjectName("sidebarHeader")
        header.setFixedHeight(70)
        header_layout = QtWidgets.QVBoxLayout(header)
        header_layout.setContentsMargins(20, 16, 20, 16)
        logo = QtWidgets.QLabel("Training Wizard")
        logo.setObjectName("logo")
        header_layout.addWidget(logo)
        header_layout.addStretch(1)

        steps_widget = QtWidgets.QWidget()
        self.steps_layout = QtWidgets.QVBoxLayout(steps_widget)
        self.steps_layout.setContentsMargins(0, 16, 0, 16)
        self.steps_layout.setSpacing(2)
        self.step_indicators = []
        for i, t in enumerate(["Model", "Train"]):
            ind = StepIndicator(i + 1, t)
            self.step_indicators.append(ind)
            self.steps_layout.addWidget(ind)

        sidebar_layout.addWidget(header)
        sidebar_layout.addWidget(steps_widget)
        sidebar_layout.addStretch()
        root.addWidget(sidebar_container)

        # Main area
        main_container = QtWidgets.QWidget()
        main_container.setObjectName("mainContainer")
        main_layout = QtWidgets.QVBoxLayout(main_container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # top bar with help
        topbar = QtWidgets.QWidget()
        topbar.setObjectName("topBar")
        topbar.setFixedHeight(46)
        topbar_layout = QtWidgets.QHBoxLayout(topbar)
        topbar_layout.setContentsMargins(12, 6, 12, 6)
        topbar_layout.addStretch()
        self.btn_help = QtWidgets.QToolButton()
        self.btn_help.setObjectName("helpButton")
        self.btn_help.setAutoRaise(True)
        self.btn_help.setToolTip("Help (F1)")
        self.btn_help.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_MessageBoxQuestion))
        self.btn_help.setIconSize(QtCore.QSize(20, 20))
        self.btn_help.setFixedSize(36, 36)
        self.btn_help.clicked.connect(self._show_help)
        QtWidgets.QShortcut(QtGui.QKeySequence.HelpContents, self, activated=self._show_help)
        topbar_layout.addWidget(self.btn_help, 0, QtCore.Qt.AlignRight)

        self.stack = QtWidgets.QStackedWidget()
        self.stack.setObjectName("contentStack")
        self.step_model = StepModel()
        self.step_train = StepTrain(mode="seg")
        self.step_model.card_selected.connect(self._on_model_card_selected)

        self.stack.addWidget(self.step_model)
        self.stack.addWidget(self.step_train)

        main_layout.addWidget(topbar)
        main_layout.addWidget(self.stack, 1)

        # Bottom nav
        nav_bar = QtWidgets.QWidget()
        nav_bar.setObjectName("navBar")
        nav_bar.setFixedHeight(72)
        nav_layout = QtWidgets.QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(24, 12, 24, 12)
        nav_layout.setSpacing(10)

        self.btn_back = QtWidgets.QPushButton("← Back")
        self.btn_back.setObjectName("navButton")
        self.btn_back.setFixedHeight(44)
        self.btn_back.setFixedWidth(110)

        self.btn_next = QtWidgets.QPushButton("Next →")
        self.btn_next.setObjectName("primaryNavButton")
        self.btn_next.setFixedHeight(44)
        self.btn_next.setFixedWidth(110)

        self.btn_back.clicked.connect(self._go_back)
        self.btn_next.clicked.connect(self._go_next)
        nav_layout.addStretch()
        nav_layout.addWidget(self.btn_back)
        nav_layout.addWidget(self.btn_next)

        main_layout.addWidget(nav_bar)
        root.addWidget(main_container, 1)

        # Solid root wrapper
        root_frame = QtWidgets.QFrame()
        root_frame.setObjectName("trainingRoot")
        wrap = QtWidgets.QVBoxLayout(root_frame)
        root_frame.setAutoFillBackground(True)
        root_frame.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        wrap.setContentsMargins(0, 0, 0, 0)
        wrap.setSpacing(0)
        wrap.addWidget(central)

        self.setCentralWidget(root_frame)

        # style
        self._apply_qss()
        self._update_nav()

    # ---- nav helpers ----
    def _on_model_card_selected(self, mode: str):
        self.step_train.set_mode(mode)
        self.stack.setCurrentIndex(1)
        self.step_train.nav.setCurrentRow(0)
        self._update_nav()

    def current_step(self) -> int:
        return self.stack.currentIndex()

    def _go_back(self):
        i = self.current_step()
        if i > 0:
            self.stack.setCurrentIndex(i - 1)
            self._update_nav()

    def _go_next(self):
        i = self.current_step()
        if i == 0:
            sel = self.step_model.value()
            self.step_train.set_mode(sel)
            self.stack.setCurrentIndex(1)
        elif i == 1:
            self._restart_soft()
        self._update_nav()

    def _update_nav(self):
        i = self.current_step()
        for idx, indicator in enumerate(self.step_indicators):
            indicator.set_active(idx == i)
            indicator.set_complete(idx > i)
        self.btn_back.setEnabled(i > 0)
        self.btn_next.setText("Finish" if i == 1 else "Next →")

    def _restart_soft(self):
        try:
            self.step_model._cards[0][1].setChecked(True)
            self.step_model._update_card_styles()
            self.step_train.seg_default_rb.setChecked(True)
            self.step_train.det_default_rb.setChecked(True)
            self.step_train.data_edit.clear()
            self.step_train.console.clear()
        except Exception:
            pass
        self.stack.setCurrentIndex(0)
        self._update_nav()
        QtWidgets.QMessageBox.information(self, "Info", "Done. Ready for a new session.")

    def _show_help(self):
        SimpleHelpDialog(self).exec_()

    # ---- styling ----
    def _apply_qss(self):
        self.setStyleSheet("""
        * { font-family: 'Segoe UI','SF Pro Display',-apple-system,BlinkMacSystemFont,Arial,sans-serif; font-size: 14px; }
        QLabel { background: transparent; }

        #trainingRoot { background: #0f1419; }
        QWidget#mainContainer { background: #0f1419; }
        QStackedWidget#contentStack { background: #0f1419; }

        QWidget#sidebar { background: #0f172a; border-right: 1px solid #334155; }
        QWidget#sidebarHeader { background: #0f172a; border-bottom: 1px solid #334155; }
        QLabel#logo { color: #f1f5f9; font-size: 18px; font-weight: 700; letter-spacing:-0.3px; }
        QLabel#stepTitle { color: #94a3b8; font-size: 14px; background: transparent; }

        QWidget#topBar { background: #0f172a; border-bottom: 1px solid #1f2937; }
        QToolButton#helpButton { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #0ea5e9, stop:1 #0284c7); border:none; border-radius:18px; }
        QToolButton#helpButton:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #0284c7, stop:1 #0369a1); }

        QLabel#pageTitle { color:#f8fafc; font-size:22px; font-weight:800; letter-spacing:-0.3px; background: transparent; }
        QLabel#pageSubtitle { color:#94a3b8; font-size:15px; background: transparent; }

        QWidget#navBar { background: #0f172a; border-top:1px solid #334155; }
        QPushButton#navButton { background:#394150; color:#cbd5e1; border:1px solid #475569; border-radius:10px; font-weight:600; }
        QPushButton#navButton:hover { background:#4b5563; border-color:#64748b; }
        QPushButton#primaryNavButton { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #0ea5e9, stop:1 #0284c7); color:white; border:none; border-radius:10px; font-weight:700; }
        QPushButton#primaryNavButton:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #0284c7, stop:1 #0369a1); }

        QWidget#modeCard { border-radius:12px; }
        QWidget#modeCard QLabel#cardTitle { color:#ffffff; background: transparent; }

        QLineEdit, QComboBox {
            background:#0b1220;
            border:2px solid #334155;
            border-radius:8px;
            padding:8px 12px;
            color:#f1f5f9;
        }
        QLineEdit:focus, QComboBox:focus { border-color:#0ea5e9; }

        QPlainTextEdit#console { background:#0b1220; border:1px solid #223; border-radius:10px; color:#e5e7eb; font-family:Consolas,'Fira Code',monospace; font-size:12px; padding:8px; }
        """)

# ================================== Entrypoint ==============================================
def main():
    QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)
    QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
