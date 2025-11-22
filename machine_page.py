# src/views/pages/machine_page.py

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFrame, QScrollArea, QMessageBox, QGridLayout,
    QDialog, QComboBox, QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal
from bson.objectid import ObjectId
from db import ProjectDB, MachineDB
from plc_connection import check_plc_and_get_active
import threading
from functools import partial

class MachinePage(QWidget):
    reconnectFinished = pyqtSignal(bool, str)
    def __init__(self, user=None):
        super().__init__()
        self.user = user
        self.machine_db = MachineDB()

        # page bg + make all labels transparent (kills stripes)
        self.setObjectName("MachinesPage")
        self.setStyleSheet("""
            QWidget#MachinesPage {
                background-color: #111827;
            }
            QWidget#MachinesPage QLabel {
                background-color: transparent;
            }
        """)

        self.setup_ui()
        self.reconnectFinished.connect(self._on_reconnect_result)


    # ------------------------------------------------------------
    # MAIN PAGE SETUP
    # ------------------------------------------------------------
    def setup_ui(self):

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 24)
        main_layout.setSpacing(12)

        # ---------- HEADER ROW: title + subtitle + button ----------
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(12)

        title_col = QVBoxLayout()
        title_col.setContentsMargins(0, 0, 0, 0)
        title_col.setSpacing(2)

        title = QLabel("Machines")
        title.setStyleSheet("""
            color: #0d6efd;
            font-size: 24px;
            font-weight: 800;
        """)

        subtitle = QLabel("Configure inspection cells, PLC connectivity and line endpoints.")
        subtitle.setStyleSheet("""
            color: #9ca3af;
            font-size: 11px;
        """)

        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header_row.addLayout(title_col)
        header_row.addStretch(1)

        # rounded / modern add button
        add_btn = QPushButton("+ Add Machine")
        add_btn.setFixedHeight(36)
        add_btn.setMinimumWidth(150)
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setStyleSheet(self.add_button_style())
        add_btn.clicked.connect(self.open_add_form)
        header_row.addWidget(add_btn, 0, Qt.AlignRight | Qt.AlignVCenter)

        main_layout.addLayout(header_row)

        # ---------- SCROLL AREA (MACHINE LIST) ----------
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
        self.container_layout.setContentsMargins(0, 12, 0, 24)
        self.container_layout.setSpacing(12)
        # center cards horizontally, stack from top
        self.container_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        self.container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        scroll.setWidget(self.container)
        main_layout.addWidget(scroll)

        self.refresh_list()

    def _on_reconnect_result(self, connected: bool, msg: str):
        """Runs on MAIN thread only."""
        if connected:
            QMessageBox.information(self, "PLC Connected ", msg)
        else:
            QMessageBox.warning(self, "PLC Not Connected ", msg)

        self.refresh_list()

    # ------------------------------------------------------------
    # RENDER MACHINE LIST
    # ------------------------------------------------------------
    def refresh_list(self):
        # -------- clear the layout completely (widgets + spacers) --------
        layout = self.container_layout
        while layout.count():
            item = layout.takeAt(0)

            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
                continue

            # if it's a nested layout, clear it too
            sub_layout = item.layout()
            if sub_layout is not None:
                while sub_layout.count():
                    sub_item = sub_layout.takeAt(0)
                    sub_w = sub_item.widget()
                    if sub_w is not None:
                        sub_w.setParent(None)
                        sub_w.deleteLater()
            # QSpacerItem is handled just by letting 'item' go out of scope

        # -------- rebuild the cards --------
        machines = self.machine_db.get_all_machines()

        if not machines:
            empty_label = QLabel("No machines added yet.")
            empty_label.setStyleSheet("color: #aaa; font-size: 15px;")
            layout.addWidget(empty_label)
            return

        for m in machines:
            layout.addWidget(self.machine_card(m))

    # ------------------------------------------------------------
    # ADD BUTTON STYLE (rounded / modern)
    # ------------------------------------------------------------
    def add_button_style(self):
        return """
        QPushButton {
            background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                              stop:0 #2563eb, stop:1 #38bdf8);
            color: #ffffff;
            border: none;
            border-radius: 18px;
            padding: 0 18px;
            font-size: 13px;
            font-weight: 600;
            letter-spacing: 0.5px;
        }
        QPushButton:hover {
            background-color: #1d4ed8;
        }
        QPushButton:pressed {
            background-color: #1e40af;
        }
        """
    
    def card_reconnect_style(self):
        return """
        QPushButton {
            background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                              stop:0 #2563eb, stop:1 #38bdf8);
            color: #ffffff;
            border: none;
            border-radius: 16px;
            padding: 0 12px;   /* slightly tighter */
            font-size: 12px;
            font-weight: 600;
            letter-spacing: 0.3px;
        }
        QPushButton:hover { background-color: #1d4ed8; }
        QPushButton:pressed { background-color: #1e40af; }
        """


    # keep old name if you use it anywhere else
    def button_style(self):
        return self.add_button_style()

    # ------------------------------------------------------------
    # MACHINE CARD WIDGET
    # ------------------------------------------------------------
    def machine_card(self, m):

        card = QFrame()
        card.setObjectName("MachineCard")
        card.setStyleSheet("""
            QFrame#MachineCard {
                background-color: #0f172a;
                border: 1px solid #1f2937;
                border-radius: 16px;
            }
            QFrame#MachineCard:hover {
                background-color: #111827;
                border: 1px solid #2563eb;
            }
        """)
        card.setMinimumHeight(130)
        card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        # Main layout: Left (info) | Right (status + buttons)
        main_layout = QHBoxLayout(card)
        main_layout.setContentsMargins(22, 16, 22, 16)
        main_layout.setSpacing(18)

        # LEFT SIDE: Machine Information
        left_layout = QVBoxLayout()
        left_layout.setSpacing(6)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setAlignment(Qt.AlignTop)

        # Machine Name
        name_label = QLabel(f"{m['name']}")
        name_label.setStyleSheet("""
            color: #e5e7eb;
            font-size: 18px;
            font-weight: 700;
            padding-bottom: 2px;
            background-color: transparent;
        """)
        left_layout.addWidget(name_label)


        # PLC Information Section
        plc_container = QWidget()
        plc_layout = QVBoxLayout(plc_container)
        plc_layout.setContentsMargins(0, 0, 0, 0)
        plc_layout.setSpacing(2)

        # PLC Brand/Model/Protocol
        plc_info_parts = []
        if m.get("plc_brand"):
            plc_info_parts.append(m.get("plc_brand", ""))
        if m.get("plc_model"):
            plc_info_parts.append(m.get("plc_model", ""))
        if m.get("plc_protocol"):
            plc_info_parts.append(m.get("plc_protocol", ""))

        if plc_info_parts:
            plc_label = QLabel(" · ".join(plc_info_parts))
            plc_label.setStyleSheet("""
                color: #60a5fa;
                font-size: 13px;
                font-weight: 500;
                padding: 2px 0;
                background-color: transparent;
            """)
            plc_layout.addWidget(plc_label)

        # IP Address
        if m.get("ip_address"):
            ip_label = QLabel(f"IP: {m.get('ip_address', '')}")
            ip_label.setStyleSheet("""
                color: #6b7280;
                font-size: 12px;
                padding: 2px 0;
                background-color: transparent;
            """)
            plc_layout.addWidget(ip_label)

        if plc_info_parts or m.get("ip_address"):
            left_layout.addWidget(plc_container)

        left_layout.addStretch()
        main_layout.addLayout(left_layout, 3)

        # RIGHT SIDE: Status and Actions
        right_layout = QVBoxLayout()
        right_layout.setSpacing(10)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setAlignment(Qt.AlignTop | Qt.AlignRight)

        # -------- modern status chip --------
        is_active = bool(m.get("active"))
        status_text = "Active" if is_active else "Disabled"
        status_color = "#22c55e" if is_active else "#f97373"
        status_bg = "rgba(34,197,94,0.14)" if is_active else "rgba(248,113,113,0.14)"

        status_frame = QFrame()
        status_frame.setObjectName("StatusChip")
        status_frame.setStyleSheet(f"""
            QFrame#StatusChip {{
                background-color: {status_bg};
                border-radius: 999px;
                border: 1px solid {status_color};
            }}
        """)
        status_layout = QHBoxLayout(status_frame)
        status_layout.setContentsMargins(10, 4, 12, 4)
        status_layout.setSpacing(6)

        dot = QLabel()
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(f"background-color: {status_color}; border-radius: 4px;")

        status_label = QLabel(status_text)
        status_label.setStyleSheet(f"""
            color: {status_color};
            font-size: 11px;
            font-weight: 600;
        """)

        status_layout.addWidget(dot)
        status_layout.addWidget(status_label)

        right_layout.addWidget(status_frame, 0, Qt.AlignRight | Qt.AlignTop)

        # -------- Action Buttons --------
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        btn_reconnect = QPushButton("Reconnect PLC")
        btn_edit = QPushButton("Edit")
        btn_delete = QPushButton("Delete")

        # make them pill buttons like "+ Add Machine"
        for b in (btn_reconnect, btn_edit, btn_delete):
            b.setFixedHeight(32)
            b.setCursor(Qt.PointingHandCursor)

        # ✅ make reconnect a bit wider than others
        btn_reconnect.setMinimumWidth(135)   
        btn_edit.setMinimumWidth(110)
        btn_delete.setMinimumWidth(110) 

        btn_reconnect.setStyleSheet(self.card_reconnect_style())
        btn_edit.setStyleSheet(self.card_button())
        btn_delete.setStyleSheet(self.card_delete_button())
        btn_reconnect.clicked.connect(partial(self.reconnect_plc, m))
        btn_edit.clicked.connect(lambda: self.open_edit_form(m))
        btn_delete.clicked.connect(lambda: self.delete_machine(m))
        btn_layout.addWidget(btn_reconnect)
        btn_layout.addWidget(btn_edit)
        btn_layout.addWidget(btn_delete)
        right_layout.addLayout(btn_layout)
        right_layout.addStretch()

        main_layout.addLayout(right_layout, 1)

        return card

    def card_button(self):
        # gradient pill, matching Add Machine style (smaller)
        return """
        QPushButton {
            background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                              stop:0 #2563eb, stop:1 #38bdf8);
            color: #ffffff;
            border: none;
            border-radius: 16px;
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
        # red pill version for delete
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
    
    def reconnect_plc(self, machine: dict):

        def _worker():
            try:
                plc_brand = machine.get("plc_brand")
                plc_protocol = machine.get("plc_protocol")
                ip = machine.get("ip_address")
                slot = machine.get("slot")

                temp_machine = {
                    "plc_brand": plc_brand,
                    "plc_protocol": plc_protocol,
                    "ip_address": ip,
                    "slot": slot,
                }

                connected, msg = check_plc_and_get_active(temp_machine)

                machine_id = str(machine["_id"])
                self.machine_db.update_machine(machine_id, {"active": bool(connected)})

                # ✅ popup + refresh via signal
                self.reconnectFinished.emit(bool(connected), str(msg))

            except Exception as e:
                self.reconnectFinished.emit(False, f"Reconnect failed: {e}")

        threading.Thread(target=_worker, daemon=True).start()




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
        super().__init__(parent)
        self.machine = machine
        self.machine_db = MachineDB()
        self.result = None

        self.setWindowTitle("Edit Machine" if machine else "Add Machine")

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

        # PLC Brand
        layout.addWidget(QLabel("PLC Brand"))
        self.plc_brand_combo = QComboBox()
        self.plc_brand_combo.addItem("Select PLC Brand", None)
        self.plc_brand_combo.addItems(list(PLC_DATA.keys()))
        self.plc_brand_combo.currentTextChanged.connect(self.on_brand_changed)
        layout.addWidget(self.plc_brand_combo)

        # Model
        layout.addWidget(QLabel("Model Series"))
        self.plc_model_combo = QComboBox()
        self.plc_model_combo.addItem("Select Model", None)
        self.plc_model_combo.setEnabled(False)
        layout.addWidget(self.plc_model_combo)

        # Protocol
        layout.addWidget(QLabel("Communication Protocol"))
        self.plc_protocol_combo = QComboBox()
        self.plc_protocol_combo.addItem("Select Protocol", None)
        self.plc_protocol_combo.setEnabled(False)
        layout.addWidget(self.plc_protocol_combo)

        # IP
        layout.addWidget(QLabel("IP Address *"))
        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText("e.g., 192.168.1.100")
        layout.addWidget(self.ip_input)

        # Slot / Rack (needed for some PLCs like Allen-Bradley)
        layout.addWidget(QLabel("Slot / Rack (if applicable)"))
        self.slot_input = QLineEdit()
        self.slot_input.setPlaceholderText("e.g., 0 or 1 (Allen-Bradley usually 0)")
        layout.addWidget(self.slot_input)

        # Pre-fill when editing
        if self.machine:
            self.name_input.setText(self.machine.get("name", ""))
            self.ip_input.setText(self.machine.get("ip_address", ""))
            self.slot_input.setText(str(self.machine.get("slot", "")) if self.machine.get("slot") is not None else "")


            plc_brand = self.machine.get("plc_brand", "")
            if plc_brand:
                idx = self.plc_brand_combo.findText(plc_brand)
                if idx >= 0:
                    self.plc_brand_combo.setCurrentIndex(idx)
                    self.on_brand_changed(plc_brand)

                    plc_model = self.machine.get("plc_model", "")
                    if plc_model:
                        midx = self.plc_model_combo.findText(plc_model)
                        if midx >= 0:
                            self.plc_model_combo.setCurrentIndex(midx)

                    plc_protocol = self.machine.get("plc_protocol", "")
                    if plc_protocol:
                        pidx = self.plc_protocol_combo.findText(plc_protocol)
                        if pidx >= 0:
                            self.plc_protocol_combo.setCurrentIndex(pidx)

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
        if not brand or brand == "Select PLC Brand":
            self.plc_model_combo.clear()
            self.plc_model_combo.addItem("Select Model", None)
            self.plc_model_combo.setEnabled(False)

            self.plc_protocol_combo.clear()
            self.plc_protocol_combo.addItem("Select Protocol", None)
            self.plc_protocol_combo.setEnabled(False)
            return

        plc_info = PLC_DATA.get(brand)
        if not plc_info:
            return

        self.plc_model_combo.clear()
        self.plc_model_combo.addItem("Select Model", None)
        self.plc_model_combo.addItems(plc_info["models"])
        self.plc_model_combo.setEnabled(True)

        self.plc_protocol_combo.clear()
        self.plc_protocol_combo.addItem("Select Protocol", None)
        self.plc_protocol_combo.addItems(plc_info["protocols"])
        self.plc_protocol_combo.setEnabled(True)

    def save(self):

        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Missing", "Machine name cannot be empty")
            return

        ip_address = self.ip_input.text().strip()
        if not ip_address:
            QMessageBox.warning(self, "Missing", "IP Address is mandatory.")
            return

        slot_raw = self.slot_input.text().strip()
        slot = int(slot_raw) if slot_raw.isdigit() else None

        plc_brand = self.plc_brand_combo.currentText()
        if plc_brand == "Select PLC Brand":
            plc_brand = None

        plc_model = self.plc_model_combo.currentText()
        if plc_model == "Select Model":
            plc_model = None

        plc_protocol = self.plc_protocol_combo.currentText()
        if plc_protocol == "Select Protocol":
            plc_protocol = None

        # ---- brand-specific requirement: AB usually needs slot ----
        if plc_brand and "allen-bradley" in plc_brand.lower() and slot is None:
            QMessageBox.warning(self, "Missing", "Slot is required for Allen-Bradley PLCs.")
            return

       # ---- REAL PLC CONNECTION TEST ----
        temp_machine = {
            "plc_brand": plc_brand,
            "plc_protocol": plc_protocol,
            "ip_address": ip_address,
            "slot": slot,
        }

        connected, msg = check_plc_and_get_active(temp_machine)

        if connected:
            QMessageBox.information(self, "PLC Connected", msg)
        else:
            QMessageBox.warning(self, "PLC Not Connected", msg)


        active_status = bool(connected)

        try:
            if self.machine:
                machine_id = str(self.machine.get("_id") or self.machine.get("id"))
                update_data = {
                    "name": name,
                    "ip_address": ip_address,
                    "slot": slot,
                    "plc_brand": plc_brand,
                    "plc_model": plc_model,
                    "plc_protocol": plc_protocol,
                    "active": active_status,
                }
                # keep None out
                update_data = {k: v for k, v in update_data.items() if v is not None}

                success = self.machine_db.update_machine(machine_id, update_data)
                if success:
                    QMessageBox.information(self, "Success", "Machine updated successfully.")
                    self.result = {"success": True}
                    self.accept()
                else:
                    QMessageBox.warning(self, "Error", "Failed to update machine.")
            else:
                data = {
                    "name": name,
                    "ip_address": ip_address,
                    "slot": slot,
                    "plc_brand": plc_brand,
                    "plc_model": plc_model,
                    "plc_protocol": plc_protocol,
                    "active": active_status,
                }
                machine_id = self.machine_db.add_machine(data)
                if machine_id:
                    QMessageBox.information(
                        self, "Success",
                        "Machine added and PLC connected."
                        if active_status else
                        "Machine added but PLC not connected (marked Disabled)."
                    )
                    self.result = {"success": True}
                    self.accept()
                else:
                    QMessageBox.warning(self, "Error", "Failed to add machine.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error saving machine: {str(e)}")


    def get_result(self):
        return self.result
