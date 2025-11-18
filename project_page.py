# project_page.py

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QFrame, QScrollArea, QMessageBox
)
from PyQt5.QtCore import Qt

from db import ProjectDB, MachineDB


class ProjectPage(QWidget):
    """
    Stand-alone Projects manager window:
      - list all projects
      - create / edit / delete
      - (optionally) jump to camera setup
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        # basic window settings (it will open as separate window)
        self.setWindowTitle("Projects")
        self.resize(900, 600)

        self.main_window = None  # can be set later if needed
        self.project_db = ProjectDB()
        self.machine_db = MachineDB()

        self.setStyleSheet("background-color: #111;")
        self.setup_ui()

    # ------------------------------------------------------------
    def set_main_window(self, main_window):
        """Optional: set MainWindow reference if you want camera setup navigation."""
        self.main_window = main_window

    # ------------------------------------------------------------
    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(25, 25, 25, 25)

        title = QLabel("Projects")
        title.setStyleSheet("color: white; font-size: 26px; font-weight: bold;")
        main_layout.addWidget(title)

        # Add button
        add_btn = QPushButton("+ Create Project")
        add_btn.setFixedWidth(200)
        add_btn.setStyleSheet(self.button_style())
        add_btn.clicked.connect(self.open_add_form)
        main_layout.addWidget(add_btn)
        main_layout.addSpacing(10)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none;")

        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setSpacing(15)

        scroll.setWidget(self.container)
        main_layout.addWidget(scroll)

        self.refresh_list()

    # ------------------------------------------------------------
    def refresh_list(self):
        # Clear old
        for i in reversed(range(self.container_layout.count())):
            item = self.container_layout.itemAt(i)
            if item:
                w = item.widget()
                if w:
                    w.deleteLater()

        projects = self.project_db.get_all_projects()

        if not projects:
            label = QLabel("No projects created yet.")
            label.setStyleSheet("color: #aaa; font-size: 15px;")
            self.container_layout.addWidget(label)
            return

        for p in projects:
            self.container_layout.addWidget(self.project_card(p))

    # ------------------------------------------------------------
    def button_style(self):
        return """
        QPushButton {
            background-color: #1B5FCC;
            color: white;
            padding: 10px;
            border-radius: 6px;
            font-size: 14px;
        }
        QPushButton:hover {
            background-color: #2E86FF;
        }
        """

    def card_button(self):
        return """
            QPushButton {
                background-color: #1B5FCC;
                padding: 8px 16px;
                color: white;
                border-radius: 6px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #2E86FF;
            }
        """

    def card_delete_button(self):
        return """
            QPushButton {
                background-color: #d9534f;
                padding: 8px 16px;
                color: white;
                border-radius: 6px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #ff6b6b;
            }
        """

    # ------------------------------------------------------------
    # PROJECT CARD
    # ------------------------------------------------------------
    def project_card(self, p):
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #1a1a1a;
                border: 1px solid #333;
                border-radius: 12px;
            }
            QFrame:hover {
                border: 1px solid #444;
                background-color: #1f1f1f;
            }
        """)
        card.setMinimumHeight(160)

        # Main layout: Left (info) | Right (actions)
        main_layout = QHBoxLayout(card)
        main_layout.setContentsMargins(25, 20, 25, 20)
        main_layout.setSpacing(20)

        # LEFT SIDE
        left_layout = QVBoxLayout()
        left_layout.setSpacing(8)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setAlignment(Qt.AlignTop)

        # Project Name
        name_label = QLabel(p["name"])
        name_label.setStyleSheet("""
            color: white;
            font-size: 22px;
            font-weight: bold;
            padding-bottom: 4px;
        """)
        left_layout.addWidget(name_label)

        # Machine info
        machine_container = QWidget()
        machine_layout = QVBoxLayout(machine_container)
        machine_layout.setContentsMargins(0, 0, 0, 0)
        machine_layout.setSpacing(6)

        machine_id = p.get("machine_id")
        machine_name = "Unknown Machine"
        machine_info = None

        if machine_id:
            machine = self.machine_db.get_machine(str(machine_id))
            if machine:
                machine_name = machine["name"]
                machine_info = machine

        machine_label = QLabel(f"🔧 Machine: {machine_name}")
        machine_label.setStyleSheet("""
            color: #aaa;
            font-size: 14px;
            padding: 4px 0;
        """)
        machine_layout.addWidget(machine_label)

        # optional PLC extra text if you later add these fields
        if machine_info:
            plc_parts = []
            if machine_info.get("plc_brand"):
                plc_parts.append(machine_info.get("plc_brand"))
            if machine_info.get("plc_model"):
                plc_parts.append(machine_info.get("plc_model"))
            if plc_parts:
                plc_info = QLabel(f"PLC: {' | '.join(plc_parts)}")
                plc_info.setStyleSheet("""
                    color: #4A9EFF;
                    font-size: 13px;
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
        btn_camera = QPushButton("Configure Cameras")
        btn_delete = QPushButton("Delete")

        btn_edit.setStyleSheet(self.card_button())
        btn_camera.setStyleSheet(self.card_button())
        btn_delete.setStyleSheet(self.card_delete_button())

        btn_edit.clicked.connect(lambda: self.open_edit_form(p))
        btn_camera.clicked.connect(lambda: self.open_camera_setup(p))
        btn_delete.clicked.connect(lambda: self.delete_project(p))

        btn_layout.addWidget(btn_edit)
        btn_layout.addWidget(btn_camera)
        btn_layout.addWidget(btn_delete)

        right_layout.addLayout(btn_layout)
        right_layout.addStretch()

        main_layout.addLayout(left_layout, 3)
        main_layout.addLayout(right_layout, 1)

        return card

    # ------------------------------------------------------------
    # CAMERA SETUP REDIRECT
    # ------------------------------------------------------------
    def open_camera_setup(self, project):
        """Navigate to camera setup page for the selected project (if wired)."""
        if not self.main_window:
            self.show_error(
                "Camera setup is not wired yet.\n"
                "You can connect this later via main_window.open_camera_setup()."
            )
            return

        self.main_window.open_camera_setup(project)

    # ------------------------------------------------------------
    # ADD / EDIT
    # ------------------------------------------------------------
    def open_add_form(self):
        self.project_form(mode="add")

    def open_edit_form(self, project):
        self.project_form(mode="edit", project=project)

    # ------------------------------------------------------------
    # PROJECT FORM (ADD / EDIT)
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

        # Project name
        name = QLineEdit()
        name.setPlaceholderText("Project name")
        name.setStyleSheet(self.input_style())

        # Machine dropdown
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
            # Get machine name safely even if it’s nested / dict
            raw_name = m.get("name", "")

            if isinstance(raw_name, dict):
                # Try common keys inside the dict, fall back to full dict as string
                name = (
                    raw_name.get("name")
                    or raw_name.get("machine_name")
                    or str(raw_name)
                )
            else:
                name = str(raw_name)

            machine_id = str(m.get("_id") or m.get("id"))
            machine_select.addItem(name, machine_id)


        if mode == "edit":
            name.setText(project["name"])
            machine_id = str(project.get("machine_id", ""))
            machine_index = machine_select.findData(machine_id)
            if machine_index >= 0:
                machine_select.setCurrentIndex(machine_index)

        layout.addWidget(name)
        layout.addWidget(machine_select)

        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(self.button_style())
        layout.addWidget(save_btn)

        def save_action():
            if not name.text().strip():
                self.show_error("Project name is required")
                return

            machine_id = machine_select.currentData()
            if not machine_id:
                self.show_error("Please select a machine")
                return

            if mode == "add":
                result = self.project_db.add_project(
                    name=name.text().strip(),
                    machine_id=machine_id
                )
                if result:
                    self.show_success("Project created")
                else:
                    self.show_error("Failed to create project")
            else:
                project_id = str(project["_id"])
                success = self.project_db.update_project(
                    project_id,
                    name=name.text().strip(),
                    machine_id=machine_id
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
    # DELETE PROJECT
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
