# project_page.py

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QFrame, QScrollArea, QMessageBox,
    QSizePolicy,
)
from PyQt5.QtCore import Qt
import os, re
from pathlib import Path
from db import ProjectDB, MachineDB
from datetime import datetime

class ProjectPage(QWidget):
    """
    Projects manager page:
      - list all projects
      - create / edit / delete
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Projects")
        self.resize(900, 600)

        self.main_window = None
        self.project_db = ProjectDB()
        self.machine_db = MachineDB()

        # page bg + transparent labels (no stripes)
        self.setObjectName("ProjectsPage")
        self.setStyleSheet("""
            QWidget#ProjectsPage {
                background-color: #111827;
            }
            QWidget#ProjectsPage QLabel {
                background-color: transparent;
            }
        """)

        self.setup_ui()

    # ------------------------------------------------------------
    def set_main_window(self, main_window):
        self.main_window = main_window

    # ------------------------------------------------------------
    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 24)
        main_layout.setSpacing(18)

        # ---------- HEADER ROW: title + subtitle + button ----------
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(12)

        title_col = QVBoxLayout()
        title_col.setContentsMargins(0, 0, 0, 0)
        title_col.setSpacing(2)

        title = QLabel("Projects")
        title.setStyleSheet("""
            color: #0d6efd;
            font-size: 24px;
            font-weight: 800;
        """)

        subtitle = QLabel("Organize inspection recipes, training pipelines and machines.")
        subtitle.setStyleSheet("""
            color: #9ca3af;
            font-size: 11px;
        """)

        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header_row.addLayout(title_col)
        header_row.addStretch(1)

        # rounded / modern create button
        add_btn = QPushButton("+ Create Project")
        add_btn.setFixedHeight(36)
        add_btn.setMinimumWidth(170)
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setStyleSheet(self.header_button_style())
        add_btn.clicked.connect(self.open_add_form)

        header_row.addWidget(add_btn, 0, Qt.AlignRight | Qt.AlignVCenter)

        main_layout.addLayout(header_row)

        # ---------- SCROLL AREA ----------
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollArea > QWidget > QWidget {
                background-color: transparent;
            }
        """)

        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(0, 8, 0, 24)
        self.container_layout.setSpacing(14)
        # center cards horizontally, stack from top
        self.container_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        # let height hug contents; width can expand but we cap card width
        self.container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        scroll.setWidget(self.container)
        main_layout.addWidget(scroll)

        self.refresh_list()

    # ------------------------------------------------------------
    # BUTTON STYLES
    # ------------------------------------------------------------
    def header_button_style(self):
        # gradient pill button (header)
        return """
        QPushButton {
            background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                            stop:0 #2563eb, stop:1 #38bdf8);
            color: #ffffff;
            border: none;
            border-radius: 18px;
            padding: 0 20px;
            font-size: 13px;
            font-weight: 600;
            letter-spacing: 0.4px;
        }
        QPushButton:hover {
            background-color: #1d4ed8;
        }
        QPushButton:pressed {
            background-color: #1e40af;
        }
        """


    def card_button(self):
        # SAME pill style as header, just slightly tighter padding
        return """
        QPushButton {
            background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                              stop:0 #2563eb, stop:1 #38bdf8);
            color: #ffffff;
            border: none;
            border-radius: 16px;      /* pill shape */
            padding: 0 16px;
            font-size: 12px;
            font-weight: 600;
            letter-spacing: 0.3px;
        }
        QPushButton:hover {
            background-color: #1d4ed8;
        }
        QPushButton:pressed {
            background-color: #1e40af;
        }
        """

    def card_delete_button(self):
        # red pill, same rounded look
        return """
        QPushButton {
            background-color: #ef4444;
            color: #ffffff;
            border: none;
            border-radius: 16px;
            padding: 0 16px;
            font-size: 12px;
            font-weight: 600;
            letter-spacing: 0.3px;
        }
        QPushButton:hover {
            background-color: #f97373;
        }
        QPushButton:pressed {
            background-color: #b91c1c;
        }
        """

    # ------------------------------------------------------------
    # RENDER PROJECT LIST
    # ------------------------------------------------------------
    def refresh_list(self):
        layout = self.container_layout

        # clear everything (widgets + layouts + spacers)
        while layout.count():
            item = layout.takeAt(0)

            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
                continue

            sub_layout = item.layout()
            if sub_layout is not None:
                while sub_layout.count():
                    sub_item = sub_layout.takeAt(0)
                    sub_w = sub_item.widget()
                    if sub_w is not None:
                        sub_w.setParent(None)
                        sub_w.deleteLater()

        projects = self.project_db.get_all_projects()

        if not projects:
            label = QLabel("No projects created yet.")
            label.setStyleSheet("color: #aaa; font-size: 15px;")
            layout.addWidget(label)
            return

        for p in projects:
            layout.addWidget(self.project_card(p))

    # ------------------------------------------------------------
    # PROJECT CARD
    # ------------------------------------------------------------
    def project_card(self, p):
        card = QFrame()
        card.setObjectName("ProjectCard")
        card.setStyleSheet("""
            QFrame#ProjectCard {
                background-color: #0f172a;
                border: 1px solid #1f2937;
                border-radius: 16px;
            }
            QFrame#ProjectCard:hover {
                background-color: #111827;
                border: 1px solid #2563eb;
            }
        """)
        card.setMinimumHeight(130)
        card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        main_layout = QHBoxLayout(card)
        main_layout.setContentsMargins(22, 16, 22, 16)
        main_layout.setSpacing(18)

        # LEFT SIDE
        left_layout = QVBoxLayout()
        left_layout.setSpacing(6)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setAlignment(Qt.AlignTop)

        name_label = QLabel(p.get("name", "Unnamed Project"))
        name_label.setStyleSheet("""
            color: #e5e7eb;
            font-size: 18px;
            font-weight: 700;
            padding-bottom: 2px;
        """)
        left_layout.addWidget(name_label)

        proj_type = p.get("type", "Not Set")
        type_label = QLabel(f"Type: {proj_type}")
        type_label.setStyleSheet("""
            color: #60a5fa;
            font-size: 13px;
            font-weight: 500;
            padding: 2px 0;
        """)
        left_layout.addWidget(type_label)

        # Machine info
        machine_container = QWidget()
        machine_layout = QVBoxLayout(machine_container)
        machine_layout.setContentsMargins(0, 0, 0, 0)
        machine_layout.setSpacing(2)

        machine_id = p.get("machine_id")
        machine_name = "Unknown Machine"
        machine_info = None

        if machine_id:
            machine = self.machine_db.get_machine(str(machine_id))
            if machine:
                raw_machine_name = machine.get("name")
                if isinstance(raw_machine_name, dict):
                    machine_name = raw_machine_name.get("name") or str(raw_machine_name)
                else:
                    machine_name = str(raw_machine_name)
                machine_info = machine

        machine_label = QLabel(f"Machine: {machine_name}")
        machine_label.setStyleSheet("""
            color: #9ca3af;
            font-size: 13px;
            padding: 2px 0;
        """)
        machine_layout.addWidget(machine_label)

        # optional PLC extra info (if present)
        if machine_info:
            plc_parts = []
            if machine_info.get("plc_brand"):
                plc_parts.append(machine_info.get("plc_brand"))
            if machine_info.get("plc_model"):
                plc_parts.append(machine_info.get("plc_model"))
            if plc_parts:
                plc_info = QLabel(f"PLC: {' · '.join(plc_parts)}")
                plc_info.setStyleSheet("""
                    color: #4A9EFF;
                    font-size: 12px;
                    padding: 2px 0;
                """)
                machine_layout.addWidget(plc_info)

        left_layout.addWidget(machine_container)
        left_layout.addStretch()

        # RIGHT SIDE: buttons
        right_layout = QVBoxLayout()
        right_layout.setSpacing(8)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setAlignment(Qt.AlignTop | Qt.AlignRight)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        btn_edit = QPushButton("Edit")
        btn_delete = QPushButton("Delete")

        # Make them pill-shaped and clickable like header
        for b in (btn_edit,btn_delete):
            b.setFixedHeight(32)
            b.setCursor(Qt.PointingHandCursor)

        btn_edit.setStyleSheet(self.card_button())
        btn_delete.setStyleSheet(self.card_delete_button())

        btn_edit.clicked.connect(lambda: self.open_edit_form(p))
        btn_delete.clicked.connect(lambda: self.delete_project(p))

        btn_layout.addWidget(btn_edit)
        btn_layout.addWidget(btn_delete)

        right_layout.addLayout(btn_layout)
        right_layout.addStretch()

        main_layout.addLayout(left_layout, 3)
        main_layout.addLayout(right_layout, 1)

        return card


    # ------------------------------------------------------------
    # ADD / EDIT
    # ------------------------------------------------------------
    def open_add_form(self):
        self.project_form(mode="add")

    def open_edit_form(self, project):
        self.project_form(mode="edit", project=project)

    # ------------------------------------------------------------
    def project_form(self, mode="add", project=None):
        win = QWidget(self, flags=Qt.Window)
        win.setWindowTitle("Create Project" if mode == "add" else "Edit Project")
        win.resize(450, 350)
        win.setStyleSheet("background-color: #111;")

        layout = QVBoxLayout(win)
        layout.setContentsMargins(25, 25, 25, 25)

        title = QLabel("Create Project" if mode == "add" else "Edit Project")
        title.setStyleSheet("color: white; font-size: 22px; font-weight: bold;")
        layout.addWidget(title)

        name = QLineEdit()
        name.setPlaceholderText("Project name")
        name.setStyleSheet(self.input_style())

        type_select = QComboBox()
        type_select.addItems([
            "Anomaly",
            "Classification",
            "Anomaly + Classification",
            "Dimension"
        ])
        type_select.setStyleSheet("""
            QComboBox {
                background-color: #1a1a1a;
                border: 1px solid #333;
                border-radius: 6px;
                padding: 10px;
                color: white;
            }
            QComboBox QAbstractItemView {
                background-color: #1a1a1a;
                color: white;
                selection-background-color: #1B5FCC;
            }
        """)

        machine_select = QComboBox()
        machine_select.setStyleSheet("""
            QComboBox {
                background-color: #1a1a1a;
                border: 1px solid #333;
                border-radius: 6px;
                padding: 10px;
                color: white;
            }
            QComboBox QAbstractItemView {
                background-color: #1a1a1a;
                color: white;
                selection-background-color: #1B5FCC;
            }
        """)

        machines = self.machine_db.get_all_machines()
        for m in machines:
            raw_name = m.get("name", "")
            if isinstance(raw_name, dict):
                machine_name = (
                    raw_name.get("name")
                    or raw_name.get("machine_name")
                    or str(raw_name)
                )
            else:
                machine_name = str(raw_name)
            machine_id = str(m.get("_id") or m.get("id"))
            machine_select.addItem(machine_name, machine_id)

        if mode == "edit":
            name.setText(project["name"])
            machine_id = str(project.get("machine_id", ""))
            machine_index = machine_select.findData(machine_id)
            if machine_index >= 0:
                machine_select.setCurrentIndex(machine_index)
            proj_type = project.get("type")
            if proj_type:
                index = type_select.findText(proj_type)
                if index >= 0:
                    type_select.setCurrentIndex(index)

        layout.addWidget(name)
        layout.addWidget(type_select)
        layout.addWidget(machine_select)

        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(self.header_button_style())
        layout.addWidget(save_btn)

        def save_action():
            if not name.text().strip():
                self.show_error("Project name is required")
                return

            machine_id_val = machine_select.currentData()
            if not machine_id_val:
                self.show_error("Please select a machine")
                return

            if mode == "add":
                result = self.project_db.add_project(
                    name=name.text().strip(),
                    machine_id=machine_id_val,
                    description="",
                    type=type_select.currentText(),
                )

                if result:
                    self.show_success(
                        f"Project created.\nFolder: {result.get('folder_path','')}"
                    )
                else:
                    self.show_error("Failed to create project")
            else:
                project_id = str(project["_id"])
                from utils.project_paths import get_project_folder
                folder_path = str(get_project_folder(name.text().strip()))

                success = self.project_db.update_project(
                    project_id,
                    name=name.text().strip(),
                    machine_id=machine_id_val,
                    description="",
                    type=type_select.currentText(),
                    folder_path=folder_path
                )

                if success:
                    self.show_success("Project updated")
                else:
                    self.show_error("Failed to update project")

            win.close()
            self.refresh_list()

        save_btn.clicked.connect(save_action)
        win.show()

    # ------------------------------------------------------------
    def delete_project(self, project):
        confirm = QMessageBox.question(
            self,
            "Delete Project",
            f"Are you sure you want to delete '{project['name']}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.No:
            return

        project_id = str(project["_id"])
        success = self.project_db.delete_project(project_id)
        if success:
            self.show_success("Project deleted")
        else:
            self.show_error("Failed to delete project")
        self.refresh_list()

    # ------------------------------------------------------------
    def input_style(self):
        return """
            QLineEdit {
                background-color: #1a1a1a;
                border: 1px solid #333;
                border-radius: 6px;
                padding: 10px;
                color: white;
            }
            QLineEdit:focus {
                border: 1px solid #2E86FF;
            }
        """

    def show_error(self, message):
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowTitle("Error")
        msg.setText(message)
        msg.exec_()

    def show_success(self, message):
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Information)
        msg.setWindowTitle("Success")
        msg.setText(message)
        msg.exec_()

    def show_info(self, message):
        QMessageBox.information(self, "Info", message)
