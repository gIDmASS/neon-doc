"""Текст из вложений: .docx, .pdf, .txt/.md/.csv, расшифровки аудио (.wav/.mp3/… -> sidecar .txt)."""
from __future__ import annotations

from html import unescape as _unescape
from pathlib import Path


def html_unescape(s: str) -> str:
    import re as _re
    return _re.sub(r"<[^>]+>", " ", _unescape(s)).strip()

AUDIO_EXT = (".wav", ".mp3", ".m4a", ".ogg", ".opus", ".flac", ".aac", ".wma",
             ".webm", ".mp4", ".mov", ".mkv", ".avi", ".m4v", ".wmv")   # видео тоже: звук достаёт faster-whisper
VIDEO_EXT = (".webm", ".mp4", ".mov", ".mkv", ".avi", ".m4v", ".wmv")
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")
TEXT_EXT = (".txt", ".md", ".csv", ".json", ".sql", ".py", ".yaml", ".yml", ".xml", ".html", ".bpmn", ".log")
PER_FILE = 15000      # символов с одного файла
TOTAL = 30000         # всего: контекст модели 32k токенов, нужен запас на план и ответ


def transcript_path(audio: Path) -> Path:
    return audio.with_name(audio.name + ".transcript.txt")


def file_text(p: Path) -> str | None:
    ext = p.suffix.lower()
    try:
        if ext in TEXT_EXT:
            return p.read_text(encoding="utf-8", errors="replace")
        if ext == ".docx":
            import docx
            d = docx.Document(str(p))
            out = [x.text for x in d.paragraphs if x.text.strip()]
            for t in d.tables:
                for r in t.rows:
                    out.append(" | ".join(c.text.strip() for c in r.cells))
            return "\n".join(out)
        if ext == ".pdf":
            import pymupdf
            with pymupdf.open(str(p)) as doc:
                return "\n".join(page.get_text() for page in doc)
        if ext in (".xlsx", ".xlsm"):
            import openpyxl
            wb = openpyxl.load_workbook(str(p), read_only=True, data_only=True)
            out = []
            for ws in wb.worksheets:
                out.append(f"### Лист «{ws.title}»")
                for row in ws.iter_rows(values_only=True):
                    if any(v is not None for v in row):
                        out.append(" | ".join("" if v is None else str(v) for v in row))
            return "\n".join(out)
        if ext == ".pptx":
            from pptx import Presentation
            out = []
            for i, sl in enumerate(Presentation(str(p)).slides, 1):
                out.append(f"### Слайд {i}")
                for sh in sl.shapes:
                    if sh.has_text_frame and sh.text_frame.text.strip():
                        out.append(sh.text_frame.text)
            return "\n".join(out)
        if ext == ".drawio":
            import re as _re
            raw = p.read_text(encoding="utf-8", errors="replace")
            labels = _re.findall(r'value="([^"]+)"', raw)
            return "Подписи на схеме draw.io:\n" + "\n".join(sorted(set(html_unescape(x) for x in labels if x.strip())))
        if ext in AUDIO_EXT:
            tp = transcript_path(p)
            return tp.read_text(encoding="utf-8") if tp.exists() else None
    except Exception as e:  # битый файл не должен ронять генерацию
        return f"[не удалось прочитать {p.name}: {e}]"
    return None


def attachments_text(folder: Path) -> str:
    if not folder.exists():
        return ""
    parts, total = [], 0
    for p in sorted(folder.iterdir()):
        if p.name.endswith(".transcript.txt") or p.is_dir():
            continue
        txt = file_text(p)
        if not txt or not txt.strip():
            continue
        txt = txt.strip()
        if len(txt) > PER_FILE:
            txt = txt[:PER_FILE] + f"\n[…обрезано, всего {len(txt)} символов]"
        if total + len(txt) > TOTAL:
            parts.append(f"## {p.name}\n[не влезло в контекст модели — сократи вложения]")
            continue
        total += len(txt)
        kind = "расшифровка аудио" if p.suffix.lower() in AUDIO_EXT else "файл"
        parts.append(f"## {p.name} ({kind})\n{txt}")
    return "\n\n".join(parts)


def attachment_info(folder: Path) -> list[dict]:
    out = []
    if not folder.exists():
        return out
    for p in sorted(folder.iterdir()):
        if p.name.endswith(".transcript.txt") or p.is_dir():
            continue
        txt = file_text(p)
        out.append({"name": p.name, "size": p.stat().st_size,
                    "audio": p.suffix.lower() in AUDIO_EXT,
                    "chars": len(txt) if txt else 0,
                    "pending": p.suffix.lower() in AUDIO_EXT and txt is None})
    return out
