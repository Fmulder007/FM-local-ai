"""Точка входа: поднимает локальный сервер и открывает окно (pywebview, запасной вариант — Edge/Chrome в app-режиме)."""
import os
import shutil
import subprocess
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "LocalAI")


def log(text):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, "log.txt"), "a", encoding="utf-8") as f:
        f.write(text + "\n")


def browser_exe():
    for p in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Google\Chrome\Application\chrome.exe"):
        if os.path.exists(p):
            return p
    return shutil.which("msedge") or shutil.which("chrome")


def run_fallback(url):
    exe = browser_exe()
    if not exe:
        import webbrowser
        webbrowser.open(url)
    proc = exe and subprocess.Popen([exe, f"--app={url}", "--window-size=1100,760",
                                     f"--user-data-dir={os.path.join(DATA_DIR, 'browser')}"])
    import server
    start = time.time()
    while True:  # выходим, когда окно закрыто и пинги прекратились, или страница попросила закрыться
        if server.quit_event.wait(2):
            if proc:
                proc.terminate()
            return
        t = server.last_ping["t"]
        if (t and time.time() - t > 15) or (not t and time.time() - start > 60):
            return


class Api:
    """Доступно странице как window.pywebview.api."""

    def pick_folder(self, start=""):
        import webview
        kind = getattr(getattr(webview, "FileDialog", None), "FOLDER", None) or webview.FOLDER_DIALOG
        res = webview.windows[0].create_file_dialog(kind, directory=start if os.path.isdir(start or "") else "")
        return res[0] if res else None


def main():
    import engine
    import server
    srv, url = server.start()
    try:
        try:
            import webview
            win = webview.create_window("Local AI", url, width=1120, height=760, min_size=(820, 560),
                                        background_color="#0b0d14", js_api=Api(), text_select=True)

            def close_on_quit():   # после полного удаления страница просит закрыть окно
                server.quit_event.wait()
                win.destroy()
            # private_mode=False — иначе pywebview не сохраняет localStorage (чаты, тема, модель) между запусками.
            webview.start(close_on_quit, private_mode=False, storage_path=os.path.join(DATA_DIR, "webview"))
        except Exception:
            log("webview failed, fallback to browser app mode:\n" + traceback.format_exc())
            run_fallback(url)
    finally:
        # Окно закрыто: Ollama (трей и сервер) не оставляем в фоне — она держит видеопамять.
        engine.shutdown()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log(traceback.format_exc())
        raise
