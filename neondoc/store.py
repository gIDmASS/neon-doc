"""Хранилище: шаблоны (library/templates/<slug>) и работы (works/<id>). Всё — обычные файлы,
их можно открыть руками, а старые .bat продолжают работать с папками работ."""
from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path

import yaml

from reportgen.schema import Meta

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "library" / "templates"
WORKS = ROOT / "works"
LIB.mkdir(parents=True, exist_ok=True)
WORKS.mkdir(parents=True, exist_ok=True)

IMG_EXT = (".png", ".jpg", ".jpeg", ".webp")

_TR = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
               ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r",
                "s", "t", "u", "f", "kh", "ts", "ch", "sh", "sch", "", "y", "", "e", "yu", "ya"]))


def slugify(s: str) -> str:
    s = "".join(_TR.get(c, c) for c in s.lower())
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:40] or "item"


def _unique(base: Path, slug: str) -> str:
    cand, n = slug, 2
    while (base / cand).exists():
        cand, n = f"{slug}-{n}", n + 1
    return cand


def read_yaml(p: Path) -> dict:
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {} if p.exists() else {}


def write_yaml(p: Path, data: dict):
    p.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def read_json(p: Path, default=None):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def write_json(p: Path, data):
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ================================================================== шаблоны

TEMPLATE_DEFAULTS = {
    "name": "Новый шаблон",
    "category": "ВУЗ",
    "description": "",
    "tags": [],
    "meta": {"work_type": "Практическая работа", "discipline": "", "module": None, "semester": 3,
             "teacher": "______________", "file_code": "XX", "toc": False, "intro": False,
             "conclusion": "ВЫВОДЫ", "h1_new_page": True},
    "roles": [],
    "fixed_sections": [],
    "prompt_hints": "",
    "brief_skeleton": {"task": "", "data": "", "decisions": ""},
}


def _previews(d: Path) -> list[str]:
    pv = d / "previews"
    if not pv.exists():
        return []
    return [f"/library/{d.name}/previews/{p.name}?v={int(p.stat().st_mtime)}"
            for p in sorted(pv.iterdir()) if p.suffix.lower() in IMG_EXT]


def list_templates() -> list[dict]:
    out = []
    for d in sorted(LIB.iterdir()):
        if (d / "template.yaml").exists():
            t = read_yaml(d / "template.yaml")
            out.append({**TEMPLATE_DEFAULTS, **t, "slug": d.name, "previews": _previews(d),
                        "works": sum(1 for w in list_works() if w.get("template") == d.name)})
    return out


def get_template(slug: str) -> dict:
    d = LIB / slug
    if not (d / "template.yaml").exists():
        raise KeyError(slug)
    t = read_yaml(d / "template.yaml")
    return {**TEMPLATE_DEFAULTS, **t, "slug": slug, "previews": _previews(d)}


def save_template(slug: str | None, data: dict) -> str:
    data = {k: v for k, v in data.items() if k in TEMPLATE_DEFAULTS}
    Meta(**{**data.get("meta", {}), "number": "1", "topic": "x", "year": 2026})  # проверка полей
    if not slug:
        slug = _unique(LIB, slugify(data.get("name", "template")))
    d = LIB / slug
    (d / "previews").mkdir(parents=True, exist_ok=True)
    write_yaml(d / "template.yaml", {**TEMPLATE_DEFAULTS, **data})
    return slug


def delete_template(slug: str):
    shutil.rmtree(LIB / slug, ignore_errors=True)


def add_preview(slug: str, filename: str, content: bytes) -> str:
    pv = LIB / slug / "previews"
    pv.mkdir(parents=True, exist_ok=True)
    n = len([p for p in pv.iterdir() if p.suffix.lower() in IMG_EXT]) + 1
    ext = Path(filename).suffix.lower() if Path(filename).suffix.lower() in IMG_EXT else ".png"
    name = f"{n:02d}{ext}"
    (pv / name).write_bytes(content)
    return name


def delete_preview(slug: str, name: str):
    p = LIB / slug / "previews" / Path(name).name
    if p.exists():
        p.unlink()
    # перенумеровать, чтобы порядок оставался 01, 02, …
    pv = LIB / slug / "previews"
    files = sorted(x for x in pv.iterdir() if x.suffix.lower() in IMG_EXT)
    tmp = [f.rename(f.with_name(f"__{i:02d}{f.suffix}")) for i, f in enumerate(files, 1)]
    for i, f in enumerate(tmp, 1):
        f.rename(f.with_name(f"{i:02d}{f.suffix.lower()}"))


# ================================================================== работы

