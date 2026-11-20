"""Собрать архивы релиза из файлов репозитория (git ls-files):

    python tools/pack_release.py [--out dist]

NEON.DOC-windows.zip — всё, кроме установщиков для Mac (.bat-файлы с CRLF).
NEON.DOC-mac.zip     — всё, кроме .bat; .command с LF и правом на запуск;
                       «Установить NEON.DOC.command» лежит рядом с папкой NEON.DOC.
"""
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAC_ONLY = {"install_mac.command", "run_mac.command", "requirements-mac.txt", "МАК — КАК УСТАНОВИТЬ.txt",
            "Установить NEON.DOC.command", "tools/mac_setup.py"}
WIN_ONLY = {"requirements-app.txt", "WINDOWS — КАК УСТАНОВИТЬ.txt"}
SKIP_PREFIX = (".git", ".github/")


def files():
    out = subprocess.run(["git", "-c", "core.quotepath=false", "ls-files"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout
    return [f for f in out.splitlines() if f and not f.startswith(SKIP_PREFIX)]


def add(z, rel, arc, exe=False, eol=None):
    data = (ROOT / rel).read_bytes()
    if eol:
        data = data.replace(b"\r\n", b"\n")
        if eol == "crlf":
            data = data.replace(b"\n", b"\r\n")
    zi = zipfile.ZipInfo(arc, time.localtime()[:6])
    zi.create_system = 3                                   # unix — права сохранятся на Mac
    zi.external_attr = (0o100000 | (0o755 if exe else 0o644)) << 16
    zi.compress_type = zipfile.ZIP_DEFLATED
    z.writestr(zi, data)


def main():
    out = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else ROOT / "dist"
    out.mkdir(parents=True, exist_ok=True)
    fs = files()
    with zipfile.ZipFile(out / "NEON.DOC-windows.zip", "w") as z:
        for f in fs:
            if f not in MAC_ONLY:
                add(z, f, "NEON.DOC/" + f, eol="crlf" if f.endswith(".bat") else None)
    with zipfile.ZipFile(out / "NEON.DOC-mac.zip", "w") as z:
        for f in fs:
            if f in WIN_ONLY or f.endswith(".bat"):
                continue
            cmd = f.endswith(".command")
            arc = f if f == "Установить NEON.DOC.command" else "NEON.DOC/" + f
            add(z, f, arc, exe=cmd, eol="lf" if cmd else None)
    for p in sorted(out.glob("*.zip")):
        print(f"{p.name}: {p.stat().st_size // 1024} КБ")


if __name__ == "__main__":
    main()
