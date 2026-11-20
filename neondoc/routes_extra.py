"""API новых разделов: Хранилище, выгрузка Word/PDF/TXT, Расшифровка, файлы в чате, Разметка."""
from __future__ import annotations

import base64
import tempfile
import time
from pathlib import Path

from fastapi import APIRouter, Body, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from . import chatctx, export, files, store, transcribe
from .jobs import jobs

router = APIRouter()


def _settings():
    from .server import settings
    return settings()


def _err(e: Exception, code=400):
    raise HTTPException(code, str(e))


# ================================================================== хранилище

@router.get("/api/files/tree")
def f_tree():
    return files.tree()


@router.get("/api/files/folders")
def f_folders():
    return files.all_folders()


@router.get("/api/files/list")
def f_list(path: str = ""):
    try:
        return files.listdir(path)
    except Exception as e:
        _err(e, 404)


@router.get("/api/files/search")
def f_search(q: str):
    return files.search(q)


@router.post("/api/files/mkdir")
def f_mkdir(data: dict = Body(...)):
    try:
        return {"path": files.mkdir(data.get("path", ""), data["name"])}
    except Exception as e:
        _err(e)


@router.post("/api/files/upload")
async def f_upload(path: str = Form(""), items: list[UploadFile] = File(...)):
    saved = []
    for f in items:
        saved.append(files.save_bytes(path, Path(f.filename).name, await f.read()))
    return {"saved": saved}


@router.post("/api/files/rename")
def f_rename(data: dict = Body(...)):
    try:
        return {"path": files.rename(data["path"], data["name"])}
    except Exception as e:
        _err(e)


@router.post("/api/files/move")
def f_move(data: dict = Body(...)):
    try:
        return {"paths": [files.move(p, data["dest"]) for p in data["paths"]]}
    except Exception as e:
        _err(e)


@router.post("/api/files/delete")
def f_delete(data: dict = Body(...)):
    try:
        for p in data["paths"]:
            files.delete(p)
        return {"ok": True}
    except Exception as e:
        _err(e)


@router.get("/api/files/raw")
def f_raw(path: str, download: int = 0):
    p = files.resolve(path)
    if not p.is_file():
        raise HTTPException(404)
    return FileResponse(p, media_type=files.mime(p), filename=p.name if download else None,
                        content_disposition_type="attachment" if download else "inline")


@router.get("/api/files/text")
def f_text(path: str):
    from .extract import file_text
    p = files.resolve(path)
    t = file_text(p) or ""
    return {"text": t[:200000], "chars": len(t)}


@router.post("/api/files/open")
def f_open(data: dict = Body(...)):
    """Открыть файл программой по умолчанию; reveal=True — показать его в Проводнике."""
    import subprocess
    import sys
    from .server import _open
    p = files.resolve(data.get("path", ""))
    if data.get("reveal") and p.is_file():
        from .osutil import reveal
        reveal(p)
        return {"ok": True}
    _open(p)
    return {"ok": True}


@router.post("/api/files/convert")
def f_convert(data: dict = Body(...)):
    """Файл из хранилища -> docx/pdf/txt рядом с ним."""
    src = files.resolve(data["path"])
    fmt = data["format"]
    if fmt not in ("docx", "pdf", "txt"):
        _err(ValueError("Формат: docx, pdf или txt"))

    def run(job):
        job.emit(f"{src.name} → .{fmt}")
        out = export.convert_file(src, fmt, src.parent)
        job.emit(f"Готово: {out.name}")
        return {"path": files.rel_of(out)}
    try:
        return jobs.start("convert", f"Конвертация в {fmt.upper()}", run).as_dict()
    except RuntimeError as e:
        _err(e, 409)


# ================================================================== выгрузка текста (ответы Qwen, конспекты)

@router.post("/api/export")
def export_text(data: dict = Body(...)):
    """{title, text, format: docx|pdf|txt, folder?, name?, subtitle?} -> файл в хранилище."""
    fmt = data.get("format", "docx")
    if fmt not in ("docx", "pdf", "txt"):
        _err(ValueError("Формат: docx, pdf или txt"))
    folder = data.get("folder") or "Входящие"
    out_dir = files.resolve(folder)
    try:
        out = export.export_text(data.get("title", ""), data["text"], fmt, out_dir,
                                 data.get("name") or data.get("title") or "документ", data.get("subtitle", ""))
    except Exception as e:
        _err(e, 500)
    return {"path": files.rel_of(out), "name": out.name}


