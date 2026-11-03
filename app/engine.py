"""Движок Ollama: поиск, скачивание/установка, запуск, загрузка моделей. LOCALAI_DEMO=1 — имитация без сети."""
import hashlib
import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:11434"
SETUP_URL = "https://ollama.com/download/OllamaSetup.exe"
RELEASES_URL = "https://api.github.com/repos/ollama/ollama/releases/latest"
REGISTRY = "https://registry.ollama.ai"
MANIFEST = "application/vnd.docker.distribution.manifest.v2+json"
NO_WINDOW = 0x08000000
DETACHED = 0x00000008
UA = {"User-Agent": "LocalAI-Installer/1.0"}
DEMO = os.environ.get("LOCALAI_DEMO") == "1"

DATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "LocalAI")
SETTINGS = os.path.join(DATA_DIR, "settings-demo.json" if DEMO else "settings.json")
DEFAULT_ENGINE_DIR = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama")
DEFAULT_MODELS_DIR = os.path.join(os.path.expanduser("~"), ".ollama", "models")
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"

_demo = {"engine": False, "models": [], "version": "0.40.0", "latest": "0.40.13", "fresh": set(), "models_dir": ""}
_show_cache = {}
_shutting = False


# ---------- настройки и папки ----------
def settings():
    try:
        with open(SETTINGS, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_settings(**kw):
    data = dict(settings(), **kw)
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(SETTINGS, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def _registry_engine_dir(field="InstallLocation"):
    """Поле записи установщика Ollama (Inno Setup): InstallLocation — на случай установки в свою папку,
    UninstallString — штатный деинсталлятор."""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as root:
            for i in range(winreg.QueryInfoKey(root)[0]):
                try:
                    with winreg.OpenKey(root, winreg.EnumKey(root, i)) as k:
                        if str(winreg.QueryValueEx(k, "DisplayName")[0]).startswith("Ollama"):
                            return winreg.QueryValueEx(k, field)[0]
                except OSError:
                    continue
    except OSError:
        pass
    return None


def _user_env(name):
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            return os.path.expandvars(winreg.QueryValueEx(k, name)[0])
    except OSError:
        return None


def _set_user_env(name, value):
    """Переменная среды пользователя (HKCU\\Environment) + WM_SETTINGCHANGE, чтобы её увидели новые процессы."""
    import ctypes
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as k:
        if value:
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)
        else:
            try:
                winreg.DeleteValue(k, name)
            except OSError:
                pass
    if value:
        os.environ[name] = value   # движок мы запускаем сами — он наследует нашу среду
    else:
        os.environ.pop(name, None)
    ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "Environment", 0x0002, 3000, None)


def find_exe():
    local = os.environ.get("LOCALAPPDATA", "")
    for d in (settings().get("engine_dir"), _registry_engine_dir()):
        if d and os.path.exists(os.path.join(d, "ollama.exe")):
            return os.path.join(d, "ollama.exe")
    for p in (shutil.which("ollama"),
              os.path.join(local, "Programs", "Ollama", "ollama.exe"),
              os.path.join(os.environ.get("ProgramFiles", ""), "Ollama", "ollama.exe")):
        if p and os.path.exists(p):
            return p
    return None


def engine_dir():
    if DEMO:
        return settings().get("engine_dir") or DEFAULT_ENGINE_DIR
    exe = find_exe()
    return os.path.dirname(exe) if exe else settings().get("engine_dir") or DEFAULT_ENGINE_DIR


def models_dir():
    """Куда Ollama кладёт модели: OLLAMA_MODELS пользователя, иначе ~/.ollama/models."""
    if DEMO:
        return _demo["models_dir"] or settings().get("models_dir") or DEFAULT_MODELS_DIR
    return _user_env("OLLAMA_MODELS") or os.environ.get("OLLAMA_MODELS") or DEFAULT_MODELS_DIR


def _existing(path):
    while path and not os.path.exists(path):
        parent = os.path.dirname(path)
        if parent == path:
            return None
        path = parent
    return path


def free_gb(path):
    p = _existing(path)
    try:
        return round(shutil.disk_usage(p).free / 1024 ** 3, 1) if p else 0.0
    except OSError:
        return 0.0


def same_drive(a, b):
    return os.path.splitdrive(os.path.abspath(a))[0].lower() == os.path.splitdrive(os.path.abspath(b))[0].lower()


def _norm(p):
    return os.path.normcase(os.path.abspath(p)).rstrip("\\/")


def _inside(a, b):
    a, b = _norm(a), _norm(b)
    return a == b or a.startswith(b + os.sep)


def _store_dirs(path):
    """Папки хранилища Ollama: blobs, manifests, а с 0.40 ещё manifests-v2 и metadata. Чужое в папке не трогаем."""
    try:
        return [d for d in os.listdir(path) if os.path.isdir(os.path.join(path, d))
                and (d in ("blobs", "metadata") or d.startswith("manifests"))]
    except OSError:
        return []


