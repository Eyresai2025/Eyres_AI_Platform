# project_manager.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import re
import datetime
import shutil

from PyQt5 import QtWidgets, QtCore


# ============================================================
#  ROOT FOLDER FOR ALL INSPECTION PROJECTS
#  (next to Main_GUI.py → ./projects/)
# ============================================================

APP_ROOT = Path(__file__).resolve().parent
PROJECTS_ROOT = APP_ROOT / "projects"


# ============================================================
#  DATA MODEL
# ============================================================

@dataclass
class InspectionProject:
    name: str
    root: Path
    machine_name: str | None = None
    inspection_type: str | None = None

    @property
    def images_dir(self) -> Path:
        return self.root / "images"

    @property
    def annotations_dir(self) -> Path:
        return self.root / "annotations"

    @property
    def models_dir(self) -> Path:
        return self.root / "models"

    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"

    @property
    def config_path(self) -> Path:
        return self.root / "project.json"


# ============================================================
#  HELPERS
# ============================================================

def _safe_folder_name(name: str) -> str:
    """Make a safe folder name from project name."""
    name = name.strip()
    name = re.sub(r"[^a-zA-Z0-9_\-]+", "_", name)
    return name or "Project"


def ensure_projects_root() -> Path:
    """Create ./projects if needed and return it."""
    PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)
    return PROJECTS_ROOT


def create_project(
    name: str,
    machine_name: str | None = None,
    inspection_type: str | None = None,
    base_dir: Path | None = None,
) -> InspectionProject:
    """Create a new project folder with subdirs + project.json."""
    if base_dir is None:
        base_dir = ensure_projects_root()

    folder_name = _safe_folder_name(name)
    root = base_dir / folder_name
    counter = 1
    while root.exists():
        counter += 1
        root = base_dir / f"{folder_name}_{counter}"

    root.mkdir(parents=True, exist_ok=True)

    proj = InspectionProject(
        name=name,
        root=root,
        machine_name=machine_name,
        inspection_type=inspection_type,
    )

    # basic folder structure
    proj.images_dir.mkdir(exist_ok=True)
    proj.annotations_dir.mkdir(exist_ok=True)
    proj.models_dir.mkdir(exist_ok=True)
    proj.logs_dir.mkdir(exist_ok=True)

    save_project(proj)
    return proj


