"""Расшифровка аудио и видео: Whisper (текст + таймкоды) + разделение по участникам (sherpa-onnx).

Хранение: transcripts/<id>/
    source.<ext>      исходный файл (копия)
    meta.json         название, длительность, участники {"S1": "Анна", ...}, статус, настройки
    segments.json     [{"start": 12.3, "end": 18.0, "speaker": "S1", "text": "..."}]
    notes/*.md        конспекты, протоколы, задачи — то, что сделал Qwen по расшифровке

Разделение по участникам работает без интернета после первой загрузки двух моделей (~33 МБ с GitHub).
Если модели не скачались — расшифровка всё равно будет, просто с одним участником.
"""
from __future__ import annotations

import json
import re
import shutil
import tarfile
import time
import urllib.request
from pathlib import Path

from . import store, voice

ROOT = store.ROOT
TDIR = ROOT / "transcripts"
TDIR.mkdir(exist_ok=True)
MDIR = ROOT / "models" / "diarization"

SEG_URL = ("https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/"
           "sherpa-onnx-pyannote-segmentation-3-0.tar.bz2")
EMB_URL = ("https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/"
           "wespeaker_en_voxceleb_resnet34_LM.onnx")


# ------------------------------------------------------------------ util

def fmt_ts(sec: float, ms: bool = False) -> str:
    sec = max(0.0, float(sec))
    h, m, s = int(sec // 3600), int(sec % 3600 // 60), int(sec % 60)
    out = f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
    return out + (f".{int((sec % 1) * 10)}" if ms else "")


def tdir(tid: str) -> Path:
    d = TDIR / Path(tid).name
    if not (d / "meta.json").exists():
        raise KeyError(tid)
    return d


def read(tid: str) -> dict:
    d = tdir(tid)
    meta = store.read_json(d / "meta.json", {})
    segs = store.read_json(d / "segments.json", [])
    notes = []
    nd = d / "notes"
    if nd.exists():
        for p in sorted(nd.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True):
            notes.append({"name": p.stem, "text": p.read_text(encoding="utf-8")})
    src = next((p.name for p in d.iterdir() if p.stem == "source"), None)
    return {**meta, "id": d.name, "segments": segs, "notes": notes, "source": src}


def list_all() -> list[dict]:
    out = []
    for d in sorted(TDIR.iterdir(), reverse=True):
        if (d / "meta.json").exists():
            m = store.read_json(d / "meta.json", {})
            out.append({"id": d.name, "title": m.get("title"), "created": m.get("created"),
                        "duration": m.get("duration"), "status": m.get("status"),
                        "speakers": m.get("speakers", {}), "video": m.get("video", False)})
    return out


def create(filename: str, data: bytes, title: str = "") -> str:
    from .extract import VIDEO_EXT
    tid = time.strftime("%Y%m%d-%H%M%S") + "-" + store.slugify(title or Path(filename).stem)[:24]
    d = TDIR / tid
    d.mkdir(parents=True)
    ext = Path(filename).suffix.lower() or ".bin"
    (d / f"source{ext}").write_bytes(data)
    store.write_json(d / "meta.json", {
        "title": title or Path(filename).stem, "file": filename, "created": time.strftime("%Y-%m-%d %H:%M"),
        "status": "new", "duration": None, "speakers": {}, "video": ext in VIDEO_EXT})
    return tid


def create_from_path(src: Path, title: str = "") -> str:
    return create(src.name, src.read_bytes(), title)


def update(tid: str, patch: dict) -> dict:
    d = tdir(tid)
    meta = store.read_json(d / "meta.json", {})
    for k in ("title", "speakers"):
        if k in patch:
            meta[k] = patch[k]
    store.write_json(d / "meta.json", meta)
    if "segments" in patch:
        segs = [{"start": float(s["start"]), "end": float(s["end"]), "speaker": s.get("speaker") or "S1",
                 "text": str(s.get("text", "")).strip()} for s in patch["segments"]]
        store.write_json(d / "segments.json", segs)
    return read(tid)


def delete(tid: str):
    shutil.rmtree(tdir(tid), ignore_errors=True)


def source_path(tid: str) -> Path:
    d = tdir(tid)
    return next(p for p in d.iterdir() if p.stem == "source")


# ------------------------------------------------------------------ текст расшифровки

def as_text(tid: str, timecodes: bool = True, speakers: bool = True) -> str:
    t = read(tid)
    names = t.get("speakers") or {}
    lines, prev = [], None
    for s in t["segments"]:
        who = names.get(s["speaker"], s["speaker"])
        head = []
        if timecodes:
            head.append(f"[{fmt_ts(s['start'])}]")
        if speakers and (who != prev or timecodes):
            head.append(f"{who}:")
        lines.append((" ".join(head) + " " if head else "") + s["text"])
        prev = who
    return "\n".join(lines)


def as_markdown(tid: str, timecodes=True, speakers=True) -> str:
    """Для Word/PDF: реплики абзацами, имя полужирным."""
    t = read(tid)
    names = t.get("speakers") or {}
    out = []
    for s in t["segments"]:
        who = names.get(s["speaker"], s["speaker"])
        pre = (f"`{fmt_ts(s['start'])}` " if timecodes else "") + (f"**{who}:** " if speakers else "")
        out.append(pre + s["text"])
    return "\n\n".join(out)


# ------------------------------------------------------------------ диаризация

def _download(url: str, dest: Path, emit):
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        got, last = 0, 0
        while True:
            b = r.read(1 << 16)
            if not b:
                break
            f.write(b)
            got += len(b)
            if total and got - last > total / 5:
                last = got
                emit(f"  {dest.name}: {100 * got // total}%")
    tmp.replace(dest)


def diarization_models(emit=lambda s: None) -> tuple[Path, Path]:
    seg = MDIR / "segmentation.onnx"
    emb = MDIR / "embedding.onnx"
    if not seg.exists():
        emit("Скачиваю модель разделения речи (5 МБ, один раз)…")
        arc = MDIR / "seg.tar.bz2"
        _download(SEG_URL, arc, emit)
        with tarfile.open(arc) as tf:
            m = next(x for x in tf.getmembers() if x.name.endswith("model.onnx"))
            with tf.extractfile(m) as src, open(seg, "wb") as dst:
                shutil.copyfileobj(src, dst)
        arc.unlink()
    if not emb.exists():
        emit("Скачиваю модель голосов (27 МБ, один раз)…")
        _download(EMB_URL, emb, emit)
    return seg, emb


def diarize(samples, num_speakers: int, emit, threshold: float = 0.6) -> list[tuple[float, float, int]]:
    import sherpa_onnx
    seg, emb = diarization_models(emit)
    cfg = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(model=str(seg)),
            num_threads=4),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(emb), num_threads=4),
        clustering=sherpa_onnx.FastClusteringConfig(num_clusters=num_speakers if num_speakers > 0 else -1,
                                                    threshold=threshold),
        min_duration_on=0.3, min_duration_off=0.5)
    if not cfg.validate():
        raise RuntimeError("Неверная конфигурация диаризации")
    sd = sherpa_onnx.OfflineSpeakerDiarization(cfg)
    state = {"last": -1}

    def cb(done, total):
        pct = int(100 * done / max(total, 1))
        if pct // 20 != state["last"]:
            state["last"] = pct // 20
            emit(f"  участники: {pct}%")
        return 0
    res = sd.process(samples, callback=cb).sort_by_start_time()
    return [(r.start, r.end, r.speaker) for r in res]


