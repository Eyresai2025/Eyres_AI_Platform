# login_window.py
# Login UI for EYRES QC project

from PyQt5.QtWidgets import (
    QWidget,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QMessageBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
)

from PyQt5.QtGui import QPixmap,QIcon
from PyQt5.QtCore import Qt
from db import Database
from pathlib import Path
import sys, os, importlib

def _app_base_dir() -> Path:
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def _find_logo() -> Path | None:
    media = _app_base_dir() / "Media"
    if not media.exists():
        return None
    for name in ("EYRES QC.png","EYRES QC Black.png","EYRES QC LOGO MARK.png"):
        p = media / name
        if p.is_file():
            return p
    for ext in ("*.png", "*.jpg", "*.jpeg", "*.bmp", "*.gif", "*.webp"):
        files = list(media.glob(ext))
        if files:
            return files[0]
    return None


class SignupDialog(QDialog):
    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db

        self.setWindowTitle("Create Account")
        self.setFixedSize(420, 440)
        self.setStyleSheet("background-color:#111; color:white;")

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel("Create New Account")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size:20px; font-weight:bold;")
        layout.addWidget(title)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)

        self.ed_username = QLineEdit()
        self.ed_email = QLineEdit()
        self.ed_password = QLineEdit()
        self.ed_confirm = QLineEdit()
        self.ed_question = QLineEdit()
        self.ed_answer = QLineEdit()

        self.ed_password.setEchoMode(QLineEdit.Password)
        self.ed_confirm.setEchoMode(QLineEdit.Password)
        self.ed_answer.setEchoMode(QLineEdit.Password)

        form.addRow("Username:", self.ed_username)
        form.addRow("Email:", self.ed_email)
        form.addRow("Password:", self.ed_password)
        form.addRow("Confirm:", self.ed_confirm)
        form.addRow("Security Question:", self.ed_question)
        form.addRow("Answer:", self.ed_answer)

        layout.addLayout(form)

        btn = QPushButton("Create Account")
        btn.setStyleSheet("background:#1B5FCC; padding:10px; font-weight:bold;")
        btn.clicked.connect(self.handle_signup)
        layout.addWidget(btn)

    def handle_signup(self):
        username = self.ed_username.text().strip()
        email = self.ed_email.text().strip()
        pwd = self.ed_password.text().strip()
        cpwd = self.ed_confirm.text().strip()
        q = self.ed_question.text().strip()
        ans = self.ed_answer.text().strip()

        if not username or not pwd or not q or not ans:
            QMessageBox.warning(self, "Error", "All fields except email are required.")
            return

        if pwd != cpwd:
            QMessageBox.warning(self, "Error", "Passwords do not match.")
            return

        try:
            self.db.create_user(username, pwd, email, q, ans)
            QMessageBox.information(self, "Success", "Account created successfully!")
            self.accept()
        except ValueError as e:
            QMessageBox.warning(self, "Error", str(e))

class ForgotPasswordDialog(QDialog):
    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db

        self.setWindowTitle("Reset Password")
        self.setFixedSize(420, 300)
        self.setStyleSheet("background:#111; color:white;")

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        self.ed_username = QLineEdit()
        self.ed_username.setPlaceholderText("Enter username")

        btn_fetch = QPushButton("Next")
        btn_fetch.clicked.connect(self.fetch_question)

        layout.addWidget(self.ed_username)
        layout.addWidget(btn_fetch)

        self.stage2 = QWidget()
        layout2 = QFormLayout(self.stage2)

        self.lbl_question = QLabel("")
        self.ed_answer = QLineEdit()
        self.ed_newpass = QLineEdit()

        self.ed_answer.setEchoMode(QLineEdit.Password)
        self.ed_newpass.setEchoMode(QLineEdit.Password)

        layout2.addRow("Security Q:", self.lbl_question)
        layout2.addRow("Answer:", self.ed_answer)
        layout2.addRow("New Password:", self.ed_newpass)

        self.btn_reset = QPushButton("Reset Password")
        self.btn_reset.clicked.connect(self.reset_pass)

        layout2.addWidget(self.btn_reset)
        self.stage2.hide()
        layout.addWidget(self.stage2)

    def fetch_question(self):
        username = self.ed_username.text().strip()
        q = self.db.get_security_question(username)
        if not q:
            QMessageBox.warning(self, "Error", "Username not found.")
            return

        self.lbl_question.setText(q)
        self.stage2.show()

    def reset_pass(self):
        username = self.ed_username.text().strip()
        ans = self.ed_answer.text().strip()
        newpwd = self.ed_newpass.text().strip()

        if not self.db.verify_security_answer(username, ans):
            QMessageBox.warning(self, "Error", "Incorrect security answer.")
            return

        self.db.update_password(username, newpwd)
        QMessageBox.information(self, "Success", "Password updated!")
        self.accept()


