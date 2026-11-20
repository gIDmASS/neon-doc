"""Проверка содержания. Два уровня:

  errors   — модель обязана исправить (уходят обратно в модель);
  warnings — показываются человеку, перегенерацию не вызывают.

Синтаксис JSON и типы полей уже гарантирует Ollama (format = JSON-схема) + Pydantic.
Здесь — правила предметной области. Добавляй свои сюда: это и есть твоя экспертиза.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .schema import BulletList, Figure, Outline, Paragraph, Section, Table, TextPart

ID_RE = re.compile(r"^[a-z0-9_\-]+$")
REF_RE = re.compile(r"\[\[(table|figure):([\w\-]+)\]\]")
BAD_MARKUP_RE = re.compile(r"(^#|`|^\s*[-*•]\s|\|.*\|)", re.M)
TODO_RE = re.compile(r"\[уточнить:[^\]]*\]", re.I)

# Канцелярит и пустые связки. Ошибкой не считаются — только предупреждение.
STYLE_PHRASES = ["в данном разделе", "в рамках данной работы", "является неотъемлемой",
                 "играет важную роль", "таким образом,", "следует отметить", "стоит отметить",
                 "представляет собой", "в ходе выполнения", "данный процесс", "данная работа",
                 "на сегодняшний день", "в современных условиях"]
ROLE_COLUMNS = ("исполнител", "ответствен", "участник", "механизм", "владелец процесса")


@dataclass
class Result:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_feedback(self) -> str:
        return "\n".join(f"- {e}" for e in self.errors)


def check_outline(o: Outline) -> Result:
    r = Result()
    titles = [s.title.strip().lower() for s in o.sections]
    if len(set(titles)) != len(titles):
        r.errors.append("Названия разделов повторяются.")
    for s in o.sections:
        if re.match(r"^\d", s.title):
            r.errors.append(f"Заголовок «{s.title}» начинается с номера — номера ставит шаблон.")
        if s.title.strip().upper() in ("ВВЕДЕНИЕ", "ЗАКЛЮЧЕНИЕ", "СОДЕРЖАНИЕ", "ВЫВОДЫ",
                                       "СПИСОК ИСТОЧНИКОВ", "СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ"):
            r.errors.append(f"Раздел «{s.title}» не включай в план: его добавляет программа.")
    if o.goal.lower().startswith("цель"):
        r.errors.append("Поле goal должно начинаться с глагола, без слов «Цель работы».")
    return r


def check_section(sec: Section, plan=None, known_ids: set[str] | None = None,
                  roles: list[str] | None = None) -> Result:
    r = Result()
    known_ids = known_ids or set()
    blocks = list(sec.blocks) + [b for sub in sec.subsections for b in sub.blocks]
    seen_refs: set[tuple[str, str]] = set()
    ids_here: set[str] = set()

    if re.match(r"^\d", sec.title):
        r.errors.append(f"Заголовок «{sec.title}» начинается с номера — номера ставит шаблон.")
    if not any(isinstance(b, Paragraph) for b in sec.blocks):
        r.errors.append("В разделе нет ни одного абзаца текста перед таблицами/рисунками.")
    elif not isinstance(sec.blocks[0], Paragraph):
        r.errors.append("Раздел должен начинаться с абзаца текста, а не с таблицы, списка или рисунка.")

    all_refs = {m.groups() for b in blocks for m in REF_RE.finditer(_text_of(b))}

    for i, b in enumerate(blocks):
        text = _text_of(b)
        for m in REF_RE.finditer(text):
            seen_refs.add(m.groups())

        if isinstance(b, Paragraph):
            if BAD_MARKUP_RE.search(b.text):
                r.errors.append(f"Абзац {i + 1}: недопустимая разметка (#, `, |, маркеры списка). "
                                "Списки оформляй блоком type=list, таблицы — type=table.")
            if len(b.text) < 40 and not b.text.startswith("**"):
                r.warnings.append(f"Абзац {i + 1} очень короткий: «{b.text}».")
            if re.search(r"(таблиц[аеыу]|рисун(ок|ке|ка|ку))\s+\d", b.text, re.I):
                r.errors.append(f"Абзац {i + 1}: номер таблицы/рисунка написан вручную. "
                                "Используй маркер [[table:id]] или [[figure:id]].")
            low = b.text.lower()
            for ph in STYLE_PHRASES:
                if ph in low:
                    r.warnings.append(f"Абзац {i + 1}: шаблонный оборот «{ph}».")

        if isinstance(b, BulletList) and len(b.items) == 3:
            r.warnings.append(f"Блок {i + 1}: список ровно из трёх пунктов — проверь, не натянуто ли.")

        if isinstance(b, (Table, Figure)):
            if not ID_RE.match(b.id):
                r.errors.append(f"id «{b.id}»: только латиница в нижнем регистре, цифры, _ и -.")
            if b.id in ids_here or b.id in known_ids:
                r.errors.append(f"id «{b.id}» уже использован, придумай другой.")
            ids_here.add(b.id)
            if re.match(r"^(Таблица|Рисунок)\b|^\d", b.caption):
                r.errors.append(f"Подпись «{b.caption}»: без слова «Таблица»/«Рисунок» и без номера.")
            if (b.type, b.id) not in seen_refs:
                if (b.type, b.id) in all_refs:
                    r.errors.append(f"Ссылка [[{b.type}:{b.id}]] стоит после объекта — "
                                    "по ГОСТ ссылка должна быть в тексте до него.")
                else:
                    r.errors.append(f"На {'таблицу' if b.type == 'table' else 'рисунок'} «{b.id}» "
                                    f"нет ссылки в тексте. Добавь [[{b.type}:{b.id}]] в абзац перед ним.")

        if isinstance(b, Table):
            n = len(b.columns)
            for ri, row in enumerate(b.rows, 1):
                if len(row) != n:
                    r.errors.append(f"Таблица «{b.id}», строка {ri}: {len(row)} ячеек, "
                                    f"а столбцов {n}.")
                if any(not str(c).strip() for c in row):
                    r.errors.append(f"Таблица «{b.id}», строка {ri}: пустая ячейка "
                                    "(если значения нет — пиши «–»).")

    # исполнители в таблицах — только из списка ролей задания
    if roles:
        allowed = [r.lower() for r in roles]
        for b in blocks:
            if not isinstance(b, Table):
                continue
            for ci, col in enumerate(b.columns):
                if not any(k in col.lower() for k in ROLE_COLUMNS):
                    continue
                for ri, row in enumerate(b.rows, 1):
                    if ci >= len(row):
                        continue
                    for who in re.split(r"[,;/]| и ", row[ci]):
                        w = re.sub(r"\(.*?\)", "", who).strip().lower()
                        if not w or w in ("–", "-"):
                            continue
                        if not any(a in w or w in a or a[:-1] in w for a in allowed):
                            r.errors.append(f"Таблица «{b.id}», строка {ri}, «{col}»: «{who.strip()}» "
                                            f"нет среди участников ({', '.join(roles)}).")

    # ссылки на несуществующие объекты
    existing = {(b.type, b.id) for b in blocks if isinstance(b, (Table, Figure))}
    for kind, ident in all_refs:
        if (kind, ident) not in existing and ident not in known_ids:
            r.errors.append(f"Ссылка [[{kind}:{ident}]] указывает на объект, которого нет.")

    # сверка с планом
    if plan is not None:
        n_tab = sum(isinstance(b, Table) for b in blocks)
        n_fig = sum(isinstance(b, Figure) for b in blocks)
        if n_tab < len(plan.tables):
            r.errors.append(f"По плану в разделе таблиц: {len(plan.tables)} ({'; '.join(plan.tables)}), "
                            f"а сделано {n_tab}.")
        if n_fig < len(plan.figures):
            r.errors.append(f"По плану в разделе рисунков: {len(plan.figures)} "
                            f"({'; '.join(plan.figures)}), а сделано {n_fig}.")

    for m in TODO_RE.finditer(" ".join(_text_of(b) for b in blocks)):
        r.warnings.append(f"Модель просит уточнить: {m.group(0)}")
    return r


def check_text_part(t: TextPart) -> Result:
    r = Result()
    for i, p in enumerate(t.paragraphs, 1):
        if REF_RE.search(p):
            r.errors.append(f"Абзац {i}: во введении и выводах не ссылайся на таблицы и рисунки.")
        if BAD_MARKUP_RE.search(p):
            r.errors.append(f"Абзац {i}: недопустимая разметка.")
        low = p.lower()
        for ph in STYLE_PHRASES:
            if ph in low:
                r.warnings.append(f"Абзац {i}: шаблонный оборот «{ph}».")
    return r


def _text_of(b) -> str:
    if isinstance(b, Paragraph):
        return b.text
    if isinstance(b, BulletList):
        return " ".join(b.items)
    if isinstance(b, Table):
        return " ".join([b.caption, *b.columns, *[c for row in b.rows for c in row]])
    if isinstance(b, Figure):
        return b.caption
    return ""
