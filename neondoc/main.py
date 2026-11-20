"""Запуск NEON.DOC: локальный сервер + отдельное окно (pywebview / WebView2).

    python -m neondoc            # окно приложения
    python -m neondoc --browser  # то же, но в обычном браузере (если окно не запускается)
"""
from __future__ import annotations

import socket
import sys
import threading
import time
import webbrowser


def _free_port(preferred: int = 8765) -> int:
    for port in (preferred, 0):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return s.getsockname()[1]
            except OSError:
                continue
    raise RuntimeError("Нет свободного порта")


def main():
    import uvicorn
    from .server import app

    port = _free_port()
    url = f"http://127.0.0.1:{port}/"
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)

    if "--browser" in sys.argv:
        webbrowser.open(url)
        print(f"NEON.DOC: {url}  (Ctrl+C — выход)")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            return
    try:
        import webview
        try:
            webview.settings["ALLOW_DOWNLOADS"] = True   # «Скачать PNG», выгрузка файлов
        except Exception:
            pass
        webview.create_window("NEON.DOC", url, width=1480, height=920, min_size=(1100, 700),
                              background_color="#0b0118", text_select=True)
        if sys.platform == "darwin":
            _mac_dock_icon()
        webview.start(private_mode=False)
    except Exception as e:
        print(f"Окно не запустилось ({e}), открываю в браузере: {url}")
        webbrowser.open(url)
        while True:
            time.sleep(1)


def _mac_dock_icon():
    """macOS: своя иконка в Dock вместо значка Python."""
    try:
        from pathlib import Path
        from AppKit import NSApplication, NSImage
        icon = Path(__file__).parent / "static" / "icon.png"
        img = NSImage.alloc().initByReferencingFile_(str(icon))
        NSApplication.sharedApplication().setApplicationIconImage_(img)
    except Exception:
        pass


if __name__ == "__main__":
    main()
