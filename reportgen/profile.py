"""Личные данные пользователя: ФИО, группа, преподаватель, роль и компания.

Хранятся в profile.yaml в корне проекта. Этот файл не попадает в git (см. .gitignore),
поэтому в публичном коде только заглушки. Образец — profile.example.yaml.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PROFILE_FILE = ROOT / "profile.yaml"

DEFAULTS = {
    # титульный лист студенческих работ
    "student": "Иванов И.И.",
    "group": "ГРУППА-00-0",
    "file_prefix": "Ivanov_GROUP_00_0",
    "teacher": "______________",
    # рабочие документы: кем представляется модель
    "analyst_role": "бизнес-аналитик",
    # строки эталонного .docx, которые make_template заменяет на {{заполнители}}
    "reference_markers": {
        "student": "Иванов",
        "teacher": "Петров",
        "group": "ГРУППА-00-0",
        "date": "01.09.2025",
    },
}


@lru_cache(maxsize=1)
def load() -> dict:
    data = {}
    if PROFILE_FILE.exists():
        data = yaml.safe_load(PROFILE_FILE.read_text(encoding="utf-8")) or {}
    out = {**DEFAULTS, **{k: v for k, v in data.items() if v not in (None, "")}}
    out["reference_markers"] = {**DEFAULTS["reference_markers"], **(data.get("reference_markers") or {})}
    return out


def get(key: str):
    return load()[key]
