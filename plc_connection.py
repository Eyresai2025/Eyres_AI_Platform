# src/utils/plc_connection.py
from __future__ import annotations
import socket
from typing import Optional, Tuple

def _tcp_ping(ip: str, port: int, timeout=2.0) -> bool:
    """Low-level TCP connect check (fast)."""
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except Exception:
        return False


def check_plc_and_get_active(
    machine_or_brand,
    protocol: Optional[str] = None,
    ip: Optional[str] = None,
    slot: Optional[int] = None,
    timeout: float = 2.5,
) -> Tuple[bool, str]:
    """
    Supports BOTH usages:

    1) Dict mode (your UI uses this):
        check_plc_and_get_active({
            "plc_brand": "...",
            "plc_protocol": "...",
            "ip_address": "...",
            "slot": 0
        })

    2) Old param mode:
        check_plc_and_get_active(brand, protocol, ip, slot)
    """

    # ------------------------------
    # ✅ Detect dict mode
    # ------------------------------
    if isinstance(machine_or_brand, dict):
        brand = machine_or_brand.get("plc_brand")
        protocol = machine_or_brand.get("plc_protocol")
        ip = machine_or_brand.get("ip_address")
        slot = machine_or_brand.get("slot")
    else:
        brand = machine_or_brand   # old style first arg

    if not ip:
        return False, "IP missing."

    b = (brand or "").strip().lower()
    p = (protocol or "").strip().lower()

    # ---------------------------
    # SIEMENS (S7 TCP via snap7)
    # ---------------------------
    if "siemens" in b or "s7" in p:
        try:
            import snap7
            client = snap7.client.Client()

            rack = 0
            s = 1 if slot is None or str(slot).strip() == "" else int(slot)

            # ✅ older snap7: no tcpport kwarg
            try:
                client.connect(ip, rack, s, 102)   # port as positional
            except TypeError:
                client.connect(ip, rack, s)        # fallback: default port=102

            ok = client.get_connected()
            client.disconnect()

            return ok, "Connected to Siemens S7." if ok else "Siemens S7 not reachable."

        except Exception as e:
            # fallback quick port ping
            if _tcp_ping(ip, 102, timeout=timeout):
                return True, "TCP port 102 reachable (Siemens likely online)."
            return False, f"Siemens connect failed: {e}"


    # -----------------------------------
    # ALLEN-BRADLEY (Logix PLC via pycomm3)
    # -----------------------------------
    if "allen-bradley" in b or "ethernet/ip" in p or "cip" in p:
        try:
            from pycomm3 import LogixDriver

            # AB slot usually required if not slot 0
            s = 0 if slot is None or str(slot).strip() == "" else int(slot)

            path = f"{ip}/{s}"  # ✅ LogixDriver supports IP/slot shortcut
            with LogixDriver(path, init_tags=False) as plc:
                ok = plc.connected

            return ok, "Connected to Allen-Bradley PLC." if ok else "Allen-Bradley not reachable."

        except Exception as e:
            # EtherNet/IP explicit messaging port
            if _tcp_ping(ip, 44818, timeout=timeout):
                return True, "TCP port 44818 reachable (Allen-Bradley likely online)."
            return False, f"Allen-Bradley connect failed: {e}"


    # ------------------------------
    # DELTA / SCHNEIDER / KEYENCE / MOST OTHERS via Modbus TCP
    # ------------------------------
    if "modbus" in p or b in ("delta", "schneider", "keyence"):
        try:
            from pymodbus.client import ModbusTcpClient
            client = ModbusTcpClient(ip, port=502, timeout=timeout)
            ok = client.connect()
            client.close()
            return ok, "Connected via Modbus TCP." if ok else "Modbus TCP not reachable."
        except Exception as e:
            if _tcp_ping(ip, 502, timeout=timeout):
                return True, "TCP port 502 reachable (Modbus PLC likely online)."
            return False, f"Modbus connect failed: {e}"

    # ------------------------------
    # MITSUBISHI (MC Protocol)
    # ------------------------------
    if "mitsubishi" in b or "mc protocol" in p:
        try:
            import pymcprotocol
            mc = pymcprotocol.Type3E()
            # default port 5007 for MC-protocol
            mc.connect(ip, 5007)
            mc.close()
            return True, "Connected to Mitsubishi via MC Protocol."
        except Exception as e:
            if _tcp_ping(ip, 5007, timeout=timeout):
                return True, "TCP port 5007 reachable (Mitsubishi likely online)."
            return False, f"Mitsubishi connect failed: {e}"

    # ------------------------------
    # OMRON (FINS)
    # ------------------------------
    if "omron" in b or "fins" in p:
        try:
            from fins.udp import UDPFinsConnection
            fins_conn = UDPFinsConnection()
            fins_conn.connect(ip)
            fins_conn.dest_node_add = 1
            fins_conn.srce_node_add = 25
            # if connect doesn't throw, good enough
            fins_conn.close()
            return True, "Connected to Omron via FINS."
        except Exception as e:
            return False, f"Omron connect failed: {e}"

    # ------------------------------
    # LAST FALLBACK: ICMP/TCP ping only
    # ------------------------------
    if _tcp_ping(ip, 80, timeout=timeout) or _tcp_ping(ip, 102, timeout=timeout) or _tcp_ping(ip, 502, timeout=timeout):
        return True, "IP reachable on common PLC ports (likely online)."

    return False, "PLC not reachable (no matching driver or ports closed)."
