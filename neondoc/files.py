"""Хранилище файлов проекта: папка «Хранилище» рядом с программой.

Структура по умолчанию:
    ВУЗ/<предмет>/<тип работы>      — Лабораторные, Практические, Рефераты, Курсовые, Материалы
    Работа/<тип документа>          — ТЗ, ФТ, AS-IS схемы, TO-BE схемы, Встречи, Скриншоты, …
    Входящие                        — всё, что ещё не разложено
    _Корзина                        — удалённое (можно вернуть руками)

Всё — обычные папки Windows: их можно открыть в Проводнике, программа просто показывает их красиво.
"""
from __future__ import annotations

import mimetypes
import re
import shutil
import time
from pathlib import Path

from . import store

STORAGE = store.ROOT / "Хранилище"
TRASH = STORAGE / "_Корзина"

VUZ_TYPES = ["Лабораторные", "Практические", "Рефераты", "Курсовые", "Материалы"]
WORK_TYPES = ["ТЗ", "ФТ", "AS-IS схемы", "TO-BE схемы", "Регламенты", "Инструкции",
              "Встречи и расшифровки", "Скриншоты", "Бэклог вопросов", "Материалы заказчика",
              "Описания роботов", "Архитектура", "Отчеты по обследованию"]
DEFAULT_SUBJECTS = ["ТИПУП", "ТПУПР", "ВВС", "Базы данных"]

TYPE_BY_WORK = {"Лабораторная работа": "Лабораторные", "Практическая работа": "Практические",
                "Реферат": "Рефераты", "Курсовая работа": "Курсовые"}

ICONS = {".docx": "doc", ".doc": "doc", ".pdf": "pdf", ".txt": "txt", ".md": "txt", ".xlsx": "xls", ".xls": "xls",
         ".csv": "xls", ".pptx": "ppt", ".png": "img", ".jpg": "img", ".jpeg": "img", ".webp": "img", ".gif": "img",
         ".drawio": "bpmn", ".bpmn": "bpmn", ".mp3": "audio", ".wav": "audio", ".m4a": "audio", ".ogg": "audio",
         ".mp4": "video", ".mov": "video", ".mkv": "video", ".webm": "video", ".avi": "video", ".zip": "zip"}


def ensure_tree():
    STORAGE.mkdir(exist_ok=True)
    first = not (STORAGE / "ВУЗ").exists()
    for p in ["Входящие", "_Корзина"]:
        (STORAGE / p).mkdir(exist_ok=True)
    for t in WORK_TYPES:
        (STORAGE / "Работа" / t).mkdir(parents=True, exist_ok=True)
    (STORAGE / "ВУЗ").mkdir(exist_ok=True)
    if first:
        for s in DEFAULT_SUBJECTS:
            for t in VUZ_TYPES:
                (STORAGE / "ВУЗ" / s / t).mkdir(parents=True, exist_ok=True)


