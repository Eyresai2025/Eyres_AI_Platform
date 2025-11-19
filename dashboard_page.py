# dashboard_page.py

import sys, os
from pathlib import Path

from PyQt5.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QFrame, QSizePolicy,
    QGraphicsDropShadowEffect,
)
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QPixmap, QMovie, QColor


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


# ---------- helper to find icons/GIFs in Media ----------

def _find_media_icon(filename: str) -> Path | None:
    media = _app_base_dir() / "Media"
    p = media / filename
    if p.is_file():
        return p
    return None


class DashboardPage(QWidget):
    """Simple overview dashboard: logo + stats + welcome text + user chip."""

    def __init__(self, username: str | None = None, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: #111; color: white;")

        # username coming from login
        self.username = username or "User"

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

    # ---------------- UI BUILD ----------------

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        # slightly smaller top margin -> logo + profile a bit higher
        main_layout.setContentsMargins(24, 18, 24, 32)
        main_layout.setSpacing(20)

        # -------- TOP ROW: Logo (left) + Profile chip (right) --------
        top_row = QHBoxLayout()
        top_row.setSpacing(16)

        # ---- logo ----
        logo_label = QLabel()
        logo_label.setStyleSheet("background-color: transparent;")
        logo_label.setAttribute(Qt.WA_TranslucentBackground)

        logo_path = _find_logo()
        if logo_path is not None:
            pm = QPixmap(str(logo_path))
            if not pm.isNull():
                pm = pm.scaledToHeight(110, Qt.SmoothTransformation)
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
        top_row.addWidget(logo_label, 0, Qt.AlignLeft | Qt.AlignTop)

        top_row.addStretch(1)

        # ---- profile chip ----
        profile_chip = self._build_profile_chip()
        top_row.addWidget(profile_chip, 0, Qt.AlignRight | Qt.AlignTop)

        main_layout.addLayout(top_row)
        main_layout.addSpacing(12)

        # -------- STATS CARDS ROW --------
        stats_row = QHBoxLayout()
        stats_row.setSpacing(20)

        machine_icon_path = (
            _find_media_icon("Machines.gif")
            or _find_media_icon("Machines.png")
        )
        project_icon_path = (
            _find_media_icon("projects.gif")
            or _find_media_icon("projects.png")
        )

        machine_card = self.create_stat_card(
            "Total Machines",
            str(self.machine_count),
            icon_path=machine_icon_path
        )
        project_card = self.create_stat_card(
            "Total Projects",
            str(self.project_count),
            icon_path=project_icon_path
        )

        stats_row.addWidget(machine_card)
        stats_row.addWidget(project_card)
        main_layout.addLayout(stats_row)
        main_layout.addSpacing(30)

        # Store label references for dynamic updates
        self.machine_count_label = machine_card.findChild(QLabel, "total_machines_count")
        self.project_count_label = project_card.findChild(QLabel, "total_projects_count")

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
            padding: 10px 0;
            background-color: transparent;
        """)
        welcome_label.setAlignment(Qt.AlignLeft)
        main_layout.addWidget(welcome_label)

        main_layout.addStretch()

    # ---------------- PROFILE CHIP ----------------

    def _build_profile_chip(self) -> QWidget:
        chip = QFrame()
        chip.setObjectName("UserChip")
        chip.setStyleSheet("""
            QFrame#UserChip {
                background-color: #151822;
                border-radius: 22px;
                border: 1px solid #252b3b;
            }
            QFrame#UserChip QLabel {
                background-color: transparent;
                color: #e5e7eb;
            }
        """)

        lay = QHBoxLayout(chip)
        lay.setContentsMargins(14, 8, 14, 8)
        lay.setSpacing(10)

        # avatar circle
        avatar = QLabel()
        avatar.setFixedSize(34, 34)
        avatar.setAlignment(Qt.AlignCenter)
        avatar.setStyleSheet("""
            QLabel {
                background: qradialgradient(cx:0.3, cy:0.3, radius:1,
                                            fx:0.3, fy:0.3,
                                            stop:0 #4f46e5, stop:1 #0ea5e9);
                color: #ffffff;
                border-radius: 17px;
                font-weight: 700;
                font-size: 16px;
            }
        """)
        initial = (self.username or "U")[0].upper()
        avatar.setText(initial)

        # name + status
        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)

        name_label = QLabel(self.username or "User")
        name_label.setStyleSheet("font-size: 13px; font-weight: 600;")

        status_row = QHBoxLayout()
        status_row.setContentsMargins(0, 0, 0, 0)
        status_row.setSpacing(4)

        status_dot = QLabel()
        status_dot.setFixedSize(8, 8)
        status_dot.setStyleSheet("QLabel { background-color:#22c55e; border-radius:4px; }")

        status_label = QLabel("Online")   # change to 'Logged in' if you prefer
        status_label.setStyleSheet("font-size: 11px; color:#9ca3af;")

        status_row.addWidget(status_dot)
        status_row.addWidget(status_label)
        status_row.addStretch(1)

        text_col.addWidget(name_label)
        text_col.addLayout(status_row)

        # three-dot menu icon
        more_label = QLabel("⋯")
        more_label.setAlignment(Qt.AlignCenter)
        more_label.setStyleSheet("color:#9ca3af; font-size:18px; padding-left:4px;")

        lay.addWidget(avatar)
        lay.addLayout(text_col)
        lay.addWidget(more_label)

        return chip

    # ---------------- COUNTS REFRESH ----------------

    def refresh_counts(self):
        try:
            self.machine_count = len(self.machine_db.get_all_machines())
        except Exception:
            self.machine_count = 0

        try:
            self.project_count = len(self.project_db.get_all_projects())
        except Exception:
            self.project_count = 0

        if getattr(self, "machine_count_label", None):
            self.machine_count_label.setText(str(self.machine_count))
        if getattr(self, "project_count_label", None):
            self.project_count_label.setText(str(self.project_count))

    # ---------------- STAT CARD (unchanged except bg) ----------------

    def create_stat_card(self, title, value, icon_path: Path | None = None):
        card = QFrame()
        card.setObjectName("stat_card")
        card.setStyleSheet("""
            QFrame#stat_card {
                background-color: #232323;
                border-radius: 18px;
                border: 1px solid #262b3a;
            }
            QFrame#stat_card:hover {
                background-color: #232323;
                border: 1px solid #3b82f6;
            }
            QFrame#stat_card QLabel {
                background-color: transparent;
            }
        """)

        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 160))
        card.setGraphicsEffect(shadow)

        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(20, 18, 20, 18)
        card_layout.setSpacing(18)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(6)

        title_label = QLabel(title)
        title_label.setStyleSheet("""
            font-size: 16px;
            font-weight: 700;
            color: #e5e7eb;
        """)
        text_layout.addWidget(title_label)

        value_label = QLabel(value)
        value_label.setObjectName(title.replace(" ", "_").lower() + "_count")
        value_label.setStyleSheet("""
            font-size: 32px;
            font-weight: 800;
            color: #38bdf8;
        """)
        text_layout.addWidget(value_label)

        if "Machine" in title:
            caption_text = "Configured inspection machines"
        elif "Project" in title:
            caption_text = "Active inspection projects"
        else:
            caption_text = ""

        if caption_text:
            caption_label = QLabel(caption_text)
            caption_label.setStyleSheet("""
                font-size: 11px;
                color: #9ca3af;
            """)
            text_layout.addWidget(caption_label)

        text_layout.addStretch()
        card_layout.addLayout(text_layout, 2)

        icon_label = QLabel()
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        ICON_SIZE = 110

        if isinstance(icon_path, Path):
            ext = icon_path.suffix.lower()
        else:
            ext = ""

        if isinstance(icon_path, Path) and ext == ".gif":
            movie = QMovie(str(icon_path))
            movie.setScaledSize(QSize(ICON_SIZE, ICON_SIZE))
            icon_label.setMovie(movie)
            icon_label.setFixedSize(ICON_SIZE, ICON_SIZE)
            movie.start()
        else:
            icon_pm = QPixmap()
            if isinstance(icon_path, Path):
                icon_pm = QPixmap(str(icon_path))

            if not icon_pm.isNull():
                icon_pm = icon_pm.scaled(
                    ICON_SIZE, ICON_SIZE,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                icon_label.setPixmap(icon_pm)
                icon_label.setFixedSize(ICON_SIZE, ICON_SIZE)
            else:
                icon_label.setText("📊")
                icon_label.setStyleSheet("font-size: 32px;")
                icon_label.setFixedSize(ICON_SIZE, ICON_SIZE)

        card_layout.addStretch(1)
        card_layout.addWidget(icon_label, 0, Qt.AlignRight | Qt.AlignVCenter)

        return card