def models_usage(path):
    """Сколько моделей лежит в папке: (число манифестов, ГиБ в blobs)."""
    count = max([sum(len(files) for _, _, files in os.walk(os.path.join(path, d)))
                 for d in _store_dirs(path) if d.startswith("manifests")] or [0])
    size = 0
    for root, _, files in os.walk(os.path.join(path, "blobs")):
        for f in files:
            try:
                size += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return count, round(size / 1024 ** 3, 2)


def check_dir(kind, path):
    """Проверка новой папки: путь абсолютный, диск есть, запись разрешена. Папку не создаёт."""
    path = os.path.expandvars((path or "").strip().strip('"'))
    if not path or not os.path.isabs(path) or not os.path.splitdrive(path)[0]:
        return {"ok": False, "error": "bad_path"}
    path = os.path.abspath(path)
    cur = engine_dir() if kind == "engine" else models_dir()
    res = {"ok": True, "path": path, "free_gb": free_gb(path), "same": _norm(path) == _norm(cur)}
    if res["same"]:
        return res
    base = _existing(path)
    if not base or not os.path.isdir(base):
        return {"ok": False, "error": "bad_path"}
    # Своя проба вместо tempfile: на Windows mkdtemp при отказе в доступе крутит до 10000 попыток.
    probe = os.path.join(base, f".localai-{os.getpid()}-{int(time.time() * 1000)}")
    try:
        os.mkdir(probe)
        os.rmdir(probe)
    except OSError:
        return {"ok": False, "error": "not_writable"}
    if kind == "models":
        if _inside(path, cur) or _inside(cur, path):
            return {"ok": False, "error": "nested"}
        count, size = (len(_demo["models"]), sum(m["size"] for m in _demo["models"])) if DEMO else models_usage(cur)
        res["old"] = {"path": cur, "count": count, "gb": round(size, 2)}
    return res


def paths():
    e, m = engine_dir(), models_dir()
    return {"engine": {"path": e, "free_gb": free_gb(e)},
            "models": {"path": m, "free_gb": free_gb(m)}, "same_drive": same_drive(e, m)}


def set_models_dir(path, move):
    """Сменить папку моделей. move — перенести старые (задача с прогрессом), иначе просто переключить."""
    if move:
        return _start(lambda: Job(["move"], None, "move", target=path))
    if _job and _job.state == "running":
        return False
    if DEMO:
        _demo["models"], _demo["models_dir"] = [], path
    else:
        _switch_models_dir(path)
        if find_exe():
            ensure_running()
    save_settings(models_dir=path)
    return True


def set_engine_dir(path):
    """Ollama ещё нет — просто запоминаем папку; есть — переустанавливаем туда (модели не трогаем)."""
    if not status()["installed"]:
        save_settings(engine_dir=path)
        return True
    return _start(lambda: Job(["engine"], None, "update", target=path))


def _switch_models_dir(path):
    kill_ollama()
    os.makedirs(path, exist_ok=True)
    _set_user_env("OLLAMA_MODELS", None if _norm(path) == _norm(DEFAULT_MODELS_DIR) else path)
    _show_cache.clear()


# ---------- состояние движка ----------
def _kill_by_name(names):
    """Завершить процессы по имени файла через WinAPI: taskkill /IM на этом ПК их не видит (сломан WMI)."""
    import ctypes
    from ctypes import wintypes

    class Entry(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]

    k32 = ctypes.windll.kernel32
    k32.CreateToolhelp32Snapshot.restype = k32.OpenProcess.restype = wintypes.HANDLE
    k32.Process32FirstW.argtypes = k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    for a in ("TerminateProcess", "WaitForSingleObject", "CloseHandle"):
        getattr(k32, a).argtypes = [wintypes.HANDLE] + ([wintypes.UINT] if a == "TerminateProcess" else
                                                        [wintypes.DWORD] if a == "WaitForSingleObject" else [])
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)   # TH32CS_SNAPPROCESS
    pids, e = [], Entry()
    e.dwSize = ctypes.sizeof(Entry)
    ok = k32.Process32FirstW(snap, ctypes.byref(e))
    while ok:
        if e.szExeFile.lower() in names:
            pids.append((names.index(e.szExeFile.lower()), e.th32ProcessID))
        ok = k32.Process32NextW(snap, ctypes.byref(e))
    k32.CloseHandle(snap)
    for _, pid in sorted(pids):   # сначала трей, иначе он перезапустит сервер
        h = k32.OpenProcess(0x0001 | 0x00100000, False, pid)   # PROCESS_TERMINATE | SYNCHRONIZE
        if h:
            k32.TerminateProcess(h, 1)
            k32.WaitForSingleObject(h, 3000)
            k32.CloseHandle(h)
    return len(pids)


def kill_ollama():
    """Трей «ollama app.exe», сервер и процессы-раннеры (держат видеопамять).
    Под тем же замком, что и запуск: иначе идущий запуск оживит движок сразу после остановки."""
    with _start_lock:
        _kill_by_name(["ollama app.exe", "ollama.exe", "ollama_llama_server.exe"])
        end = time.time() + 5
        while _port_open() and time.time() < end:
            time.sleep(0.2)


