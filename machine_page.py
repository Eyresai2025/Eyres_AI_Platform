# src/views/pages/machine_page.py

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFrame, QScrollArea, QMessageBox, QGridLayout,
    QDialog, QComboBox
)
from PyQt5.QtCore import Qt
from bson.objectid import ObjectId

from db import ProjectDB, MachineDB


class MachinePage(QWidget):

    def __init__(self, user=None):
        super().__init__()
        self.user = user
        self.machine_db = MachineDB()
        self.setStyleSheet("background-color: #111;")
        self.setup_ui()

    # ------------------------------------------------------------
    # MAIN PAGE SETUP
    # ------------------------------------------------------------
    def setup_ui(self):

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(25, 25, 25, 25)

        # TITLE
        title = QLabel("Machines")
        title.setStyleSheet("color: white; font-size: 26px; font-weight: bold;")
        main_layout.addWidget(title)

        # ADD BUTTON
        add_btn = QPushButton("+ Add Machine")
        add_btn.setFixedWidth(180)
        add_btn.setStyleSheet(self.button_style())
        add_btn.clicked.connect(self.open_add_form)
        main_layout.addWidget(add_btn)
        main_layout.addSpacing(10)

        # SCROLL AREA (MACHINE LIST)
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
    # RENDER MACHINE LIST
    # ------------------------------------------------------------
    def refresh_list(self):

        # Clear previous widgets
        for i in reversed(range(self.container_layout.count())):
            item = self.container_layout.itemAt(i)
            w = item.widget()
            if w:
                w.deleteLater()

        machines = self.machine_db.get_all_machines()

        if not machines:
            empty_label = QLabel("No machines added yet.")
            empty_label.setStyleSheet("color: #aaa; font-size: 15px;")
            self.container_layout.addWidget(empty_label)
            return

        for m in machines:
            self.container_layout.addWidget(self.machine_card(m))

    # ------------------------------------------------------------
    # BASIC BUTTON STYLE
    # ------------------------------------------------------------
    def button_style(self):
        return """
        QPushButton {
            background-color: #1B5FCC;
            color: white;
            border-radius: 6px;
            padding: 10px;
            font-size: 14px;
        }
        QPushButton:hover {
            background-color: #2E86FF;
        }
        """

    # ------------------------------------------------------------
    # MACHINE CARD WIDGET
    # ------------------------------------------------------------
    def machine_card(self, m):

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

        # Main layout: Left (info) | Right (status + buttons)
        main_layout = QHBoxLayout(card)
        main_layout.setContentsMargins(25, 20, 25, 20)
        main_layout.setSpacing(20)

        # LEFT SIDE: Machine Information
        left_layout = QVBoxLayout()
        left_layout.setSpacing(8)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setAlignment(Qt.AlignTop)

        # Machine Name
        name_label = QLabel(f"{m['name']}")
        name_label.setStyleSheet("""
            color: white;
            font-size: 22px;
            font-weight: bold;
            padding-bottom: 4px;
        """)
        left_layout.addWidget(name_label)

        # Description (if exists)
        desc_text = m.get("description", "")
        if desc_text:
            desc = QLabel(desc_text)
            desc.setStyleSheet("""
                color: #aaa;
                font-size: 14px;
                padding-bottom: 8px;
            """)
            desc.setWordWrap(True)
            left_layout.addWidget(desc)

        # PLC Information Section
        plc_container = QWidget()
        plc_layout = QVBoxLayout(plc_container)
        plc_layout.setContentsMargins(0, 0, 0, 0)
        plc_layout.setSpacing(6)

        # PLC Brand/Model/Protocol
        plc_info_parts = []
        if m.get("plc_brand"):
            plc_info_parts.append(f"PLC: {m.get('plc_brand', '')}")
        if m.get("plc_model"):
            plc_info_parts.append(m.get("plc_model", ""))
        if m.get("plc_protocol"):
            plc_info_parts.append(f"({m.get('plc_protocol', '')})")

        if plc_info_parts:
            plc_label = QLabel(" | ".join(plc_info_parts))
            plc_label.setStyleSheet("""
                color: #4A9EFF;
                font-size: 14px;
                font-weight: 500;
                padding: 4px 0;
            """)
            plc_layout.addWidget(plc_label)

        # IP Address
        if m.get("ip_address"):
            ip_label = QLabel(f"📍 IP: {m.get('ip_address', '')}")
            ip_label.setStyleSheet("""
                color: #888;
                font-size: 13px;
                padding: 2px 0;
            """)
            plc_layout.addWidget(ip_label)

        if plc_info_parts or m.get("ip_address"):
            left_layout.addWidget(plc_container)

        left_layout.addStretch()

        # RIGHT SIDE: Status and Actions
        right_layout = QVBoxLayout()
        right_layout.setSpacing(12)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setAlignment(Qt.AlignTop | Qt.AlignRight)

        # Status Badge
        status = "ACTIVE" if m.get("active") else "DISABLED"
        status_color = "#3CCF4E" if m.get("active") else "#d9534f"
        status_bg = "#1a3a1a" if m.get("active") else "#3a1a1a"

        status_frame = QFrame()
        status_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {status_bg};
                border: 1px solid {status_color};
                border-radius: 6px;
                padding: 6px 12px;
            }}
        """)
        status_layout = QHBoxLayout(status_frame)
        status_layout.setContentsMargins(0, 0, 0, 0)

        status_label = QLabel(status)
        status_label.setStyleSheet(f"""
            color: {status_color};
            font-size: 12px;
            font-weight: bold;
            letter-spacing: 1px;
        """)
        status_layout.addWidget(status_label)
        right_layout.addWidget(status_frame)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        btn_edit = QPushButton("Edit")
        btn_delete = QPushButton("Delete")

        btn_edit.setStyleSheet(self.card_button())
        btn_delete.setStyleSheet(self.card_delete_button())

        btn_edit.clicked.connect(lambda: self.open_edit_form(m))
        btn_delete.clicked.connect(lambda: self.delete_machine(m))

        btn_layout.addWidget(btn_edit)
        btn_layout.addWidget(btn_delete)
        right_layout.addLayout(btn_layout)

        right_layout.addStretch()

        # Combine left and right
        main_layout.addLayout(left_layout, 3)  # Left takes 3 parts
        main_layout.addLayout(right_layout, 1)  # Right takes 1 part

        return card

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
    # ADD FORM
    # ------------------------------------------------------------
    def open_add_form(self):
        """Open Add Machine dialog with PLC configuration."""
        dialog = AddMachineDialog(parent=self)
        if dialog.exec_() == QDialog.Accepted:
            self.refresh_list()

    # ------------------------------------------------------------
    # EDIT FORM
    # ------------------------------------------------------------
    def open_edit_form(self, machine):
        """Open Edit Machine dialog with PLC configuration."""
        dialog = AddMachineDialog(parent=self, machine=machine)
        if dialog.exec_() == QDialog.Accepted:
            self.refresh_list()

    # ------------------------------------------------------------
    # DELETE MACHINE
    # ------------------------------------------------------------
    def delete_machine(self, machine):

        confirm = QMessageBox.question(
            self,
            "Delete Machine",
            f"Are you sure you want to delete '{machine['name']}'?",
            QMessageBox.Yes | QMessageBox.No
        )

        if confirm == QMessageBox.No:
            return

        machine_id = str(machine["_id"])
        success = self.machine_db.delete_machine(machine_id)
        if success:
            self.show_success("Machine deleted")
        else:
            self.show_error("Failed to delete machine")
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
        """Simple error message display"""
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowTitle("Error")
        msg.setText(message)
        msg.exec_()

    def show_success(self, message):
        """Simple success message display"""
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Information)
        msg.setWindowTitle("Success")
        msg.setText(message)
        msg.exec_()


# ===================================================================
# Add Machine Dialog with PLC Configuration
# ===================================================================

"""
Add Machine Dialog with PLC Configuration
Dialog for adding/editing machines with PLC brand, model, and protocol selection.
"""

# PLC Configuration Data
PLC_DATA = {
    "Siemens": {
        "models": ["S7-200", "S7-300", "S7-400", "S7-1200", "S7-1500", "LOGO!"],
        "protocols": ["S7 TCP", "Modbus TCP"]
    },
    "Mitsubishi": {
        "models": ["FX Series", "Q Series", "L Series", "iQ-R"],
        "protocols": ["MC Protocol", "Modbus TCP"]
    },
    "Allen-Bradley": {
        "models": ["MicroLogix", "CompactLogix", "ControlLogix"],
        "protocols": ["EtherNet/IP", "CIP"]
    },
    "Omron": {
        "models": ["CP Series", "CJ Series", "NJ/NX Series"],
        "protocols": ["FINS", "EtherNet/IP"]
    },
    "Keyence": {
        "models": ["KV-3000", "KV-7000", "KV-Nano"],
        "protocols": ["KV Protocol", "Modbus TCP"]
    },
    "Delta": {
        "models": ["DVP Series", "AH Series", "AS Series"],
        "protocols": ["Modbus RTU", "Modbus TCP"]
    },
    "Schneider": {
        "models": ["Modicon M221", "Modicon M241", "Modicon M251"],
        "protocols": ["Modbus TCP", "Modbus RTU"]
    }
}


class AddMachineDialog(QDialog):
    """
    Dialog for adding a new machine with PLC configuration.
    """

    def __init__(self, parent=None, machine=None):
        """
        Initialize the dialog.

        Args:
            parent: Parent widget
            machine: Optional machine data for edit mode
        """
        super().__init__(parent)
        self.machine = machine
        self.machine_db = MachineDB()
        self.result = None

        if machine:
            self.setWindowTitle("Edit Machine")
        else:
            self.setWindowTitle("Add Machine")

        self.setMinimumWidth(400)
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
            }
            QLabel {
                color: white;
                font-size: 13px;
                padding: 5px 0;
            }
            QLineEdit, QComboBox {
                background-color: #2b2b2b;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 6px;
                color: white;
                font-size: 13px;
            }
            QLineEdit:focus, QComboBox:focus {
                border: 2px solid #1E88E5;
            }
            QComboBox QAbstractItemView {
                background-color: #2b2b2b;
                color: white;
                selection-background-color: #1E88E5;
                border: 1px solid #444;
            }
            QPushButton {
                background-color: #1E88E5;
                color: white;
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #42A5F5;
            }
            QPushButton:pressed {
                background-color: #1565C0;
            }
            QPushButton#cancelButton {
                background-color: #666;
            }
            QPushButton#cancelButton:hover {
                background-color: #777;
            }
        """)

        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        # Machine Name
        layout.addWidget(QLabel("Machine Name"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Enter machine name")
        layout.addWidget(self.name_input)

        # Description
        layout.addWidget(QLabel("Description"))
        self.desc_input = QLineEdit()
        self.desc_input.setPlaceholderText("Optional description")
        layout.addWidget(self.desc_input)

        # PLC Brand
        layout.addWidget(QLabel("PLC Brand"))
        self.plc_brand_combo = QComboBox()
        self.plc_brand_combo.addItem("Select PLC Brand", None)
        self.plc_brand_combo.addItems(list(PLC_DATA.keys()))
        self.plc_brand_combo.currentTextChanged.connect(self.on_brand_changed)
        layout.addWidget(self.plc_brand_combo)

        # PLC Model Series
        layout.addWidget(QLabel("Model Series"))
        self.plc_model_combo = QComboBox()
        self.plc_model_combo.addItem("Select Model", None)
        self.plc_model_combo.setEnabled(False)
        layout.addWidget(self.plc_model_combo)

        # Communication Protocol
        layout.addWidget(QLabel("Communication Protocol"))
        self.plc_protocol_combo = QComboBox()
        self.plc_protocol_combo.addItem("Select Protocol", None)
        self.plc_protocol_combo.setEnabled(False)
        layout.addWidget(self.plc_protocol_combo)

        # IP Address (optional)
        layout.addWidget(QLabel("IP Address (Optional)"))
        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText("e.g., 192.168.1.100")
        layout.addWidget(self.ip_input)

        # Load existing machine data if editing
        if self.machine:
            self.name_input.setText(self.machine.get("name", ""))
            self.desc_input.setText(self.machine.get("description", ""))
            self.ip_input.setText(self.machine.get("ip_address", ""))

            # Load PLC configuration
            plc_brand = self.machine.get("plc_brand", "")
            if plc_brand:
                index = self.plc_brand_combo.findText(plc_brand)
                if index >= 0:
                    self.plc_brand_combo.setCurrentIndex(index)
                    # Trigger update to populate model and protocol
                    self.on_brand_changed(plc_brand)

                    # Set model
                    plc_model = self.machine.get("plc_model", "")
                    if plc_model:
                        model_index = self.plc_model_combo.findText(plc_model)
                        if model_index >= 0:
                            self.plc_model_combo.setCurrentIndex(model_index)

                    # Set protocol
                    plc_protocol = self.machine.get("plc_protocol", "")
                    if plc_protocol:
                        protocol_index = self.plc_protocol_combo.findText(plc_protocol)
                        if protocol_index >= 0:
                            self.plc_protocol_combo.setCurrentIndex(protocol_index)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.save)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("cancelButton")
        cancel_btn.clicked.connect(self.reject)

        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        self.setLayout(layout)

    def on_brand_changed(self, brand):
        """Update model and protocol dropdowns when brand changes."""
        if not brand or brand == "Select PLC Brand":
            # Clear and disable model and protocol dropdowns
            self.plc_model_combo.clear()
            self.plc_model_combo.addItem("Select Model", None)
            self.plc_model_combo.setEnabled(False)

            self.plc_protocol_combo.clear()
            self.plc_protocol_combo.addItem("Select Protocol", None)
            self.plc_protocol_combo.setEnabled(False)
            return

        # Get PLC data for selected brand
        plc_info = PLC_DATA.get(brand)
        if not plc_info:
            return

        # Update model dropdown
        self.plc_model_combo.clear()
        self.plc_model_combo.addItem("Select Model", None)
        self.plc_model_combo.addItems(plc_info["models"])
        self.plc_model_combo.setEnabled(True)

        # Update protocol dropdown
        self.plc_protocol_combo.clear()
        self.plc_protocol_combo.addItem("Select Protocol", None)
        self.plc_protocol_combo.addItems(plc_info["protocols"])
        self.plc_protocol_combo.setEnabled(True)

    def save(self):
        """Save the machine data via MachineDB."""
        name = self.name_input.text().strip()

        if not name:
            QMessageBox.warning(self, "Missing", "Machine name cannot be empty")
            return

        # Get PLC configuration values
        plc_brand = self.plc_brand_combo.currentText()
        if plc_brand == "Select PLC Brand":
            plc_brand = None

        plc_model = self.plc_model_combo.currentText()
        if plc_model == "Select Model":
            plc_model = None

        plc_protocol = self.plc_protocol_combo.currentText()
        if plc_protocol == "Select Protocol":
            plc_protocol = None

        description = self.desc_input.text().strip() or None
        ip_address = self.ip_input.text().strip() or None

        try:
            if self.machine:
                # Update existing
                machine_id = str(self.machine.get("_id") or self.machine.get("id"))
                update_data = {
                    "name": name,
                    "description": description,
                    "ip_address": ip_address,
                    "plc_brand": plc_brand,
                    "plc_model": plc_model,
                    "plc_protocol": plc_protocol,
                }
                # remove None fields
                update_data = {k: v for k, v in update_data.items() if v is not None}

                success = self.machine_db.update_machine(machine_id, update_data)
                if success:
                    QMessageBox.information(self, "Success", "Machine updated successfully.")
                    self.result = {"success": True}
                    self.accept()
                else:
                    QMessageBox.warning(self, "Error", "Failed to update machine.")
            else:
                # Add new
                data = {
                    "name": name,
                    "description": description,
                    "plc_brand": plc_brand,
                    "plc_model": plc_model,
                    "plc_protocol": plc_protocol,
                    "ip_address": ip_address,
                }
                machine_id = self.machine_db.add_machine(data)
                if machine_id:
                    QMessageBox.information(self, "Success", "Machine added successfully.")
                    self.result = {"success": True}
                    self.accept()
                else:
                    QMessageBox.warning(self, "Error", "Failed to add machine.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error saving machine: {str(e)}")

    def get_result(self):
        """Return result dict or None."""
        return self.result