WORK_DEFAULTS = {
    "title": "", "template": "", "created": "", "updated": "",
    "meta": {}, "roles": [],
    "brief": {"task": "", "data": "", "decisions": ""},
    "sources": "",
    "manual_minutes": None,   # сколько заняла бы работа вручную — для кейса «до/после»
    "review_minutes": None,   # сколько ушло на проверку и правки после генерации
    "notes": "",
}


def work_dir(wid: str) -> Path:
    d = WORKS / Path(wid).name
    if not d.exists():
        raise KeyError(wid)
    return d


def create_work(template_slug: str, title: str) -> str:
    t = get_template(template_slug)
    wid = time.strftime("%Y%m%d-%H%M%S") + "-" + slugify(title or t["name"])[:24]
    d = WORKS / wid
    (d / "figures").mkdir(parents=True)
    (d / "attachments").mkdir()
    now = time.strftime("%Y-%m-%d %H:%M")
    work = {**WORK_DEFAULTS, "title": title or t["name"], "template": template_slug,
            "created": now, "updated": now,
            "meta": {**t["meta"], "number": "", "topic": "", "year": int(time.strftime("%Y")),
                     "date": "______________"},
            "roles": list(t.get("roles") or []),
            "brief": {**WORK_DEFAULTS["brief"], **(t.get("brief_skeleton") or {})}}
    if not str(work["meta"].get("teacher") or "").strip("_ "):
        from reportgen import profile
        work["meta"]["teacher"] = profile.get("teacher")
    write_json(d / "work.json", work)
    sync_task_files(wid)
    return wid


def get_work(wid: str) -> dict:
    d = work_dir(wid)
    w = {**WORK_DEFAULTS, **read_json(d / "work.json", {})}
    w["id"] = wid
    w["outline"] = read_json(d / "outline.json")
    w["report"] = read_json(d / "report.json")
    w["review"] = [x for x in (d / "review.txt").read_text(encoding="utf-8").splitlines() if x.strip()] \
        if (d / "review.txt").exists() else []
    from .extract import attachment_info
    w["attachments"] = attachment_info(d / "attachments")
    w["figures"] = sorted(p.name for p in (d / "figures").iterdir() if p.suffix.lower() in IMG_EXT) \
        if (d / "figures").exists() else []
    docx = sorted(d.glob("*.docx"))
    w["docx"] = docx[0].name if docx else None
    w["stats"] = work_stats(d)
    w["stage"] = ("done" if w["docx"] else "text" if w["report"] else "plan" if w["outline"] else "brief")
    return w


def update_work(wid: str, patch: dict) -> dict:
    d = work_dir(wid)
    w = {**WORK_DEFAULTS, **read_json(d / "work.json", {})}
    for k in WORK_DEFAULTS:
        if k in patch and k not in ("created",):
            w[k] = patch[k]
    w["updated"] = time.strftime("%Y-%m-%d %H:%M")
    write_json(d / "work.json", w)
    sync_task_files(wid)
    return get_work(wid)


def delete_work(wid: str):
    shutil.rmtree(work_dir(wid), ignore_errors=True)


def list_works() -> list[dict]:
    out = []
    for d in sorted(WORKS.iterdir(), reverse=True):
        if (d / "work.json").exists():
            w = read_json(d / "work.json", {})
            out.append({"id": d.name, "title": w.get("title"), "template": w.get("template"),
                        "created": w.get("created"), "updated": w.get("updated"),
                        "manual_minutes": w.get("manual_minutes"),
                        "review_minutes": w.get("review_minutes"),
                        "has_docx": any(d.glob("*.docx")), "stats": work_stats(d)})
    return out


def compose_brief(w: dict, attachments_text: str) -> str:
    b = w.get("brief") or {}
    parts = []
    if b.get("task", "").strip():
        parts.append("# Задание\n\n" + b["task"].strip())
    if b.get("data", "").strip():
        parts.append("# Исходные данные\n\n" + b["data"].strip())
    if b.get("decisions", "").strip():
        parts.append("# Мои решения\n\n" + b["decisions"].strip())
    if attachments_text.strip():
        parts.append("# Приложенные материалы\n\n" + attachments_text.strip())
    figs = [p.stem for p in (WORKS / w["id"] / "figures").iterdir()] if w.get("id") else []
    if figs:
        parts.append("Готовые рисунки (id): " + ", ".join(sorted(figs)) + ".")
    return "\n\n".join(parts)


