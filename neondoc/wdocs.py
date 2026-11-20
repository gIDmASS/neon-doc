"""Рабочие документы (вкладка «Работа» в шаблонах): описание робота, архитектурное решение,
отчёт по обследованию и любые будущие шаблоны того же вида.

Шаблон  = library/worktpl/<slug>/spec.yaml (+ template.docx для заполняемых, + rules.md).
Документ = wdocs/<id>/doc.json, materials/ (файлы заказчика), figures/ (рисунки), out/ (сборки).

Модель заполняет документ по разделам: каждый раздел — отдельный запрос со своей JSON-схемой,
так таблицы приходят таблицами, а не текстом. Чего нет в материалах — модель ставит
[уточнить: …] и пишет вопрос; все вопросы собираются в список «Вопросы к заказчику».
"""
from __future__ import annotations

import json
import math
import re
import shutil
import time
from collections import Counter
from pathlib import Path

import yaml

from . import store

ROOT = store.ROOT
TPL = ROOT / "library" / "worktpl"
WDOCS = ROOT / "wdocs"
TPL.mkdir(parents=True, exist_ok=True)
WDOCS.mkdir(parents=True, exist_ok=True)

IMG_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")
CTX_BUDGET = 36000        # символов материалов на один раздел (~12k токенов)
CHUNK = 1400
TODO_RE = re.compile(r"\[уточнить:\s*([^\]]+)\]", re.I)


# ================================================================== шаблоны

def _today() -> str:
    return time.strftime("%d.%m.%Y")


def fmt(s, fields: dict, strip: bool = True) -> str:
    """'{code} {name}' -> значения полей; {today} -> сегодняшняя дата. Неизвестное — как было."""
    if not isinstance(s, str):
        return s
    vals = {"today": _today(), **{k: ("" if v is None else str(v)) for k, v in (fields or {}).items()}}
    out = re.sub(r"\{(\w+)\}", lambda m: vals.get(m.group(1), m.group(0)), s)
    return out.strip() if strip else out


def list_templates() -> list[dict]:
    out = []
    for d in sorted(TPL.iterdir()):
        if (d / "spec.yaml").exists():
            try:
                t = get_template(d.name)
            except Exception as e:  # битый spec не должен ломать галерею
                t = {"slug": d.name, "name": d.name, "description": f"Ошибка в spec.yaml: {e}",
                     "sections": [], "fields": [], "previews": [], "broken": True}
            t["docs"] = sum(1 for x in list_all() if x.get("template") == d.name)
            out.append(t)
    return sorted(out, key=lambda t: (t.get("order", 99), t.get("name", "")))


def get_template(slug: str) -> dict:
    d = TPL / Path(slug).name
    p = d / "spec.yaml"
    if not p.exists():
        raise KeyError(slug)
    t = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    t["slug"] = d.name
    t.setdefault("category", "Работа")
    t.setdefault("kind", "build")
    t["has_docx"] = (d / "template.docx").exists()
    t["rules_text"] = (d / t["rules"]).read_text(encoding="utf-8") if t.get("rules") and (d / t["rules"]).exists() else ""
    pv = d / "previews"
    t["previews"] = [f"/worktpl/{d.name}/previews/{x.name}?v={int(x.stat().st_mtime)}"
                     for x in sorted(pv.iterdir()) if x.suffix.lower() in IMG_EXT] if pv.exists() else []
    for s in t.get("sections", []):
        s.setdefault("level", 1)
        s.setdefault("ai", s.get("kind") not in ("figures", "fixed", "heading"))
    return t


def tpl_dir(slug: str) -> Path:
    return TPL / Path(slug).name


# ================================================================== документы

def ddir(did: str) -> Path:
    d = WDOCS / Path(did).name
    if not (d / "doc.json").exists():
        raise KeyError(did)
    return d


def _read(did: str) -> dict:
    return json.loads((ddir(did) / "doc.json").read_text(encoding="utf-8"))