def safe_name(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return name[:150] or "без_имени"


def resolve(rel: str) -> Path:
    """Путь внутри хранилища. Выйти за его пределы нельзя."""
    rel = (rel or "").replace("\\", "/").strip("/")
    p = (STORAGE / rel).resolve()
    root = STORAGE.resolve()
    if p != root and root not in p.parents:
        raise PermissionError("Путь вне хранилища")
    return p


def rel_of(p: Path) -> str:
    return p.resolve().relative_to(STORAGE.resolve()).as_posix()


def unique(p: Path) -> Path:
    if not p.exists():
        return p
    stem, suf, n = p.stem, p.suffix, 2
    while (p.with_name(f"{stem} ({n}){suf}")).exists():
        n += 1
    return p.with_name(f"{stem} ({n}){suf}")


def tree() -> dict:
    ensure_tree()

    def walk(d: Path, depth=0):
        kids = []
        if depth < 6:
            for c in sorted((x for x in d.iterdir() if x.is_dir()), key=lambda x: (x.name.startswith("_"), x.name.lower())):
                kids.append(walk(c, depth + 1))
        count = sum(1 for x in d.iterdir() if x.is_file() and not x.name.endswith(".annot.json"))
        return {"name": d.name if d != STORAGE else "Хранилище", "path": "" if d == STORAGE else rel_of(d),
                "files": count, "children": kids}
    return walk(STORAGE)


def info(p: Path) -> dict:
    st = p.stat()
    ext = p.suffix.lower()
    return {"name": p.name, "path": rel_of(p), "dir": p.is_dir(), "ext": ext,
            "kind": "folder" if p.is_dir() else ICONS.get(ext, "file"),
            "size": st.st_size if p.is_file() else None,
            "mtime": time.strftime("%d.%m.%Y %H:%M", time.localtime(st.st_mtime)), "ts": st.st_mtime}


def listdir(rel: str) -> dict:
    ensure_tree()
    d = resolve(rel)
    if not d.is_dir():
        raise FileNotFoundError(rel)
    items = [info(x) for x in d.iterdir() if not x.name.startswith("~$") and not x.name.endswith(".annot.json")]
    items.sort(key=lambda x: (not x["dir"], x["name"].lower()))
    crumbs = [{"name": "Хранилище", "path": ""}]
    acc = []
    for part in ([] if d == STORAGE.resolve() else rel_of(d).split("/")):
        acc.append(part)
        crumbs.append({"name": part, "path": "/".join(acc)})
    return {"path": "" if d == STORAGE.resolve() else rel_of(d), "crumbs": crumbs, "items": items}


def mkdir(rel: str, name: str) -> str:
    d = resolve(rel) / safe_name(name)
    d.mkdir(parents=True, exist_ok=True)
    return rel_of(d)


def save_bytes(rel_dir: str, filename: str, data: bytes) -> str:
    d = resolve(rel_dir)
    d.mkdir(parents=True, exist_ok=True)
    p = unique(d / safe_name(filename))
    p.write_bytes(data)
    return rel_of(p)


def copy_in(src: Path, rel_dir: str, name: str | None = None) -> str:
    d = resolve(rel_dir)
    d.mkdir(parents=True, exist_ok=True)
    p = unique(d / safe_name(name or src.name))
    shutil.copy2(src, p)
    return rel_of(p)


def rename(rel: str, new_name: str) -> str:
    p = resolve(rel)
    q = unique(p.with_name(safe_name(new_name)))
    p.rename(q)
    return rel_of(q)


def move(rel: str, dest_dir: str) -> str:
    p = resolve(rel)
    d = resolve(dest_dir)
    if p.is_dir() and (d == p or p in d.parents):
        raise ValueError("Нельзя переместить папку в саму себя")
    q = unique(d / p.name)
    shutil.move(str(p), str(q))
    return rel_of(q)


def delete(rel: str) -> str:
    """Не удаляем насовсем — переносим в _Корзина."""
    p = resolve(rel)
    if p == STORAGE.resolve() or p == TRASH.resolve():
        raise PermissionError("Эту папку удалить нельзя")
    if TRASH.resolve() in p.parents:
        shutil.rmtree(p) if p.is_dir() else p.unlink()
        return ""
    TRASH.mkdir(exist_ok=True)
    q = unique(TRASH / p.name)
    shutil.move(str(p), str(q))
    return rel_of(q)


def mime(p: Path) -> str:
    return mimetypes.guess_type(p.name)[0] or "application/octet-stream"


def search(q: str, limit: int = 60) -> list[dict]:
    """Поиск по имени и по тексту (docx/pdf/txt/расшифровки)."""
    from .extract import file_text
    ensure_tree()
    words = [w for w in re.findall(r"\w+", q.lower()) if len(w) > 1]
    if not words:
        return []
    out = []
    for p in STORAGE.rglob("*"):
        if not p.is_file() or p.name.startswith("~$") or p.name.endswith(".annot.json") or TRASH.resolve() in p.resolve().parents:
            continue
        name = p.name.lower()
        score, snippet = 0, ""
        if all(w in name for w in words):
            score += 10
        if p.stat().st_size < 30_000_000 and p.suffix.lower() in (".docx", ".pdf", ".txt", ".md", ".csv", ".json", ".xlsx", ".pptx"):
            txt = _cached_text(p, file_text)
            low = txt.lower()
            hits = sum(low.count(w) for w in words)
            if hits and all(w in low for w in words):
                score += min(hits, 20)
                i = low.find(words[0])
                snippet = txt[max(0, i - 80): i + 160].replace("\n", " ").strip()
        if score:
            out.append({**info(p), "score": score, "snippet": snippet})
    out.sort(key=lambda x: -x["score"])
    return out[:limit]


_TEXT_CACHE: dict[str, tuple[float, str]] = {}


def _cached_text(p: Path, fn) -> str:
    k, m = str(p), p.stat().st_mtime
    if k in _TEXT_CACHE and _TEXT_CACHE[k][0] == m:
        return _TEXT_CACHE[k][1]
    t = fn(p) or ""
    _TEXT_CACHE[k] = (m, t)
    return t


def folder_for_work(meta: dict) -> str:
    """ВУЗ/<дисциплина>/<тип> — сюда кладём собранную работу."""
    subj = safe_name((meta.get("discipline") or "").strip() or "Без предмета")
    typ = TYPE_BY_WORK.get(meta.get("work_type"), "Материалы")
    d = STORAGE / "ВУЗ" / subj / typ
    if not (STORAGE / "ВУЗ" / subj).exists():
        for t in VUZ_TYPES:
            (STORAGE / "ВУЗ" / subj / t).mkdir(parents=True, exist_ok=True)
    d.mkdir(parents=True, exist_ok=True)
    return rel_of(d)


def all_folders() -> list[str]:
    ensure_tree()
    return sorted(rel_of(p) for p in STORAGE.rglob("*") if p.is_dir() and TRASH.resolve() not in p.resolve().parents
                  and p.resolve() != TRASH.resolve())
