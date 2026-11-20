"""Схема содержания отчёта.

Разделение ответственности:
  * Meta      — титул и параметры документа. Заполняет человек (task.yaml), НЕ модель.
  * Outline   — план работы. Шаг 1 модели.
  * Section   — содержание одного раздела. Шаг 2 модели (по вызову на раздел).
  * Report    — всё вместе; это и есть вход рендера (report.json можно править руками).

Ссылки на таблицы и рисунки модель пишет маркерами [[table:id]] / [[figure:id]];
номера ставит рендер. Так модель не может перепутать нумерацию.
"""
from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

from . import profile

# ---------------------------------------------------------------- meta (человек)


class Meta(BaseModel):
    work_type: Literal["Лабораторная работа", "Практическая работа", "Реферат", "Курсовая работа"]
    number: str = Field(description="Номер работы, например 3 или 4-5")
    discipline: str
    module: str | None = None
    topic: str
    direction: str = "38.03.05 «Бизнес-информатика»"
    semester: int
    student: str = Field(default_factory=lambda: profile.get("student"))
    group: str = Field(default_factory=lambda: profile.get("group"))
    teacher: str = "______________"
    date: str = "______________"
    city: str = "Москва"
    year: int
    file_code: str = Field(description="Аббревиатура дисциплины для имени файла, например TIPUP")
    file_prefix: str = Field(default_factory=lambda: profile.get("file_prefix"))
    # параметры структуры
    toc: bool = False
    intro: bool = False                      # раздел ВВЕДЕНИЕ (иначе «Цель работы:» в первом разделе)
    conclusion: Literal["ВЫВОДЫ", "ЗАКЛЮЧЕНИЕ"] | None = "ВЫВОДЫ"
    h1_new_page: bool = True

    @property
    def work_title(self) -> str:
        if self.work_type == "Реферат" or not str(self.number).strip():
            return self.work_type
        return f"{self.work_type} №{self.number}"

    @property
    def file_name(self) -> str:
        kind = {"Лабораторная работа": "LR", "Практическая работа": "PR",
                "Реферат": "Referat", "Курсовая работа": "KR"}[self.work_type]
        num = f"№{self.number}" if kind in ("LR", "PR") else ""
        return f"{self.file_prefix}_{self.file_code}_{kind}{num}.docx"



# ---------------------------------------------------------------- блоки (модель)


class Paragraph(BaseModel):
    type: Literal["paragraph"]
    text: str = Field(description="Один абзац. Допустим только **полужирный** для вводных слов "
                                  "('**Цель модели:** ...'). Ссылки: [[table:id]], [[figure:id]].")


class BulletList(BaseModel):
    type: Literal["list"]
    ordered: bool = False
    items: list[str] = Field(min_length=2)


class Table(BaseModel):
    type: Literal["table"]
    id: str = Field(description="Латиница без пробелов, например arrows_a0")
    caption: str = Field(description="Название без слова 'Таблица' и номера")
    columns: list[str] = Field(min_length=2)
    rows: list[list[str]] = Field(min_length=1)


class Figure(BaseModel):
    type: Literal["figure"]
    id: str = Field(description="Латиница без пробелов; файл рисунка ищется как figures/<id>.png")
    caption: str = Field(description="Название без слова 'Рисунок' и номера")


Block = Annotated[Union[Paragraph, BulletList, Table, Figure], Field(discriminator="type")]


class Subsection(BaseModel):
    title: str
    blocks: list[Block] = Field(min_length=1)


class Section(BaseModel):
    title: str = Field(description="Заголовок без номера")
    blocks: list[Block] = Field(min_length=1)
    subsections: list[Subsection] = Field(default_factory=list)


# ---------------------------------------------------------------- план (шаг 1)


class PlannedSection(BaseModel):
    title: str
    purpose: str = Field(description="Что раскрывает раздел, 1–2 предложения")
    tables: list[str] = Field(default_factory=list, description="Какие таблицы нужны (кратко)")
    figures: list[str] = Field(default_factory=list, description="Какие рисунки нужны (кратко)")


class Outline(BaseModel):
    goal: str = Field(description="Цель работы одним предложением, без слов 'Цель работы:'")
    sections: list[PlannedSection] = Field(min_length=2, max_length=8)


class TextPart(BaseModel):
    """Введение или выводы: просто абзацы."""
    paragraphs: list[str] = Field(min_length=2, max_length=6)


# ---------------------------------------------------------------- отчёт целиком


class Report(BaseModel):
    meta: Meta
    goal: str
    intro: list[str] = Field(default_factory=list)
    sections: list[Section]
    conclusion: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------- схема для Ollama


def ollama_schema(model: type[BaseModel]) -> dict:
    """JSON-схема без $ref/$defs/title: грамматика Ollama так надёжнее."""
    raw = model.model_json_schema()
    defs = raw.pop("$defs", {})

    def resolve(node, is_props=False):
        if isinstance(node, dict):
            if "$ref" in node and not is_props:
                return resolve(defs[node["$ref"].split("/")[-1]])
            out = {}
            for k, v in node.items():
                if is_props:                      # здесь ключи — имена полей, их не трогаем
                    out[k] = resolve(v)
                    continue
                if k in ("title", "discriminator", "default"):   # метаданные схемы
                    continue
                # oneOf -> anyOf: в грамматике это одно и то же, а anyOf поддерживается шире
                out["anyOf" if k == "oneOf" else k] = resolve(v, is_props=(k == "properties"))
            if out.get("type") == "object" and not is_props:
                out.setdefault("additionalProperties", False)
                # всё обязательное: модели проще, пустой список лучше пропущенного поля
                out["required"] = list(out.get("properties", {}).keys())
            return out
        if isinstance(node, list):
            return [resolve(x) for x in node]
        return node

    return resolve(raw)