class LoginWindow(QWidget):
    def __init__(self, on_login_success=None):
        super().__init__()
        self.db = Database()
        self.on_login_success = on_login_success
        self.setWindowTitle("EYRES QC - Login")
        # ---- Window icon ----
        icon_path = _app_base_dir() / "Media" / "app.ico"
        if icon_path.is_file():
            self.setWindowIcon(QIcon(str(icon_path)))

        # self.setFixedSize(450, 450)  # Increased height to accommodate logo
        self.resize(600, 500)
        self.setStyleSheet("background-color: #111;")
        self.build_ui()
    
    def open_signup(self):
        dlg = SignupDialog(self.db, self)
        dlg.exec_()

    def open_forgot_password(self):
        dlg = ForgotPasswordDialog(self.db, self)
        dlg.exec_()

    def build_ui(self):
        # Outer layout: full screen, dark background
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Wrapper to keep content centered
        center_wrapper = QWidget(self)
        center_layout = QVBoxLayout(center_wrapper)
        center_layout.setAlignment(Qt.AlignCenter)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)

        # Card that holds the form
        card = QWidget(center_wrapper)
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(12)
        card_layout.setContentsMargins(30, 24, 30, 24)

        # Good width for this style on 1080p
        card.setFixedWidth(460)

        # ---------- LOGO (image OR text fallback) ----------
        logo_widget = QLabel()
        logo_widget.setAlignment(Qt.AlignCenter)

        pm = None
        logo_path = _find_logo()
        if logo_path is not None:
            pm = QPixmap(str(logo_path))

        if pm is not None and not pm.isNull():
            # Bigger logo when image is available
            pm = pm.scaled(128, 128, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            logo_widget.setPixmap(pm)
        else:
            # Fallback text when logo image is missing
            logo_widget.setText("EYRES QC")
            logo_widget.setStyleSheet("""
                QLabel {
                    color: #2E86FF;
                    font-size: 32px;
                    font-weight: 900;
                }
            """)

        card_layout.addWidget(logo_widget)

        # --- Login title only ---
        title = QLabel("Login")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("""
            QLabel {
                color: #ffffff;
                font-size: 22px;
                font-weight: 800;
                margin-top: 4px;
            }
        """)
        card_layout.addWidget(title)
        card_layout.addSpacing(10)

        # --- Username ---
        self.username = QLineEdit()
        self.username.setPlaceholderText("Username")
        self.username.setMinimumHeight(38)
        self.username.setStyleSheet("""
            QLineEdit {
                padding: 10px;
                border-radius: 6px;
                background-color: #2a2a2a;
                border: 1px solid #333;
                color: white;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 1px solid #1B5FCC;
            }
        """)
        card_layout.addWidget(self.username)

        # --- Password ---
        self.password = QLineEdit()
        self.password.setPlaceholderText("Password")
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setMinimumHeight(38)
        self.password.setStyleSheet("""
            QLineEdit {
                padding: 10px;
                border-radius: 6px;
                background-color: #2a2a2a;
                border: 1px solid #333;
                color: white;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 1px solid #1B5FCC;
            }
        """)
        card_layout.addWidget(self.password)

        # --- Login button ---
        login_btn = QPushButton("Login")
        login_btn.setMinimumHeight(40)
        login_btn.setStyleSheet("""
            QPushButton {
                background-color: #1B5FCC;
                color: white;
                padding: 10px;
                border-radius: 6px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2E86FF;
            }
        """)
        login_btn.clicked.connect(self.try_login)
        card_layout.addWidget(login_btn)

        # Enter key triggers login
        self.password.returnPressed.connect(self.try_login)

        card_layout.addSpacing(6)

        # --- Bottom links row (Create / Forgot) ---
        links_row = QWidget(card)
        links_layout = QHBoxLayout(links_row)
        links_layout.setContentsMargins(0, 0, 0, 0)
        links_layout.setSpacing(16)

        self.signup_link = QPushButton("Create Account")
        self.signup_link.setFlat(True)
        self.signup_link.setCursor(Qt.PointingHandCursor)
        self.signup_link.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #2E86FF;
                border: none;
                font-size: 13px;
            }
            QPushButton:hover {
                text-decoration: underline;
            }
        """)
        self.signup_link.clicked.connect(self.open_signup)

        self.forgot_link = QPushButton("Forgot Password?")
        self.forgot_link.setFlat(True)
        self.forgot_link.setCursor(Qt.PointingHandCursor)
        self.forgot_link.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #2E86FF;
                border: none;
                font-size: 13px;
            }
            QPushButton:hover {
                text-decoration: underline;
            }
        """)
        self.forgot_link.clicked.connect(self.open_forgot_password)

        links_layout.addWidget(self.signup_link, 0, Qt.AlignLeft)
        links_layout.addWidget(self.forgot_link, 0, Qt.AlignRight)
        card_layout.addWidget(links_row)

        # Put card into center wrapper, wrapper into main layout
        center_layout.addWidget(card)
        main_layout.addWidget(center_wrapper)



    def try_login(self):
        """Attempt to login user."""
        username = self.username.text().strip()
        password = self.password.text().strip()

        if not username or not password:
            QMessageBox.warning(self, "Error", "Please enter username and password")
            return

        user = self.db.find_user(username, password)
        if not user:
            QMessageBox.warning(self, "Error", "Invalid username or password")
            return

        # Call callback AFTER ensuring user is authenticated
        # The callback will create MainWindow BEFORE closing this window
        if self.on_login_success:
            # Pass control to AppController which will handle window lifecycle safely
            self.on_login_success(user)
        else:
            QMessageBox.information(self, "Success", f"Welcome, {username}!")

