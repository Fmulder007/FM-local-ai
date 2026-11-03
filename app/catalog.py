"""Каталог моделей Ollama и подбор под железо. Размеры — по реестру Ollama (ГБ)."""

# Порядок = по размеру. fast_cpu — MoE, быстро и на CPU. alt — дополнительные модели: показываем в каталоге,
# но сами не советуем (рекомендация — из линеек Qwen3/Gemma 3).
# caps — что умеет модель (как в Ollama /api/show → capabilities): text, code, think, vision, tools.
# Размеры (ГиБ) и возможности сверены с registry.ollama.ai: сумма слоёв манифеста, .Tools/.Think в шаблоне,
# слой projector или мультимодальная архитектура (qwen25vl, mistral3) — vision.
# Рисовать картинки и делать видео локальные модели Ollama не умеют — в интерфейсе это «нет» у всех.
QWEN = ["text", "code", "think", "tools"]
GEMMA = ["text", "code", "vision"]
TOOLS = ["text", "code", "tools"]
R1 = ["text", "code", "think"]
MODELS = [
    {"id": "qwen2.5-coder:1.5b", "title": "Qwen2.5 Coder 1.5B", "size": 0.92, "caps": TOOLS, "tag": "coder", "alt": True},
    {"id": "deepseek-r1:1.5b", "title": "DeepSeek-R1 1.5B", "size": 1.04, "caps": R1, "tag": "reason", "alt": True},
    {"id": "llama3.2:1b",  "title": "Llama 3.2 1B",  "size": 1.23, "caps": TOOLS, "tag": "tiny", "alt": True},
    {"id": "gemma3:1b",   "title": "Gemma 3 1B",   "size": 0.75, "caps": ["text"], "tag": "tiny"},
    {"id": "qwen3:1.7b",  "title": "Qwen3 1.7B",   "size": 1.27, "caps": QWEN,  "tag": "tiny"},
    {"id": "llama3.2:3b",  "title": "Llama 3.2 3B",  "size": 1.88, "caps": TOOLS, "tag": "light", "alt": True},
    {"id": "phi4-mini:3.8b", "title": "Phi-4 mini 3.8B", "size": 2.32, "caps": TOOLS, "tag": "light", "alt": True},
    {"id": "qwen3:4b",    "title": "Qwen3 4B",     "size": 2.33, "caps": QWEN,  "tag": "light"},
    {"id": "qwen2.5vl:3b", "title": "Qwen2.5-VL 3B", "size": 2.98, "caps": ["text", "vision"], "tag": "vision", "alt": True},
    {"id": "gemma3:4b",   "title": "Gemma 3 4B",   "size": 3.12, "caps": GEMMA, "tag": "light"},
    {"id": "mistral:7b",   "title": "Mistral 7B",    "size": 4.07, "caps": TOOLS, "tag": "light", "alt": True},
    {"id": "qwen2.5-coder:7b", "title": "Qwen2.5 Coder 7B", "size": 4.36, "caps": TOOLS, "tag": "coder", "alt": True},
    {"id": "llava:7b",     "title": "LLaVA 7B",      "size": 4.41, "caps": ["text", "vision"], "tag": "vision", "alt": True},
    {"id": "llama3.1:8b",  "title": "Llama 3.1 8B",  "size": 4.58, "caps": TOOLS, "tag": "balanced", "alt": True},
    {"id": "qwen3:8b",    "title": "Qwen3 8B",     "size": 4.87, "caps": QWEN,  "tag": "balanced"},
    {"id": "deepseek-r1:8b", "title": "DeepSeek-R1 8B", "size": 4.87, "caps": R1, "tag": "reason", "alt": True},
    {"id": "qwen2.5vl:7b", "title": "Qwen2.5-VL 7B", "size": 5.56, "caps": ["text", "vision"], "tag": "vision", "alt": True},
    {"id": "mistral-nemo:12b", "title": "Mistral Nemo 12B", "size": 6.59, "caps": TOOLS, "tag": "smart", "alt": True},
    {"id": "gemma3n:e2b", "title": "Gemma 3n E2B", "size": 7.30, "caps": ["text", "code"], "tag": "compact", "alt": True},
    {"id": "gemma3:12b",  "title": "Gemma 3 12B",  "size": 7.60, "caps": GEMMA, "tag": "smart"},
    {"id": "qwen2.5-coder:14b", "title": "Qwen2.5 Coder 14B", "size": 8.37, "caps": TOOLS, "tag": "coder", "alt": True},
    {"id": "deepseek-r1:14b", "title": "DeepSeek-R1 14B", "size": 8.37, "caps": R1, "tag": "reason", "alt": True},
    {"id": "phi4:14b",     "title": "Phi-4 14B",     "size": 8.43, "caps": ["text", "code"], "tag": "smart", "alt": True},
    {"id": "qwen3:14b",   "title": "Qwen3 14B",    "size": 8.64, "caps": QWEN,  "tag": "smart"},
    {"id": "gemma3n:e4b", "title": "Gemma 3n E4B", "size": 9.10, "caps": ["text", "code"], "tag": "compact", "alt": True},
    {"id": "gpt-oss:20b",  "title": "gpt-oss 20B",   "size": 12.85, "caps": ["text", "code", "think", "tools"], "tag": "reason", "alt": True, "fast_cpu": True},
    {"id": "mistral-small3.2:24b", "title": "Mistral Small 3.2 24B", "size": 14.14, "caps": ["text", "code", "vision", "tools"], "tag": "pro", "alt": True},
    {"id": "gemma3:27b",  "title": "Gemma 3 27B",  "size": 16.22, "caps": GEMMA, "tag": "pro"},
    {"id": "qwen3:30b",   "title": "Qwen3 30B-A3B", "size": 17.28, "caps": QWEN, "tag": "pro", "fast_cpu": True},
    {"id": "qwen3-coder:30b", "title": "Qwen3 Coder 30B-A3B", "size": 17.28, "caps": TOOLS, "tag": "coder", "alt": True, "fast_cpu": True},
    {"id": "qwen2.5-coder:32b", "title": "Qwen2.5 Coder 32B", "size": 18.49, "caps": TOOLS, "tag": "coder", "alt": True},
    {"id": "deepseek-r1:32b", "title": "DeepSeek-R1 32B", "size": 18.49, "caps": R1, "tag": "reason", "alt": True},
    {"id": "qwen3:32b",   "title": "Qwen3 32B",    "size": 18.81, "caps": QWEN, "tag": "pro", "alt": True},
    {"id": "qwen2.5vl:32b", "title": "Qwen2.5-VL 32B", "size": 19.71, "caps": ["text", "vision"], "tag": "vision", "alt": True},
]
MODELS.sort(key=lambda m: m["size"])
BY_ID = {m["id"]: m for m in MODELS}

