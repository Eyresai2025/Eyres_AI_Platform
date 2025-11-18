import sys, os
from pathlib import Path

from PyQt5.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QFrame
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap

from db import MachineDB, ProjectDB


# ----------------- helpers for logo path -----------------

def _app_base_dir() -> Path:
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def _find_logo() -> Path | None:
    media = _app_base_dir() / "Media"
    if not media.exists():
        return None

    preferred_names = (
        "EYRES QC.png",
        "EYRES QC Black.png",
        "EYRES QC LOGO MARK.png",
        "LOGO-02.png",
        "logo.png",
        "Logo.png",
        "logo@2x.png",
    )

    for name in preferred_names:
        p = media / name
        if p.is_file():
            return p

    for ext in ("*.png", "*.jpg", "*.jpeg", "*.bmp", "*.gif", "*.webp"):
        files = list(media.glob(ext))
        if files:
            return files[0]
    return None


class DashboardPage(QWidget):
    """Simple overview dashboard: logo + stats + welcome text."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: #111; color: white;")

        self.machine_db = MachineDB()
        self.project_db = ProjectDB()

        try:
            self.machine_count = len(self.machine_db.get_all_machines())
        except Exception:
            self.machine_count = 0

        try:
            self.project_count = len(self.project_db.get_all_projects())
        except Exception:
            self.project_count = 0

        self._build_ui()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 32, 32, 32)
        main_layout.setSpacing(20)

        # -------- TOP ROW: Logo only --------
        top_row = QHBoxLayout()
        top_row.setSpacing(16)

        logo_label = QLabel()
        logo_label.setStyleSheet("background-color: transparent;")
        logo_label.setAttribute(Qt.WA_TranslucentBackground)

        logo_path = _find_logo()
        if logo_path is not None:
            pm = QPixmap(str(logo_path))
            if not pm.isNull():
                pm = pm.scaledToHeight(120, Qt.SmoothTransformation)
                logo_label.setPixmap(pm)

        if logo_label.pixmap() is None:
            logo_label.setText("EYRES QC")
            logo_label.setStyleSheet("""
                background-color: transparent;
                font-size: 22px;
                font-weight: bold;
                color: #2E86FF;
            """)

        logo_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        top_row.addWidget(logo_label, 0, Qt.AlignLeft)
        top_row.addStretch(1)

        main_layout.addLayout(top_row)
        main_layout.addSpacing(16)

        # -------- STATS CARDS ROW --------
        stats_row = QHBoxLayout()
        stats_row.setSpacing(20)

        machine_card = self.create_stat_card(
            "Total Machines",
            str(self.machine_count),
            "assets/icons/machine.png"
        )
        project_card = self.create_stat_card(
            "Total Projects",
            str(self.project_count),
            "assets/icons/project.png"
        )

        stats_row.addWidget(machine_card)
        stats_row.addWidget(project_card)
        main_layout.addLayout(stats_row)
        main_layout.addSpacing(30)

        # Store label references for dynamic updates
        self.machine_count_label = machine_card.findChild(QLabel, "total_machines_count")
        self.project_count_label = project_card.findChild(QLabel, "total_projects_count")
        
        # Fallback: if findChild fails, search recursively
        if not self.machine_count_label:
            for widget in machine_card.findChildren(QLabel):
                if widget.objectName() == "total_machines_count":
                    self.machine_count_label = widget
                    break
        if not self.project_count_label:
            for widget in project_card.findChildren(QLabel):
                if widget.objectName() == "total_projects_count":
                    self.project_count_label = widget
                    break

        # -------- WELCOME TEXT --------
        welcome_label = QLabel("Welcome to EYRES QC Dashboard!")
        welcome_label.setStyleSheet("""
            font-size: 18px;
            color: #AAAAAA;
            padding: 10px;
        """)
        welcome_label.setAlignment(Qt.AlignLeft)
        main_layout.addWidget(welcome_label)

        main_layout.addStretch()

    def refresh_counts(self):
        try:
            self.machine_count = len(self.machine_db.get_all_machines())
        except:
            self.machine_count = 0

        try:
            self.project_count = len(self.project_db.get_all_projects())
        except:
            self.project_count = 0

        # Update labels dynamically
        if hasattr(self, 'machine_count_label') and self.machine_count_label:
            self.machine_count_label.setText(str(self.machine_count))
        if hasattr(self, 'project_count_label') and self.project_count_label:
            self.project_count_label.setText(str(self.project_count))

    def create_stat_card(self, title, value, icon_path):
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #1a1a1a;
                border-radius: 8px;
                border: 1px solid #2a2a2a;
            }
            QFrame:hover {
                background-color: #222222;
                border: 1px solid #3a3a3a;
            }
        """)

        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(15)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(5)

        title_label = QLabel(title)
        title_label.setStyleSheet("""
            font-size: 14px;
            color: #AAAAAA;
            font-weight: 500;
        """)
        text_layout.addWidget(title_label)

        value_label = QLabel(value)
        value_label.setObjectName(title.replace(" ", "_").lower() + "_count")
        value_label.setStyleSheet("""
            font-size: 32px;
            font-weight: bold;
            color: #2E86FF;
        """)
        text_layout.addWidget(value_label)

        text_layout.addStretch()
        card_layout.addLayout(text_layout)

        icon_label = QLabel()
        icon_pix = QPixmap(icon_path)
        if not icon_pix.isNull():
            icon_pix = icon_pix.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            icon_label.setPixmap(icon_pix)
        else:
            icon_label.setText("📊")
            icon_label.setStyleSheet("font-size: 32px;")

        icon_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        card_layout.addWidget(icon_label)

        return card