def shutdown(wait=900):
    """Закрытие программы: отменяем задачу и ждём её конца (установщик Ollama прервать нельзя), потом гасим Ollama."""
    global _shutting
    _shutting = True
    job = _job
    if job and job.state == "running":
        cancel()
        end = time.time() + wait
        while job.state == "running" and time.time() < end:
            time.sleep(0.3)
    if not DEMO:
        kill_ollama()


def _port_open():
    # На Windows отказ в соединении приходит только через ~2 с повторов SYN — быстрый пробный connect.
    try:
        socket.create_connection(("127.0.0.1", 11434), timeout=0.3).close()
        return True
    except OSError:
        return False


def api_up():
    if not _port_open():
        return False
    try:
        urllib.request.urlopen(BASE + "/api/version", timeout=1.5).read()
        return True
    except Exception:
        return False


def status():
    if DEMO:
        return {"installed": _demo["engine"], "running": _demo["engine"]}
    up = api_up()
    return {"installed": up or bool(find_exe()), "running": up}


_start_lock = threading.Lock()


def ensure_running(timeout=40, own=False):
    """own — вызов из самой задачи. Чужим вызовам (чат, состояние) нельзя поднимать движок, пока задача
    его намеренно остановила: при переносе он запустится со старой папкой, при установке — займёт файлы."""
    if DEMO or api_up():
        return True
    with _start_lock:   # состояние и чат могут спросить одновременно — запускаем один сервер
        if api_up():
            return True
        if not own and (_shutting or (_job and _job.state == "running"
                                      and (_job.step in ("engine", "move") or _job.kind == "uninstall"))):
            return False
        exe = find_exe()
        if not exe:
            return False
        # Только NO_WINDOW: с DETACHED_PROCESS у serve нет консоли, и каждый его дочерний ollama/llama-server
        # (раннер модели) получает собственное чёрное окно. Со скрытой консолью дети наследуют её.
        subprocess.Popen([exe, "serve"], creationflags=NO_WINDOW,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        end = time.time() + timeout
        while time.time() < end:
            if api_up():
                return True
            time.sleep(0.5)
        return False


def wake():
    """Мы гасим Ollama при выходе, значит, при запуске поднимаем её сами — иначе список моделей пуст."""
    if not api_up() and find_exe():
        ensure_running()


def _tags():
    if not _port_open():
        return []
    try:
        return json.load(urllib.request.urlopen(BASE + "/api/tags", timeout=5)).get("models", [])
    except Exception:
        return []


def models():
    import catalog
    if DEMO:
        return [dict(m, caps=catalog.BY_ID.get(m["id"], {}).get("caps", ["text"])) for m in _demo["models"]]
    out = []
    for m in _tags():
        # Старые версии Ollama не отдают capabilities в /api/tags — тогда берём из /api/show.
        oc = m.get("capabilities") or show(m["name"], m.get("digest", "")).get("capabilities", [])
        out.append({"id": m["name"], "size": round(m.get("size", 0) / 1024 ** 3, 2),
                    "digest": m.get("digest", ""), "caps": catalog.caps_from_ollama(m["name"], oc)})
    return out


def show(name, digest=""):
    key = (name, digest)
    if key not in _show_cache:
        try:
            req = urllib.request.Request(BASE + "/api/show", data=json.dumps({"model": name}).encode(),
                                         headers={"Content-Type": "application/json"})
            _show_cache[key] = json.load(urllib.request.urlopen(req, timeout=10))
        except Exception:
            return {}
    return _show_cache[key]


def caps(name):
    return next((m["caps"] for m in models() if m["id"] == name), [])


def version():
    if DEMO:
        return _demo["version"] if _demo["engine"] else ""
    if not _port_open():
        return ""
    try:
        return json.load(urllib.request.urlopen(BASE + "/api/version", timeout=3)).get("version", "")
    except Exception:
        return ""


def _where(p):
    """Где работает загруженная модель: по доле весов в видеопамяти из /api/ps."""
    size, vram = p.get("size") or 0, p.get("size_vram") or 0
    if not size:
        return None
    pct = round(vram * 100 / size)
    return {"mode": "gpu" if pct >= 99 else "cpu" if vram == 0 else "mixed", "vram_pct": pct,
            "ctx": p.get("context_length") or 0}


def loaded(name):
    """Модель уже в памяти (по /api/ps)? Если нет, первый ответ начнётся только после её загрузки."""
    if not _port_open():
        return False
    try:
        ps = json.load(urllib.request.urlopen(BASE + "/api/ps", timeout=3)).get("models", [])
    except Exception:
        return False
    return any(name in (p.get("name"), p.get("model")) for p in ps)


def model_info(name):
    import catalog
    if DEMO:
        m = next((m for m in _demo["models"] if m["id"] == name), None)
        if not m:
            return None
        return {"id": name, "size": m["size"], "params": "8.2B", "quant": "Q4_K_M", "family": name.split(":")[0],
                "ctx_max": 40960, "caps": catalog.BY_ID.get(name, {}).get("caps", ["text"]),
                "where": {"mode": "gpu", "vram_pct": 100, "ctx": 4096}, "version": version()}
    tag = next((m for m in _tags() if m["name"] == name), None)
    if not tag:
        return None
    sh = show(name, tag.get("digest", ""))
    mi, det = sh.get("model_info") or {}, sh.get("details") or tag.get("details") or {}
    arch = mi.get("general.architecture", "")
    ps = []
    try:
        ps = json.load(urllib.request.urlopen(BASE + "/api/ps", timeout=3)).get("models", [])
    except Exception:
        pass
    loaded = next((p for p in ps if name in (p.get("name"), p.get("model"))), None)
    return {"id": name, "size": round(tag.get("size", 0) / 1024 ** 3, 2),
            "params": det.get("parameter_size", ""), "quant": det.get("quantization_level", ""),
            "family": det.get("family", ""),
            "ctx_max": mi.get(f"{arch}.context_length") or (tag.get("details") or {}).get("context_length") or 0,
            "caps": catalog.caps_from_ollama(name, tag.get("capabilities") or sh.get("capabilities", [])),
            "where": _where(loaded) if loaded else None, "version": version()}


# ---------- обновления ----------
def _ver(v):
    return tuple(int(p) if p.isdigit() else 0 for p in v.lstrip("v").split("-")[0].split("."))


def latest_version():
    if DEMO:
        return _demo["latest"]
    data = json.load(urllib.request.urlopen(urllib.request.Request(RELEASES_URL, headers=UA), timeout=10))
    return data.get("tag_name", "").lstrip("v")


def _manifest_url(name):
    """qwen3:8b → .../v2/library/qwen3/manifests/8b. Модели с других хостов (hf.co и т. п.) не проверяем."""
    repo, _, tag = name.partition(":")
    parts = repo.split("/")
    if len(parts) > 1 and "." in parts[0]:
        if parts[0] != "registry.ollama.ai":
            return None
        parts = parts[1:]
    if len(parts) == 1:
        parts = ["library"] + parts
    return f"{REGISTRY}/v2/{'/'.join(parts)}/manifests/{tag or 'latest'}"


def registry_digest(name):
    """digest модели в Ollama = sha256 её манифеста в реестре (проверено на qwen3:8b)."""
    url = _manifest_url(name)
    if not url:
        return None
    body = urllib.request.urlopen(urllib.request.Request(url, headers=dict(UA, Accept=MANIFEST)), timeout=10).read()
    return hashlib.sha256(body).hexdigest()


def check_updates():
    cur = version()
    res = {"engine": {"current": cur, "latest": "", "available": False}, "models": {}}
    try:
        latest = latest_version()
        res["engine"].update(latest=latest, available=bool(cur and latest and _ver(latest) > _ver(cur)))
    except Exception as e:  # noqa: BLE001
        res["engine"]["error"] = str(e)
    for m in models():
        if DEMO:
            res["models"][m["id"]] = {"available": m["id"] not in _demo["fresh"], "checked": True}
            continue
        try:
            remote = registry_digest(m["id"])
            res["models"][m["id"]] = {"available": bool(remote and m["digest"] and remote != m["digest"]),
                                      "checked": remote is not None}
        except Exception as e:  # noqa: BLE001
            res["models"][m["id"]] = {"available": False, "checked": False, "error": str(e)}
    return res


def delete_model(name):
    if DEMO:
        _demo["models"] = [m for m in _demo["models"] if m["id"] != name]
        return True
    req = urllib.request.Request(BASE + "/api/delete", method="DELETE",
                                 data=json.dumps({"name": name}).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=30).read()
        return True
    except Exception:
        return False


# ---------- задача установки ----------
class Job:
    def __init__(self, steps, model, kind="install", target=None):
        self.steps, self.model, self.kind = steps, model, kind   # kind: install | update | move | uninstall
        self.target = target        # новая папка: движка (переустановка) или моделей (перенос); у uninstall — что удалять
        self.step = steps[0] if steps else "done"
        self.phase = ""
        self.percent = 0.0
        self.done_b = self.total_b = 0
        self.speed = 0.0
        self.state = "running"      # running | done | error | cancelled
        self.error = ""
        self.cancel = False
        self._resp = None
        self._mark = (time.time(), 0)

    def tick(self, done, total):
        self.done_b, self.total_b = done, total
        self.percent = round(done * 100 / total, 1) if total else 0.0
        now = time.time()
        t0, b0 = self._mark
        if now - t0 >= 1:
            self.speed = max(0.0, (done - b0) / (now - t0))
            self._mark = (now, done)

    def begin(self, step, phase):
        self.step, self.phase = step, phase
        self.percent, self.done_b, self.total_b, self.speed = 0.0, 0, 0, 0.0
        self._mark = (time.time(), 0)

    def dump(self):
        return {"steps": self.steps, "step": self.step, "phase": self.phase, "model": self.model, "kind": self.kind,
                "percent": self.percent, "done": self.done_b, "total": self.total_b,
                "speed": self.speed, "state": self.state, "error": self.error, "target": self.target}


class Cancelled(Exception):
    pass


_job = None
_lock = threading.Lock()


def current_job():
    return _job.dump() if _job else None


def _start(make_job):
    global _job
    with _lock:
        if _job and _job.state == "running":
            return False
        _job = make_job()
    threading.Thread(target=_run, args=(_job,), daemon=True).start()
    return True


def start_setup(model):
    """Ставит движок (если нет) и скачивает модель. Возвращает False, если задача уже идёт."""
    return _start(lambda: Job((["engine"] if not status()["installed"] else []) + ["model"], model))


def start_update(model=None):
    """Без model — обновить Ollama тем же установщиком; с model — повторный pull (качаются только изменённые слои)."""
    return _start(lambda: Job(["model"] if model else ["engine"], model, "update"))


def cancel(job=None):
    job = job or _job
    if job and job.state == "running":
        job.cancel = True
        try:
            if job._resp:
                job._resp.close()
        except Exception:
            pass


def _check(job):
    if job.cancel:
        raise Cancelled()


def _run(job):
    try:
        if job.kind == "uninstall":
            _uninstall(job)
            job.state, job.step, job.percent = "done", "done", 100.0
            return
        if "move" in job.steps:
            _move_models(job)
        if "engine" in job.steps:
            _install_engine(job, update=job.kind == "update")
        _check(job)
        if "model" in job.steps:
            job.begin("model", "start")
            if not ensure_running(own=True):
                raise RuntimeError("engine_not_running")
            _pull(job)
        job.state, job.step, job.percent = "done", "done", 100.0
    except Cancelled:
        job.state = "cancelled"
    except Exception as e:  # noqa: BLE001 — показываем причину пользователю
        job.state, job.error = ("cancelled", "") if job.cancel else ("error", str(e) or e.__class__.__name__)


def _install_engine(job, update=False):
    # Своя папка: при переносе — job.target, при первой установке — из настроек; обычное обновление — на месте.
    old = engine_dir() if job.target else None
    known = {_norm(d) for d in (DEFAULT_ENGINE_DIR, _registry_engine_dir(), settings().get("engine_dir")) if d}
    target =job.target or (None if update else settings().get("engine_dir"))
    job.begin("engine", "download")
    if DEMO:
        total = 1100 * 1024 ** 2
        for i in range(1, 41):
            _check(job)
            job.tick(total * i // 40, total)
            time.sleep(0.08)
        job.begin("engine", "install")
        time.sleep(1.5)
        _demo["engine"] = True
        if job.target:
            save_settings(engine_dir=job.target)
        elif update:
            _demo["version"] = _demo["latest"]
        return
    # Постоянное место во %TEMP%: после отмены/обрыва докачиваем .part через Range.
    folder = os.path.join(tempfile.gettempdir(), "LocalAI")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "OllamaSetup.exe")
    part = path + ".part"
    if update:
        # Недокачанный файл мог остаться от прошлой версии — для обновления качаем заново.
        for f in (path, part):
            if os.path.exists(f):
                os.remove(f)
    if not os.path.exists(path):
        _download(job, part)
        os.replace(part, path)
    # Подпись должна быть действительной и выданной именно Ollama, иначе файл удаляем.
    sig = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"$s = Get-AuthenticodeSignature -LiteralPath '{path}'; \"$($s.Status)|$($s.SignerCertificate.Subject)\""],
        capture_output=True, text=True, creationflags=NO_WINDOW).stdout.strip()
    state_, _, subject = sig.partition("|")
    if state_ != "Valid" or "O=Ollama" not in subject:
        os.remove(path)
        raise RuntimeError(f"bad_signature:{state_ or 'unknown'}")
    job.begin("engine", "install")
    if update:
        # Запущенный движок держит свои файлы — останавливаем; после установки он стартует снова.
        kill_ollama()
    cmd = f'"{path}" /VERYSILENT /NORESTART /SUPPRESSMSGBOXES'
    if target:
        cmd += f' /DIR="{target if len(target) <= 3 else target.rstrip(chr(92) + "/")}"'
    subprocess.run(cmd, timeout=900, creationflags=NO_WINDOW)
    if not (os.path.exists(os.path.join(target, "ollama.exe")) if target else find_exe()):
        raise RuntimeError("engine_install_failed")
    os.remove(path)
    if target:
        save_settings(engine_dir=target)
    # Перенос: старую копию удаляем, только если это точно была папка установки Ollama.
    if old and _norm(old) != _norm(target) and not _inside(target, old) and _norm(old) in known \
            and os.path.exists(os.path.join(old, "ollama app.exe")):
        shutil.rmtree(old, ignore_errors=True)
    threading.Thread(target=_hide_ollama_window, daemon=True).start()
    if update and not ensure_running(own=True):
        raise RuntimeError("engine_not_running")


