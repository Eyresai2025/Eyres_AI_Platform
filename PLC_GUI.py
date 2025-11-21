# plc_data_monitor.py
import sys, csv, re, threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from PyQt5.QtWidgets import QSizePolicy
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QLineEdit, QSpinBox, QGroupBox, QTextEdit, QProgressBar,
    QHeaderView, QSplitter, QFileDialog, QMessageBox, QTabWidget, QCheckBox, QScrollArea,
    QListWidget, QAbstractItemView
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import QTimer, Qt, pyqtSignal, QThread
import pymongo
from pylogix import PLC
import random
from types import SimpleNamespace



# ----------------------- PLC Worker -----------------------
class PLCWorker(QThread):
    data_received   = pyqtSignal(dict)
    status_signal   = pyqtSignal(str)
    error_signal    = pyqtSignal(str)
    tags_retrieved  = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.plc: Optional[PLC] = None
        self.ip_address = "192.168.1.1"
        self.slot = 0
        self.tags_to_read: List[str] = []
        self.is_reading = False
        self.read_interval = 1000
        self.batch_size = 50
        # --- simulation mode ---
        self.simulation = False
        self.sim_counter = 0
    
    def _fake_value_for_tag(self, tag: str, step: int):
        """
        Simple dummy pattern so values change every cycle.
        You can customize this.
        """
        # digital-ish tags:
        if tag.lower().startswith(("di_", "do_")):
            return step % 2  # 0 / 1 toggling

        # analog-ish tags:
        base = (hash(tag) % 100)  # stable per tag
        jitter = (step % 10)
        return base + jitter


    def connect_plc(self, ip: str, slot: int):
        try:
            self.ip_address = ip
            self.slot = slot

            self.plc = PLC()
            self.plc.IPAddress = ip
            self.plc.ProcessorSlot = slot

            result = self.plc.GetPLCTime()
            if result.Status == "Success":
                self.simulation = False
                self.status_signal.emit(f"Connected to PLC at {ip}")
                return True
            else:
                # ---- SIM fallback ----
                self.plc = None
                self.simulation = True
                self.error_signal.emit(f"PLC connection failed: {result.Status}")
                self.status_signal.emit("→ Switching to SIMULATION mode (dummy PLC data).")
                return False

        except Exception as e:
            # ---- SIM fallback ----
            self.plc = None
            self.simulation = True
            self.error_signal.emit(f"Connection error: {str(e)}")
            self.status_signal.emit("→ Switching to SIMULATION mode (dummy PLC data).")
            return False


    def _start_simulation(self, reason: str):
        """Enable dummy-PLC mode."""
        self.simulation = True
        self.plc = None
        self.sim_counter = 0
        self.status_signal.emit(
            f"{reason}\n→ Switching to SIMULATION mode (dummy PLC data)."
        )


    def get_all_tags(self):
        try:
            if self.simulation:
                # generate some fake tags
                fake_tags = [f"SimTag{i}" for i in range(1, 51)]
                self.tags_retrieved.emit(fake_tags)
                self.status_signal.emit(f"SIM: generated {len(fake_tags)} fake tags")
                return

            if not self.plc:
                self.error_signal.emit("Not connected to PLC")
                return

            tags = self.plc.GetTagList()
            if tags.Status == "Success":
                tag_names = [tag.TagName for tag in tags.Value]
                self.tags_retrieved.emit(tag_names)
                self.status_signal.emit(f"Retrieved {len(tag_names)} tags")
            else:
                self.error_signal.emit(f"Failed to get tags: {tags.Status}")
        except Exception as e:
            if self.simulation:
                # should not really come here in sim mode
                self.error_signal.emit(f"SIM get_all_tags error: {str(e)}")
            else:
                self.error_signal.emit(f"Error getting tags: {str(e)}")

    def start_reading(self, tags: List[str], interval: int, batch_size: int):
        self.tags_to_read = list(tags)
        self.read_interval = interval
        self.batch_size = max(1, int(batch_size))
        self.is_reading = True
        self.status_signal.emit(
            f"Started reading {len(tags)} tags every {interval}ms (batch={self.batch_size})"
        )

    def stop_reading(self):
        self.is_reading = False
        self.status_signal.emit("Stopped reading")

    def read_one(self, tag: str):
        try:
            if self.simulation:
                # pretend any tag is readable
                self.sim_counter += 1
                return SimpleNamespace(
                    TagName=tag,
                    Value=self._fake_value_for_tag(tag, self.sim_counter),
                    Status="Success",
                )

            if not self.plc:
                return None
            return self.plc.Read(tag)
        except Exception:
            return None


    def read_single_cycle(self, tags: List[str]):
        try:
            # --- SIMULATION MODE ---
            if self.simulation:
                self.sim_counter += 1
                data = {'timestamp': datetime.now(), 'values': {}}
                for t in tags:
                    data['values'][t] = self._fake_value_for_tag(t, self.sim_counter)
                self.data_received.emit(data)
                return

            # --- REAL PLC MODE ---
            if not self.plc:
                self.error_signal.emit("Not connected to PLC")
                return

            data = {'timestamp': datetime.now(), 'values': {}}
            bs = max(1, int(self.batch_size))
            for i in range(0, len(tags), bs):
                chunk = tags[i:i + bs]
                try:
                    results = self.plc.Read(chunk)  # list read
                    if not isinstance(results, list):
                        results = [results]
                    for r in results:
                        tagname = getattr(r, 'TagName', None)
                        if not tagname:
                            continue
                        if r.Status == "Success":
                            data['values'][tagname] = r.Value
                        else:
                            data['values'][tagname] = f"Error:{r.Status}"
                except Exception as e:
                    for t in chunk:
                        data['values'][t] = f"Error:{type(e).__name__}"
            self.data_received.emit(data)
        except Exception as e:
            self.error_signal.emit(f"Read error: {str(e)}")

    def read_sim_cycle(self, tags: List[str]):
        """Emit fake values for SIM mode."""
        from random import random, randint, choice

        self.sim_counter += 1
        data = {'timestamp': datetime.now(), 'values': {}}

        for t in tags:
            tl = t.lower()
            if tl.startswith("di_") or tl.startswith("do_") or tl.endswith(".x"):
                val = choice([0, 1])  # bits
            elif tl.startswith("ai_") or "temp" in tl or "pressure" in tl or "level" in tl:
                val = round(10 + random() * 90, 2)  # floats
            else:
                val = randint(0, 100)  # generic ints

            data['values'][t] = val

        self.data_received.emit(data)


    def run(self):
        while True:
            if self.is_reading and self.tags_to_read:
                if self.simulation or not self.plc:
                    self.read_sim_cycle(self.tags_to_read)
                else:
                    self.read_single_cycle(self.tags_to_read)

                self.msleep(self.read_interval)
            else:
                self.msleep(100)

# ----------------------- Mongo / Storage -----------------------
class MongoDBHandler:
    def __init__(self, connection_string: str = "mongodb://localhost:27017/"):
        self.connection_string = connection_string
        self.client = None
        self.db = None
        self.collection = None

    def connect(self, db_name: str = "plc_data", collection_name: str = "readings"):
        try:
            self.client = pymongo.MongoClient(self.connection_string)
            self.db = self.client[db_name]
            self.collection = self.db[collection_name]
            return True
        except Exception as e:
            print(f"MongoDB connection error: {e}")
            return False

    def insert_data(self, data: Dict):
        try:
            if self.collection:
                d = data.copy()
                d['timestamp'] = data['timestamp'].isoformat()
                self.collection.insert_one(d)
                return True
        except Exception as e:
            print(f"MongoDB insert error: {e}")
            return False

    def close(self):
        if self.client:
            self.client.close()


