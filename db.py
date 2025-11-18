# db.py
"""
Unified database module for EYRES QC.

Includes:
    - MongoDB singleton (connection, collections, indexes, default admin)
    - Database: auth / user management (login, create, forgot password)
    - ProjectDB, MachineDB wrappers for dashboard_models.*
    - Camera overrides helpers (load/save) for camera_app
"""

from typing import Dict, Tuple
import pymongo
import hashlib
from datetime import datetime

# ----------------------------------------------------------------------
# MongoDB singleton
# ----------------------------------------------------------------------


class MongoDB:
    """
    Industrial-grade MongoDB singleton.
    Handles:
        - DB connection
        - Automatic collection creation
        - Automatic index creation
        - Automatic default admin user
    """

    _instance = None

    @staticmethod
    def get_instance():
        if MongoDB._instance is None:
            MongoDB._instance = MongoDB()
        return MongoDB._instance

    def __init__(self):
        # Prevent re-init if called directly
        if hasattr(self, "_initialized") and self._initialized:
            return

        try:
            # Single client + DB for the whole suite
            self.client = pymongo.MongoClient("mongodb://localhost:27017")
            self.db = self.client["eyres_qc"]

            self._create_collections()
            self._create_indexes()
            self._create_default_users()
            self._repair_corrupted_machine_records()

            self._initialized = True

        except Exception as e:
            print("❌ MongoDB Init Error:", e)
            raise e

    # ------------ collections ------------

    def _create_collections(self):
        required = [
            "users",
            "projects",
            "machines",
            "system_logs",
            "camera_overrides",  # added for camera settings
        ]

        existing = set(self.db.list_collection_names())
        for name in required:
            if name not in existing:
                self.db.create_collection(name)
                print(f"📁 Created collection: {name}")

    # ------------ indexes ------------

    def _create_indexes(self):
        # Users
        self.db.users.create_index("username", unique=True)
        self.db.users.create_index("role")

        # Projects
        self.db.projects.create_index("name", unique=True)
        self.db.projects.create_index("machine_id")

        # Machines
        self.db.machines.create_index("name", unique=True)

        # Camera overrides
        self.db.camera_overrides.create_index(
            [("type", 1), ("key", 1)],
            unique=True,
        )

    # ------------ default admin ------------

    def _create_default_users(self):
        admin_exists = self.db.users.find_one({"username": "admin"})
        if admin_exists:
            return

        default_password = self._hash("admin123")

        admin_user = {
            "username": "admin",
            "password": default_password,
            "role": "admin",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }

        self.db.users.insert_one(admin_user)
        print("👤 Default admin created → username: admin / password: admin123")

    # ------------ utils ------------

    def _hash(self, text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

    def collection(self, name: str):
        return self.db[name]

    def _backup_machines_collection(self, path="/tmp/machines_backup.json"):
        """Optional: one-time quick backup snippet (not required, but safe)."""
        try:
            coll = self.db["machines"]
            docs = list(coll.find({}))
            import json
            from bson import json_util
            with open(path, "w", encoding="utf-8") as f:
                f.write(json_util.dumps(docs))
        except Exception as e:
            print(f"⚠️  Backup failed: {e}")

    def _repair_corrupted_machine_records(self):
        """
        Idempotent: find machines where `name` is a dict and flatten them.
        Safe to run on every app start.
        """
        try:
            coll = self.db["machines"]
        except Exception:
            return

        fixed = 0
        for doc in coll.find({}):
            name_field = doc.get("name")
            if isinstance(name_field, dict):
                # flatten nested dict into top-level fields, preserve _id
                nested = name_field.copy()
                update_fields = {}
                for k, v in nested.items():
                    # avoid accidental overwrite of _id
                    if k == "_id":
                        continue
                    update_fields[k] = v

                # pick canonical name
                canonical_name = nested.get("name") or nested.get("machine_name") or str(nested)
                update_fields["name"] = canonical_name

                # update document
                try:
                    coll.update_one({"_id": doc["_id"]}, {"$set": update_fields})
                    fixed += 1
                except Exception:
                    continue

        if fixed:
            print(f"🔧 Repaired {fixed} corrupted machine records.")


# Global singleton accessor
mongo = MongoDB.get_instance()

# ----------------------------------------------------------------------
# Auth / user management
# ----------------------------------------------------------------------


class Database:
    """
    Auth wrapper used by Login / Forgot Password UI.

    Uses MongoDB singleton above instead of creating a new client.
    """

    def __init__(self, uri="mongodb://localhost:27017", db_name="eyres_qc"):
        # Keep signature for backward compatibility, but use `mongo`
        self.db = mongo.db
        self.users = self.db["users"]

    def _hash(self, value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()

    # ----------------------- AUTH FUNCTIONS -----------------------

    def find_user(self, username: str, password: str):
        """Used by Login Window."""
        pwd_hash = self._hash(password)
        return self.users.find_one({"username": username, "password": pwd_hash})

    def user_exists(self, username: str) -> bool:
        return self.users.find_one({"username": username}) is not None

    def create_user(
        self, username: str, password: str, email: str,
        sec_question: str, sec_answer: str
    ):
        if self.user_exists(username):
            raise ValueError("Username already exists")

        self.users.insert_one({
            "username": username,
            "email": email,
            "password": self._hash(password),
            "security_question": sec_question,
            "security_answer": self._hash(sec_answer),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        })

    def get_security_question(self, username: str):
        user = self.users.find_one({"username": username})
        if user:
            return user.get("security_question")
        return None

    def verify_security_answer(self, username: str, answer: str) -> bool:
        user = self.users.find_one({"username": username})
        if not user:
            return False
        return user["security_answer"] == self._hash(answer)

    def update_password(self, username: str, new_password: str):
        self.users.update_one(
            {"username": username},
            {
                "$set": {
                    "password": self._hash(new_password),
                    "updated_at": datetime.utcnow(),
                }
            }
        )


# ----------------------------------------------------------------------
# Project / Machine wrappers
# ----------------------------------------------------------------------

# NOTE: using dashboard_models instead of models
from dashboard_models.project import Projects
from dashboard_models.machine import Machines


class ProjectDB:
    """Database wrapper for project operations."""

    def __init__(self):
        self.model = Projects

    def get_all_projects(self):
        """Get all projects from database."""
        return self.model.list_projects()

    def add_project(self, name, machine_id, description="", type=None):
        """Add a new project."""
        result = self.model.create_project(name, machine_id, description=description, type=type)
        if result.get("success"):
            return result["project"]
        return None

    def delete_project(self, project_id):
        """Delete a project by ID."""
        return self.model.delete_project(project_id)

    def get_project(self, project_id):
        """Get a project by ID."""
        return self.model.get_project(project_id)

    def update_project(self, project_id, name=None, machine_id=None, description=None, type=None):
        """Update project information."""
        data = {}
        if name is not None:
            data["name"] = name
        if machine_id is not None:
            from bson.objectid import ObjectId
            data["machine_id"] = ObjectId(machine_id)
        if description is not None:
            data["description"] = description
        if type is not None:
            data["type"] = type
        return self.model.update_project(project_id, data)


class MachineDB:
    """Database wrapper for machine operations."""

    def __init__(self):
        self.model = Machines
        self._coll = mongo.collection("machines")

    def get_all_machines(self):
        return self.model.list_machines()

    def _normalize_payload(self, payload: dict) -> dict:
        """
        Ensure payload is a flat dict with consistent field names.
        Accepts payloads created either by old UI or new UI.
        """
        p = {}
        # prefer explicit keys if present
        p["name"] = payload.get("name") or payload.get("machine_name") or payload.get("label") or None
        p["description"] = payload.get("description") or payload.get("desc") or None
        p["ip_address"] = payload.get("ip_address") or payload.get("plc_ip") or None
        p["plc_brand"] = payload.get("plc_brand") or None
        p["plc_model"] = payload.get("plc_model") or None
        p["plc_protocol"] = payload.get("plc_protocol") or None
        # default flags
        if "active" in payload:
            p["active"] = payload["active"]
        else:
            p.setdefault("active", True)
        # remove None values so model layer can fill defaults
        return {k: v for k, v in p.items() if v is not None}

    def add_machine(self, *args, **kwargs):
        """
        Accept either:
          - add_machine(name_str, plc_ip='', description='')
          - add_machine(payload_dict)
        and always write a flattened document via model.create_machine(payload).
        """
        # If first arg is a dict, treat it as payload
        if len(args) == 1 and isinstance(args[0], dict):
            payload = self._normalize_payload(args[0])
        else:
            # old signature: name, plc_ip, description (positional or kwargs)
            name = kwargs.get("name") if "name" in kwargs else (args[0] if len(args) > 0 else None)
            plc_ip = kwargs.get("plc_ip") or (args[1] if len(args) > 1 else None)
            description = kwargs.get("description") or (args[2] if len(args) > 2 else None)
            payload = self._normalize_payload({
                "name": name,
                "ip_address": plc_ip,
                "description": description
            })

        if not payload.get("name"):
            raise ValueError("Machine name is required")

        # call model layer (expects a dict payload)
        result = self.model.create_machine(payload)
        if result.get("success"):
            return result["machine"]
        return None

    def update_machine(self, machine_id, data: dict):
        """Update expects a dict payload with fields to change."""
        return self.model.update_machine(machine_id, data)

    def delete_machine(self, machine_id):
        return self.model.delete_machine(machine_id)

    def get_machine(self, machine_id):
        return self.model.get_machine(machine_id)


# ----------------------------------------------------------------------
# Camera overrides API (Arena + MVS)
# ----------------------------------------------------------------------

# ----------------------------------------------------------------------
# Camera / Mongo health check
# ----------------------------------------------------------------------

def ensure_mongo_connected() -> bool:
    """
    Simple ping using the shared MongoDB singleton.
    Returns True if MongoDB responds, False otherwise.
    """
    try:
        mongo.client.admin.command("ping")
        return True
    except Exception as e:
        print(f"[db] MongoDB ping failed: {e}")
        return False


def load_camera_overrides() -> Tuple[Dict[str, dict], Dict[int, dict]]:
    """
    Load all stored camera overrides from `camera_overrides` collection.

    Returns:
        (arena_overrides, mvs_overrides)
        arena_overrides: {serial(str): {...}}
        mvs_overrides:   {index(int): {...}}
    """
    arena_overrides: Dict[str, dict] = {}
    mvs_overrides: Dict[int, dict] = {}

    try:
        coll = mongo.collection("camera_overrides")
    except Exception as e:
        print(f"[db] load_camera_overrides: cannot access collection: {e}")
        return arena_overrides, mvs_overrides

    try:
        for doc in coll.find({}):
            t = doc.get("type")
            key = doc.get("key")
            ov = doc.get("overrides") or {}

            if t == "arena" and key is not None:
                arena_overrides[str(key)] = ov
            elif t == "mvs" and key is not None:
                try:
                    mvs_overrides[int(key)] = ov
                except (TypeError, ValueError):
                    continue
    except Exception as e:
        print(f"[db] load_camera_overrides: error while reading: {e}")

    return arena_overrides, mvs_overrides


def save_camera_overrides(
    arena_overrides: Dict[str, dict],
    mvs_overrides: Dict[int, dict],
) -> None:
    """
    Persist current overrides into MongoDB:

    Collection: `camera_overrides`
    Docs: {type: 'arena'|'mvs', key: serial|index, overrides: {...}, updated_at: datetime}
    """
    try:
        coll = mongo.collection("camera_overrides")
    except Exception as e:
        print(f"[db] save_camera_overrides: cannot access collection: {e}")
        return

    now = datetime.utcnow()

    # Save Arena overrides
    for serial, ov in (arena_overrides or {}).items():
        try:
            coll.update_one(
                {"type": "arena", "key": str(serial)},
                {"$set": {"overrides": ov, "updated_at": now}},
                upsert=True,
            )
        except Exception as e:
            print(f"[db] save_camera_overrides: arena[{serial}] failed: {e}")

    # Save MVS overrides
    for idx, ov in (mvs_overrides or {}).items():
        try:
            coll.update_one(
                {"type": "mvs", "key": str(idx)},
                {"$set": {"overrides": ov, "updated_at": now}},
                upsert=True,
            )
        except Exception as e:
            print(f"[db] save_camera_overrides: mvs[{idx}] failed: {e}")