def _speaker_at(t0: float, t1: float, turns) -> int | None:
    best, best_ov = None, 0.0
    for a, b, spk in turns:
        if b < t0:
            continue
        if a > t1:
            break
        ov = min(b, t1) - max(a, t0)
        if ov > best_ov:
            best, best_ov = spk, ov
    if best is None and turns:   # слово в паузе между репликами — берём ближайшую
        mid = (t0 + t1) / 2
        best = min(turns, key=lambda x: min(abs(x[0] - mid), abs(x[1] - mid)))[2]
    return best


# ------------------------------------------------------------------ основной процесс

def decode_audio(path: str, sr: int = 16000):
    """Звук из любого аудио/видео -> моно float32 16 кГц. Свой декодер на PyAV: функция из faster-whisper
    ломается на новых версиях av (аргумент metadata_errors)."""
    import av
    import numpy as np
    try:
        from faster_whisper.audio import decode_audio as fw
        return fw(path, sampling_rate=sr)
    except TypeError:
        pass
    chunks = []
    with av.open(path, mode="r") as c:
        st = next(s for s in c.streams if s.type == "audio")
        rs = av.AudioResampler(format="s16", layout="mono", rate=sr)
        for frame in c.decode(st):
            for f in rs.resample(frame):
                chunks.append(f.to_ndarray().reshape(-1))
        for f in rs.resample(None):
            chunks.append(f.to_ndarray().reshape(-1))
    a = np.concatenate(chunks) if chunks else np.zeros(1, dtype=np.int16)
    return (a.astype(np.float32) / 32768.0)