def sync_task_files(wid: str):
    """work.json -> task.yaml, brief.md, sources.txt (их читает reportgen)."""
    from .extract import attachments_text
    d = work_dir(wid)
    w = {**WORK_DEFAULTS, **read_json(d / "work.json", {}), "id": wid}
    t = {}
    try:
        t = get_template(w["template"])
    except KeyError:
        pass
    meta = {k: v for k, v in (w.get("meta") or {}).items() if k in Meta.model_fields}
    meta.setdefault("number", "")
    meta.setdefault("topic", w.get("title", ""))
    meta.setdefault("year", int(time.strftime("%Y")))
    task = {**meta, "roles": w.get("roles") or [],
            "fixed_sections": t.get("fixed_sections") or [],
            "prompt_hints": t.get("prompt_hints") or ""}
    write_yaml(d / "task.yaml", task)
    (d / "brief.md").write_text(compose_brief(w, attachments_text(d / "attachments")), encoding="utf-8")
    (d / "sources.txt").write_text(w.get("sources") or "", encoding="utf-8")


def reset_from(wid: str, stage: str):
    """Сбросить результаты, начиная со стадии: plan -> всё; text -> разделы и docx."""
    d = work_dir(wid)
    if stage == "plan":
        for f in ("outline.json",):
            (d / f).unlink(missing_ok=True)
    if stage in ("plan", "text"):
        shutil.rmtree(d / "sections", ignore_errors=True)
        for f in ("report.json", "review.txt"):
            (d / f).unlink(missing_ok=True)
        for f in d.glob("*.docx"):
            try:
                f.unlink()
            except PermissionError:
                # файл открыт в Word — не мешаем; новая сборка ляжет рядом под другим именем
                pass


def save_outline(wid: str, outline: dict):
    from reportgen.schema import Outline
    o = Outline(**outline)
    d = work_dir(wid)
    old = read_json(d / "outline.json")
    write_json(d / "outline.json", o.model_dump())
    # изменённый план делает старые разделы недействительными — только изменившиеся
    if old:
        for i, s in enumerate(o.sections, 1):
            old_s = old["sections"][i - 1] if i - 1 < len(old["sections"]) else None
            if old_s != s.model_dump():
                (d / "sections" / f"{i:02d}.json").unlink(missing_ok=True)
        for i in range(len(o.sections) + 1, 50):
            (d / "sections" / f"{i:02d}.json").unlink(missing_ok=True)


def save_report(wid: str, report: dict):
    """Правки текста в приложении: report.json + файлы разделов (чтобы «дописать» их не затёрло)."""
    from reportgen.schema import Report
    d = work_dir(wid)
    r = Report(**report)
    write_json(d / "report.json", r.model_dump())
    sd = d / "sections"
    sd.mkdir(exist_ok=True)
    for i, s in enumerate(r.sections, 1):
        write_json(sd / f"{i:02d}.json", s.model_dump())
    if r.intro:
        write_json(sd / "intro.json", {"paragraphs": r.intro})
    if r.conclusion:
        write_json(sd / "conclusion.json", {"paragraphs": r.conclusion})


def regenerate_section(wid: str, index: int):
    d = work_dir(wid)
    (d / "sections" / f"{index:02d}.json").unlink(missing_ok=True)


# ================================================================== метрики

def work_stats(d: Path) -> dict:
    f = d / "run_log.jsonl"
    st = {"calls": 0, "model_seconds": 0.0, "first_try": 0, "steps": 0, "failed_calls": 0,
          "tokens_out": 0, "todo": 0}
    if f.exists():
        seen_steps = set()
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            st["calls"] += 1
            st["model_seconds"] += float(r.get("wall_s") or 0)
            st["tokens_out"] += int(r.get("output_tokens") or 0)
            if not r.get("ok"):
                st["failed_calls"] += 1
            if r.get("attempt") == 1:
                st["steps"] += 1
                if r.get("ok"):
                    st["first_try"] += 1
            seen_steps.add(r.get("step"))
    rp = d / "report.json"
    if rp.exists():
        st["todo"] = len(re.findall(r"\[уточнить:", rp.read_text(encoding="utf-8")))
    st["model_seconds"] = round(st["model_seconds"], 1)
    return st


def metrics() -> dict:
    ws = list_works()
    done = [w for w in ws if w["has_docx"]]
    model_min = sum(w["stats"]["model_seconds"] for w in ws) / 60
    steps = sum(w["stats"]["steps"] for w in ws)
    first = sum(w["stats"]["first_try"] for w in ws)
    paired = [w for w in done if w.get("manual_minutes")]
    saved = sum((w["manual_minutes"] or 0) - (w["review_minutes"] or 0) - w["stats"]["model_seconds"] / 60
                for w in paired)
    return {"works": len(ws), "done": len(done), "model_minutes": round(model_min, 1),
            "first_try_rate": round(100 * first / steps) if steps else None,
            "todo_total": sum(w["stats"]["todo"] for w in ws),
            "paired": len(paired), "saved_minutes": round(saved) if paired else None,
            "manual_total": sum(w["manual_minutes"] or 0 for w in paired),
            "after_total": round(sum((w["review_minutes"] or 0) + w["stats"]["model_seconds"] / 60
                                     for w in paired))}
