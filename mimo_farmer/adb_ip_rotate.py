"""ADB-based mobile IP rotation for MiMo Farmer.

Uses USB-tethered Android phone to rotate IP via:
1. Airplane mode toggle (reliable IP change, ~15s)
2. Mobile data toggle (faster, ~8s, might reuse IP)

Requirements:
- Android phone connected via USB
- USB tethering active (phone provides internet to laptop)
- ADB installed and device authorized
"""

import subprocess
import time
import re
import socket
import requests
from pathlib import Path

# Auto-detect ADB path
ADB_PATHS = [
    str(Path.home() / "AppData" / "Local" / "Android" / "Sdk" / "platform-tools" / "adb.exe"),
    "adb",  # fallback to PATH
]


def _find_adb() -> str:
    for p in ADB_PATHS:
        try:
            r = subprocess.run([p, "version"], capture_output=True, timeout=5)
            if r.returncode == 0:
                return p
        except Exception:
            continue
    return None


def _run_adb(adb: str, args: list[str], timeout: int = 15) -> tuple[int, str]:
    """Run adb command, return (returncode, stdout)."""
    try:
        cmd = [adb] + args
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip()
    except subprocess.TimeoutExpired:
        return -1, "timeout"
    except Exception as e:
        return -1, str(e)


def check_device(adb: str = None) -> bool:
    """Check if an Android device is connected and authorized."""
    adb = adb or _find_adb()
    if not adb:
        return False
    rc, out = _run_adb(adb, ["devices"])
    if rc != 0:
        return False
    lines = out.strip().split('\n')[1:]  # skip header
    for line in lines:
        if '\tdevice' in line:
            return True
    return False


def get_device_info(adb: str = None) -> dict:
    """Get connected device info."""
    adb = adb or _find_adb()
    info = {}
    if not adb:
        return info

    rc, model = _run_adb(adb, ["shell", "getprop", "ro.product.model"])
    if rc == 0:
        info["model"] = model

    rc, android = _run_adb(adb, ["shell", "getprop", "ro.build.version.release"])
    if rc == 0:
        info["android"] = android

    rc, sdk = _run_adb(adb, ["shell", "getprop", "ro.build.version.sdk"])
    if rc == 0:
        info["sdk"] = sdk

    return info


def get_current_ip() -> str | None:
    """Get current public IP via HTTP."""
    try:
        r = requests.get("https://api.ipify.org", timeout=10)
        return r.text.strip()
    except Exception:
        try:
            r = requests.get("https://ifconfig.me/ip", timeout=10)
            return r.text.strip()
        except Exception:
            return None


def rotate_airplane(adb: str = None, wait: int = 12) -> dict:
    """Rotate IP by toggling airplane mode. ~15s total."""
    adb = adb or _find_adb()
    if not adb:
        return {"success": False, "error": "ADB not found"}

    # Get IP before
    ip_before = get_current_ip()

    # Enable airplane mode
    rc, _ = _run_adb(adb, ["shell", "settings", "put", "global", "airplane_mode_on", "1"])
    if rc != 0:
        return {"success": False, "error": "Failed to enable airplane mode"}

    # Broadcast airplane mode change (some Android versions need this)
    _run_adb(adb, ["shell", "am", "broadcast", "-a", "android.intent.action.AIRPLANE_MODE", "--ez", "state", "true"])

    # Wait for radio to fully off
    time.sleep(3)

    # Disable airplane mode
    rc, _ = _run_adb(adb, ["shell", "settings", "put", "global", "airplane_mode_on", "0"])
    if rc != 0:
        return {"success": False, "error": "Failed to disable airplane mode"}

    _run_adb(adb, ["shell", "am", "broadcast", "-a", "android.intent.action.AIRPLANE_MODE", "--ez", "state", "false"])

    # Wait for reconnection
    print(f"  [adb] Waiting {wait}s for reconnection...", end="", flush=True)
    for i in range(wait):
        time.sleep(1)
        print(".", end="", flush=True)
    print()

    # Get IP after
    ip_after = get_current_ip()

    return {
        "success": True,
        "ip_before": ip_before,
        "ip_after": ip_after,
        "changed": ip_before != ip_after,
    }


def rotate_data(adb: str = None, wait: int = 8) -> dict:
    """Rotate IP by toggling mobile data. ~8s total."""
    adb = adb or _find_adb()
    if not adb:
        return {"success": False, "error": "ADB not found"}

    ip_before = get_current_ip()

    # Disable mobile data
    rc, _ = _run_adb(adb, ["shell", "svc", "data", "disable"])
    if rc != 0:
        return {"success": False, "error": "Failed to disable mobile data"}

    time.sleep(2)

    # Enable mobile data
    rc, _ = _run_adb(adb, ["shell", "svc", "data", "enable"])
    if rc != 0:
        return {"success": False, "error": "Failed to enable mobile data"}

    print(f"  [adb] Waiting {wait}s for reconnection...", end="", flush=True)
    for i in range(wait):
        time.sleep(1)
        print(".", end="", flush=True)
    print()

    ip_after = get_current_ip()

    return {
        "success": True,
        "ip_before": ip_before,
        "ip_after": ip_after,
        "changed": ip_before != ip_after,
    }


def rotate_ip(method: str = "airplane", adb: str = None) -> dict:
    """Rotate IP using specified method."""
    if method == "airplane":
        return rotate_airplane(adb)
    elif method == "data":
        return rotate_data(adb)
    else:
        return {"success": False, "error": f"Unknown method: {method}"}


# --- CLI test ---
if __name__ == "__main__":
    adb = _find_adb()
    if not adb:
        print("[!] ADB not found")
        exit(1)

    print(f"[+] ADB: {adb}")

    if not check_device(adb):
        print("[!] No device connected. Connect phone via USB and enable USB debugging.")
        exit(1)

    info = get_device_info(adb)
    print(f"[+] Device: {info.get('model', '?')} (Android {info.get('android', '?')})")

    ip = get_current_ip()
    print(f"[+] Current IP: {ip}")

    print("\n[1] Testing airplane mode rotation...")
    result = rotate_airplane(adb)
    print(f"    Result: {result}")

    if result.get("changed"):
        print(f"    ✓ IP changed: {result['ip_before']} → {result['ip_after']}")
    else:
        print(f"    ✗ IP same: {result.get('ip_after', '?')}")
