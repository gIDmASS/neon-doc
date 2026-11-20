"""Мелочи, которые на Windows и macOS делаются по-разному: открыть файл, показать в папке."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"


def open_path(p: Path):
    """Открыть файл или папку программой по умолчанию."""
    if IS_WIN:
        os.startfile(str(p))  # noqa
    elif IS_MAC:
        subprocess.Popen(["open", str(p)])
    else:
        subprocess.Popen(["xdg-open", str(p)])


def reveal(p: Path):
    """Показать файл в проводнике / Finder (с выделением)."""
    if IS_WIN:
        subprocess.Popen(["explorer", "/select,", str(p)])
    elif IS_MAC:
        subprocess.Popen(["open", "-R", str(p)])
    else:
        subprocess.Popen(["xdg-open", str(p.parent if p.is_file() else p)])


def soffice_path() -> str | None:
    import shutil
    found = shutil.which("soffice") or shutil.which("libreoffice")
    if found:
        return found
    if IS_MAC:
        for base in ("/Applications", str(Path.home() / "Applications")):
            mac = f"{base}/LibreOffice.app/Contents/MacOS/soffice"
            if Path(mac).exists():
                return mac
    if IS_WIN:
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", "")):
            p = Path(base) / "LibreOffice" / "program" / "soffice.exe"
            if base and p.exists():
                return str(p)
    return None