def _hide_ollama_window(timeout=30):
    """Установщик сам запускает «ollama app.exe», и тот открывает своё окно поверх нашего.
    WM_CLOSE убирает его в трей, движок при этом продолжает работать."""
    import ctypes
    from ctypes import wintypes
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    found = []

    def image(hwnd):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        h = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return ""
        buf, size = ctypes.create_unicode_buffer(1024), wintypes.DWORD(1024)
        ok = kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
        kernel32.CloseHandle(h)
        return os.path.basename(buf.value).lower() if ok else ""

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _):
        if user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd) and image(hwnd) == "ollama app.exe":
            found.append(hwnd)
        return True

    end = time.time() + timeout
    while time.time() < end and not found:
        user32.EnumWindows(visit, 0)
        time.sleep(0.5)
    for hwnd in found:
        user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE


def _move_models(job):
    """Перенос моделей в job.target: Ollama стоп → blobs/manifests на новое место (на том же диске — мгновенно)
    → OLLAMA_MODELS → запуск. При отмене или ошибке всё возвращается, старая папка остаётся рабочей."""
    src, dst = models_dir(), job.target
    job.begin("move", "stop")
    if DEMO:
        total = int(sum(m["size"] for m in _demo["models"]) * 1024 ** 3) or 1
        job.phase = "copy"
        for i in range(1, 31):
            _check(job)
            job.tick(total * i // 30, total)
            time.sleep(0.08)
        job.begin("move", "restart")
        time.sleep(0.8)
        _demo["models_dir"] = dst
        save_settings(models_dir=dst)
        return
    files, subs = [], _store_dirs(src)
    for sub in subs:
        for root, _, names in os.walk(os.path.join(src, sub)):
            for n in names:
                s = os.path.join(root, n)
                files.append((s, os.path.join(dst, os.path.relpath(s, src)), os.path.getsize(s)))
    total = sum(f[2] for f in files) or 1
    fast = same_drive(src, dst)
    if not fast and free_gb(dst) * 1024 ** 3 < total + 512 * 1024 ** 2:
        raise RuntimeError("no_space")
    kill_ollama()
    moved, copied, done = [], [], 0
    job.phase = "copy"
    try:
        for s, d, size in files:
            _check(job)
            os.makedirs(os.path.dirname(d), exist_ok=True)
            if os.path.exists(d) and os.path.getsize(d) == size:
                pass   # такой слой уже лежит в новой папке
            elif fast:
                os.replace(s, d)
                moved.append((s, d))
            else:
                copied.append(d)
                _copy(job, s, d, done, total)
            done += size
            job.tick(done, total)
        job.begin("move", "restart")
        _switch_models_dir(dst)
        save_settings(models_dir=dst)
    except BaseException:
        for s, d in moved:
            try:
                os.replace(d, s)
            except OSError:
                pass
        for d in copied:
            for f in (d, d + ".part"):
                if os.path.exists(f):
                    os.remove(f)
        if not _shutting:
            ensure_running(own=True)
        raise
    for sub in subs:
        shutil.rmtree(os.path.join(src, sub), ignore_errors=True)
    if not ensure_running(own=True):
        raise RuntimeError("engine_not_running")


def _copy(job, src, dst, base, total):
    with open(src, "rb") as fi, open(dst + ".part", "wb") as fo:
        while True:
            _check(job)
            chunk = fi.read(8 << 20)
            if not chunk:
                break
            fo.write(chunk)
            base += len(chunk)
            job.tick(base, total)
    os.replace(dst + ".part", dst)


def _download(job, part):
    done = os.path.getsize(part) if os.path.exists(part) else 0
    headers = dict(UA, **({"Range": f"bytes={done}-"} if done else {}))
    try:
        resp = urllib.request.urlopen(urllib.request.Request(SETUP_URL, headers=headers), timeout=30)
    except urllib.error.HTTPError as e:
        if e.code == 416 and done:  # .part уже целый; если нет — его отбракует проверка подписи
            return
        raise
    job._resp = resp
    if resp.status != 206:
        done = 0
    total = done + int(resp.headers.get("Content-Length") or 0)
    with open(part, "ab" if done else "wb") as f:
        while True:
            _check(job)
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            job.tick(done, total)
    job._resp = None
    if total and done != total:
        raise RuntimeError("download_incomplete")


def _pull(job):
    job.phase = "download"
    if DEMO:
        size = next((m for m in __import__("catalog").MODELS if m["id"] == job.model), {"size": 2})["size"]
        total = int(size * 1024 ** 3)
        for i in range(1, 51):
            _check(job)
            job.tick(total * i // 50, total)
            time.sleep(0.1)
        job.phase = "verify"
        time.sleep(1)
        if not any(m["id"] == job.model for m in _demo["models"]):
            _demo["models"].append({"id": job.model, "size": size})
        _demo["fresh"].add(job.model)
        return
    req = urllib.request.Request(BASE + "/api/pull", headers={"Content-Type": "application/json"},
                                 data=json.dumps({"name": job.model, "stream": True}).encode())
    # Пока Ollama считает sha256 большого слоя, строк нет минутами (особенно на HDD).
    resp = urllib.request.urlopen(req, timeout=900)
    job._resp = resp
    layers = {}
    for line in resp:
        _check(job)
        msg = json.loads(line)
        if msg.get("error"):
            raise RuntimeError(msg["error"])
        status_ = msg.get("status", "")
        if msg.get("total"):
            layers[status_] = (msg.get("completed", 0), msg["total"])
            job.phase = "download"
            job.tick(sum(c for c, _ in layers.values()), sum(t for _, t in layers.values()))
        elif status_.startswith(("verifying", "writing")):
            job.phase = "verify"
        elif status_ == "success":
            break
    job._resp = None


# ---------- полное удаление ----------
UNINSTALL_PARTS = ("models", "engine", "app")
OLLAMA_HOME = os.path.dirname(DEFAULT_MODELS_DIR)                     # ~/.ollama: ключи, история, модели
OLLAMA_DATA = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Ollama")   # логи и настройки трея
STARTUP_LNK = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup\Ollama.lnk")


def _app_exe():
    """Сам LocalAI.exe — только у собранной программы; при запуске из исходников удалять нечего."""
    import sys
    return sys.executable if getattr(sys, "frozen", False) else ""


def uninstall_info():
    m = models_dir()
    count, gb = (len(_demo["models"]), round(sum(x["size"] for x in _demo["models"]), 2)) if DEMO else models_usage(m)
    return {"models": {"path": m, "count": count, "gb": gb},
            "engine": {"path": engine_dir(), "installed": status()["installed"]},
            "app": {"data": DATA_DIR, "exe": _app_exe()}}


def start_uninstall(parts):
    """Полное удаление: parts — что удалять из UNINSTALL_PARTS. Идущую задачу отменяем и ждём её конца."""
    global _job
    parts = [p for p in UNINSTALL_PARTS if p in parts]
    if not parts:
        return False
    with _lock:
        if _job and _job.state == "running" and _job.kind == "uninstall":
            return False
        prev, job = _job, Job(["u_stop"] + ["u_" + p for p in parts], None, "uninstall", target=parts)
        _job = job

    def run():
        if prev and prev.state == "running":
            cancel(prev)
            end = time.time() + 900   # установщик Ollama прервать нельзя — ждём
            while prev.state == "running" and time.time() < end:
                time.sleep(0.3)
        _run(job)
    threading.Thread(target=run, daemon=True).start()
    return True


def _rm_tree_progress(job, dirs):
    """Удалить папки целиком, двигая прогресс по объёму удалённых файлов."""
    files = [os.path.join(r, n) for d in dirs for r, _, ns in os.walk(d) for n in ns]
    sizes = {}
    for f in files:
        try:
            sizes[f] = os.path.getsize(f)
        except OSError:
            sizes[f] = 0
    total, done = sum(sizes.values()) or 1, 0
    job.phase = "delete"
    for f in files:
        try:
            os.remove(f)
        except OSError:
            pass
        done += sizes[f]
        job.tick(done, total)
    for d in dirs:
        shutil.rmtree(d, ignore_errors=True)
    left = [d for d in dirs if os.path.exists(d)]
    if left:
        raise RuntimeError("delete_failed:" + left[0])


def _rmdir_if_empty(path):
    try:
        os.rmdir(path)
    except OSError:
        pass


def _uninstall(job):
    parts = job.target
    job.begin("u_stop", "stop")
    if DEMO:   # имитация: на диске ничего не трогаем
        time.sleep(0.8)
        if "models" in parts:
            job.begin("u_models", "delete")
            total = int(sum(m["size"] for m in _demo["models"]) * 1024 ** 3) or 1
            for i in range(1, 26):
                job.tick(total * i // 25, total)
                time.sleep(0.06)
            _demo["models"] = []
        if "engine" in parts:
            job.begin("u_engine", "uninstall")
            time.sleep(1.5)
            _demo["engine"] = False
        if "app" in parts:
            job.begin("u_app", "cleanup")
            time.sleep(0.8)
        return
    kill_ollama()
    mdir, edir = models_dir(), engine_dir()
    if "models" in parts:
        # Только служебные папки Ollama; чужие файлы в папке моделей остаются.
        job.begin("u_models", "delete")
        _rm_tree_progress(job, [os.path.join(mdir, d) for d in _store_dirs(mdir)])
        _rmdir_if_empty(mdir)
        _set_user_env("OLLAMA_MODELS", None)
    if "engine" in parts:
        job.begin("u_engine", "uninstall")
        _uninstall_ollama(edir, keep=None if "models" in parts else mdir)
    if "app" not in parts:
        save_settings(**{k: None for k, p in (("models_dir", "models"), ("engine_dir", "engine")) if p in parts})
        return
    job.begin("u_app", "cleanup")
    shutil.rmtree(os.path.join(tempfile.gettempdir(), "LocalAI"), ignore_errors=True)   # скачанный установщик
    _schedule_self_delete()


def _uninstall_ollama(edir, keep):
    """Штатный деинсталлятор Ollama (Inno Setup), затем остатки. keep — папка моделей, которую надо сохранить:
    деинсталлятор Ollama сам стирает ~/.ollama/models, поэтому на время убираем её в сторону."""
    unins = os.path.join(edir, "unins000.exe")
    if not os.path.exists(unins):
        s = (_registry_engine_dir("UninstallString") or "").strip().strip('"')
        unins = s if s.lower().endswith(".exe") and os.path.exists(s) else ""
    known = {_norm(d) for d in (DEFAULT_ENGINE_DIR, _registry_engine_dir(), settings().get("engine_dir")) if d}
    aside = None
    if keep and os.path.isdir(keep) and (_inside(keep, OLLAMA_HOME) or _inside(keep, edir)):
        aside = os.path.join(os.path.dirname(edir) if _inside(keep, edir) else os.path.dirname(OLLAMA_HOME),
                             f".localai-keep-models-{os.getpid()}")
        os.replace(keep, aside)
    try:
        if unins:
            subprocess.run([unins, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], timeout=600, creationflags=NO_WINDOW)
            # Inno перезапускает себя из %TEMP% и сразу возвращает управление — ждём, пока файлы исчезнут.
            end = time.time() + 300
            while time.time() < end and (os.path.exists(os.path.join(edir, "ollama.exe"))
                                         or _registry_engine_dir("UninstallString")):
                time.sleep(1)
        elif os.path.exists(os.path.join(edir, "ollama.exe")) and _norm(edir) not in known:
            raise RuntimeError("no_uninstaller")   # чужая папка без деинсталлятора — стирать вслепую не будем
        # Остатки: папка движка (только известная папка установки), данные трея, автозапуск, ~/.ollama.
        if os.path.isdir(edir) and _norm(edir) in known:
            shutil.rmtree(edir, ignore_errors=True)
        shutil.rmtree(OLLAMA_DATA, ignore_errors=True)
        if os.path.exists(STARTUP_LNK):
            os.remove(STARTUP_LNK)
        for f in ("id_ed25519", "id_ed25519.pub", "history"):
            p = os.path.join(OLLAMA_HOME, f)
            if os.path.isfile(p):
                os.remove(p)
    finally:
        if aside:
            os.makedirs(os.path.dirname(keep), exist_ok=True)
            os.replace(aside, keep)
    _rmdir_if_empty(os.path.join(OLLAMA_HOME, "models"))
    _rmdir_if_empty(OLLAMA_HOME)
    if os.path.exists(os.path.join(edir, "ollama.exe")):
        raise RuntimeError("engine_uninstall_failed")


def _schedule_self_delete():
    """Программа не может удалить себя на ходу: скрытый PowerShell ждёт выхода наших процессов
    (onefile: загрузчик-родитель и python-потомок), затем стирает exe, %APPDATA%\\LocalAI, распаковку _MEI и себя."""
    import sys
    pids = [os.getpid()] + ([os.getppid()] if getattr(sys, "frozen", False) else [])
    targets = [DATA_DIR] + [p for p in (_app_exe(), getattr(sys, "_MEIPASS", "")) if p]
    q = lambda s: "'" + s.replace("'", "''") + "'"   # noqa: E731 — строка PowerShell
    script = os.path.join(tempfile.gettempdir(), f"localai-uninstall-{os.getpid()}.ps1")
    body = "\n".join([
        "$ErrorActionPreference = 'SilentlyContinue'",
        f"foreach ($id in @({','.join(map(str, pids))})) {{ Wait-Process -Id $id }}",
        "Start-Sleep -Seconds 1",
        f"$targets = @({','.join(q(t) for t in targets)})",
        # Профиль WebView2/Edge освобождается не сразу после выхода — несколько попыток.
        "for ($i = 0; $i -lt 30; $i++) {",
        "  $left = @($targets | Where-Object { Test-Path -LiteralPath $_ })",
        "  if ($left.Count -eq 0) { break }",
        "  foreach ($t in $left) { Remove-Item -LiteralPath $t -Recurse -Force }",
        "  Start-Sleep -Seconds 1",
        "}",
        "Remove-Item -LiteralPath $MyInvocation.MyCommand.Path -Force",
    ])
    with open(script, "w", encoding="utf-8-sig") as f:   # BOM: PowerShell 5.1 иначе портит кириллицу в путях
        f.write(body)
    # Без DETACHED: PowerShell без консоли сразу выходит. BREAKAWAY — чтобы не погиб вместе с job-объектом родителя
    # (если job его не разрешает, запускаем без него).
    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", script]
    for flags in (NO_WINDOW | 0x01000000, NO_WINDOW):   # CREATE_BREAKAWAY_FROM_JOB
        try:
            subprocess.Popen(cmd, creationflags=flags, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, close_fds=True)
            return
        except OSError:
            continue
    raise RuntimeError("cleanup_failed")