@router.get("/api/works/{wid}/export")
def work_export(wid: str, fmt: str = "pdf", folder: str = ""):
    d = store.work_dir(wid)
    docs = sorted(d.glob("*.docx"))
    if not docs:
        _err(ValueError("Документ ещё не собран"))
    w = store.read_json(d / "work.json", {})
    target = files.resolve(folder or files.folder_for_work(w.get("meta") or {}))
    try:
        if fmt == "docx":
            out = target / docs[0].name
            out.write_bytes(docs[0].read_bytes())
        else:
            out = export.convert_file(docs[0], fmt, target)
    except Exception as e:
        _err(e, 500)
    return {"path": files.rel_of(out), "name": out.name}


# ================================================================== расшифровка

@router.get("/api/transcripts")
def t_list():
    return transcribe.list_all()


@router.post("/api/transcripts")
async def t_create(file: UploadFile = File(...), title: str = Form(""), opts: str = Form("{}")):
    import json
    tid = transcribe.create(file.filename, await file.read(), title)
    return {"id": tid, "job": _start_transcribe(tid, json.loads(opts or "{}"))}


@router.post("/api/transcripts/from-storage")
def t_from_storage(data: dict = Body(...)):
    src = files.resolve(data["path"])
    tid = transcribe.create_from_path(src, data.get("title") or src.stem)
    return {"id": tid, "job": _start_transcribe(tid, data.get("opts") or {})}


def _start_transcribe(tid: str, opts: dict):
    s = _settings()
    opts = {"language": s.get("transcribe_language", "ru"), "diarize": s.get("diarize", True), "speakers": 0,
            "model": s["whisper_model"], "device": s["whisper_device"], **opts}
    try:
        return jobs.start("transcribe", "Расшифровка: " + transcribe.read(tid)["title"],
                          lambda job: transcribe.run(tid, opts, job)).as_dict()
    except RuntimeError as e:
        return {"error": str(e)}


@router.post("/api/transcripts/{tid}/run")
def t_rerun(tid: str, data: dict = Body({})):
    j = _start_transcribe(tid, data or {})
    if j.get("error"):
        _err(RuntimeError(j["error"]), 409)
    return j


@router.get("/api/transcripts/{tid}")
def t_get(tid: str):
    try:
        return transcribe.read(tid)
    except KeyError:
        raise HTTPException(404)


@router.put("/api/transcripts/{tid}")
def t_put(tid: str, data: dict = Body(...)):
    return transcribe.update(tid, data)


@router.delete("/api/transcripts/{tid}")
def t_del(tid: str):
    transcribe.delete(tid)
    return {"ok": True}


@router.get("/api/transcripts/{tid}/media")
def t_media(tid: str):
    p = transcribe.source_path(tid)
    return FileResponse(p, media_type=files.mime(p))


@router.post("/api/transcripts/{tid}/ai")
def t_ai(tid: str, data: dict = Body(...)):
    s = _settings()
    try:
        return jobs.start("ai", "Qwen по расшифровке",
                          lambda job: transcribe.ai_action(tid, data.get("action", "summary"), data.get("custom", ""), s, job)).as_dict()
    except RuntimeError as e:
        _err(e, 409)


@router.delete("/api/transcripts/{tid}/notes/{name}")
def t_del_note(tid: str, name: str):
    (transcribe.tdir(tid) / "notes" / f"{Path(name).name}.md").unlink(missing_ok=True)
    return transcribe.read(tid)


@router.post("/api/transcripts/{tid}/export")
def t_export(tid: str, data: dict = Body(...)):
    """{format, timecodes, speakers, folder, note?} — расшифровка или конспект в хранилище."""
    t = transcribe.read(tid)
    fmt = data.get("format", "docx")
    folder = data.get("folder") or "Работа/Встречи и расшифровки"
    if data.get("note"):
        n = next((x for x in t["notes"] if x["name"] == data["note"]), None)
        if not n:
            raise HTTPException(404)
        text, title, sub = n["text"], f"{t['title']} — {n['name'][7:] or 'конспект'}", ""
    else:
        tc, sp = data.get("timecodes", True), data.get("speakers", True)
        text = transcribe.as_text(tid, tc, sp) if fmt == "txt" else transcribe.as_markdown(tid, tc, sp)
        names = ", ".join((t.get("speakers") or {}).values())
        title = t["title"]
        sub = f"Расшифровка от {t.get('created', '')}" + (f". Участники: {names}" if names else "") + \
              (f". Длительность {transcribe.fmt_ts(t['duration'])}" if t.get("duration") else "")
    try:
        out = export.export_text(title if fmt != "txt" or not data.get("note") else "", text, fmt,
                                 files.resolve(folder), title, sub)
    except Exception as e:
        _err(e, 500)
    return {"path": files.rel_of(out), "name": out.name}