def _write(did: str, doc: dict):
    doc["updated"] = time.strftime("%Y-%m-%d %H:%M")
    (WDOCS / did / "doc.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def _empty_section(s: dict, fields: dict) -> dict:
    out = {"enabled": bool(s.get("enabled", True)), "questions": [], "generated": None}
    k = s["kind"]
    if k in ("text", "steps"):
        out["text"] = fmt(s.get("default", ""), fields)
    elif k == "table":
        rows = [[fmt(c, fields) for c in r] for r in (s.get("default_rows") or [])]
        if not rows and s.get("fixed_rows"):
            fc = s.get("fixed_col", 0)
            rows = []
            for i, name in enumerate(s["fixed_rows"]):
                r = [""] * len(s["columns"])
                r[fc] = name
                if s.get("autonum") and fc != 0:
                    r[0] = str(i + 1)
                rows.append(r)
        out["rows"] = rows
    elif k == "list":
        out["items"] = [fmt(x, fields) for x in (s.get("default_items") or [])]
    elif k == "asis_steps":
        out["steps"] = []
    elif k == "choice":
        out["value"] = s.get("default", (s.get("options") or [""])[0])
        out["text"] = ""
    elif k == "figures":
        out["figures"] = []
    return out


def _sync_sections(doc: dict, t: dict) -> dict:
    """Новые разделы в spec появляются и в старых документах; поля — тоже."""
    fields = doc.setdefault("fields", {})
    for f in t.get("fields", []):
        if f["key"] not in fields:
            fields[f["key"]] = f.get("default", False) if f.get("type") == "bool" else fmt(f.get("default", ""), fields)
    secs = doc.setdefault("sections", {})
    for s in t.get("sections", []):
        if s["id"] not in secs:
            secs[s["id"]] = _empty_section(s, fields)
    _apply_off_if(doc, t)
    return doc


def _apply_off_if(doc: dict, t: dict):
    """Разделы, которые не нужны при выбранных полях (например, «Предварительные действия» для Python)."""
    for s in t.get("sections", []):
        cond = s.get("off_if")
        if not cond:
            continue
        sec = doc["sections"][s["id"]]
        hit = all(str(doc["fields"].get(k, "")) == str(v) for k, v in cond.items())
        if sec.get("auto_off") is None or sec.get("auto_off") != hit:
            sec["enabled"] = not hit
            sec["auto_off"] = hit


def create(slug: str, title: str = "", fields: dict | None = None) -> str:
    t = get_template(slug)
    did = time.strftime("%Y%m%d-%H%M%S") + "-" + store.slugify(title or t["name"])[:24]
    d = WDOCS / did
    for sub in ("materials", "figures", "out"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    now = time.strftime("%Y-%m-%d %H:%M")
    doc = {"template": slug, "title": title or t["name"], "created": now, "updated": now,
           "fields": dict(fields or {}), "brief": "", "transcripts": [], "sections": {},
           "questions_done": [], "last_build": None}
    _sync_sections(doc, t)
    _write(did, doc)
    return did


def get(did: str) -> dict:
    doc = _read(did)
    try:
        t = get_template(doc["template"])
        _sync_sections(doc, t)
    except KeyError:
        t = None
    d = ddir(did)
    doc["id"] = did
    doc["materials"] = materials_info(did)
    doc["figure_files"] = sorted(p.name for p in (d / "figures").iterdir() if p.suffix.lower() in IMG_EXT)
    outs = sorted((d / "out").glob("*"), key=lambda p: p.stat().st_mtime, reverse=True) if (d / "out").exists() else []
    doc["outputs"] = [{"name": p.name, "size": p.stat().st_size,
                       "time": time.strftime("%d.%m %H:%M", time.localtime(p.stat().st_mtime))} for p in outs[:12]]
    doc["todo"] = sum(len(q["items"]) for q in questions(did, doc, t))
    return doc


def update(did: str, patch: dict) -> dict:
    doc = _read(did)
    for k in ("title", "fields", "brief", "questions_done"):
        if k in patch:
            doc[k] = patch[k]
    if "sections" in patch:
        for sid, val in (patch["sections"] or {}).items():
            cur = doc["sections"].setdefault(sid, {})
            for kk, vv in val.items():
                if kk in ("enabled", "text", "rows", "items", "steps", "value", "figures", "questions"):
                    cur[kk] = vv
            if "enabled" in val:
                cur["auto_off"] = cur.get("auto_off")   # ручное включение/выключение остаётся
            if any(k in val for k in ("text", "rows", "items", "steps", "value")):
                cur["edited"] = True
    try:
        _apply_off_if(doc, get_template(doc["template"])) if "fields" in patch else None
    except KeyError:
        pass
    _write(did, doc)
    return get(did)


def delete(did: str):
    shutil.rmtree(ddir(did), ignore_errors=True)


def list_all() -> list[dict]:
    out = []
    for d in sorted(WDOCS.iterdir(), reverse=True):
        p = d / "doc.json"
        if not p.exists():
            continue
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        filled = sum(1 for s in doc.get("sections", {}).values() if _has_content(s))
        out.append({"id": d.name, "title": doc.get("title"), "template": doc.get("template"),
                    "created": doc.get("created"), "updated": doc.get("updated"),
                    "last_build": doc.get("last_build"), "filled": filled,
                    "total": len(doc.get("sections", {}))})
    return out


def _has_content(s: dict) -> bool:
    return bool((s.get("text") or "").strip() or any(any(str(c).strip() for c in r) for r in s.get("rows") or [])
                or s.get("items") or s.get("steps") or s.get("figures"))


# ------------------------------------------------------------------ материалы и рисунки

def materials_info(did: str) -> list[dict]:
    from .extract import AUDIO_EXT, VIDEO_EXT, file_text
    d = ddir(did) / "materials"
    out = []
    for p in sorted(d.iterdir()):
        if p.is_dir() or p.name.endswith(".transcript.txt") or p.name.startswith("~$"):
            continue
        media = p.suffix.lower() in AUDIO_EXT + VIDEO_EXT
        txt = None if media else file_text(p)
        out.append({"name": p.name, "size": p.stat().st_size, "chars": len(txt or ""),
                    "kind": "media" if media else ("image" if p.suffix.lower() in IMG_EXT else "text")})
    doc = _read(did)
    from . import transcribe
    for tid in doc.get("transcripts", []):
        try:
            t = transcribe.read(tid)
            out.append({"name": t.get("title") or tid, "transcript": tid, "status": t.get("status"),
                        "kind": "transcript", "chars": sum(len(s.get("text", "")) for s in t.get("segments", []))})
        except KeyError:
            out.append({"name": f"(удалена) {tid}", "transcript": tid, "status": "missing", "kind": "transcript", "chars": 0})
    return out


def add_material(did: str, filename: str, data: bytes) -> str:
    from .files import safe_name, unique
    p = unique(ddir(did) / "materials" / safe_name(filename))
    p.write_bytes(data)
    return p.name


def add_material_path(did: str, src: Path) -> str:
    return add_material(did, src.name, src.read_bytes())


def remove_material(did: str, name: str):
    p = ddir(did) / "materials" / Path(name).name
    p.unlink(missing_ok=True)


def link_transcript(did: str, tid: str, on: bool = True):
    doc = _read(did)
    lst = [x for x in doc.get("transcripts", []) if x != tid]
    if on:
        lst.append(tid)
    doc["transcripts"] = lst
    _write(did, doc)


def add_figure(did: str, filename: str, data: bytes, section: str | None = None, caption: str = "") -> str:
    from .files import safe_name, unique
    ext = Path(filename).suffix.lower()
    if ext not in IMG_EXT:
        raise ValueError("Рисунок: нужен png, jpg, webp, gif или bmp")
    p = unique(ddir(did) / "figures" / safe_name(filename))
    p.write_bytes(data)
    if section:
        doc = _read(did)
        sec = doc["sections"].setdefault(section, {"enabled": True})
        sec.setdefault("figures", []).append({"file": p.name, "caption": caption or Path(p.name).stem})
        _write(did, doc)
    return p.name


def remove_figure(did: str, name: str):
    (ddir(did) / "figures" / Path(name).name).unlink(missing_ok=True)
    doc = _read(did)
    for s in doc["sections"].values():
        if s.get("figures"):
            s["figures"] = [f for f in s["figures"] if f.get("file") != name]
    _write(did, doc)


# ================================================================== текст для модели

def materials_texts(did: str) -> list[tuple[str, str]]:
    from . import transcribe
    from .extract import file_text, AUDIO_EXT, VIDEO_EXT
    d = ddir(did) / "materials"
    out = []
    for p in sorted(d.iterdir()):
        if p.is_dir() or p.suffix.lower() in AUDIO_EXT + VIDEO_EXT + IMG_EXT or p.name.endswith(".transcript.txt"):
            continue
        t = file_text(p)
        if t and t.strip():
            out.append((p.name, t.strip()))
    for tid in _read(did).get("transcripts", []):
        try:
            tr = transcribe.read(tid)
            if tr.get("status") == "done":
                txt = transcribe.as_text(tid)
                notes = "\n\n".join(n["text"] for n in tr.get("notes", [])[:3])
                if notes:
                    txt += "\n\n[Конспекты этой встречи]\n" + notes
                out.append((f"Расшифровка: {tr.get('title') or tid}", txt))
        except KeyError:
            pass
    return out


def _words(s: str) -> list[str]:
    return re.findall(r"[a-zа-яё0-9]{3,}", s.lower())


def _stem(w: str) -> str:
    return w[:6] if len(w) > 6 else w


def pick_context(texts: list[tuple[str, str]], query: str, budget: int = CTX_BUDGET) -> tuple[str, str]:
    """Всё, если влезает; иначе начало каждого файла + куски, похожие на запрос (TF-IDF)."""
    if not texts:
        return "", ""
    total = sum(len(t) for _, t in texts)
    if total <= budget:
        return "\n\n".join(f"=== {n} ===\n{t}" for n, t in texts), ""
    q = Counter(_stem(w) for w in _words(query))
    chunks = [(n, i, t[i:i + CHUNK]) for n, t in texts for i in range(0, len(t), CHUNK)]
    df = Counter()
    for _, _, c in chunks:
        df.update(set(_stem(w) for w in _words(c)))
    N = len(chunks)

    def score(c):
        tf = Counter(_stem(w) for w in _words(c))
        return sum(tf[w] * math.log(1 + N / (1 + df[w])) for w in q)
    picked, used = [], 0
    for n, t in texts:
        picked.append((n, 0, t[:CHUNK]))
        used += min(len(t), CHUNK)
    seen = {(a, b) for a, b, _ in picked}
    for ch in sorted(chunks, key=lambda x: -score(x[2])):
        if used + len(ch[2]) > budget:
            break
        if (ch[0], ch[1]) not in seen:
            picked.append(ch)
            seen.add((ch[0], ch[1]))
            used += len(ch[2])
    picked.sort(key=lambda x: (x[0], x[1]))
    parts, cur = [], None
    for n, i, c in picked:
        if n != cur:
            parts.append(f"=== {n} (фрагменты) ===")
            cur = n
        parts.append(f"[…позиция {i}…]\n{c}")
    return "\n\n".join(parts), f"материалы большие ({total} симв.) — взяты фрагменты ({used} симв.)"


# ================================================================== генерация

MARKUP_HELP = """Разметка текста (её понимает сборщик документа):
- абзацы разделяй пустой строкой;
- нумерованный список: «1. …»; вложенный уровень — отступ 3 пробела перед номером; сборщик сам сделает формат «1. a. i.»;
- маркированный список: «- …»;
- **жирный**, *курсив*; переменная — #Имя переменной#; ссылка на шаг — **Шаг N** (с заглавной);
- примечание (пояснение без условий, курсивом под пунктом): строка «> Примечание: …» с тем же отступом, что у пункта;
- таблица: строка «Таблица: Краткое название», на следующей строке — таблица markdown (| A | B |, строка |---|---|);
- запрос/код: блок ```sql Заголовок блока``` … ``` (язык: sql, json, xml, python, bash, http, text). Внутри можно выделить используемые атрибуты **жирным**;
- рисунок: «![Краткое название](имя_файла)» — только файлы из списка приложенных рисунков;
- шаблон уведомления: строка «Шаблон: Краткое описание», за ней строки шаблона без пустых строк."""

SYSTEM = """Ты — {role}. Ты заполняешь рабочий документ «{tname}».
Пиши по-русски, официально-деловым стилем, конкретно и без воды.
Опирайся только на материалы, описание от аналитика и уже заполненные разделы. Не выдумывай ФИО, ссылки, адреса, цифры, названия полей.
Если нужного факта нет — поставь в текст маркер [уточнить: что именно] и добавь короткий вопрос к заказчику в "questions".
Вопросы формулируй так, чтобы их можно было сразу задать заказчику на встрече.
{rules}"""


def _schema(s: dict) -> dict:
    k = s["kind"]
    qs = {"type": "array", "items": {"type": "string"}}
    if k in ("text", "steps"):
        return {"type": "object", "properties": {"text": {"type": "string"}, "questions": qs},
                "required": ["text", "questions"]}
    if k == "list":
        return {"type": "object", "properties": {"items": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                                                 "questions": qs}, "required": ["items", "questions"]}
    if k == "choice":
        return {"type": "object", "properties": {"value": {"type": "string", "enum": s.get("options") or []},
                                                 "text": {"type": "string"}, "questions": qs},
                "required": ["value", "text", "questions"]}
    if k == "asis_steps":
        step = {"type": "object", "properties": {"title": {"type": "string"}, "role": {"type": "string"},
                                                 "actions": {"type": "array", "items": {"type": "string"}, "minItems": 1}},
                "required": ["title", "role", "actions"]}
        return {"type": "object", "properties": {"steps": {"type": "array", "items": step, "minItems": 1},
                                                 "questions": qs}, "required": ["steps", "questions"]}
    if k == "table":
        cols = table_ai_cols(s)
        if s.get("fixed_rows"):
            n = len(s["fixed_rows"])
            vals = {"type": "array", "items": {"type": "array", "items": {"type": "string"},
                                               "minItems": len(cols), "maxItems": len(cols)},
                    "minItems": n, "maxItems": n}
            return {"type": "object", "properties": {"values": vals, "questions": qs}, "required": ["values", "questions"]}
        row = {"type": "array", "items": {"type": "string"}, "minItems": len(cols), "maxItems": len(cols)}
        return {"type": "object", "properties": {"rows": {"type": "array", "items": row}, "questions": qs},
                "required": ["rows", "questions"]}
    raise ValueError(f"раздел «{s['title']}» не заполняется моделью")


def table_ai_cols(s: dict) -> list[int]:
    """Номера столбцов, которые пишет модель (без автонумерации и без закреплённого столбца)."""
    skip = set()
    if s.get("autonum"):
        skip.add(0)
    if s.get("fixed_rows"):
        skip.add(s.get("fixed_col", 0))
    return [i for i in range(len(s["columns"])) if i not in skip]


def section_as_text(s: dict, sec: dict, limit: int = 2500) -> str:
    """Короткое представление готового раздела — как контекст для следующих разделов."""
    k = s["kind"]
    if k in ("text", "steps"):
        txt = sec.get("text") or ""
    elif k == "table":
        rows = sec.get("rows") or []
        txt = "\n".join(" | ".join(str(c) for c in r) for r in rows if any(str(c).strip() for c in r))
        if txt:
            txt = " | ".join(s["columns"]) + "\n" + txt
    elif k == "list":
        txt = "\n".join("- " + x for x in sec.get("items") or [])
    elif k == "asis_steps":
        txt = "\n".join(f"Шаг {i}. {st.get('title')} ({st.get('role')}): " + "; ".join(st.get("actions") or [])
                        for i, st in enumerate(sec.get("steps") or [], 1))
    elif k == "choice":
        txt = f"{sec.get('value')}. {sec.get('text') or ''}"
    elif k == "figures":
        txt = "Рисунки: " + ", ".join(f"{f['file']} («{f.get('caption')}»)" for f in sec.get("figures") or [])
    else:
        txt = ""
    txt = txt.strip()
    return txt[:limit] + ("…" if len(txt) > limit else "")


def _kind_instructions(s: dict, doc: dict, t: dict) -> str:
    k = s["kind"]
    if k == "text":
        extra = "Верни текст раздела в поле text (без заголовка раздела)."
        if t["kind"] == "build":
            extra += "\n" + MARKUP_HELP
        else:
            extra += " Только абзацы через пустую строку; маркированный список «- …» допустим."
        return extra
    if k == "steps":
        return ("Верни в поле text нумерованный список шагов (без заголовка раздела). Каждый пункт верхнего уровня — "
                "одно логическое действие робота и начинается со слова «Робот». Условия — подпунктами, каждое начинается "
                "с «Если». В конце пункта — переход: «…, робот переходит на **Шаг N**» или «робот завершает работу». "
                "Список любого уровня — минимум из двух пунктов.\n" + MARKUP_HELP)
    if k == "table":
        cols = [s["columns"][i] for i in table_ai_cols(s)]
        if s.get("fixed_rows"):
            rows = "\n".join(f"{i}. {r}" for i, r in enumerate(s["fixed_rows"], 1))
            return (f"Верни в values по одной строке на каждую позицию ниже (ровно {len(s['fixed_rows'])}), "
                    f"в каждой строке значения столбцов: {', '.join(cols)}.\nПозиции:\n{rows}")
        return (f"Верни строки таблицы в rows; в каждой строке ровно {len(cols)} значения — столбцы: "
                f"{' | '.join(cols)}." + (" Номер строки не пиши — он проставится сам." if s.get("autonum") else "")
                + " Внутри ячейки перенос строки — \\n.")
    if k == "list":
        return "Верни пункты списка в items — без нумерации и без знаков препинания в конце."
    if k == "asis_steps":
        return ("Верни шаги в steps: title — короткое название шага (с глагола), role — исполнитель "
                "(например, «Бухгалтер»), actions — действия по порядку, каждое начинается с «Пользователь …».")
    if k == "choice":
        return f"Верни value — одно из: {', '.join(s.get('options') or [])}; в text — 1–2 предложения обоснования."
    return ""


def build_prompt(did: str, sid: str, doc: dict | None = None, t: dict | None = None) -> list[dict]:
    doc = doc or get(did)
    t = t or get_template(doc["template"])
    s = next(x for x in t["sections"] if x["id"] == sid)
    rules = ""
    if t.get("rules_text"):
        rules = "\nТребования к оформлению документа (соблюдай их):\n" + t["rules_text"]
    from reportgen import profile
    system = SYSTEM.format(role=profile.get("analyst_role"), tname=t["name"], rules=rules)

    fields = "\n".join(f"- {f['label']}: {doc['fields'].get(f['key'], '')}" for f in t.get("fields", [])
                       if f.get("type") != "bool" and str(doc["fields"].get(f["key"], "")).strip())
    done = []
    budget = 9000
    for x in t["sections"]:
        if x["id"] == sid or not doc["sections"].get(x["id"], {}).get("enabled", True):
            continue
        txt = section_as_text(x, doc["sections"].get(x["id"], {}))
        if txt and budget > 0:
            done.append(f"## {x['title']}\n{txt}")
            budget -= len(txt)
    mats = [m for m in doc.get("materials", []) if m.get("kind") != "transcript"]
    figs = doc.get("figure_files") or []
    ctx, note = pick_context(materials_texts(did), f"{s['title']} {s.get('hint', '')} {doc.get('brief', '')}")

    parts = [f"# Документ: {t['name']} — {doc.get('title', '')}"]
    if fields:
        parts.append("# Карточка\n" + fields)
    if (doc.get("brief") or "").strip():
        parts.append("# Что известно (описание аналитика)\n" + doc["brief"].strip())
    if mats:
        parts.append("# Приложенные файлы\n" + "\n".join(f"- {m['name']}" for m in mats))
    if figs and t["kind"] == "build":
        parts.append("# Приложенные рисунки (для ![…](файл))\n" + "\n".join(f"- {f}" for f in figs))
    if done:
        parts.append("# Уже заполненные разделы\n" + "\n\n".join(done))
    if ctx:
        parts.append("# Материалы\n" + ctx)
    parts.append(f"# Задача\nЗаполни раздел «{s['title']}».\nЧто должно быть в разделе: {s.get('hint', '')}\n"
                 + _kind_instructions(s, doc, t) + "\nВерни только JSON.")
    return [{"role": "system", "content": system}, {"role": "user", "content": "\n\n".join(parts)}], note


def _apply(s: dict, sec: dict, data: dict):
    k = s["kind"]
    if k in ("text", "steps"):
        sec["text"] = (data.get("text") or "").strip()
    elif k == "list":
        sec["items"] = [re.sub(r"[;.,]\s*$", "", x.strip()) for x in data.get("items") or [] if x.strip()]
    elif k == "choice":
        sec["value"] = data.get("value") or sec.get("value")
        sec["text"] = (data.get("text") or "").strip()
    elif k == "asis_steps":
        sec["steps"] = [{"title": x.get("title", "").strip(), "role": x.get("role", "").strip(),
                         "actions": [a.strip() for a in x.get("actions") or [] if a.strip()]}
                        for x in data.get("steps") or []]
    elif k == "table":
        cols = table_ai_cols(s)
        n = len(s["columns"])
        if s.get("fixed_rows"):
            fc = s.get("fixed_col", 0)
            rows = []
            for i, name in enumerate(s["fixed_rows"]):
                r = [""] * n
                r[fc] = name
                vals = (data.get("values") or [])[i] if i < len(data.get("values") or []) else []
                for j, c in enumerate(cols):
                    r[c] = str(vals[j]).replace("\\n", "\n") if j < len(vals) else ""
                if s.get("autonum") and fc != 0:
                    r[0] = str(i + 1)
                rows.append(r)
        else:
            rows = []
            for vals in data.get("rows") or []:
                r = [""] * n
                for j, c in enumerate(cols):
                    r[c] = str(vals[j]).replace("\\n", "\n") if j < len(vals) else ""
                rows.append(r)
        sec["rows"] = rows
    sec["questions"] = [q.strip() for q in data.get("questions") or [] if q.strip()]
    sec["generated"] = time.strftime("%Y-%m-%d %H:%M")
    sec["edited"] = False


def generate(did: str, sids: list[str] | None, job, only_empty: bool = False) -> dict:
    """Заполнить разделы моделью. sids=None — все, которые модель умеет заполнять."""
    from reportgen import llm
    t = get_template(_read(did)["template"])
    plan = [s for s in t["sections"] if s.get("ai") and (sids is None or s["id"] in sids)]
    job.emit(f"Модель: {llm.ping()} · разделов: {len(plan)}")
    done, failed = 0, []
    for i, s in enumerate(plan, 1):
        if job.stop_requested():
            from reportgen.pipeline import Stopped
            raise Stopped()
        doc = get(did)
        sec = doc["sections"].get(s["id"], {})
        if sids is None and not sec.get("enabled", True):
            job.emit(f"[{i}/{len(plan)}] {s['title']} — выключен, пропуск")
            continue
        if only_empty and _has_content(sec) and s["kind"] != "table":
            job.emit(f"[{i}/{len(plan)}] {s['title']} — уже заполнен, пропуск")
            continue
        if sids is None and sec.get("edited") and _has_content(sec):
            job.emit(f"[{i}/{len(plan)}] {s['title']} — правлен вручную, не трогаю")
            continue
        msgs, note = build_prompt(did, s["id"], doc, t)
        job.emit(f"[{i}/{len(plan)}] {s['title'].rstrip('.')}…" + (f" ({note})" if note else ""))
        data, err = None, None
        for attempt in range(1, 3):
            t0 = time.time()
            try:
                content, stats = llm.chat(msgs, _schema(s))
                data = json.loads(content)
                job.emit(f"    — OK за {time.time() - t0:.0f} с, {stats.get('output_tokens') or '?'} ток.")
                break
            except Exception as e:  # noqa
                err = e
                job.emit(f"    попытка {attempt}: ошибка — {e}")
        if data is None:
            failed.append(s["title"])
            continue
        raw = _read(did)
        cur = raw["sections"].setdefault(s["id"], {"enabled": True})
        _apply(s, cur, data)
        _write(did, raw)
        for q in cur["questions"][:5]:
            job.emit(f"    • вопрос: {q}")
        done += 1
    job.emit(f"Готово: заполнено {done}" + (f", не удалось: {', '.join(failed)}" if failed else ""))
    return {"done": done, "failed": failed}


# ================================================================== вопросы к заказчику

def questions(did: str, doc: dict | None = None, t: dict | None = None) -> list[dict]:
    doc = doc or _read(did)
    if t is None:
        try:
            t = get_template(doc["template"])
        except KeyError:
            return []
    done = set(doc.get("questions_done") or [])
    seen: set = set()
    out = []
    for s in t["sections"]:
        sec = doc["sections"].get(s["id"]) or {}
        if not sec.get("enabled", True):
            continue
        items = list(sec.get("questions") or [])
        blob = json.dumps({k: sec.get(k) for k in ("text", "rows", "items", "steps")}, ensure_ascii=False)
        for m in TODO_RE.finditer(blob):
            q = "Уточнить: " + m.group(1).strip().rstrip(".")
            if q not in items:
                items.append(q)
        items = [q for q in dict.fromkeys(items) if q not in done and q not in seen]
        seen.update(items)
        if items:
            out.append({"section": s["id"], "title": s["title"], "items": items})
    return out


def questions_text(did: str) -> str:
    doc = _read(did)
    lines = [f"Вопросы к заказчику — {doc.get('title', '')}", ""]
    n = 0
    for g in questions(did):
        lines.append(g["title"])
        for q in g["items"]:
            n += 1
            lines.append(f"{n}. {q}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


# ================================================================== проверка

def check(did: str) -> list[dict]:
    """Проверка документа: пустые разделы, незаполненные [поля], и для описания робота —
    «Требования к оформлению» (то, что можно проверить автоматически)."""
    from . import wdocs_render as R
    doc = get(did)
    t = get_template(doc["template"])
    out = []

    def add(level, sec, msg, sid=None):
        out.append({"level": level, "section": sec, "sid": sid, "msg": msg})

    figs = set(doc.get("figure_files") or [])
    mat_names = {m["name"].lower() for m in doc.get("materials", [])}
    mats_rows = doc["sections"].get("materials", {}).get("rows") or []
    for r in mats_rows:
        for c in r:
            mat_names.add(str(c).strip().lower())
    for f in t.get("fields", []):
        if f.get("type") != "bool" and not str(doc["fields"].get(f["key"], "")).strip():
            add("warn", "Карточка", f"не заполнено поле «{f['label']}»")

    for s in t["sections"]:
        sec = doc["sections"].get(s["id"], {})
        if not sec.get("enabled", True) or s["kind"] in ("heading", "fixed"):
            continue
        title, sid = s["title"], s["id"]
        if not _has_content(sec) and s["kind"] != "choice":
            if not s.get("intro"):
                add("warn", title, "раздел пустой", sid)
            continue
        blob = section_as_text(s, sec, 10 ** 6)
        for m in TODO_RE.finditer(blob):
            add("todo", title, f"[уточнить: {m.group(1)}]", sid)
        for m in re.finditer(r"<[А-ЯA-Z][^<>]{3,80}>", blob):
            add("warn", title, f"осталась заглушка шаблона {m.group(0)}", sid)
        if s["kind"] == "table":
            for i, r in enumerate(sec.get("rows") or [], 1):
                empty = [s["columns"][j] for j in table_ai_cols(s) if j < len(r) and not str(r[j]).strip()]
                if empty and len(empty) < len(table_ai_cols(s)):
                    add("info", title, f"строка {i}: пусто — {', '.join(empty)}", sid)
        if s["kind"] == "figures" and not sec.get("figures"):
            add("warn", title, "нет рисунка", sid)
        if s["kind"] == "figures":
            for f in sec.get("figures") or []:
                if f.get("file") not in figs:
                    add("err", title, f"файл рисунка не найден: {f.get('file')}", sid)

        if t["kind"] == "build" and s["kind"] in ("text", "steps"):
            out += [{**x, "section": title, "sid": sid} for x in R.lint_markup(sec.get("text") or "", s, figs, mat_names)]

    if t["kind"] == "build":
        launch = doc["sections"].get("launch", {}).get("text") or ""
        if launch and not re.search(r"понедельник|вторник|сред|четверг|пятниц|суббот|воскресен|ежедневно|будн", launch, re.I):
            add("warn", "Режим запуска робота.", "укажи конкретные дни недели и время запуска", "launch")
        if launch and not re.search(r"праздн|выходн|производственн", launch, re.I):
            add("warn", "Режим запуска робота.", "укажи, как робот работает в выходные и праздники / по производственному календарю", "launch")
        biz = doc["sections"].get("business", {}).get("text") or ""
        if biz and len([p for p in re.split(r"\n\s*\n", biz) if p.strip()]) != 3:
            add("info", "Бизнес-описание", "по шаблону — ровно три абзаца (для кого/что, подробнее, цифры и польза)", "business")
        if biz and not re.search(r"\d", biz):
            add("warn", "Бизнес-описание", "нет количественных показателей (сколько времени тратили сотрудники)", "business")
    order = {"err": 0, "warn": 1, "todo": 2, "info": 3}
    return sorted(out, key=lambda x: order.get(x["level"], 9))
