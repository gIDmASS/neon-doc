"""HTTP-API приложения NEON.DOC. Окно (pywebview) показывает static/index.html, а всё остальное — здесь."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests
import yaml
from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from reportgen import llm, pipeline

from . import files, store, voice
from .routes_extra import router as extra_router
from .extract import AUDIO_EXT, transcript_path
from .jobs import jobs

ROOT = store.ROOT
STATIC = Path(__file__).resolve().parent / "static"
SETTINGS_FILE = ROOT / "settings.yaml"
CHATS = ROOT / "chats"
CHATS.mkdir(exist_ok=True)

DEFAULT_SETTINGS = {
    "ollama_url": "http://localhost:11434",
    "model": "qwen3.6:27b",
    "num_ctx": 32768,
    "max_attempts": 3,
    "whisper_model": "large-v3-turbo",
    "whisper_device": "auto",     # auto | cuda | mlx | cpu
    "chat_temperature": 0.6,
    "chat_think": False,          # «подумать дольше» по умолчанию
    "vision": True,               # отправлять картинки модели (qwen3.6 видит изображения)
    "diarize": True,              # делить расшифровку по участникам
    "transcribe_language": "ru",  # ru | en | auto
    "glossary": "",               # термины для Whisper: имена, аббревиатуры (RPA, BPMN, OCR…)
    "auto_file_works": True,      # собранную работу класть в Хранилище/ВУЗ/<предмет>/<тип>
    "ui": {},                     # тема, анимации, шрифты — хранит интерфейс
}


def settings() -> dict:
    s = {**DEFAULT_SETTINGS, **store.read_yaml(SETTINGS_FILE)}
    llm.OLLAMA_URL, llm.MODEL = s["ollama_url"], s["model"]
    llm.NUM_CTX, llm.MAX_ATTEMPTS = int(s["num_ctx"]), int(s["max_attempts"])
    return s


app = FastAPI(title="NEON.DOC")
app.mount("/static", StaticFiles(directory=STATIC), name="static")
app.mount("/library", StaticFiles(directory=store.LIB), name="library")
app.include_router(extra_router)
from .routes_wdocs import router as wdocs_router  # noqa: E402
from . import wdocs as _wdocs  # noqa: E402
app.mount("/worktpl", StaticFiles(directory=_wdocs.TPL), name="worktpl")
app.include_router(wdocs_router)
files.ensure_tree()


def model_missing_msg(url: str, model: str) -> str:
    """Понятный текст, когда Ollama отвечает 404: модели из настроек нет на этом компьютере."""
    try:
        names = [m["name"] for m in requests.get(f"{url}/api/tags", timeout=5).json().get("models", [])]
    except Exception:
        names = []
    have = ", ".join(names) if names else "ни одной"
    return (f"Модель «{model}» не скачана на этом компьютере. Скачанные модели: {have}. "
            f"Выбери одну из них в Настройки → Модель, или скачай нужную в Терминале: ollama pull {model}")


def _404(e):
    raise HTTPException(404, f"Не найдено: {e}")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


# ================================================================== статус и настройки

@app.get("/api/health")
def health():
    s = settings()
    out = {"ollama": False, "model": s["model"], "model_ok": False, "models": [],
           "voice": voice.status(), "job": jobs.current.as_dict(10**9) if jobs.current else None}
    try:
        r = requests.get(f"{s['ollama_url']}/api/tags", timeout=2)
        names = [m["name"] for m in r.json().get("models", [])]
        out.update(ollama=True, models=names, model_ok=s["model"] in names)
    except Exception:
        pass
    return out


@app.get("/api/settings")
def get_settings():
    return settings()


@app.put("/api/settings")
def put_settings(data: dict = Body(...)):
    s = {**settings(), **{k: v for k, v in data.items() if k in DEFAULT_SETTINGS}}
    store.write_yaml(SETTINGS_FILE, s)
    return settings()


# ================================================================== шаблоны

@app.get("/api/templates")
def templates():
    return store.list_templates()


@app.get("/api/templates/{slug}")
def template(slug: str):
    try:
        return store.get_template(slug)
    except KeyError as e:
        _404(e)


@app.post("/api/templates")
def create_template(data: dict = Body(...)):
    try:
        return {"slug": store.save_template(None, data)}
    except Exception as e:
        raise HTTPException(400, str(e))


@app.put("/api/templates/{slug}")
def update_template(slug: str, data: dict = Body(...)):
    try:
        return {"slug": store.save_template(slug, data)}
    except Exception as e:
        raise HTTPException(400, str(e))


@app.delete("/api/templates/{slug}")
def del_template(slug: str):
    store.delete_template(slug)
    return {"ok": True}


@app.post("/api/templates/{slug}/previews")
async def upload_previews(slug: str, files: list[UploadFile] = File(...)):
    for f in files:
        store.add_preview(slug, f.filename, await f.read())
    return store.get_template(slug)


@app.delete("/api/templates/{slug}/previews/{name}")
def remove_preview(slug: str, name: str):
    store.delete_preview(slug, name)
    return store.get_template(slug)


@app.post("/api/templates/{slug}/previews/from-docx")
async def previews_from_docx(slug: str, file: UploadFile | None = File(None), work_id: str | None = Form(None)):
    from .previews import make_previews
    tmp = None
    if file is not None:
        tmp = ROOT / f"_preview_src_{int(time.time())}.docx"
        tmp.write_bytes(await file.read())
        src = tmp
    elif work_id:
        d = store.work_dir(work_id)
        docs = sorted(d.glob("*.docx"))
        if not docs:
            raise HTTPException(400, "В работе ещё нет .docx")
        src = docs[0]
    else:
        raise HTTPException(400, "Нужен файл .docx или работа")

    def run(job):
        job.emit(f"Превью из {src.name}…")
        pages = make_previews(src, store.LIB / slug / "previews")
        job.emit(f"Готово: {len(pages)} стр.")
        if tmp:
            tmp.unlink(missing_ok=True)
        return {"pages": len(pages)}
    try:
        return jobs.start("previews", f"Превью шаблона {slug}", run).as_dict()
    except RuntimeError as e:
        raise HTTPException(409, str(e))


# ================================================================== работы

@app.get("/api/works")
def works():
    return store.list_works()


@app.post("/api/works")
def new_work(data: dict = Body(...)):
    try:
        return store.get_work(store.create_work(data["template"], data.get("title", "")))
    except KeyError as e:
        _404(e)


@app.get("/api/works/{wid}")
def work(wid: str):
    try:
        return store.get_work(wid)
    except KeyError as e:
        _404(e)


@app.put("/api/works/{wid}")
def put_work(wid: str, data: dict = Body(...)):
    try:
        return store.update_work(wid, data)
    except KeyError as e:
        _404(e)
    except Exception as e:
        raise HTTPException(400, str(e))


@app.delete("/api/works/{wid}")
def del_work(wid: str):
    store.delete_work(wid)
    return {"ok": True}


@app.post("/api/works/{wid}/attachments")
async def upload_attachments(wid: str, files: list[UploadFile] = File(...)):
    d = store.work_dir(wid) / "attachments"
    d.mkdir(exist_ok=True)
    audio = []
    for f in files:
        p = d / Path(f.filename).name
        p.write_bytes(await f.read())
        if p.suffix.lower() in AUDIO_EXT:
            audio.append(p)
    store.sync_task_files(wid)
    job = None
    if audio:
        s = settings()

        def run(job):
            for a in audio:
                job.emit(f"Расшифровка {a.name}…")
                text = voice.transcribe(a, s["whisper_model"], s["whisper_device"])
                transcript_path(a).write_text(text, encoding="utf-8")
                job.emit(f"  {len(text)} символов")
            store.sync_task_files(wid)
        try:
            job = jobs.start("transcribe", "Расшифровка аудио", run, wid).as_dict()
        except RuntimeError as e:
            job = {"error": str(e)}
    return {"work": store.get_work(wid), "job": job}


@app.delete("/api/works/{wid}/attachments/{name}")
def del_attachment(wid: str, name: str):
    d = store.work_dir(wid) / "attachments"
    p = d / Path(name).name
    p.unlink(missing_ok=True)
    transcript_path(p).unlink(missing_ok=True)
    store.sync_task_files(wid)
    return store.get_work(wid)


@app.post("/api/works/{wid}/figures")
async def upload_figure(wid: str, file: UploadFile = File(...), fig_id: str = Form(...)):
    d = store.work_dir(wid) / "figures"
    d.mkdir(exist_ok=True)
    ext = Path(file.filename).suffix.lower() or ".png"
    safe = store.slugify(fig_id).replace("-", "_") if not fig_id.replace("_", "").isalnum() else fig_id
    for old in d.glob(f"{safe}.*"):
        old.unlink()
    (d / f"{safe}{ext}").write_bytes(await file.read())
    store.sync_task_files(wid)
    return store.get_work(wid)


@app.get("/api/works/{wid}/figures/{name}")
def get_figure(wid: str, name: str):
    p = store.work_dir(wid) / "figures" / Path(name).name
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p)


@app.delete("/api/works/{wid}/figures/{name}")
def del_figure(wid: str, name: str):
    (store.work_dir(wid) / "figures" / Path(name).name).unlink(missing_ok=True)
    store.sync_task_files(wid)
    return store.get_work(wid)


def _file_work(wid: str, docx_path, emit):
    """Копия собранного .docx в Хранилище/ВУЗ/<дисциплина>/<тип работы> (перезаписывает прошлую сборку)."""
    try:
        if not settings().get("auto_file_works", True) or not docx_path:
            return
        docx_path = Path(docx_path)
        w = store.read_json(store.work_dir(wid) / "work.json", {})
        dest = files.resolve(files.folder_for_work(w.get("meta") or {})) / docx_path.name
        dest.write_bytes(docx_path.read_bytes())
        emit(f"Копия в хранилище: {files.rel_of(dest)}")
    except Exception as e:  # не мешаем основной сборке
        emit(f"В хранилище не скопировано: {e}")


def _run_pipeline(wid: str, steps: list[str], title: str):
    settings()
    d = store.work_dir(wid)
    store.sync_task_files(wid)

    def run(job):
        t0 = time.time()
        job.emit(f"Модель: {llm.ping()}")
        if "plan" in steps:
            pipeline.cmd_plan(d, job.emit, job.stop_requested)
        if "write" in steps:
            pipeline.cmd_write(d, job.emit, job.stop_requested)
        if "render" in steps or "write" in steps:
            out = pipeline.cmd_render(d, job.emit)
            _file_work(wid, out, job.emit)
        job.emit(f"Время: {time.time() - t0:.0f} с")
    try:
        return jobs.start("pipeline", title, run, wid).as_dict()
    except RuntimeError as e:
        raise HTTPException(409, str(e))


@app.post("/api/works/{wid}/plan")
def plan(wid: str):
    store.reset_from(wid, "plan")
    return _run_pipeline(wid, ["plan"], "План работы")


@app.post("/api/works/{wid}/write")
def write(wid: str):
    d = store.work_dir(wid)
    (d / "report.json").unlink(missing_ok=True)
    for f in d.glob("*.docx"):
        try:
            f.unlink()
        except PermissionError:   # открыт в Word — новая сборка сохранится рядом
            pass
    return _run_pipeline(wid, ["write"], "Текст работы")


@app.post("/api/works/{wid}/sections/{index}/regenerate")
def regen_section(wid: str, index: int):
    store.regenerate_section(wid, index)
    return write(wid)


@app.post("/api/works/{wid}/render")
def render_now(wid: str):
    d = store.work_dir(wid)
    if not (d / "report.json").exists():
        raise HTTPException(400, "Текста ещё нет")
    store.sync_task_files(wid)
    lines = []
    try:
        path = pipeline.cmd_render(d, lines.append)
        _file_work(wid, path, lines.append)
    except Exception as e:
        raise HTTPException(400, f"Сборка не удалась: {e}")
    return {"docx": path.name, "lines": lines, "work": store.get_work(wid)}


@app.put("/api/works/{wid}/outline")
def put_outline(wid: str, data: dict = Body(...)):
    try:
        store.save_outline(wid, data)
    except Exception as e:
        raise HTTPException(400, str(e))
    return store.get_work(wid)


@app.put("/api/works/{wid}/report")
def put_report(wid: str, data: dict = Body(...)):
    try:
        store.save_report(wid, data)
    except Exception as e:
        raise HTTPException(400, str(e))
    return render_now(wid)


@app.post("/api/works/{wid}/open")
def open_docx(wid: str, what: str = "docx"):
    d = store.work_dir(wid)
    target = d
    if what == "docx":
        docs = sorted(d.glob("*.docx"))
        if not docs:
            raise HTTPException(400, "Документ ещё не собран")
        target = docs[0]
    _open(target)
    return {"ok": True}


def _open(p: Path):
    from .osutil import open_path
    open_path(p)


@app.get("/api/works/{wid}/download")
def download(wid: str):
    docs = sorted(store.work_dir(wid).glob("*.docx"))
    if not docs:
        raise HTTPException(404)
    return FileResponse(docs[0], filename=docs[0].name)


# ================================================================== задачи

@app.get("/api/jobs/current")
def job_current(since: int = 0):
    return jobs.current.as_dict(since) if jobs.current else None


@app.get("/api/jobs/{jid}")
def job(jid: str, since: int = 0):
    j = jobs.get(jid)
    if not j:
        raise HTTPException(404)
    return j.as_dict(since)


@app.post("/api/jobs/stop")
def job_stop():
    jobs.stop()
    return {"ok": True}


# ================================================================== голос

@app.post("/api/voice/start")
def voice_start():
    try:
        voice.recorder().start()
    except Exception as e:
        raise HTTPException(400, f"Микрофон недоступен: {e}")
    return {"recording": True}


@app.get("/api/voice/level")
def voice_level():
    r = voice.recorder()
    return {"recording": r.active, "level": r.level(),
            "seconds": round(time.time() - r.started, 1) if r.active else 0}


@app.post("/api/voice/stop")
def voice_stop():
    s = settings()
    try:
        wav = voice.recorder().stop()
    except Exception as e:
        raise HTTPException(400, str(e))
    try:
        t0 = time.time()
        text = voice.transcribe(wav, s["whisper_model"], s["whisper_device"])
        return {"text": text, "seconds": round(time.time() - t0, 1), "device": voice.status()["device"]}
    except Exception as e:
        raise HTTPException(500, f"Расшифровка не удалась: {e}")
    finally:
        wav.unlink(missing_ok=True)


@app.post("/api/voice/warmup")
def voice_warmup():
    s = settings()

    def run(job):
        job.emit(f"Загрузка Whisper {s['whisper_model']} (первый раз скачивается ~1,6 ГБ)…")
        voice.get_model(s["whisper_model"], s["whisper_device"])
        job.emit(f"Готово: {voice.status()['device']}")
    try:
        return jobs.start("whisper", "Загрузка Whisper", run).as_dict()
    except RuntimeError as e:
        raise HTTPException(409, str(e))


# ================================================================== чат

@app.get("/api/chats")
def chats():
    out = []
    for p in sorted(CHATS.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        c = store.read_json(p, {})
        out.append({"id": p.stem, "title": c.get("title") or "Без названия",
                    "updated": time.strftime("%d.%m %H:%M", time.localtime(p.stat().st_mtime))})
    return out


@app.get("/api/chats/{cid}")
def get_chat(cid: str):
    p = CHATS / f"{Path(cid).name}.json"
    return store.read_json(p, {"id": cid, "title": "", "messages": [], "work_id": None})


@app.put("/api/chats/{cid}")
def put_chat(cid: str, data: dict = Body(...)):
    store.write_json(CHATS / f"{Path(cid).name}.json", data)
    return {"ok": True}


@app.delete("/api/chats/{cid}")
def del_chat(cid: str):
    import shutil
    (CHATS / f"{Path(cid).name}.json").unlink(missing_ok=True)
    shutil.rmtree(CHATS / Path(cid).name, ignore_errors=True)
    return {"ok": True}


CHAT_SYSTEM = ("Ты — помощник бизнес-аналитика (RPA/OCR, требования, BPMN, ТЗ по ГОСТ 34) и студента направления "
               "«Бизнес-информатика». Отвечай по-русски, по делу, в Markdown (таблицы — Markdown-таблицами). "
               "Если чего-то не знаешь или этого нет в файлах — так и скажи, не выдумывай. "
               "Отмечай спорные места и задавай уточняющие вопросы, когда задача неоднозначна. "
               "Когда опираешься на файл, называй его; в расшифровках указывай таймкоды [мм:сс].")


def _work_context(wid: str) -> str:
    d = store.work_dir(wid)
    ctx = (d / "brief.md").read_text(encoding="utf-8")[:12000]
    rep = store.read_json(d / "report.json")
    if rep:
        txt = []
        for sec in rep["sections"]:
            txt.append("## " + sec["title"])
            for b in sec["blocks"]:
                if b["type"] == "paragraph":
                    txt.append(b["text"])
                elif b["type"] == "table":
                    txt.append(f"[Таблица {b['caption']}: {len(b['rows'])} строк, столбцы "
                               f"{', '.join(b['columns'])}]")
        ctx += "\n\nТЕКУЩИЙ ТЕКСТ РАБОТЫ:\n" + "\n".join(txt)[:12000]
    return ctx


@app.post("/api/chat")
def chat(data: dict = Body(...)):
    """Поток NDJSON: {"t": мысли} / {"c": текст} / {"n": служебная пометка}."""
    from . import chatctx
    s = settings()
    raw = [m for m in data.get("messages", []) if m.get("role") in ("user", "assistant")]
    cid = data.get("chat_id")
    system = CHAT_SYSTEM
    notes = []
    if data.get("system_extra"):
        system += "\n\n" + data["system_extra"]
    wid = data.get("work_id")
    if wid:
        try:
            system += "\n\nКонтекст — работа, над которой идёт речь:\n" + _work_context(wid)
        except KeyError:
            pass
    question = next((m["content"] for m in reversed(raw) if m["role"] == "user"), "")
    if cid:
        ftxt, notes = chatctx.context(cid, question)
        if ftxt:
            system += "\n\nПРИКРЕПЛЁННЫЕ ФАЙЛЫ (отвечай по ним, если вопрос о них):\n" + ftxt
    msgs = [{"role": "system", "content": system}]
    for i, m in enumerate(raw):
        mm = {"role": m["role"], "content": m["content"]}
        # картинки отправляем только с последним сообщением пользователя — иначе контекст забивается
        if cid and s.get("vision", True) and m["role"] == "user" and i == len(raw) - 1 and m.get("images"):
            imgs = chatctx.images_b64(cid, m["images"])
            if imgs:
                mm["images"] = imgs
        msgs.append(mm)
    think = bool(data.get("think", s.get("chat_think", False)))
    payload = {"model": s["model"], "stream": True, "think": think, "messages": msgs,
               "options": {"temperature": float(s["chat_temperature"]), "num_ctx": int(s["num_ctx"])},
               "keep_alive": "30m"}

    def line(k, v):
        return json.dumps({k: v}, ensure_ascii=False) + "\n"

    def gen():
        for n in notes:
            yield line("n", n)
        try:
            r = requests.post(f"{s['ollama_url']}/api/chat", json=payload, stream=True, timeout=1800)
            if r.status_code >= 400 and any("images" in m for m in msgs):
                err = r.text[:300]
                for m in msgs:
                    m.pop("images", None)
                yield line("n", f"Модель не приняла картинку ({err.strip()}); отвечаю без неё.")
                r = requests.post(f"{s['ollama_url']}/api/chat", json=payload, stream=True, timeout=1800)
            if r.status_code >= 400 and think:
                payload["think"] = False
                r = requests.post(f"{s['ollama_url']}/api/chat", json=payload, stream=True, timeout=1800)
            if r.status_code == 404:
                yield line("c", "\n\n[" + model_missing_msg(s["ollama_url"], s.get("model", "")) + "]")
                return
            r.raise_for_status()
            with r:
                for ln in r.iter_lines():
                    if not ln:
                        continue
                    part = json.loads(ln)
                    if part.get("error"):
                        yield line("c", f"\n\n[ошибка Ollama: {part['error']}]")
                        break
                    msg = part.get("message", {})
                    if msg.get("thinking"):
                        yield line("t", msg["thinking"])
                    if msg.get("content"):
                        yield line("c", msg["content"])
                    if part.get("done"):
                        ev, ed = part.get("eval_count"), part.get("eval_duration")
                        if ev and ed:
                            yield line("s", {"tokens": ev, "tps": round(ev / (ed / 1e9), 1),
                                             "prompt": part.get("prompt_eval_count")})
                        break
        except Exception as e:
            yield line("c", f"\n\n[ошибка связи с Ollama: {e}]")
    return StreamingResponse(gen(), media_type="application/x-ndjson; charset=utf-8")


# ================================================================== метрики

@app.get("/api/metrics")
def metrics():
    return store.metrics()


@app.exception_handler(KeyError)
def key_error(_req, exc):
    return JSONResponse({"detail": f"Не найдено: {exc}"}, status_code=404)