def run(tid: str, opts: dict, job) -> dict:
    """opts: language (ru|en|auto), diarize (bool), speakers (0=авто), model, device."""
    d = tdir(tid)
    meta = store.read_json(d / "meta.json", {})
    meta.update(status="running", options=opts)
    store.write_json(d / "meta.json", meta)
    try:
        src = source_path(tid)
        job.emit(f"Читаю звук из {meta.get('file', src.name)}…")
        samples = decode_audio(str(src), 16000)
        dur = len(samples) / 16000
        job.emit(f"Длительность {fmt_ts(dur)}")
        meta["duration"] = round(dur, 1)

        job.emit(f"Whisper {opts.get('model')}: загрузка…")
        model = voice.get_model(opts.get("model") or "large-v3-turbo", opts.get("device") or "auto")
        job.emit(f"Whisper готов ({voice.status()['device']}). Распознаю речь…")
        if isinstance(model, voice.MLXWhisper):
            job.emit("  (на Mac прогресс появится в конце: MLX отдаёт текст целиком; первый запуск скачает модель ~1,6 ГБ)")
        lang = None if opts.get("language") == "auto" else (opts.get("language") or "ru")
        prompt = (opts.get("glossary") or "").strip() or None
        segments, info = model.transcribe(samples, language=lang, vad_filter=True, beam_size=5,
                                          word_timestamps=True, initial_prompt=prompt)
        words, wsegs, last = [], [], -1
        for s in segments:
            if job.stop_requested():
                raise RuntimeError("Остановлено")
            wsegs.append((s.start, s.end, s.text.strip()))
            for w in (s.words or []):
                words.append((w.start, w.end, w.word))
            pct = int(100 * s.end / max(dur, 1))
            if pct // 10 != last:
                last = pct // 10
                job.emit(f"  текст: {pct}%  [{fmt_ts(s.end)}] {s.text.strip()[:70]}")
        job.emit(f"Язык: {info.language}, фраз: {len(wsegs)}")

        turns = []
        if opts.get("diarize", True) and dur > 3:
            try:
                job.emit("Разделяю по участникам…")
                turns = diarize(samples, int(opts.get("speakers") or 0), job.emit)
                job.emit(f"  найдено участников: {len({t[2] for t in turns})}")
            except Exception as e:  # без диаризации расшифровка всё равно полезна
                job.emit(f"Разделение по участникам не удалось ({e}) — будет один участник")
                turns = []

        out = []
        if turns and words:
            cur = None
            for w0, w1, wt in words:
                spk = _speaker_at(w0, w1, turns)
                sid = f"S{(spk or 0) + 1}"
                gap = cur and (w0 - cur["end"] > 1.5)
                long = cur and (cur["end"] - cur["start"] > 30 and re.search(r"[.!?…]$", cur["text"]))
                if not cur or cur["speaker"] != sid or gap or long:
                    if cur:
                        out.append(cur)
                    cur = {"start": round(w0, 2), "end": round(w1, 2), "speaker": sid, "text": wt.strip()}
                else:
                    cur["end"] = round(w1, 2)
                    cur["text"] = (cur["text"] + wt).strip() if wt.startswith(" ") else cur["text"] + wt
            if cur:
                out.append(cur)
        else:
            out = [{"start": round(a, 2), "end": round(b, 2), "speaker": "S1", "text": t} for a, b, t in wsegs if t]

        spk_ids = sorted({s["speaker"] for s in out}, key=lambda x: int(x[1:]))
        old = meta.get("speakers") or {}
        meta["speakers"] = {k: old.get(k, f"Участник {k[1:]}") for k in spk_ids}
        meta["status"] = "done"
        meta["language"] = info.language
        store.write_json(d / "segments.json", out)
        store.write_json(d / "meta.json", meta)
        job.emit(f"Готово: {len(out)} реплик, участников: {len(spk_ids)}")
        return {"id": tid, "segments": len(out)}
    except Exception:
        meta["status"] = "error"
        store.write_json(d / "meta.json", meta)
        raise


