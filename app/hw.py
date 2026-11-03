"""Определение железа без WMI (на части ПК WMI сломан): nvidia-smi, реестр, ctypes."""
import ctypes
import os
import shutil
import subprocess
import winreg

NO_WINDOW = 0x08000000
GB = 1024 ** 3
DISPLAY_CLASS = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"


class _MemStatus(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
        ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def ram_gb():
    st = _MemStatus()
    st.dwLength = ctypes.sizeof(st)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
    return round(st.ullTotalPhys / GB, 1)


def _vendor(name):
    n = name.lower()
    if "nvidia" in n or "geforce" in n or "quadro" in n or "rtx" in n:
        return "nvidia"
    if "amd" in n or "radeon" in n:
        return "amd"
    if "intel" in n:
        return "intel"
    return "other"


def _nvidia_smi():
    exe = shutil.which("nvidia-smi") or next(
        (p for p in (r"C:\Windows\System32\nvidia-smi.exe",
                     r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe") if os.path.exists(p)), None)
    if not exe:
        return []
    try:
        out = subprocess.run([exe, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=10, creationflags=NO_WINDOW).stdout
    except Exception:
        return []
    gpus = []
    for line in out.splitlines():
        name, _, mem = line.rpartition(",")
        try:
            gpus.append({"name": name.strip(), "vram_gb": round(int(mem) / 1024, 1), "vendor": "nvidia"})
        except ValueError:
            pass
    return gpus


def _registry_gpus():
    gpus = []
    try:
        root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, DISPLAY_CLASS)
    except OSError:
        return gpus
    i = 0
    while True:
        try:
            sub = winreg.EnumKey(root, i)
        except OSError:
            break
        i += 1
        if not sub.isdigit():
            continue
        try:
            key = winreg.OpenKey(root, sub)
            name = winreg.QueryValueEx(key, "DriverDesc")[0]
        except OSError:
            continue
        vram = 0
        for value in ("HardwareInformation.qwMemorySize", "HardwareInformation.MemorySize"):
            try:
                raw = winreg.QueryValueEx(key, value)[0]
            except OSError:
                continue
            vram = int.from_bytes(raw, "little") if isinstance(raw, bytes) else int(raw)
            if vram:
                break
        if vram < 0:
            vram += 1 << 32
        gpus.append({"name": name, "vram_gb": round(vram / GB, 1), "vendor": _vendor(name)})
    return gpus


def detect():
    gpus = _nvidia_smi()
    for g in _registry_gpus():
        if g["vendor"] == "nvidia" and gpus:
            continue
        if not any(g["name"] == x["name"] for x in gpus):
            gpus.append(g)
    # Дискретной считаем NVIDIA и AMD с заметной памятью; встроенная графика = режим CPU.
    usable = [g for g in gpus if g["vendor"] == "nvidia" or (g["vendor"] == "amd" and g["vram_gb"] >= 3)]
    best = max(usable, key=lambda g: g["vram_gb"], default=None)
    # Свободное место считает server.build_state — по диску выбранной папки моделей.
    return {
        "ram_gb": ram_gb(),
        "gpus": gpus,
        "gpu": best,
        "vram_gb": best["vram_gb"] if best else 0,
        "cpu": os.environ.get("PROCESSOR_IDENTIFIER", ""),
        "cores": os.cpu_count() or 1,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(detect(), ensure_ascii=False, indent=1))