class DataStorage:
    def __init__(self):
        self.csv_file = None
        self.csv_writer = None
        self.mongo_handler = None
        self.use_csv = True
        self.use_mongo = False
        self.current_display_tags: List[str] = []  # display headers
        self.display_to_plc: Dict[str, Optional[str]] = {}

    def setup_csv(self, filename: str):
        try:
            self.csv_file = open(filename, 'w', newline='', encoding='utf-8')
            self.csv_writer = csv.writer(self.csv_file, quoting=csv.QUOTE_ALL, escapechar='\\')
            return True
        except Exception as e:
            print(f"CSV setup error: {e}")
            return False

    def setup_mongo(self, connection_string: str, db_name: str, collection_name: str):
        self.mongo_handler = MongoDBHandler(connection_string)
        return self.mongo_handler.connect(db_name, collection_name)

    def write_headers(self):
        if self.csv_writer and self.csv_file:
            headers = ['timestamp'] + self.current_display_tags
            self.csv_writer.writerow(headers)
            self.csv_file.flush()

    def store_data(self, timestamp: datetime, values_by_plc: Dict[str, object]):
        if self.use_csv and self.csv_writer:
            try:
                row = [timestamp.isoformat()]
                for disp in self.current_display_tags:
                    plc = self.display_to_plc.get(disp)
                    val = '' if plc is None else values_by_plc.get(plc, '')
                    row.append(self._clean_for_csv(val))
                self.csv_writer.writerow(row)
                self.csv_file.flush()
            except Exception as e:
                print(f"CSV write error: {e}")

        if self.use_mongo and self.mongo_handler:
            try:
                doc = {'timestamp': timestamp.isoformat()}
                for disp in self.current_display_tags:
                    plc = self.display_to_plc.get(disp)
                    doc[disp] = None if plc is None else values_by_plc.get(plc, None)
                self.mongo_handler.insert_data(doc)
            except Exception as e:
                print(f"MongoDB insert error: {e}")

    def _clean_for_csv(self, value):
        if value is None:
            return ''
        if isinstance(value, bytes):
            try:
                try: return value.decode('utf-8', errors='ignore').strip()
                except: return value.hex()
            except:
                return 'BINARY_DATA'
        try:
            s = str(value)
            repl = {',': ';','"': "'",'\n': ' ','\r': ' ','\t':' ','\0':'','\\':'/'}
            for a,b in repl.items(): s = s.replace(a,b)
            if len(s) > 1000: s = s[:1000] + "...(truncated)"
            return s
        except Exception:
            return f"ERROR:{type(value).__name__}"

    def close(self):
        if self.csv_file:
            self.csv_file.close()
        if self.mongo_handler:
            self.mongo_handler.close()


