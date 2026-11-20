"""Собрать NEON.DOC-mac.zip для переноса на Mac (запускается на ПК через make_mac_package.bat).

В архив: код, шаблоны, установщик для Mac и (по умолчанию) твои данные — Хранилище, работы,
рабочие документы, чаты, расшифровки. Не попадают: модели Whisper (на Mac свои), резервные копии,
логи, .bat-файлы, временные файлы Word и исходные записи встреч больше 300 МБ (текст расшифровки остаётся).

    python tools/pack_mac.py            # с данными
    python tools/pack_mac.py --no-data  # только программа
"""
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODE = ["neondoc", "reportgen", "library", "prompts", "tasks", "templates", "tests", "tools"]
FILES = ["README.md", "requirements.txt", "requirements-mac.txt", "wdoc.py", "install_mac.command",
         "run_mac.command", "МАК — КАК УСТАНОВИТЬ.txt"]
DATA = ["Хранилище", "works", "wdocs", "chats", "transcripts"]
DATA_FILES = ["settings.yaml"]
EXTRA = ["models/diarization"]          # модели разделения по участникам (32 МБ, одинаковы для Win и Mac)
SKIP_DIRS = {"__pycache__", ".venv", ".git", ".idea", "whisper"}
BIG = 300 * 1024 * 1024
EXEC = {".command"}


def add(z: zipfile.ZipFile, p: Path, skipped: list, arcname: str | None = None):
    rel = p.relative_to(ROOT)
    if any(part in SKIP_DIRS or part.startswith("_backup") for part in rel.parts):
        return 0
    if rel.parts[0] == "models" and rel.parts[:2] != ("models", "diarization"):
        return 0
    if p.name.startswith("~$") or p.suffix.lower() in (".bat", ".log", ".pyc"):
        return 0
    size = p.stat().st_size
    if size > BIG and rel.parts[0] == "transcripts":
        skipped.append(f"{rel} ({size // 2**20} МБ)")
        return 0
    zi = zipfile.ZipInfo(arcname or f"NEON.DOC/{rel.as_posix()}", time.localtime(p.stat().st_mtime)[:6])
    zi.create_system = 3                       # unix — чтобы сохранились права на Mac
    mode = 0o755 if p.suffix in EXEC else 0o644
    zi.external_attr = (0o100000 | mode) << 16
    zi.compress_type = zipfile.ZIP_DEFLATED
    data = p.read_bytes()
    if p.suffix in EXEC:                       # скрипты для Mac — только LF
        data = data.replace(b"\r\n", b"\n")
    z.writestr(zi, data)
    return size


def main():
    with_data = "--no-data" not in sys.argv
    out = Path(next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--out=")),
                    Path.home() / "Downloads" / "NEON.DOC-mac.zip"))
    total, skipped, n = 0, [], 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for d in CODE + EXTRA + (DATA if with_data else []):
            base = ROOT / d
            if not base.exists():
                continue
            for p in sorted(base.rglob("*")):
                if p.is_file():
                    s = add(z, p, skipped)
                    total += s
                    n += 1 if s or p.stat().st_size == 0 else 0
        for f in FILES + (DATA_FILES if with_data else []):
            if (ROOT / f).exists():
                total += add(z, ROOT / f, skipped)
                n += 1
        root_cmd = ROOT / "Установить NEON.DOC.command"
        if root_cmd.exists():                  # кнопка установки — рядом с папкой, на виду
            total += add(z, root_cmd, skipped, arcname=root_cmd.name)
    print(f"Готово: {out}")
    print(f"Файлов: {n}, исходный объём {total / 2**20:.0f} МБ, архив {out.stat().st_size / 2**20:.0f} МБ")
    print("Данные: " + ("включены (" + ", ".join(DATA) + ")" if with_data else "НЕ включены"))
    if skipped:
        print("Пропущены большие записи (текст расшифровок остался):")
        for s in skipped:
            print("  -", s)


if __name__ == "__main__":
    main()
