"""Докачка всего, что нужно NEON.DOC на Mac, и самопроверка. Вызывает install_mac.command.

    python tools/mac_setup.py models   — Whisper (MLX), модели диаризации
    python tools/mac_setup.py office   — LibreOffice для PDF, если нет ни Word, ни LibreOffice
    python tools/mac_setup.py check    — проверка: библиотеки, Ollama, модели, PDF
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

G, Y, R, E = "\033[1;32m", "\033[1;33m", "\033[1;31m", "\033[0m"


def ok(s): print(f"{G}✓{E} {s}", flush=True)
def warn(s): print(f"{Y}!{E} {s}", flush=True)
def bad(s): print(f"{R}✗{E} {s}", flush=True)


def settings() -> dict:
    import yaml
    p = ROOT / "settings.yaml"
    s = (yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else None) or {}
    s.setdefault("whisper_model", "large-v3-turbo")
    s.setdefault("ollama_url", "http://127.0.0.1:11434")
    return s


# ------------------------------------------------------------------ модели

def models():
    s = settings()
    from neondoc.voice import MLX_REPOS
    repo = MLX_REPOS.get(s["whisper_model"], MLX_REPOS["large-v3-turbo"])
    print(f"Whisper для Mac: {repo} (~1,6 ГБ)…", flush=True)
    try:
        from huggingface_hub import snapshot_download
        snapshot_download(repo_id=repo)
        ok("Whisper скачан")
    except Exception as e:
        warn(f"Whisper не скачался ({e}) — скачается сам при первой расшифровке")
    print("Модели разделения по участникам…", flush=True)
    try:
        from neondoc import transcribe
        transcribe.diarization_models(lambda m: print("  " + m, flush=True))
        ok("модели диаризации на месте")
    except Exception as e:
        warn(f"диаризация: {e} — скачается при первой расшифровке")


# ------------------------------------------------------------------ LibreOffice

def _have_office() -> str | None:
    for p in ("/Applications/Microsoft Word.app",):
        if Path(p).exists():
            return "Microsoft Word"
    from neondoc.osutil import soffice_path
    return "LibreOffice" if soffice_path() else None


def office():
    have = _have_office()
    if have:
        ok(f"PDF будет делаться через {have}")
        return
    print("Нет ни Word, ни LibreOffice — ставлю LibreOffice для PDF (~350 МБ)…", flush=True)
    base = "https://download.documentfoundation.org/libreoffice/stable/"
    try:
        html = urllib.request.urlopen(base, timeout=30).read().decode("utf-8", "ignore")
        vers = sorted({tuple(map(int, v.split("."))) for v in re.findall(r'href="(\d+\.\d+\.\d+)/"', html)})
        ver = ".".join(map(str, vers[-1]))
        url = f"{base}{ver}/mac/aarch64/LibreOffice_{ver}_MacOS_aarch64.dmg"
        tmp = Path(tempfile.mkdtemp())
        dmg = tmp / "LibreOffice.dmg"
        print(f"  LibreOffice {ver}…", flush=True)
        with urllib.request.urlopen(url, timeout=60) as r, open(dmg, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            done, last = 0, -1
            while chunk := r.read(1 << 20):
                f.write(chunk)
                done += len(chunk)
                pct = int(100 * done / total) if total else 0
                if pct // 10 != last:
                    last = pct // 10
                    print(f"  {pct}%", flush=True)
        mnt = tmp / "mnt"
        subprocess.run(["hdiutil", "attach", str(dmg), "-nobrowse", "-quiet", "-mountpoint", str(mnt)], check=True)
        try:
            app = next(mnt.glob("*.app"))
            dest = Path("/Applications")
            if not dest.exists() or not shutil.os.access(dest, shutil.os.W_OK):
                dest = Path.home() / "Applications"
                dest.mkdir(exist_ok=True)
            subprocess.run(["ditto", str(app), str(dest / app.name)], check=True)
            subprocess.run(["xattr", "-dr", "com.apple.quarantine", str(dest / app.name)])
        finally:
            subprocess.run(["hdiutil", "detach", str(mnt), "-quiet"])
        shutil.rmtree(tmp, ignore_errors=True)
        ok(f"LibreOffice установлен в {dest}")
    except Exception as e:
        warn(f"LibreOffice не установился ({e}). PDF всё равно будет — упрощённый. "
             "Можно поставить Word или LibreOffice позже, вручную.")


# ------------------------------------------------------------------ проверка

def check() -> int:
    errors = 0
    print("\n── Проверка ──", flush=True)
    for mod, name in [("webview", "окно приложения"), ("fastapi", "сервер"), ("docx", "Word-документы"),
                      ("pymupdf", "PDF"), ("openpyxl", "Excel"), ("pptx", "PowerPoint"),
                      ("mlx_whisper", "расшифровка (MLX)"), ("sherpa_onnx", "разделение по участникам"),
                      ("av", "чтение аудио/видео"), ("sounddevice", "микрофон")]:
        try:
            __import__(mod)
            ok(name)
        except Exception as e:
            bad(f"{name}: {e}")
            errors += 1
    s = settings()
    try:
        tags = json.loads(urllib.request.urlopen(s["ollama_url"] + "/api/tags", timeout=5).read())
        names = [m["name"] for m in tags.get("models", [])]
        want = str(s.get("model"))
        if want in names or f"{want}:latest" in names:
            ok(f"Ollama и модель {s.get('model')}")
        else:
            bad(f"Ollama работает, но модели {s.get('model')} нет (есть: {', '.join(names) or '—'})")
            errors += 1
    except Exception as e:
        bad(f"Ollama не отвечает ({e})")
        errors += 1
    from neondoc.voice import MLX_REPOS
    repo = MLX_REPOS.get(s["whisper_model"], MLX_REPOS["large-v3-turbo"])
    try:
        from huggingface_hub import try_to_load_from_cache
        hit = try_to_load_from_cache(repo, "config.json")
        ok("Whisper скачан") if isinstance(hit, str) else warn("Whisper скачается при первой расшифровке")
    except Exception:
        warn("Whisper: не удалось проверить кэш")
    d = ROOT / "models" / "diarization"
    ok("модели диаризации") if (d / "segmentation.onnx").exists() and (d / "embedding.onnx").exists() \
        else warn("модели диаризации скачаются при первой расшифровке")
    have = _have_office()
    ok(f"PDF через {have}") if have else warn("PDF — упрощённый (нет Word/LibreOffice)")
    print(flush=True)
    return errors


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "models":
        models()
    elif cmd == "office":
        office()
    else:
        sys.exit(1 if check() else 0)