# ----------------------- Main Window -----------------------
class ModernPLCWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.plc_worker = PLCWorker()
        self.data_storage = DataStorage()
        self.cached_all_tags = [] 

        # UI state
        self.available_tags: List[str] = []               # from PLC
        self.display_tags: List[str] = []                 # what you asked for (headers)
        self.display_to_plc: Dict[str, Optional[str]] = {}# display -> real plc name or None
        self.read_tags: List[str] = []                    # dedup list actually read
        self.is_connected = False
        self.is_reading = False
        self.records_count = 0

        # ---- SPECIFIC TAGS (your list) ----
        # ---- SPECIFIC TAGS (full list) ----
        self.specific_tags = [
            # --------- AI ---------
            "ai_C_HydOil_LevelPV","ai_C_MainPanel_TempPV","ai_C_TBOPanel_TempPV","ai_Hydraulic_oil_Temp",
            "ai_LH_Guide_Rod1_Pos","ai_LH_Guide_Rod2_Pos","ai_LH_Humidity_Sensor","ai_LH_Jacket_Drain_TempPV",
            "ai_LH_Loader_LVDT","ai_LH_PCI_Bead_Lift","ai_LH_PCI_Green_Pressure","ai_LH_PCI_Yellow_Pressure",
            "ai_LH_Platen_Drain_Temp_PV","ai_LH_Press_IntPressurePV","ai_LH_Press_IntTempPV","ai_LH_Press_LVDT",
            "ai_LH_Press_ShapingPV","ai_LH_Pump_PressurePV","ai_LH_Rio_Box_Temp","ai_LH_SQ_PT",
            "ai_LH_TBLBox_TempPV","ai_LH_TBPLBox_TempPV","ai_LH_UnLoader_LVDT","ai_RH_Guide_Rod1_Pos",
            "ai_RH_Guide_Rod2_Pos","ai_RH_Humidity_Sensor","ai_RH_Jacket_Drain_TempPV","ai_RH_Loader_LVDT",
            "ai_RH_PCI_Bead_Lift","ai_RH_PCI_Green_Pressure","ai_RH_PCI_Yellow_Pressure","ai_RH_Platen_Drain_Temp_PV",
            "ai_RH_Press_IntPressurePV","ai_RH_Press_IntTempPV","ai_RH_Press_LVDT","ai_RH_Press_ShapingPV",
            "ai_RH_Pump_PressurePV","ai_RH_Rio_Box_Temp","ai_RH_SQ_PT","ai_RH_TBLBox_TempPV",
            "ai_RH_TBPLBox_TempPV","ai_RH_UnLoader_LVDT",
            # --------- AO ---------
            "ao_LH_BSP_Platen","ao_LH_HydPumpPressure_CV","ao_LH_Internal_HPS_CV","ao_LH_JacketHeatingSteam_CV",
            "ao_LH_Loader_UpDown_CV","ao_LH_PlatenHeatingSteam_CV","ao_LH_Platen_Bottom","ao_LH_Press_UpDown_CV",
            "ao_LH_Shaping_CV","ao_LH_TopRing_UpDown_CV","ao_LH_Unloader_UpDown_CV","ao_RH_BSP_Platen",
            "ao_RH_HydPumpPressure_CV","ao_RH_Internal_HPS_CV","ao_RH_JacketHeatingSteam_CV","ao_RH_Loader_UpDown_CV",
            "ao_RH_PlatenHeatingSteam_CV","ao_RH_Platen_Bottom","ao_RH_Press_UpDown_CV","ao_RH_Shaping_CV",
            "ao_RH_TopRing_UpDown_CV","ao_RH_Unloader_UpDown_CV",
            # --------- DI ---------
            "di_C_24DC_MCB_trip","di_C_Auto_Shaping","di_C_Auto_Vaccum","di_C_CoolingOil_Filter",
            "di_C_EStop_Enable_FB","di_C_LampAndFan_MCB_Trip","di_C_LampAndFan_RCCB_MCB_Trip","di_C_OilCoolingPump_MPCB_Trip",
            "di_C_PanelDoorSwitchOn","di_C_PhaseSequnece_and_Loss_Detector","di_C_PumpMotor_MPCB_Trip","di_C_Reset",
            "di_LH_Bayonut_Unlock_SSW","di_LH_Bayonut_lock_SSW","di_LH_BeadWidth_adj_Dec_SSW","di_LH_BeadWidth_adj_Homing",
            "di_LH_BeadWidth_adj_Inc_SSW","di_LH_BeadWidth_adj_Over_Travel","di_LH_BeadWidth_adj_Teeth_Counter",
            "di_LH_C_PressureLine_Filter","di_LH_C_ReturnLine_Filter","di_LH_Conveyor_Motor_MPCB_Trip","di_LH_Conveyor_On",
            "di_LH_CureEnable_FB","di_LH_GTH_InPosition_FB","di_LH_GTH_TyreSensor","di_LH_LoaderChuck_Close_FB",
            "di_LH_LoaderChuck_Open_FB","di_LH_LoaderChuck_Open_PS","di_LH_Loader_Enable_FB","di_LH_Loader_GT_Sensor",
            "di_LH_Loader_Inside_Press_FB","di_LH_Loader_Outside_Press_FB","di_LH_Loader_Overtravel","di_LH_Loader_Tyre_Sensing_2",
            "di_LH_LowerRing_Down_FB","di_LH_LowerRing_Up_FB","di_LH_MainInletAirOn_PS","di_LH_PCI_Auto_SSW",
            "di_LH_PCI_Bayonut_Lock","di_LH_PCI_Bayonut_Lock1_MovingPart","di_LH_PCI_Bayonut_UnLock1_MovingPart","di_LH_PCI_Bayonut_Unlock",
            "di_LH_PCI_Deflation_Green_SSW","di_LH_PCI_Deflation_Yellow_SSW","di_LH_PCI_Enable_FB","di_LH_PCI_FaultReset_PB",
            "di_LH_PCI_Inflation_Green_SSW","di_LH_PCI_Inflation_Yellow_SSW","di_LH_PCI_Manual_SSW","di_LH_PCI_RimClose_SSW",
            "di_LH_PCI_RimOpen_SSW","di_LH_PCI_Rotation_Green","di_LH_PCI_Rotation_Green_SSW","di_LH_PCI_Rotation_Yellow",
            "di_LH_PCI_Rotation_Yellow_SSW","di_LH_PCI_Tire_Detect_PHS","di_LH_PciRim_BeadWidth_adj_Motor_Trip","di_LH_Press_Auto_Mode",
            "di_LH_Press_Enable_FB","di_LH_Press_MC_Mode","di_LH_Press_Manual_Mode","di_LH_Press_Unlocked_FB1",
            "di_LH_Press_Unlocked_FB2","di_LH_RimFullup_Lock_Unlock","di_LH_Rotation_Manual_lock","di_LH_SMO_Extend_FB",
            "di_LH_SMO_Lock_FB","di_LH_SMO_Retract_FB","di_LH_SMO_Unlock_FB","di_LH_TBL24DC_MCB_Trip",
            "di_LH_UnLoader_Intermediate","di_LH_UnloaderChuck_Close_FB","di_LH_UnloaderChuck_Open_FB","di_LH_UnloaderChuck_Open_PS",
            "di_LH_Unloader_Close_Ssw","di_LH_Unloader_Down_SSW","di_LH_Unloader_Enable_FB","di_LH_Unloader_In_Ssw",
            "di_LH_Unloader_Open_SSW","di_LH_Unloader_Out_Ssw","di_LH_Unloader_PCI_In_FB","di_LH_Unloader_Pci_SSW",
            "di_LH_Unloader_PressIn_FB","di_LH_Unloader_PressOut_FB","di_LH_Unloader_Press_SSW","di_LH_Unloader_TyreSensor",
            "di_LH_Unloader_Up_SSW","di_Load_Enable","di_RH_Bayonut_Lock_SSW","di_RH_Bayonut_Unlock_SSW",
            "di_RH_BeadWidth_adj_Homing","di_RH_BeadWidth_adj_Over_travel","di_RH_BeadWidth_adj_teeth_counter","di_RH_C_PressureLine_Filter",
            "di_RH_C_ReturnLine_Filter","di_RH_Conveyor_On","di_RH_CureEnable_FB","di_RH_GTH_InPosition_FB",
            "di_RH_GTH_TyreSensor","di_RH_LoaderChuck_Close_FB","di_RH_LoaderChuck_Open_FB","di_RH_LoaderChuck_Open_PS",
            "di_RH_Loader_Enable_FB","di_RH_Loader_GT_Sensor","di_RH_Loader_Inside_Press_FB","di_RH_Loader_Outside_Press_FB",
            "di_RH_Loader_Overtravel","di_RH_Loader_Tyre_Sensing_2","di_RH_LowerRing_Down_FB","di_RH_LowerRing_Up_FB",
            "di_RH_MainInletAirOn_PS","di_RH_PCI_Auto_SSW","di_RH_PCI_Bayonut_Lock","di_RH_PCI_Bayonut_UnLock",
            "di_RH_PCI_Bayonut_Lock1_MovingPart","di_RH_PCI_Bayonut_UnLock1_MovingPart","di_RH_PCI_Deflation_Green_SSW","di_RH_PCI_Deflation_Yellow_SSW",
            "di_RH_PCI_Enable_FB","di_RH_PCI_FaultReset_PB","di_RH_PCI_Inflation_Green_SSW","di_RH_PCI_Inflation_Yellow_SSW",
            "di_RH_PCI_Manual_SSW","di_RH_PCI_RimClose_SSW","di_RH_PCI_RimFullUp_Lock_Unlock","di_RH_PCI_RimOpen_SSW",
            "di_RH_PCI_Rotation_Green","di_RH_PCI_Rotation_Green_SSW","di_RH_PCI_Rotation_Yellow","di_RH_PCI_Rotation_Yellow_SSW",
            "di_RH_PCI_Tire_Detect_PHS","di_RH_PciRim_BeadWidth_adj_Dec_SSW","di_RH_PciRim_BeadWidth_adj_Inc_SSW","di_RH_PciRim_BeadWidth_adj_Motor_Trip",
            "di_RH_Press_Auto_Mode","di_RH_Press_Enable_FB","di_RH_Press_MC_Mode","di_RH_Press_Manual_Mode",
            "di_RH_Press_Unlocked_FB1","di_RH_Press_Unlocked_FB2","di_RH_Rotation_Manual_Lock","di_RH_SMO_Extend_FB",
            "di_RH_SMO_Lock_FB","di_RH_SMO_Retract_FB","di_RH_SMO_Unlock_FB","di_RH_TBR_24DC_MCB_Trip",
            "di_RH_UnLoader_Intermediate","di_RH_UnloaderChuck_Close_FB","di_RH_UnloaderChuck_Open_FB","di_RH_UnloaderChuck_Open_PS",
            "di_RH_Unloader_Close_SSW","di_RH_Unloader_Down_SSW","di_RH_Unloader_Enable_FB","di_RH_Unloader_In_SSW",
            "di_RH_Unloader_Open_SSW","di_RH_Unloader_Out_SSW","di_RH_Unloader_PCI_In_FB","di_RH_Unloader_PCI_SSW",
            "di_RH_Unloader_PressIn_FB","di_RH_Unloader_PressOut_FB","di_RH_Unloader_Press_SSW","di_RH_Unloader_TyreSensor",
            "di_RH_Unloader_Up_SSW","di_Softstarter_Bypassed","di_Softstarter_Overload","di_Softstarter_Run",
            # --------- DO ---------
            "do_C_AC_Lamp_On","do_C_E_Stop_Lamp","do_C_OilCooling_Motor_On","do_C_Pump_ON","do_C_SoftStarter_ON",
            "do_LH_BlockOff_On","do_LH_C_CureAir_Off","do_LH_Circulation_Drain_On","do_LH_Deflation_Green","do_LH_Deflation_Yellow",
            "do_LH_Green_Tower_Lamp","do_LH_HPS_On","do_LH_Hooter_Tower_Lamp","do_LH_Internal_PS_Lamp","do_LH_LoaderChuck_Close",
            "do_LH_LoaderChuck_Open","do_LH_Loader_Down","do_LH_Loader_Press_In","do_LH_Loader_Press_Out","do_LH_Loader_Up",
            "do_LH_LowerRing_Down","do_LH_LowerRing_Up","do_LH_MD_On","do_LH_Mould_Blow_Out","do_LH_N2_Leak_Test_Valve_Off",
            "do_LH_N2_Leak_Test_Valve_On","do_LH_N2_Purging_On","do_LH_OpenVacuum_On","do_LH_PCI_Bayonut_lock","do_LH_PCI_Green_Inflation",
            "do_LH_PCI_Green_Inflation_Lamp","do_LH_PCI_Lifter_Down","do_LH_PCI_Lifter_SlowSpeed","do_LH_PCI_Lifter_UP","do_LH_PCI_Pos1Arm_In",
            "do_LH_PCI_Pos1Arm_Out","do_LH_PCI_Pos1Deflate","do_LH_PCI_Pos1TyreStripper","do_LH_PCI_Pos2Arm_In","do_LH_PCI_Pos2Arm_Out",
            "do_LH_PCI_Reset_Lamp","do_LH_PCI_Rotation_Green","do_LH_PCI_Rotation_Yellow","do_LH_PCI_Saf_Lock1","do_LH_PCI_Unloader_In",
            "do_LH_PCI_Unloader_Out","do_LH_PCI_Yellow_Inflation","do_LH_PCI_Yellow_Inflation_Lamp","do_LH_PressCV_Enable",
            "do_LH_Press_Close_Lock","do_LH_Press_Lock1","do_LH_Press_Lock2","do_LH_Red_Tower_Lamp","do_LH_Return_MD_On",
            "do_LH_SMO_Extend","do_LH_SMO_Lock","do_LH_SMO_Retract","do_LH_SMO_UnLock","do_LH_SQBooster_Enable",
            "do_LH_SQ_Disable_1","do_LH_SQ_Disable_2","do_LH_SQ_PneumaticBooster","do_LH_SQ_PumpBooster","do_LH_SQ_SlowSpeed",
            "do_LH_Shapping_On","do_LH_Squeeze_Extend","do_LH_Squeeze_Retract","do_LH_TBI_Cooler_On","do_LH_TBLCooler_On",
            "do_LH_TBPLCooler_On","do_LH_TopRing_Down","do_LH_TopRing_Slow_Speed","do_LH_TopRing_Up","do_LH_UnloaderChuck_Close",
            "do_LH_UnloaderChuck_Open","do_LH_Unloader_Down","do_LH_Unloader_SlowSpeed","do_LH_Unloader_SwingIn","do_LH_Unloader_SwingOut",
            "do_LH_Unloader_Up","do_LH_Vacuum_On","do_LH_Vent_On","do_LH_Yellow_Tower_Lamp","do_LH_loader_SlowSpeed",
            "do_Oil_Cooling_On","do_Pump_On","do_RH_BlockOff_On","do_RH_C_CureAir_Off","do_RH_C_Pump_ON",
            "do_RH_Circulation_Drain_On","do_RH_Deflation_Green","do_RH_Deflation_Yellow","do_RH_Green_Tower_Lamp","do_RH_HPS_On",
            "do_RH_Hooter_Tower_Lamp","do_RH_Internal_PS_Lamp","do_RH_LoaderChuck_Close","do_RH_LoaderChuck_Open","do_RH_Loader_Down",
            "do_RH_Loader_Press_In","do_RH_Loader_Press_Out","do_RH_Loader_SlowSpeed","do_RH_Loader_Up","do_RH_LowerRing_Down",
            "do_RH_LowerRing_Up","do_RH_MD_On","do_RH_Mould_Blow_Out","do_RH_N2_Leak_Test_Valve_Off","do_RH_N2_Leak_Test_Valve_On",
            "do_RH_N2_Purging_On","do_RH_OpenVacuum_On","do_RH_PCI_Bayonut_lock","do_RH_PCI_Green_Inflation","do_RH_PCI_Green_Inflation_Lamp",
            "do_RH_PCI_Lifter_Down","do_RH_PCI_Lifter_SlowSpeed","do_RH_PCI_Lifter_Up","do_RH_PCI_Pos1Arm_In","do_RH_PCI_Pos1Arm_Out",
            "do_RH_PCI_Pos1Deflate","do_RH_PCI_Pos1TyreStripper","do_RH_PCI_Pos2Arm_In","do_RH_PCI_Pos2Arm_Out","do_RH_PCI_Reset_Lamp",
            "do_RH_PCI_Rotation_Green","do_RH_PCI_Rotation_Yellow","do_RH_PCI_Saf_Lock1","do_RH_PCI_Unloader_In","do_RH_PCI_Unloader_Out",
            "do_RH_PCI_Yellow_Inflation","do_RH_PCI_Yellow_Inflation_Lamp","do_RH_PressCV_Enable","do_RH_Press_Close_Lock","do_RH_Press_Lock1",
            "do_RH_Press_Lock2","do_RH_Red_Tower_Lamp","do_RH_Return_MD_On","do_RH_SMO_Extend","do_RH_SMO_Lock","do_RH_SMO_Retract",
            "do_RH_SMO_UnLock","do_RH_SQBooster_Enable","do_RH_SQ_Disable_1","do_RH_SQ_Disable_2","do_RH_SQ_PneumaticBooster",
            "do_RH_SQ_PumpBooster","do_RH_SQ_SlowSpeed","do_RH_Shapping_On","do_RH_Squeeze_Extend","do_RH_Squeeze_Retract",
            "do_RH_TBI_Cooler_On","do_RH_TBLCooler_On","do_RH_TBPLCooler_On","do_RH_TopRing_Down","do_RH_TopRing_Slow_Speed",
            "do_RH_TopRing_Up","do_RH_UnloaderChuck_Close","do_RH_UnloaderChuck_Open","do_RH_Unloader_Down","do_RH_Unloader_SlowSpeed",
            "do_RH_Unloader_SwingIn","do_RH_Unloader_SwingOut","do_RH_Unloader_Up","do_RH_Vacuum_On","do_RH_Vent_On",
            "do_RH_Yellow_Tower_Lamp","do_Reset","do_S_C_ControlPower_On",

            # --------- EP1/EP2/EP3 step bits (original forms; auto-fix will resolve) ---------
            "EP1_Step[1].X","EP1_Step[2].X","EP1_Step[3].X","EP1_Step[4].X","EP1_Step[5].X",
            "EP1_Step[6].X","EP1_Step[7].X","EP1_Step[8].X","EP1_Step[9].X","EP1_Step[10].X",

            "EP2_Step[0].X","EP2_Step[1].X","EP2_Step[2].X","EP2_Step[3].X","EP2_Step[4].X",
            "EP2_Step[5].X","EP2_Step[6].X","EP2_Step[7].X","EP2_Step[8].X","EP2_Step[9].X",
            "EP2_Step[10].X","EP2_Step[11].X","EP2_Step[12].X","EP2_Step[13].X","EP2_Step[14].X",
            "EP2_Step[15].X","EP2_Step[16].X","EP2_Step[17].X","EP2_Step[18].X","EP2_Step[19].X",
            "EP2_Step[20].X",

            "EP3_Step[0].X","EP3_Step[1].X","EP3_Step[2].X","EP3_Step[3].X","EP3_Step[4].X",
            "EP3_Step[5].X","EP3_Step[6].X","EP3_Step[7].X","EP3_Step[8].X","EP3_Step[9].X",
            "EP3_Step[10].X","EP3_Step[11].X","EP3_Step[12].X","EP3_Step[13].X","EP3_Step[14].X",
            "EP3_Step[15].X","EP3_Step[16].X","EP3_Step[17].X","EP3_Step[18].X","EP3_Step[19].X",
            "EP3_Step[20].X","EP3_Step[21].X","EP3_Step[22].X","EP3_Step[23].X","EP3_Step[24].X",
            "EP3_Step[25].X","EP3_Step[26].X","EP3_Step[27].X","EP3_Step[28].X","EP3_Step[29].X",
            "EP3_Step[30].X","EP3_Step[31].X","EP3_Step[32].X","EP3_Step[33].X","EP3_Step[34].X",
            "EP3_Step[35].X","EP3_Step[36].X",

            # --------- LH group (note: underscore vs dot) ---------
            "LH.Curing.Step_No",
            "LH.Curing_Interlock_Ok",
            "LH.Initiate_Curing",
            "LH.Curing.Completed",
            "LH.Machine_Idle",
            "LH_Curing.Active",
        ]

        self.setup_ui()
        self.setup_connections()
        QTimer.singleShot(100, self.auto_connect)

    # ---------- Mapping helpers ----------
    def _tok(self, s: str) -> List[str]:
        return [t for t in re.split(r'[^0-9a-zA-Z]+', s.lower()) if t]

    def _ep_desired_parts(self, tag: str) -> Optional[Tuple[int,int,str]]:
        m = re.match(r'^(EP)([1-3])_Step\[(\d+)\]\.(X)$', tag, re.IGNORECASE)
        if not m: return None
        _, epn_s, idx_s, member = m.groups()
        return (int(epn_s), int(idx_s), member.lower())

    def _generate_ep_patterns(self, ep: int, idx: int, member: str) -> List[re.Pattern]:
        # Try common real PLC spellings: underscores, zero-padding, flattened names, etc.
        idx2 = f"{idx:02d}"
        pats = [
            rf"^EP{ep}[_]?Step\[{idx}\][\._]{member}$",
            rf"^EP{ep}[_]?Step\[{idx}\]{member}$",
            rf"^EP{ep}[_]?Step{idx}[\._]{member}$",
            rf"^EP{ep}[_]?Step_{idx}[\._]{member}$",
            rf"^EP{ep}[_]?Step{idx2}[\._]{member}$",
            rf"^EP{ep}[_]?Step_{idx2}[\._]{member}$",
            rf"^EP{ep}[_]?Step\[{idx}\]_{member}$",
            rf"^EP{ep}[_]?Step_{idx}_{member}$",
        ]
        return [re.compile(p, re.IGNORECASE) for p in pats]

    def _generate_lh_patterns(self, tag: str) -> List[re.Pattern]:
        # Accept LH.Curing.Step_No, LH.Curing_Interlock_Ok, LH.Initiate_Curing, LH.Machine_Idle etc.
        # Convert tokens into fuzzy underscore/dot-insensitive regex.
        toks = self._tok(tag)
        if not toks or toks[0] != 'lh':
            toks = ['lh'] + toks  # ensure 'lh' prefix
        pat = r".*".join(map(re.escape, toks))
        return [re.compile(pat, re.IGNORECASE)]

    def _probe_candidate(self, name: str) -> bool:
        res = self.plc_worker.read_one(name)
        return (res is not None) and getattr(res, "Status", "") == "Success"

    def _best_match_from_available(self, patterns: List[re.Pattern], startswith: Optional[str]=None) -> Optional[str]:
        cands: List[str] = []
        pool = self.available_tags if not startswith else [t for t in self.available_tags if t.lower().startswith(startswith)]
        for t in pool:
            for p in patterns:
                if p.search(t):
                    cands.append(t)
                    break
        if not cands:
            return None
        # Prefer shortest, then alphabetical
        cands.sort(key=lambda s: (len(s), s.lower()))
        return cands[0]

    def _map_specific_tags(self, desired: List[str]) -> Tuple[Dict[str, Optional[str]], List[Tuple[str,str]], List[str]]:
        """
        Returns (display->plc map, fixes list, unresolved list).
        We use:
          1) direct probe
          2) EP-pattern search in available list + probe
          3) LH-pattern search in available list + probe
          4) simple underscore/dot replacement variants + probe
        """
        mapping: Dict[str, Optional[str]] = {}
        fixes: List[Tuple[str,str]] = []
        unresolved: List[str] = []

        # precompute lowercase available for cheap contains checks
        self.available_tags = self.available_tags or []

        for disp in desired:
            # 1) direct
            if self._probe_candidate(disp):
                mapping[disp] = disp
                continue

            # 2) EP family
            ep_parts = self._ep_desired_parts(disp)
            chosen: Optional[str] = None
            if ep_parts:
                ep, idx, member = ep_parts
                pats = self._generate_ep_patterns(ep, idx, member)
                candidate = self._best_match_from_available(pats, startswith=f"ep{ep}")
                if candidate and self._probe_candidate(candidate):
                    chosen = candidate

            # 3) LH family
            if (not chosen) and (disp.lower().startswith('lh.')):
                pats = self._generate_lh_patterns(disp)
                candidate = self._best_match_from_available(pats, startswith="lh")
                if candidate and self._probe_candidate(candidate):
                    chosen = candidate

            # 4) simple underscore/dot swaps
            if not chosen:
                variants = set()
                if '.' in disp:
                    a,b = disp.split('.',1)
                    variants.add(f"{a}_{b}")
                if '_':  # also try replacing first '_' with '.'
                    parts = disp.split('_',1)
                    if len(parts)==2:
                        variants.add(f"{parts[0]}.{parts[1]}")
                for v in list(variants):
                    if self._probe_candidate(v):
                        chosen = v
                        break

            if chosen:
                mapping[disp] = chosen
                if chosen != disp:
                    fixes.append((disp, chosen))
            else:
                mapping[disp] = None
                unresolved.append(disp)

        return mapping, fixes, unresolved

    def setup_ui(self):
        self.setWindowTitle("PLC Data Monitor - Professional Edition")
        screen = QApplication.primaryScreen()
        self.setGeometry(screen.availableGeometry())
        self.setWindowFlags(Qt.Window)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(0)

        # ---------- LEFT SIDEBAR (fixed-ish width) ----------
        left_scroll_area = QScrollArea()
        left_scroll_area.setWidgetResizable(True)
        left_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        left_panel = QWidget()
        # ask for a bit more width so buttons can breathe
        left_panel.setMinimumWidth(360)

        left_scroll_area.setMinimumWidth(360)
        left_scroll_area.setMaximumWidth(420)   # you can tweak (380–420 works well)
        left_scroll_area.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(10)
        left_layout.setContentsMargins(10, 10, 10, 10)

        # ---- Connection group ----
        conn_group = QGroupBox("PLC Connection")
        cg = QVBoxLayout(conn_group)
        cg.setSpacing(8)

        ip_row = QHBoxLayout()
        ip_row.addWidget(QLabel("IP Address:"))
        self.ip_edit = QLineEdit("192.168.1.1")
        ip_row.addWidget(self.ip_edit)
        cg.addLayout(ip_row)

        slot_row = QHBoxLayout()
        slot_row.addWidget(QLabel("Slot:"))
        self.slot_spin = QSpinBox()
        self.slot_spin.setRange(0, 10)
        self.slot_spin.setValue(0)
        slot_row.addWidget(self.slot_spin)
        cg.addLayout(slot_row)

        btn_row = QHBoxLayout()
        self.connect_btn = QPushButton("Connect to PLC")
        self.connect_btn.setStyleSheet(
            "QPushButton { background:#2e7d32; color:#fff; font-weight:700; }"
        )
        self.disconnect_btn = QPushButton("Disconnect")
        self.disconnect_btn.setStyleSheet(
            "QPushButton { background:#c62828; color:#fff; }"
        )
        self.disconnect_btn.setEnabled(False)
        btn_row.addWidget(self.connect_btn)
        btn_row.addWidget(self.disconnect_btn)
        cg.addLayout(btn_row)

        left_layout.addWidget(conn_group)

        # ---- Tag management group ----
        tags_group = QGroupBox("Tag Management")
        tg = QVBoxLayout(tags_group)
        tg.setSpacing(8)

        self.get_tags_btn = QPushButton("Get All Tags from PLC")
        self.get_tags_btn.setEnabled(False)
        self.get_tags_btn.setStyleSheet(
            "QPushButton { background:#1565c0; color:#fff; }"
        )
        tg.addWidget(self.get_tags_btn)

        row_save = QHBoxLayout()
        self.auto_save_taglist_check = QCheckBox("Auto-save tag list to CSV")
        self.auto_save_taglist_check.setChecked(True)
        self.save_taglist_btn = QPushButton("Save Tag List CSV…")
        self.save_taglist_btn.setEnabled(False)
        row_save.addWidget(self.auto_save_taglist_check)
        row_save.addStretch()
        row_save.addWidget(self.save_taglist_btn)
        tg.addLayout(row_save)

        self.taglist_csv_path_label = QLabel("No tag list CSV saved yet")
        self.taglist_csv_path_label.setStyleSheet(
            "color:#888; font-size:10px;"
        )
        tg.addWidget(self.taglist_csv_path_label)

        tg.addWidget(QLabel("Available Tags (from PLC):"))
        self.tags_list_widget = QListWidget()
        self.tags_list_widget.setSelectionMode(
            QAbstractItemView.ExtendedSelection
        )
        self.tags_list_widget.setMaximumHeight(150)
        tg.addWidget(self.tags_list_widget)

        avail_btns = QHBoxLayout()
        self.select_all_btn = QPushButton("Select All Tags")
        self.select_all_btn.setEnabled(False)
        self.clear_selection_btn = QPushButton("Clear Selection")
        self.clear_selection_btn.setEnabled(False)
        avail_btns.addWidget(self.select_all_btn)
        avail_btns.addWidget(self.clear_selection_btn)
        tg.addLayout(avail_btns)

          # row 1: shorter buttons side by side
        add_row1 = QHBoxLayout()
        self.add_selected_btn = QPushButton("Add Selected Tags")
        self.add_selected_btn.setEnabled(False)
        self.add_all_btn = QPushButton("Add All Tags")
        self.add_all_btn.setEnabled(False)
        add_row1.addWidget(self.add_selected_btn)
        add_row1.addWidget(self.add_all_btn)
        tg.addLayout(add_row1)

        # row 2: long button gets full width
        self.add_specific_btn = QPushButton("Add 300+ Specific Tags (Auto-map)")
        self.add_specific_btn.setEnabled(False)
        self.add_specific_btn.setStyleSheet(
            "QPushButton { background:#8e24aa; color:#fff; font-weight:700; }"
        )
        tg.addWidget(self.add_specific_btn)

        tg.addWidget(QLabel("Selected (Display) Tags for Monitoring:"))
        self.selected_tags_list = QListWidget()
        self.selected_tags_list.setMaximumHeight(120)
        tg.addWidget(self.selected_tags_list)

        sel_btns = QHBoxLayout()
        self.remove_tag_btn = QPushButton("Remove Selected")
        self.remove_tag_btn.setEnabled(False)
        self.clear_all_btn = QPushButton("Clear All")
        sel_btns.addWidget(self.remove_tag_btn)
        sel_btns.addWidget(self.clear_all_btn)
        tg.addLayout(sel_btns)

        self.selected_count_label = QLabel("No tags selected")
        self.selected_count_label.setStyleSheet(
            "color:#4caf50; font-weight:700;"
        )
        tg.addWidget(self.selected_count_label)

        left_layout.addWidget(tags_group)

        # ---- Data collection group ----
        collect_group = QGroupBox("Data Collection")
        clg = QVBoxLayout(collect_group)
        clg.setSpacing(8)

        row = QHBoxLayout()
        row.addWidget(QLabel("Read Interval (ms):"))
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(100, 30000)
        self.interval_spin.setValue(1000)
        self.interval_spin.setSingleStep(100)
        row.addWidget(self.interval_spin)
        clg.addLayout(row)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Batch Size:"))
        self.batch_spin = QSpinBox()
        self.batch_spin.setRange(1, 100)
        self.batch_spin.setValue(50)
        row2.addWidget(self.batch_spin)
        clg.addLayout(row2)

        self.start_btn = QPushButton("Start Continuous Reading")
        self.start_btn.setStyleSheet(
            "QPushButton { background:#00695c; color:#fff; font-weight:700; }"
        )
        self.start_btn.setEnabled(False)
        self.stop_btn = QPushButton("Stop Reading")
        self.stop_btn.setStyleSheet(
            "QPushButton { background:#ef6c00; color:#fff; }"
        )
        self.stop_btn.setEnabled(False)
        self.single_read_btn = QPushButton("Single Read")
        self.single_read_btn.setEnabled(False)

        clg.addWidget(self.start_btn)
        clg.addWidget(self.stop_btn)
        clg.addWidget(self.single_read_btn)

        left_layout.addWidget(collect_group)

        # ---- Storage group ----
        storage_group = QGroupBox("Data Storage")
        sg = QVBoxLayout(storage_group)

        rowc = QHBoxLayout()
        self.csv_check = QCheckBox("Save to CSV")
        self.csv_check.setChecked(True)
        self.csv_browse_btn = QPushButton("Browse...")
        rowc.addWidget(self.csv_check)
        rowc.addWidget(self.csv_browse_btn)
        sg.addLayout(rowc)

        self.csv_path_label = QLabel("No file selected")
        self.csv_path_label.setStyleSheet("color:#888; font-size:10px;")
        sg.addWidget(self.csv_path_label)

        self.auto_csv_check = QCheckBox("Auto-generate CSV filename")
        self.auto_csv_check.setChecked(True)
        sg.addWidget(self.auto_csv_check)

        left_layout.addWidget(storage_group)

        # ---- Status group ----
        status_group = QGroupBox("Status")
        st = QVBoxLayout(status_group)
        self.status_label = QLabel("Ready to connect...")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(
            "QLabel { background:#333; padding:8px; border-radius:3px; }"
        )
        st.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        st.addWidget(self.progress_bar)

        left_layout.addWidget(status_group)

        # ---- Stats group ----
        stats_group = QGroupBox("Statistics")
        sgl = QVBoxLayout(stats_group)

        rowx = QHBoxLayout()
        rowx.addWidget(QLabel("Records Collected:"))
        self.records_count_label = QLabel("0")
        self.records_count_label.setStyleSheet(
            "QLabel { font-weight:700; color:#4caf50; }"
        )
        rowx.addWidget(self.records_count_label)
        rowx.addStretch()
        sgl.addLayout(rowx)

        rowy = QHBoxLayout()
        rowy.addWidget(QLabel("Tags Monitoring:"))
        self.tags_count_label = QLabel("0")
        self.tags_count_label.setStyleSheet(
            "QLabel { font-weight:700; color:#2196f3; }"
        )
        rowy.addWidget(self.tags_count_label)
        rowy.addStretch()
        sgl.addLayout(rowy)

        self.clear_data_btn = QPushButton("Clear Data Display")
        sgl.addWidget(self.clear_data_btn)

        left_layout.addWidget(stats_group)
        left_layout.addStretch()

        left_scroll_area.setWidget(left_panel)

        # ---------- RIGHT PANEL ----------
        right_panel = QWidget()
        rp = QVBoxLayout(right_panel)
        rp.setContentsMargins(10, 10, 10, 10)

        self.tab_widget = QTabWidget()

        # Real-time tab
        realtime_tab = QWidget()
        rt = QVBoxLayout(realtime_tab)

        data_scroll = QScrollArea()
        data_scroll.setWidgetResizable(True)
        self.data_table = QTableWidget()
        self.data_table.setColumnCount(3)
        self.data_table.setHorizontalHeaderLabels(
            ["Display Tag", "Current Value", "Timestamp"]
        )
        self.data_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )
        self.data_table.setAlternatingRowColors(True)
        data_scroll.setWidget(self.data_table)
        rt.addWidget(data_scroll)

        self.tab_widget.addTab(realtime_tab, "Real-time Data")

        # Log tab
        log_tab = QWidget()
        lt = QVBoxLayout(log_tab)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        lt.addWidget(self.log_text)

        self.clear_log_btn = QPushButton("Clear Log")
        self.save_log_btn = QPushButton("Save Log to File")
        btns = QHBoxLayout()
        btns.addWidget(self.clear_log_btn)
        btns.addWidget(self.save_log_btn)
        btns.addStretch()
        lt.addLayout(btns)

        self.tab_widget.addTab(log_tab, "System Log")
        rp.addWidget(self.tab_widget)

        # ---------- SPLITTER ----------
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_scroll_area)
        splitter.addWidget(right_panel)

        # <<< IMPORTANT: make right side dominate, left fixed-ish >>>
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 1200])

        main_layout.addWidget(splitter)

        self.apply_dark_theme()



    def apply_dark_theme(self):
        self.setStyleSheet("""
            QMainWindow { background:#2b2b2b; color:#fff; }
            QWidget { background:#2b2b2b; color:#fff;font-family:"Segoe UI";        /* <---- add */
            font-size:10pt;  }
            QGroupBox { font-weight:700; border:2px solid #555; border-radius:5px; margin-top:1ex; padding-top:10px; background:#353535;font-size:10pt;  }
            QGroupBox::title { left:10px; padding:0 5px; color:#fff; }
            QPushButton { background:#404040; color:#fff; border:1px solid #555; padding:6px 8px; border-radius:4px; font-size:12px; font-size:9pt; }
            QPushButton:hover { background:#505050; border:1px solid #666; }
            QPushButton:pressed { background:#303030; }
            QPushButton:disabled { background:#333; color:#666; border:1px solid #444; }
            QLineEdit, QSpinBox { background:#404040; color:#fff; border:1px solid #555; padding:6px; border-radius:3px; font-size:12px;font-size:9pt;  }
            QLineEdit:focus, QSpinBox:focus { border:1px solid #1565c0; }
            QTableWidget { background:#404040; color:#fff; gridline-color:#555; border:1px solid #555; font-size:12px; }
            QTableWidget::item { padding:8px; border-bottom:1px solid #555; }
            QTableWidget::item:selected { background:#1565c0; }
            QHeaderView::section { background:#353535; color:#fff; padding:8px; border:1px solid #555; font-weight:700; }
            QTextEdit { background:#404040; color:#fff; border:1px solid #555; font-family:monospace; font-size:11px; }
            QTabWidget::pane { border:1px solid #555; background:#2b2b2b; }
            QTabBar::tab { background:#353535; color:#fff; padding:8px 16px; border:1px solid #555; margin-right:2px; }
            QTabBar::tab:selected { background:#404040; border-bottom:2px solid #1565c0; }
            QProgressBar { border:1px solid #555; border-radius:3px; text-align:center; color:#fff; background:#353535; }
            QProgressBar::chunk { background:#1565c0; border-radius:2px; }
            QListWidget { background:#404040; color:#fff; border:1px solid #555; font-size:11px; }
            QListWidget::item { padding:4px; border-bottom:1px solid #555; }
            QListWidget::item:selected { background:#1565c0; }
        """)

    # ---------- Connections / handlers ----------
    def setup_connections(self):
        self.plc_worker.data_received.connect(self.on_data_received)
        self.plc_worker.status_signal.connect(self.on_status_update)
        self.plc_worker.error_signal.connect(self.on_error)
        self.plc_worker.tags_retrieved.connect(self.on_tags_retrieved)

        self.connect_btn.clicked.connect(self.connect_to_plc)
        self.disconnect_btn.clicked.connect(self.disconnect_from_plc)
        self.get_tags_btn.clicked.connect(self.get_all_tags)
        self.select_all_btn.clicked.connect(self.select_all_tags)
        self.clear_selection_btn.clicked.connect(self.clear_tags_selection)
        self.add_selected_btn.clicked.connect(self.add_selected_tags)
        self.add_all_btn.clicked.connect(self.add_all_tags)
        self.add_specific_btn.clicked.connect(self.add_specific_tags_automap)
        self.save_taglist_btn.clicked.connect(self.save_taglist_dialog)
        self.remove_tag_btn.clicked.connect(self.remove_selected_tag)
        self.clear_all_btn.clicked.connect(self.clear_all_tags)
        self.start_btn.clicked.connect(self.start_reading)
        self.stop_btn.clicked.connect(self.stop_reading)
        self.single_read_btn.clicked.connect(self.single_read)
        self.csv_browse_btn.clicked.connect(self.browse_csv_file)
        self.clear_data_btn.clicked.connect(self.clear_data)
        self.clear_log_btn.clicked.connect(self.clear_log)
        self.save_log_btn.clicked.connect(self.save_log)

        self.tags_list_widget.itemSelectionChanged.connect(self.on_tags_selection_changed)
        self.selected_tags_list.itemSelectionChanged.connect(self.on_selected_tags_selection_changed)

        self.plc_worker.start()

    def auto_connect(self):
        self.connect_to_plc()

    def connect_to_plc(self):
        ip = self.ip_edit.text().strip()
        slot = self.slot_spin.value()
        if not ip:
            QMessageBox.warning(self, "Input Error", "Please enter PLC IP address")
            return

        self.progress_bar.setVisible(True)
        self.status_label.setText(f"Connecting to PLC at {ip}...")
        self.connect_btn.setEnabled(False)   # prevent double clicks while connecting

        def do_connect():
            success = self.plc_worker.connect_plc(ip, slot)

            # ---- REAL PLC CONNECTED ----
            if success:
                self.is_connected = True
                self.status_label.setText(f"Connected to PLC at {ip}")

            # ---- SIMULATION CONNECTED ----
            elif self.plc_worker.simulation:
                self.is_connected = True   # treat SIM as connected
                self.status_label.setText("SIMULATION mode active (dummy PLC).")

            else:
                self.is_connected = False

            # enable/disable UI based on is_connected (real OR sim)
            if self.is_connected:
                self.connect_btn.setEnabled(False)
                self.disconnect_btn.setEnabled(True)

                self.get_tags_btn.setEnabled(True)
                self.add_selected_btn.setEnabled(True)
                self.add_all_btn.setEnabled(True)
                self.add_specific_btn.setEnabled(True)

                self.start_btn.setEnabled(True)
                self.single_read_btn.setEnabled(True)
            else:
                self.connect_btn.setEnabled(True)
                self.disconnect_btn.setEnabled(False)

            self.progress_bar.setVisible(False)

        threading.Thread(target=do_connect, daemon=True).start()

    def disconnect_from_plc(self):
        self.plc_worker.stop_reading()
        self.is_connected = False
        self.is_reading = False
        self.connect_btn.setEnabled(True)
        self.disconnect_btn.setEnabled(False)
        self.get_tags_btn.setEnabled(False)
        self.select_all_btn.setEnabled(False)
        self.clear_selection_btn.setEnabled(False)
        self.add_selected_btn.setEnabled(False)
        self.add_all_btn.setEnabled(False)
        self.add_specific_btn.setEnabled(False)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.single_read_btn.setEnabled(False)
        self.remove_tag_btn.setEnabled(False)
        self.status_label.setText("Disconnected from PLC")
        self.log_message("Disconnected from PLC")

    def get_all_tags(self):
        self.progress_bar.setVisible(True)
        self.status_label.setText("Retrieving tags from PLC...")
        self.plc_worker.get_all_tags()

    def on_tags_retrieved(self, tags: List[str]):
        """Handle retrieved tags + auto-save to CSV (optional)"""
        self.progress_bar.setVisible(False)
        self.tags_list_widget.clear()

        if tags:
            tags_sorted = sorted(tags)
            self.available_tags = tags_sorted[:] 
            self.tags_list_widget.addItems(tags_sorted)
            self.cached_all_tags = tags_sorted
            self.save_taglist_btn.setEnabled(True)

            self.status_label.setText(f"Retrieved {len(tags_sorted)} tags from PLC")
            self.log_message(f"Successfully retrieved {len(tags_sorted)} tags from PLC")
            self.select_all_btn.setEnabled(True)
            self.clear_selection_btn.setEnabled(True)

            # Auto-save CSV if enabled
            if self.auto_save_taglist_check.isChecked():
                path = self.save_taglist_csv(self.cached_all_tags)
                from pathlib import Path as _P
                self.taglist_csv_path_label.setText(_P(path).name)
                self.log_message(f"Auto-saved tag list to: {path}")
        else:
            self.cached_all_tags = []
            self.save_taglist_btn.setEnabled(False)
            self.status_label.setText("No tags found in PLC")
            self.log_message("No tags found in PLC")


    def select_all_tags(self):
        self.tags_list_widget.selectAll()
        self.log_message(f"Selected all {self.tags_list_widget.count()} tags")

    def clear_tags_selection(self):
        self.tags_list_widget.clearSelection()
        self.log_message("Cleared tag selection")

    def add_selected_tags(self):
        selected_items = self.tags_list_widget.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "Information", "Please select tags to add")
            return
        added = 0
        for it in selected_items:
            tag = it.text()
            if tag not in self.display_tags:
                self.selected_tags_list.addItem(tag)
                self.display_tags.append(tag)
                self.display_to_plc[tag] = tag
                added += 1
        self.update_tags_count()
        self.log_message(f"Added {added} tags to monitoring list")

    def add_all_tags(self):
        if self.tags_list_widget.count() == 0:
            QMessageBox.information(self, "Information", "No tags available to add")
            return
        self.selected_tags_list.clear()
        self.display_tags.clear()
        self.display_to_plc.clear()
        for i in range(self.tags_list_widget.count()):
            tag = self.tags_list_widget.item(i).text()
            self.selected_tags_list.addItem(tag)
            self.display_tags.append(tag)
            self.display_to_plc[tag] = tag
        self.update_tags_count()
        self.log_message(f"Added all {len(self.display_tags)} tags to monitoring list")

    def add_specific_tags_automap(self):
        if not self.is_connected:
            QMessageBox.warning(self, "Warning", "Please connect to PLC first")
            return

        if self.is_reading:
            self.stop_reading()

        self.selected_tags_list.clear()
        self.display_tags = list(self.specific_tags)  # keep your labels
        self.update_tags_count()
        self.log_message(f"Loaded {len(self.display_tags)} predefined tags. Auto-mapping to real PLC names...")

        self.progress_bar.setVisible(True); QApplication.processEvents()

        # Build mapping
        self.display_to_plc, fixes, unresolved = self._map_specific_tags(self.display_tags)

        # Fill UI with display names
        self.selected_tags_list.addItems(self.display_tags)
        self.update_tags_count()

        # Prepare actual read set (skip unresolved)
        mapped = [p for p in self.display_to_plc.values() if p]
        # Deduplicate but keep order
        seen = set(); self.read_tags = []
        for t in mapped:
            if t not in seen:
                self.read_tags.append(t); seen.add(t)

        # Log
        for old, new in fixes:
            self.log_message(f"✓ Fixed tag: {old}  →  {new}")
        for bad in unresolved:
            self.log_message(f"✗ Could not resolve (skipped from read): {bad}")

        self.status_label.setText(f"Specific tags mapped. Readable: {len(self.read_tags)}, unresolved: {len(unresolved)}")
        self.progress_bar.setVisible(False)

    def remove_selected_tag(self):
        items = self.selected_tags_list.selectedItems()
        if not items:
            QMessageBox.information(self, "Information", "Please select tags to remove")
            return
        for it in items:
            disp = it.text()
            self.selected_tags_list.takeItem(self.selected_tags_list.row(it))
            if disp in self.display_tags:
                self.display_tags.remove(disp)
            if disp in self.display_to_plc:
                self.display_to_plc.pop(disp, None)
        self.update_tags_count()
        self.log_message(f"Removed {len(items)} tags from monitoring list")

    def clear_all_tags(self):
        self.selected_tags_list.clear()
        self.display_tags.clear()
        self.display_to_plc.clear()
        self.read_tags.clear()
        self.update_tags_count()
        self.log_message("Cleared all selected tags")

    def on_tags_selection_changed(self):
        cnt = len(self.tags_list_widget.selectedItems())
        self.add_selected_btn.setText(f"Add Selected ({cnt})" if cnt else "Add Selected Tags")

    def on_selected_tags_selection_changed(self):
        self.remove_tag_btn.setEnabled(len(self.selected_tags_list.selectedItems()) > 0)

    def update_tags_count(self):
        count = len(self.display_tags)
        self.tags_count_label.setText(str(count))
        self.selected_count_label.setText(f"{count} display tags selected")
        self.start_btn.setEnabled(count > 0)
        self.single_read_btn.setEnabled(count > 0)

    def start_reading(self):
        if not self.display_tags:
            QMessageBox.warning(self, "Warning", "No tags selected for monitoring. Please add tags first.")
            return

        # ensure mapping exists for the auto-map flow
        if not self.display_to_plc:
            self.add_specific_tags_automap()

        if not self._setup_storage():
            return

        # --- NEW: if read_tags is still empty, derive it from display_to_plc ---
        if not self.read_tags:
            mapped = [p for p in self.display_to_plc.values() if p]  # PLC names
            seen = set()
            self.read_tags = []
            for t in mapped:
                if t not in seen:
                    self.read_tags.append(t)
                    seen.add(t)
        # ---------------------------------------------------------

        # read only resolvable PLC names
        if not self.read_tags:
            QMessageBox.warning(self, "Warning", "No resolvable tags to read. Check log for unmapped names.")
            return

        self.is_reading = True
        self.plc_worker.start_reading(
            self.read_tags,
            self.interval_spin.value(),
            self.batch_spin.value()
        )
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.single_read_btn.setEnabled(False)
        self.records_count = 0
        self._update_records_count()
        self.log_message(
            f"Started continuous reading of {len(self.read_tags)} PLC tags "
            f"(display columns: {len(self.display_tags)})"
        )

    def stop_reading(self):
        self.is_reading = False
        self.plc_worker.stop_reading()
        self.start_btn.setEnabled(True); self.stop_btn.setEnabled(False); self.single_read_btn.setEnabled(True)
        self.data_storage.close()
        self.log_message("Stopped data collection")

    def single_read(self):
        if not self.display_tags:
            QMessageBox.warning(self, "Warning", "No tags selected for monitoring")
            return

        if not self.display_to_plc:
            self.add_specific_tags_automap()

        if not self._setup_storage():
            return

        # --- NEW: if read_tags is empty, derive it from display_to_plc ---
        if not self.read_tags:
            mapped = [p for p in self.display_to_plc.values() if p]
            seen = set()
            self.read_tags = []
            for t in mapped:
                if t not in seen:
                    self.read_tags.append(t)
                    seen.add(t)
        # ---------------------------------------------------------

        if not self.read_tags:
            QMessageBox.warning(self, "Warning", "No resolvable tags to read. Check log for unmapped names.")
            return

        self.plc_worker.batch_size = self.batch_spin.value()
        self.plc_worker.read_single_cycle(self.read_tags)
        self.log_message("Performed single read operation")


    def _setup_storage(self):
        try:
            if self.csv_check.isChecked():
                if not self.data_storage.csv_file:
                    if not self.auto_csv_check.isChecked() and self.csv_path_label.text() != "No file selected":
                        filename = str(Path.cwd() / Path(self.csv_path_label.text()))
                    else:
                        filename = str(Path.cwd() / f"plc_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
                    if not self.data_storage.setup_csv(filename):
                        QMessageBox.critical(self, "Error", "Failed to create CSV file")
                        return False
                    self.csv_path_label.setText(Path(filename).name)
                    self.data_storage.use_csv = True
                    self.data_storage.current_display_tags = list(self.display_tags)
                    self.data_storage.display_to_plc = dict(self.display_to_plc)
                    self.data_storage.write_headers()
                    self.log_message(f"CSV storage setup: {filename}")
            return True
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Storage setup failed: {str(e)}")
            return False

    def on_data_received(self, data: Dict):
        try:
            ts = data['timestamp']
            values_plc = data['values']  # keys are real PLC names
            # store with display headers
            self.data_storage.store_data(ts, values_plc)
            # update UI table
            self._update_table(ts, values_plc)
            self.records_count += 1
            self._update_records_count()
        except Exception as e:
            self.log_message(f"Error processing data: {str(e)}")

    def _update_table(self, timestamp: datetime, values_plc: Dict[str, object]):
        tstr = timestamp.strftime("%H:%M:%S.%f")[:-3]
        if self.data_table.rowCount() != len(self.display_tags):
            self.data_table.setRowCount(len(self.display_tags))
        for i, disp in enumerate(self.display_tags):
            plc = self.display_to_plc.get(disp)
            val = 'N/A' if plc is None else values_plc.get(plc, 'N/A')

            if self.data_table.item(i, 0) is None:
                self.data_table.setItem(i, 0, QTableWidgetItem(disp))
            else:
                self.data_table.item(i, 0).setText(disp)

            if self.data_table.item(i, 1) is None:
                self.data_table.setItem(i, 1, QTableWidgetItem(str(val)))
            else:
                self.data_table.item(i, 1).setText(str(val))

            if 'Error' in str(val):
                self.data_table.item(i, 1).setBackground(Qt.darkRed)
                self.data_table.item(i, 1).setForeground(Qt.white)
            else:
                self.data_table.item(i, 1).setBackground(Qt.transparent)
                self.data_table.item(i, 1).setForeground(Qt.white)

            if self.data_table.item(i, 2) is None:
                self.data_table.setItem(i, 2, QTableWidgetItem(tstr))
            else:
                self.data_table.item(i, 2).setText(tstr)

    def _update_records_count(self):
        self.records_count_label.setText(str(self.records_count))

    def on_status_update(self, message: str):
        self.status_label.setText(message)
        self.log_message(f"INFO: {message}")

    def on_error(self, message: str):
        # If we are in simulation, connection errors are not fatal -> no popup
        if self.plc_worker.simulation and ("connection failed" in message.lower() or "timed out" in message.lower()):
            self.status_label.setText(f"SIM MODE: {message}")
            self.log_message(f"SIM INFO: {message}")
            return

        self.status_label.setText(f"Error: {message}")
        self.log_message(f"ERROR: {message}")
        QMessageBox.critical(self, "Error", message)


    def log_message(self, message: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{ts}] {message}")
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())

    def clear_data(self):
        self.data_table.setRowCount(0)
        self.records_count = 0
        self._update_records_count()
        self.log_message("Cleared data display")

    def clear_log(self):
        self.log_text.clear()
        self.log_message("Log cleared")

    def save_log(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Log File", f"plc_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt", "Text Files (*.txt)"
        )
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(self.log_text.toPlainText())
                self.log_message(f"Log saved to {filename}")
                QMessageBox.information(self, "Success", f"Log saved to {filename}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save log: {str(e)}")

    def browse_csv_file(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save CSV File",
            f"plc_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "CSV Files (*.csv)"
        )
        if filename:
            self.csv_path_label.setText(Path(filename).name)
            self.auto_csv_check.setChecked(False)

    def save_taglist_csv(self, tags: List[str], filename: str = None) -> str:
        """Save the full PLC tag list to a CSV (1 tag per line, with 'tag' header). Returns path."""
        from pathlib import Path
        import csv
        from datetime import datetime

        if filename is None:
            filename = str(Path.cwd() / f"plc_taglist_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")

        try:
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                w = csv.writer(f)
                w.writerow(['tag'])
                for t in tags:
                    w.writerow([t])
            return filename
        except Exception as e:
            self.log_message(f"Failed to save tag list CSV: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save tag list CSV:\n{e}")
            return filename

    def save_taglist_dialog(self):
        """Manual Save As… for the full PLC tag list CSV."""
        if not self.cached_all_tags:
            QMessageBox.information(self, "No Tags", "No tags loaded yet. Click 'Get All Tags' first.")
            return
        from datetime import datetime
        from pathlib import Path

        default_name = f"plc_taglist_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Tag List CSV", default_name, "CSV Files (*.csv)"
        )
        if filename:
            path = self.save_taglist_csv(self.cached_all_tags, filename)
            self.taglist_csv_path_label.setText(Path(path).name)
            self.log_message(f"Tag list saved to: {path}")
            QMessageBox.information(self, "Saved", f"Saved {len(self.cached_all_tags)} tags to:\n{path}")


    def closeEvent(self, event):
        if self.is_reading:
            self.stop_reading()
        if self.is_connected:
            self.disconnect_from_plc()
        self.plc_worker.wait(1000)
        self.data_storage.close()
        self.log_message("Application closed")
        event.accept()


def main():
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("PLC Data Monitor")
    app.setApplicationVersion("2.2.0")
    app.setOrganizationName("Industrial Automation")
    app.setStyle('Fusion')
    app.setFont(QFont("Segoe UI", 9)) 
    window = ModernPLCWindow()
    window.setWindowFlags(Qt.Window)
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