@router.post("/api/transcripts/{tid}/to-work")
def t_to_work(tid: str, data: dict = Body(...)):
    """Положить расшифровку (или конспект) во вложения работы — модель увидит её при составлении плана и текста."""
    t = transcribe.read(tid)
    wid = data["work_id"]
    d = store.work_dir(wid) / "attachments"
    d.mkdir(exist_ok=True)
    if data.get("note"):
        n = next(x for x in t["notes"] if x["name"] == data["note"])
        text, name = n["text"], f"{t['title']} — {n['name']}.md"
    else:
        text, name = transcribe.as_text(tid), f"Расшифровка — {t['title']}.txt"
    (d / files.safe_name(name)).write_text(text, encoding="utf-8")
    store.sync_task_files(wid)
    return store.get_work(wid)


# ================================================================== файлы в чате

@router.get("/api/chats/{cid}/files")
def c_files(cid: str):
    return chatctx.list_files(cid)


@router.post("/api/chats/{cid}/files")
async def c_upload(cid: str, items: list[UploadFile] = File(...)):
    recs, job = [], None
    media = []
    for f in items:
        rec = chatctx.add_file(cid, f.filename, await f.read())
        recs.append(rec)
        if rec["kind"] == "media":
            media.append(rec["name"])
    if media:
        s = _settings()
        tids = []
        for n in media:
            tid = transcribe.create_from_path(chatctx.file_path(cid, n), Path(n).stem)
            chatctx.set_transcript(cid, n, tid)
            tids.append(tid)
        opts = {"language": s.get("transcribe_language", "ru"), "diarize": s.get("diarize", True), "speakers": 0,
                "model": s["whisper_model"], "device": s["whisper_device"]}

        def run(job):
            for tid in tids:
                transcribe.run(tid, opts, job)
        try:
            job = jobs.start("transcribe", "Расшифровка вложений чата", run).as_dict()
        except RuntimeError as e:
            job = {"error": str(e)}
    return {"files": chatctx.list_files(cid), "job": job}


@router.post("/api/chats/{cid}/files/link")
def c_link(cid: str, data: dict = Body(...)):
    """Прикрепить файл из хранилища или готовую расшифровку."""
    if data.get("transcript_id"):
        t = transcribe.read(data["transcript_id"])
        chatctx.add_transcript_ref(cid, t["id"], t["title"])
    elif data.get("path"):
        p = files.resolve(data["path"])
        rec = chatctx.add_file(cid, p.name, p.read_bytes())
        if rec["kind"] == "media":
            return c_after_media(cid, rec["name"])
    return {"files": chatctx.list_files(cid), "job": None}


def c_after_media(cid, name):
    s = _settings()
    tid = transcribe.create_from_path(chatctx.file_path(cid, name), Path(name).stem)
    chatctx.set_transcript(cid, name, tid)
    opts = {"language": s.get("transcribe_language", "ru"), "diarize": s.get("diarize", True), "speakers": 0,
            "model": s["whisper_model"], "device": s["whisper_device"]}
    try:
        job = jobs.start("transcribe", "Расшифровка вложения", lambda j: transcribe.run(tid, opts, j)).as_dict()
    except RuntimeError as e:
        job = {"error": str(e)}
    return {"files": chatctx.list_files(cid), "job": job}


@router.delete("/api/chats/{cid}/files/{name}")
def c_del(cid: str, name: str):
    chatctx.remove_file(cid, name)
    return chatctx.list_files(cid)


@router.get("/api/chats/{cid}/files/{name}")
def c_raw(cid: str, name: str):
    p = chatctx.file_path(cid, name)
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type=files.mime(p))


# ================================================================== разметка картинок

@router.post("/api/annot/save")
def annot_save(data: dict = Body(...)):
    """{png: dataURL, folder, name, work_id?, fig_id?, project?: json} — сохранить картинку в хранилище и/или в работу."""
    raw = base64.b64decode(data["png"].split(",", 1)[-1])
    out = {}
    name = files.safe_name(data.get("name") or time.strftime("разметка_%Y-%m-%d_%H-%M-%S"))
    if not name.lower().endswith(".png"):
        name += ".png"
    if data.get("folder") is not None:
        out["path"] = files.save_bytes(data.get("folder") or "Работа/Скриншоты", name, raw)
        if data.get("project"):
            import json
            pj = files.resolve(out["path"]).with_suffix(".annot.json")
            pj.write_text(json.dumps(data["project"], ensure_ascii=False), encoding="utf-8")
    if data.get("work_id") and data.get("fig_id"):
        d = store.work_dir(data["work_id"]) / "figures"
        d.mkdir(exist_ok=True)
        for old in d.glob(f"{data['fig_id']}.*"):
            old.unlink()
        (d / f"{data['fig_id']}.png").write_bytes(raw)
        store.sync_task_files(data["work_id"])
        out["figure"] = data["fig_id"]
    return out


@router.get("/api/annot/project")
def annot_project(path: str):
    import json
    p = files.resolve(path).with_suffix(".annot.json")
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
