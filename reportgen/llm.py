"""Клиент Ollama: structured outputs + цикл «генерация → проверка → исправление»."""
from __future__ import annotations

import json
import os
import time
from typing import Callable, TypeVar

import requests
from pydantic import BaseModel, ValidationError

from .schema import ollama_schema
from .validate import Result

T = TypeVar("T", bound=BaseModel)

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("REPORTGEN_MODEL", "qwen3.6:27b")
NUM_CTX = int(os.environ.get("REPORTGEN_NUM_CTX", "32768"))
MAX_ATTEMPTS = int(os.environ.get("REPORTGEN_MAX_ATTEMPTS", "3"))


def chat(messages: list[dict], schema: dict, *, timeout=600) -> tuple[str, dict]:
    payload = {
        "model": MODEL,
        "messages": messages,
        "format": schema,
        "stream": False,
        "think": False,
        "options": {"temperature": 0, "num_ctx": NUM_CTX},
        "keep_alive": "30m",
    }
    resp = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=timeout)
    if resp.status_code == 404:
        try:
            names = [m["name"] for m in requests.get(f"{OLLAMA_URL}/api/tags", timeout=5).json().get("models", [])]
        except Exception:
            names = []
        raise RuntimeError(f"Модель «{MODEL}» не скачана на этом компьютере (есть: {', '.join(names) or 'ни одной'}). "
                           f"Выбери другую в Настройки → Модель или выполни: ollama pull {MODEL}")
    resp.raise_for_status()
    data = resp.json()
    stats = {
        "prompt_tokens": data.get("prompt_eval_count"),
        "output_tokens": data.get("eval_count"),
        "seconds": round((data.get("total_duration") or 0) / 1e9, 1),
    }
    return data["message"]["content"], stats


def generate(model_cls: type[T], messages: list[dict],
             check: Callable[[T], Result], log: Callable[[dict], None]) -> tuple[T | None, Result]:
    """Просим модель заполнить схему; при ошибках возвращаем их ей на исправление."""
    schema = ollama_schema(model_cls)
    msgs = list(messages)
    last: Result = Result(errors=["модель не ответила"])
    obj = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        t0 = time.time()
        content, stats = chat(msgs, schema)
        try:
            obj = model_cls.model_validate_json(content)
            last = check(obj)
        except ValidationError as e:
            obj = None
            last = Result(errors=[f"{'/'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()])
        rec = {"step": model_cls.__name__, "attempt": attempt, "ok": last.ok,
               "errors": last.errors, "warnings": last.warnings,
               "wall_s": round(time.time() - t0, 1), **stats}
        if not last.ok:
            rec["raw"] = content[:4000]   # что именно ответила модель — для разбора
        log(rec)
        if last.ok:
            return obj, last
        msgs += [
            {"role": "assistant", "content": content},
            {"role": "user", "content":
                "Проверка нашла ошибки:\n" + last.as_feedback() +
                "\n\nИсправь только их, остальное оставь как было. Верни JSON целиком."},
        ]
    return obj, last


def ping() -> str:
    r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
    r.raise_for_status()
    names = [m["name"] for m in r.json().get("models", [])]
    if MODEL not in names:
        raise RuntimeError(f"Модель {MODEL} не найдена в Ollama. Есть: {', '.join(names)}")
    return MODEL