_FROM_OLLAMA = {"completion": "text", "thinking": "think", "vision": "vision", "tools": "tools"}


def caps_from_ollama(name, ollama_caps):
    """capabilities из Ollama → наши значки. «Код» Ollama не сообщает: берём из каталога, для чужих моделей —
    считаем, что текстовая модель пишет и код."""
    out = [_FROM_OLLAMA[c] for c in ollama_caps if c in _FROM_OLLAMA]
    known = BY_ID.get(name)
    if "text" in out and (known is None or "code" in known["caps"]):
        out.insert(1, "code")
    return out


OVERHEAD = 1.2   # множитель на контекст и буферы
EXTRA = 0.6      # ГБ запаса
CPU_DENSE_LIMIT = 5.0  # плотные модели крупнее на CPU слишком медленные
ENGINE_DISK_GB = 3.0


def _need(size):
    return size * OVERHEAD + EXTRA


def rate(model, hw):
    """mode: gpu — целиком в видеопамяти (быстро); mixed — GPU+ОЗУ; cpu — только процессор; no — не влезает."""
    need = _need(model["size"])
    vram, ram = hw["vram_gb"], hw["ram_gb"]
    if vram and need <= vram * 0.95:
        return "gpu"
    if need <= ram * 0.7:
        if vram:
            return "mixed"
        return "cpu"
    return "no"


def recommend(hw, engine_installed=True, engine_free_gb=None):
    """hw["disk_free_gb"] — диск папки моделей; engine_free_gb — диск папки Ollama, если он другой."""
    rows = []
    for m in MODELS:
        mode = rate(m, hw)
        engine_need = 0 if engine_installed else ENGINE_DISK_GB
        if engine_free_gb is None:
            disk_ok = hw["disk_free_gb"] >= m["size"] + engine_need + 1
        else:
            disk_ok = hw["disk_free_gb"] >= m["size"] + 1 and engine_free_gb >= engine_need + 1
        # fits — подходит этому ПК: целиком в видеопамяти или умеренная модель на CPU/смешанном режиме.
        ok = mode == "gpu" or (mode in ("mixed", "cpu") and m["size"] <= CPU_DENSE_LIMIT)
        rows.append({**m, "mode": mode, "disk_ok": disk_ok, "fits": disk_ok and ok})

    def fits(r, modes):
        return r["disk_ok"] and r["mode"] in modes and not r.get("alt")

    # Надёжнее всего — модель целиком в видеопамяти; иначе умеренная модель на CPU/смешанном режиме.
    pick = next((r for r in reversed(rows) if fits(r, ("gpu",))), None) or \
        next((r for r in reversed(rows) if fits(r, ("mixed", "cpu")) and r["size"] <= CPU_DENSE_LIMIT), None)
    if pick is None:
        pick = next(r for r in rows if not r.get("alt"))
    for r in rows:
        r["recommended"] = r["id"] == pick["id"]
    return rows