# ------------------------------------------------------------------ Qwen по расшифровке

ACTIONS = {
    "summary": ("Конспект", "Сделай краткий конспект разговора: 5–10 пунктов о главном. Потом раздел «Итог» в 2–3 предложения."),
    "protocol": ("Протокол встречи", "Составь протокол встречи по шаблону:\n## Участники\n## Повестка\n## Обсуждали\n"
                 "## Решения\n## Задачи\nтаблица | Что сделать | Ответственный | Срок |\n## Открытые вопросы\n"
                 "Ставь таймкоды [мм:сс] у решений, чтобы можно было найти место в записи. Не выдумывай сроки — если их не называли, пиши «не назван»."),
    "questions": ("Вопросы и неясности", "Выпиши всё, что осталось неясным или противоречивым: вопросы к заказчику, допущения, "
                  "места, где участники поняли друг друга по-разному. Для каждого — таймкод и почему это важно."),
    "requirements": ("Требования", "Вытащи из разговора требования к системе/процессу. Таблица: | № | Требование | Тип (функц./нефункц./бизнес) | "
                     "Кто сказал | Таймкод |. Потом список пограничных случаев, которые упоминали или которые напрашиваются."),
    "asis": ("Процесс AS-IS", "Опиши процесс «как есть», о котором шла речь: шаги по порядку (кто → что делает → с какими данными/системами), "
             "развилки и исключения. В конце — таблица шагов | № | Исполнитель | Действие | Вход | Выход | — её удобно перенести в BPMN."),
}


def ai_action(tid: str, action: str, custom: str, settings: dict, job) -> str:
    import requests
    title, instr = ACTIONS.get(action, ("Ответ", custom))
    if action == "custom":
        title, instr = (custom[:40] or "Ответ"), custom
    text = as_text(tid, timecodes=True, speakers=True)
    if len(text) > 60000:
        job.emit(f"Расшифровка длинная ({len(text)} симв.) — беру начало и конец, середину сжимаю")
        text = text[:40000] + "\n[…середина пропущена…]\n" + text[-18000:]
    sys_p = ("Ты — помощник бизнес-аналитика. Работаешь только с расшифровкой ниже, факты не придумываешь. "
             "Если чего-то в расшифровке нет — так и пиши. Отвечай по-русски, в Markdown.")
    job.emit(f"Qwen: {title}…")
    r = requests.post(f"{settings['ollama_url']}/api/chat", json={
        "model": settings["model"], "stream": False, "think": False, "keep_alive": "30m",
        "options": {"temperature": 0.2, "num_ctx": max(int(settings["num_ctx"]), 32768)},
        "messages": [{"role": "system", "content": sys_p},
                     {"role": "user", "content": f"РАСШИФРОВКА:\n{text}\n\nЗАДАЧА: {instr}"}]}, timeout=1800)
    r.raise_for_status()
    ans = r.json()["message"]["content"].strip()
    nd = tdir(tid) / "notes"
    nd.mkdir(exist_ok=True)
    name = f"{time.strftime('%H%M%S')} {title}"
    from .files import safe_name
    (nd / f"{safe_name(name)}.md").write_text(f"# {title}\n\n{ans}", encoding="utf-8")
    job.emit(f"Готово: {len(ans)} симв.")
    return ans
