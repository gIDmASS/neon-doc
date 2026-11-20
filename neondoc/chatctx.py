"""Файлы в чате с Qwen: хранение, текст для контекста, картинки, поиск по большим файлам.

chats/<id>.json          — сообщения
chats/<id>/files/        — прикреплённые файлы
chats/<id>/files.json    — [{name, kind, chars, transcript_id}]

Если весь текст файлов не влезает в контекст модели, берём куски, где чаще встречаются слова
из вопроса (простой поиск без эмбеддингов: быстрый и предсказуемый).
"""
from __future__ import annotations

import base64
import io
import math
import re
from collections import Counter
from pathlib import Path

from . import store
from .extract import AUDIO_EXT, IMAGE_EXT, file_text

CHATS = store.ROOT / "chats"
FILE_BUDGET = 48000      # символов текста файлов на один запрос (~16k токенов)
CHUNK = 1400


def cdir(cid: str) -> Path:
    d = CHATS / Path(cid).name
    (d / "files").mkdir(parents=True, exist_ok=True)
    return d


def list_files(cid: str) -> list[dict]:
    d = CHATS / Path(cid).name
    return store.read_json(d / "files.json", []) if d.exists() else []


def _save_list(cid: str, items: list[dict]):
    store.write_json(cdir(cid) / "files.json", items)


def kind_of(name: str) -> str:
    ext = Path(name).suffix.lower()
    return "image" if ext in IMAGE_EXT else "media" if ext in AUDIO_EXT else "text"


def add_file(cid: str, filename: str, data: bytes) -> dict:
    from .files import safe_name, unique
    d = cdir(cid) / "files"
    p = unique(d / safe_name(Path(filename).name))
    p.write_bytes(data)
    rec = {"name": p.name, "kind": kind_of(p.name), "size": len(data), "chars": 0, "transcript_id": None}
    if rec["kind"] == "text":
        rec["chars"] = len(file_text(p) or "")
    items = [x for x in list_files(cid) if x["name"] != p.name] + [rec]
    _save_list(cid, items)
    return rec


def set_transcript(cid: str, name: str, tid: str):
    items = list_files(cid)
    for x in items:
        if x["name"] == name:
            x["transcript_id"] = tid
    _save_list(cid, items)


def add_transcript_ref(cid: str, tid: str, title: str) -> dict:
    rec = {"name": f"Расшифровка — {title}", "kind": "transcript", "size": 0, "chars": 0, "transcript_id": tid}
    items = [x for x in list_files(cid) if x.get("transcript_id") != tid] + [rec]
    _save_list(cid, items)
    return rec


def remove_file(cid: str, name: str):
    items = list_files(cid)
    for x in items:
        if x["name"] == name and x["kind"] != "transcript":
            (cdir(cid) / "files" / Path(name).name).unlink(missing_ok=True)
    _save_list(cid, [x for x in items if x["name"] != name])


def file_path(cid: str, name: str) -> Path:
    return cdir(cid) / "files" / Path(name).name


# ------------------------------------------------------------------ текст для модели

def _texts(cid: str) -> list[tuple[str, str]]:
    from . import transcribe
    out = []
    for x in list_files(cid):
        txt = None
        if x.get("transcript_id"):
            try:
                t = transcribe.read(x["transcript_id"])
                if t.get("status") == "done":
                    txt = transcribe.as_text(x["transcript_id"])
                    notes = "\n\n".join(n["text"] for n in t.get("notes", [])[:3])
                    if notes:
                        txt += "\n\n[Ранее сделанные конспекты]\n" + notes
            except KeyError:
                txt = None
        elif x["kind"] == "text":
            txt = file_text(file_path(cid, x["name"]))
        if txt and txt.strip():
            out.append((x["name"], txt.strip()))
    return out


def _words(s: str) -> list[str]:
    return [w for w in re.findall(r"[a-zа-яё0-9]{3,}", s.lower())]


def _stem(w: str) -> str:
    return w[:6] if len(w) > 6 else w   # грубая «основа» для русского: отчёт/отчёта/отчётом


def context(cid: str, question: str) -> tuple[str, list[str]]:
    """Текст файлов для системного промпта + пометки, что пришлось обрезать."""
    texts = _texts(cid)
    if not texts:
        return "", []
    total = sum(len(t) for _, t in texts)
    if total <= FILE_BUDGET:
        return "\n\n".join(f"=== ФАЙЛ: {n} ===\n{t}" for n, t in texts), []

    # Не влезает: режем на куски и берём самые подходящие к вопросу (+ начало каждого файла)
    q = Counter(_stem(w) for w in _words(question))
    chunks = []
    for n, t in texts:
        for i in range(0, len(t), CHUNK):
            chunks.append((n, i, t[i:i + CHUNK]))
    df = Counter()
    for _, _, c in chunks:
        df.update(set(_stem(w) for w in _words(c)))
    N = len(chunks)

    def score(c):
        tf = Counter(_stem(w) for w in _words(c))
        return sum(tf[w] * math.log(1 + N / (1 + df[w])) for w in q)
    ranked = sorted(chunks, key=lambda x: -score(x[2]))
    picked, used = [], 0
    for n, t in texts:                      # начало каждого файла — чтобы модель знала, что это за файл
        picked.append((n, 0, t[:CHUNK]))
        used += min(len(t), CHUNK)
    for ch in ranked:
        if used + len(ch[2]) > FILE_BUDGET:
            break
        if (ch[0], ch[1]) not in {(a, b) for a, b, _ in picked}:
            picked.append(ch)
            used += len(ch[2])
    picked.sort(key=lambda x: (x[0], x[1]))
    parts, cur = [], None
    for n, i, c in picked:
        if n != cur:
            parts.append(f"=== ФАЙЛ: {n} (фрагменты) ===")
            cur = n
        parts.append(f"[…позиция {i}…]\n{c}")
    note = f"Файлы большие ({total} симв.), в контекст взяты фрагменты, похожие на вопрос ({used} симв.)."
    return "\n\n".join(parts), [note]


def images_b64(cid: str, names: list[str], max_side: int = 1600) -> list[str]:
    out = []
    for n in names:
        p = file_path(cid, n)
        if not p.exists() or kind_of(n) != "image":
            continue
        data = p.read_bytes()
        try:
            from PIL import Image
            im = Image.open(io.BytesIO(data))
            if max(im.size) > max_side:
                im.thumbnail((max_side, max_side))
            buf = io.BytesIO()
            im.convert("RGB").save(buf, "JPEG", quality=88)
            data = buf.getvalue()
        except Exception:
            pass
        out.append(base64.b64encode(data).decode())
    return out
