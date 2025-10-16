# app_prefs.py
from __future__ import annotations
import json, os, tempfile, base64
from typing import Any, Dict
from PyQt5.QtCore import QStandardPaths, QByteArray

APP_DIR_NAME = "AI-Model-Training-Suite" 

def _app_data_dir() -> str:
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    # Fallback if QStandardPaths returns empty (rare on some systems)
    if not base:
        base = os.path.expanduser("~/.config")
    path = os.path.join(base, APP_DIR_NAME)
    os.makedirs(path, exist_ok=True)
    return path

def _prefs_path() -> str:
    return os.path.join(_app_data_dir(), "session.json")

def _atomic_write(path: str, data: str) -> None:
    """Write data atomically to avoid corruption on crash."""
    d = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(prefix=".tmp_", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data)
        os.replace(tmp, path)
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass

class AppPrefs:
    """Tiny JSON-backed preference store with typed helpers."""
    def __init__(self):
        self._path = _prefs_path()
        self._data: Dict[str, Any] = {}
        self.load()

    # ---------- core load/save ----------
    def load(self) -> None:
        try:
            if os.path.exists(self._path):
                with open(self._path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            else:
                self._data = {}
        except Exception:
            # Corrupt or unreadable: start fresh (don’t crash the app)
            self._data = {}

    def save(self) -> None:
        try:
            _atomic_write(self._path, json.dumps(self._data, indent=2))
        except Exception:
            pass

    # ---------- generic get/set ----------
    def get(self, key: str, default: Any=None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    # ---------- typed helpers ----------
    # window geometry/state (QByteArray -> base64 string)
    def set_geometry(self, ba: QByteArray) -> None:
        if isinstance(ba, QByteArray):
            self._data["window_geometry_b64"] = base64.b64encode(bytes(ba)).decode("ascii")

    def get_geometry(self) -> QByteArray:
        b64 = self._data.get("window_geometry_b64")
        if not b64:
            return QByteArray()
        try:
            return QByteArray(base64.b64decode(b64))
        except Exception:
            return QByteArray()

    def set_win_state(self, ba: QByteArray) -> None:
        if isinstance(ba, QByteArray):
            self._data["window_state_b64"] = base64.b64encode(bytes(ba)).decode("ascii")

    def get_win_state(self) -> QByteArray:
        b64 = self._data.get("window_state_b64")
        if not b64:
            return QByteArray()
        try:
            return QByteArray(base64.b64decode(b64))
        except Exception:
            return QByteArray()

    # last tool index (int)
    def set_last_tool_index(self, idx: int) -> None:
        self._data["last_tool_index"] = int(idx)

    def get_last_tool_index(self, default: int=0) -> int:
        try:
            return int(self._data.get("last_tool_index", default))
        except Exception:
            return default

    # maximized flag (bool)
    def set_maximized(self, maximized: bool) -> None:
        self._data["maximized"] = bool(maximized)

    def get_maximized(self, default: bool=False) -> bool:
        v = self._data.get("maximized", default)
        return bool(v)
