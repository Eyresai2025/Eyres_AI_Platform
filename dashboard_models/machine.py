# src/models/machine.py

from datetime import datetime
from bson.objectid import ObjectId
from db import mongo



class MachineModel:
    """
    Machine = logical PLC unit
    UI will call it 'Machine', internally we store PLC information.

    One machine can have multiple projects.
    """

    def __init__(self):
        self.collection = mongo.collection("machines")

    # --------------------------------------------------------
    # Create Machine
    # --------------------------------------------------------
    def create_machine(self, name, plc_ip="", plc_port=0, description=""):
        if not name:
            return {"success": False, "error": "Machine name is required"}

        machine = {
            "name": name,
            "plc_ip": plc_ip,               # Future Phase 2: PLC read/write
            "plc_port": plc_port,
            "description": description,
            "active": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }

        result = self.collection.insert_one(machine)
        machine["_id"] = result.inserted_id

        return {"success": True, "machine": machine}

    # --------------------------------------------------------
    # Update machine
    # --------------------------------------------------------
    def update_machine(self, machine_id, data: dict):
        try:
            mid = ObjectId(machine_id)
        except:
            return False

        data["updated_at"] = datetime.utcnow()

        result = self.collection.update_one(
            {"_id": mid},
            {"$set": data}
        )

        return result.modified_count > 0

    # --------------------------------------------------------
    # Delete machine
    # --------------------------------------------------------
    def delete_machine(self, machine_id):
        try:
            mid = ObjectId(machine_id)
        except:
            return False

        result = self.collection.delete_one({"_id": mid})
        return result.deleted_count > 0

    # --------------------------------------------------------
    # Get machine by ID
    # --------------------------------------------------------
    def get_machine(self, machine_id):
        try:
            return self.collection.find_one({"_id": ObjectId(machine_id)})
        except:
            return None

    # --------------------------------------------------------
    # List all machines
    # --------------------------------------------------------
    def list_machines(self):
        return list(self.collection.find().sort("created_at", -1))

    # --------------------------------------------------------
    # Enable/Disable machine (soft toggle)
    # --------------------------------------------------------
    def set_active_status(self, machine_id, state: bool):
        try:
            mid = ObjectId(machine_id)
        except:
            return False

        result = self.collection.update_one(
            {"_id": mid},
            {"$set": {"active": state, "updated_at": datetime.utcnow()}}
        )
        return result.modified_count > 0


# ------------------------------------------------------------
# Export instance
# ------------------------------------------------------------
Machines = MachineModel()

