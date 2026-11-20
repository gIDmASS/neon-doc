"""API рабочих документов (вкладка «Работа» в шаблонах)."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Body, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse

from . import files, wdocs
from . import wdocs_render as R
from .jobs import jobs

router = APIRouter()


def _err(e: Exception, code=400):
    raise HTTPException(code, str(e))


def _doc(did: str) -> dict:
    try:
        return wdocs.get(did)
    except KeyError:
        _err(KeyError("Документ не найден"), 404)


# ------------------------------------------------------------------ шаблоны

@router.get("/api/wtemplates")
def wt_list():
    return wdocs.list_templates()


@router.get("/api/wtemplates/{slug}")
def wt_get(slug: str):
    try:
        return wdocs.get_template(slug)
    except KeyError:
        _err(KeyError("Шаблон не найден"), 404)


# ------------------------------------------------------------------ документы

@router.get("/api/wdocs")
def wd_list():
    return wdocs.list_all()


@router.post("/api/wdocs")
def wd_create(data: dict = Body(...)):
    try:
        return wdocs.get(wdocs.create(data["template"], data.get("title", ""), data.get("fields") or {}))
    except Exception as e:
        _err(e)


@router.get("/api/wdocs/{did}")
def wd_get(did: str):
    return _doc(did)


@router.put("/api/wdocs/{did}")
def wd_put(did: str, data: dict = Body(...)):
    _doc(did)
    return wdocs.update(did, data)


@router.delete("/api/wdocs/{did}")
def wd_del(did: str):
    _doc(did)
    wdocs.delete(did)
    return {"ok": True}


# ------------------------------------------------------------------ материалы

@router.post("/api/wdocs/{did}/materials")
async def wd_mat_add(did: str, files_: list[UploadFile] = File(..., alias="files")):
    _doc(did)
    from . import transcribe
    from .extract import AUDIO_EXT, VIDEO_EXT
    added, media = [], []
    for f in files_:
        data = await f.read()
        if Path(f.filename).suffix.lower() in AUDIO_EXT + VIDEO_EXT:
            tid = transcribe.create(f.filename, data, Path(f.filename).stem)
            wdocs.link_transcript(did, tid)
            media.append(tid)
        else:
            added.append(wdocs.add_material(did, f.filename, data))
    job = None
    if media:   # расшифровка — фоном; одна задача за раз, остальные можно запустить из «Расшифровки»
        from .routes_extra import _start_transcribe
        job = _start_transcribe(media[0], {})
    return {"added": added, "transcripts": media, "job": job, "doc": wdocs.get(did)}


@router.post("/api/wdocs/{did}/materials/from-storage")
def wd_mat_storage(did: str, data: dict = Body(...)):
    _doc(did)
    p = files.resolve(data["path"])
    if not p.is_file():
        _err(ValueError("Это не файл"))
    from . import transcribe
    from .extract import AUDIO_EXT, VIDEO_EXT
    if p.suffix.lower() in AUDIO_EXT + VIDEO_EXT:
        from .routes_extra import _start_transcribe
        tid = transcribe.create_from_path(p, p.stem)
        wdocs.link_transcript(did, tid)
        _start_transcribe(tid, {})
    else:
        wdocs.add_material_path(did, p)
    return wdocs.get(did)


@router.delete("/api/wdocs/{did}/materials/{name}")
def wd_mat_del(did: str, name: str):
    _doc(did)
    wdocs.remove_material(did, name)
    return wdocs.get(did)


@router.get("/api/wdocs/{did}/materials/{name}")
def wd_mat_raw(did: str, name: str):
    p = wdocs.ddir(did) / "materials" / Path(name).name
    if not p.exists():
        _err(KeyError(name), 404)
    return FileResponse(p, filename=p.name)


@router.post("/api/wdocs/{did}/transcripts")
def wd_tr(did: str, data: dict = Body(...)):
    _doc(did)
    wdocs.link_transcript(did, data["tid"], bool(data.get("on", True)))
    return wdocs.get(did)


# ------------------------------------------------------------------ рисунки

@router.post("/api/wdocs/{did}/figures")
async def wd_fig_add(did: str, file: UploadFile = File(...), section: str = Form(""), caption: str = Form("")):
    _doc(did)
    try:
        name = wdocs.add_figure(did, file.filename, await file.read(), section or None, caption)
    except Exception as e:
        _err(e)
    return {"name": name, "doc": wdocs.get(did)}


@router.post("/api/wdocs/{did}/figures/from-storage")
def wd_fig_storage(did: str, data: dict = Body(...)):
    _doc(did)
    p = files.resolve(data["path"])
    try:
        name = wdocs.add_figure(did, p.name, p.read_bytes(), data.get("section") or None, data.get("caption", ""))
    except Exception as e:
        _err(e)
    return {"name": name, "doc": wdocs.get(did)}


@router.post("/api/wdocs/{did}/figures/from-annot")
def wd_fig_annot(did: str, data: dict = Body(...)):
    """PNG из редактора разметки (dataURL) -> рисунок документа."""
    import base64
    _doc(did)
    raw = data["png"].split(",", 1)[-1]
    name = wdocs.add_figure(did, (data.get("name") or "скриншот") + ".png", base64.b64decode(raw),
                            data.get("section") or None, data.get("caption", ""))
    return {"name": name}


@router.delete("/api/wdocs/{did}/figures/{name}")
def wd_fig_del(did: str, name: str):
    _doc(did)
    wdocs.remove_figure(did, name)
    return wdocs.get(did)


@router.get("/api/wdocs/{did}/figures/{name}")
def wd_fig_raw(did: str, name: str):
    p = wdocs.ddir(did) / "figures" / Path(name).name
    if not p.exists():
        _err(KeyError(name), 404)
    return FileResponse(p)


# ------------------------------------------------------------------ Qwen, проверка, вопросы

@router.post("/api/wdocs/{did}/generate")
def wd_generate(did: str, data: dict = Body(default={})):
    doc = _doc(did)
    from .server import settings
    settings()
    sids = data.get("sections")
    title = "Qwen: " + (doc["title"] if not sids or len(sids) > 1 else
                        next((s["title"] for s in wdocs.get_template(doc["template"])["sections"] if s["id"] == sids[0]), sids[0]))
    try:
        return jobs.start("wdoc", title, lambda job: wdocs.generate(did, sids, job, bool(data.get("only_empty"))),
                          work_id=did).as_dict()
    except RuntimeError as e:
        _err(e, 409)


@router.get("/api/wdocs/{did}/prompt/{sid}", response_class=PlainTextResponse)
def wd_prompt(did: str, sid: str):
    """Что именно уйдёт в Qwen для раздела — для отладки и для копирования в другой чат."""
    msgs, note = wdocs.build_prompt(did, sid)
    return "\n\n".join(f"===== {m['role'].upper()} =====\n{m['content']}" for m in msgs)


@router.get("/api/wdocs/{did}/check")
def wd_check(did: str):
    _doc(did)
    return wdocs.check(did)


@router.get("/api/wdocs/{did}/questions")
def wd_questions(did: str):
    _doc(did)
    return {"groups": wdocs.questions(did), "text": wdocs.questions_text(did)}


# ------------------------------------------------------------------ сборка

@router.post("/api/wdocs/{did}/build")
def wd_build(did: str, data: dict = Body(default={})):
    _doc(did)
    fmt = data.get("format", "docx")
    if fmt not in ("docx", "pdf", "txt", "confluence"):
        _err(ValueError("Формат: docx, pdf, txt или confluence"))
    try:
        r = R.build(did, fmt)
    except Exception as e:
        _err(e)
    out = {"name": r["path"].name, "warnings": r["warnings"],
           "url": f"/api/wdocs/{did}/out/{r['path'].name}"}
    if data.get("to_storage", True):
        try:
            out["storage"] = R.file_to_storage(did, r["path"])
        except Exception as e:  # noqa
            out["warnings"].append(f"в Хранилище не скопировано: {e}")
    return out


@router.get("/api/wdocs/{did}/confluence", response_class=PlainTextResponse)
def wd_confluence(did: str):
    try:
        return R.confluence_text(did)
    except Exception as e:
        _err(e)


@router.get("/api/wdocs/{did}/out/{name}")
def wd_out(did: str, name: str):
    p = wdocs.ddir(did) / "out" / Path(name).name
    if not p.exists():
        _err(KeyError(name), 404)
    return FileResponse(p, filename=p.name)


@router.post("/api/wdocs/{did}/out/{name}/open")
def wd_out_open(did: str, name: str, data: dict = Body(default={})):
    from .osutil import open_path, reveal
    p = wdocs.ddir(did) / "out" / Path(name).name
    reveal(p) if data.get("reveal") else open_path(p)
    return {"ok": True}