def save_project(proj: InspectionProject):
    """Write project.json inside the project folder."""
    cfg = {
        "name": proj.name,
        "root": str(proj.root),
        "machine_name": proj.machine_name,
        "inspection_type": proj.inspection_type,
        "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    proj.config_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def load_project_from_folder(folder: Path) -> InspectionProject | None:
    """Load project from an existing folder (expects project.json)."""
    cfg_path = folder / "project.json"
    if not cfg_path.is_file():
        return None
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    root = Path(cfg.get("root", folder))
    return InspectionProject(
        name=cfg.get("name", folder.name),
        root=root,
        machine_name=cfg.get("machine_name"),
        inspection_type=cfg.get("inspection_type"),
    )


def list_projects(base_dir: Path | None = None) -> list[InspectionProject]:
    """Return all projects under ./projects."""
    if base_dir is None:
        base_dir = ensure_projects_root()
    if not base_dir.exists():
        return []

    projects: list[InspectionProject] = []
    for child in base_dir.iterdir():
        if child.is_dir():
            proj = load_project_from_folder(child)
            if proj:
                projects.append(proj)

    # newest first (optional)
    projects.sort(key=lambda p: p.root.stat().st_mtime, reverse=True)
    return projects


def save_last_project_path(path: Path):
    """Remember last opened project (./projects/_last_project.json)."""
    meta = PROJECTS_ROOT / "_last_project.json"
    meta.write_text(json.dumps({"last": str(path)}), encoding="utf-8")


def load_last_project() -> Path | None:
    """Return saved last project folder path (if exists)."""
    meta = PROJECTS_ROOT / "_last_project.json"
    if not meta.is_file():
        return None
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
        p = Path(data.get("last", ""))
        return p if p.exists() else None
    except Exception:
        return None


# --------- NEW: DELETE SUPPORT ---------------------------------

def delete_project(proj: InspectionProject) -> bool:
    """
    Delete the project folder completely (images, annotations, models, logs).
    Returns True if deleted, False otherwise.
    """
    try:
        if proj.root.exists() and proj.root.is_dir():
            shutil.rmtree(proj.root)
        # If last project meta points here, remove it
        meta = PROJECTS_ROOT / "_last_project.json"
        if meta.is_file():
            try:
                data = json.loads(meta.read_text(encoding="utf-8"))
                if Path(data.get("last", "")) == proj.root:
                    meta.unlink(missing_ok=True)
            except Exception:
                pass
        return True
    except Exception:
        return False


# ============================================================
#  DIALOG: SELECT / CREATE / DELETE PROJECT
# ============================================================

class ProjectDialog(QtWidgets.QDialog):
    """
    - Left: list of existing projects
    - Right: fields to create a new project
    - Buttons: Open, Delete, Create
    - Use exec_and_get() -> InspectionProject | None
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select / Create Inspection Project")
        self.setModal(True)
        self._selected_proj: InspectionProject | None = None

        self.resize(680, 400)

        layout = QtWidgets.QHBoxLayout(self)

        # ---- Existing projects list ----
        left = QtWidgets.QFrame()
        lv = QtWidgets.QVBoxLayout(left)
        lv.setContentsMargins(8, 8, 8, 8)
        lv.setSpacing(6)

        title = QtWidgets.QLabel("Existing Projects:")
        title.setStyleSheet("font-weight: 600;")
        lv.addWidget(title)

        self.list_widget = QtWidgets.QListWidget()
        lv.addWidget(self.list_widget, 1)

        # Buttons: Open + Delete
        btn_row = QtWidgets.QHBoxLayout()
        self.btn_open = QtWidgets.QPushButton("Open")
        self.btn_delete = QtWidgets.QPushButton("Delete")
        self.btn_open.clicked.connect(self._open_selected)
        self.btn_delete.clicked.connect(self._delete_selected)
        btn_row.addWidget(self.btn_open)
        btn_row.addWidget(self.btn_delete)
        lv.addLayout(btn_row)

        layout.addWidget(left, 1)

        # ---- New project form ----
        right = QtWidgets.QFrame()
        rv = QtWidgets.QFormLayout(right)
        rv.setContentsMargins(8, 8, 8, 8)
        rv.setSpacing(6)

        self.ed_name = QtWidgets.QLineEdit()
        self.ed_machine = QtWidgets.QLineEdit()
        self.cb_type = QtWidgets.QComboBox()
        self.cb_type.addItems([
            "",
            "Anomaly Detection",
            "Classification",
            "Dimensioning",
            "Assembly Monitoring",
        ])

        rv.addRow("Project Name:", self.ed_name)
        rv.addRow("Machine Name:", self.ed_machine)
        rv.addRow("Inspection Type:", self.cb_type)

        self.btn_create = QtWidgets.QPushButton("Create New Project")
        self.btn_create.clicked.connect(self._create_new)
        rv.addRow(self.btn_create)

        layout.addWidget(right, 1)

        self._load_existing_projects()

    # ---------------- internal helpers ----------------

    def _load_existing_projects(self):
        self.list_widget.clear()
        self._projects = list_projects()
        for proj in self._projects:
            item = QtWidgets.QListWidgetItem(f"{proj.name}  —  {proj.root}")
            item.setData(QtCore.Qt.UserRole, proj)
            self.list_widget.addItem(item)

    def _get_selected_project(self) -> InspectionProject | None:
        item = self.list_widget.currentItem()
        if not item:
            return None
        return item.data(QtCore.Qt.UserRole)

    def _open_selected(self):
        proj = self._get_selected_project()
        if proj is None:
            QtWidgets.QMessageBox.warning(
                self, "No selection", "Please select a project to open."
            )
            return
        self._selected_proj = proj
        save_last_project_path(proj.root)
        self.accept()

    def _delete_selected(self):
        proj = self._get_selected_project()
        if proj is None:
            QtWidgets.QMessageBox.warning(
                self, "No selection", "Please select a project to delete."
            )
            return

        # Confirmation
        reply = QtWidgets.QMessageBox.question(
            self,
            "Delete Project",
            f"Are you sure you want to delete this project?\n\n"
            f"Name: {proj.name}\nPath: {proj.root}\n\n"
            f"This will remove images, annotations, models, and logs.",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return

        ok = delete_project(proj)
        if not ok:
            QtWidgets.QMessageBox.critical(
                self,
                "Delete Failed",
                "Could not delete the project folder. Close any open files and try again.",
            )
            return

        # Reload list
        self._load_existing_projects()
        QtWidgets.QMessageBox.information(
            self,
            "Project Deleted",
            f"Project '{proj.name}' has been deleted.",
        )

    def _create_new(self):
        txt = self.ed_name.text()
        name = txt.strip()
        if not name:
            QtWidgets.QMessageBox.warning(
                self, "Missing name", "Please enter a project name."
            )
            return
        machine = self.ed_machine.text().strip() or None
        itype = self.cb_type.currentText().strip() or None

        proj = create_project(name, machine_name=machine, inspection_type=itype)
        save_last_project_path(proj.root)
        self._selected_proj = proj
        self.accept()

    # ---------------- public API ----------------

    def exec_and_get(self) -> InspectionProject | None:
        """Show dialog and return selected/created project or None."""
        if self.exec_() == QtWidgets.QDialog.Accepted:
            return self._selected_proj
        return None
