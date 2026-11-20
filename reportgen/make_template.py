"""Собирает templates/misis_report.docx из эталона — своего правильно оформленного отчёта МИСИС.

Что делает:
  * оставляет титульный лист эталона (его стили, поля, колонтитул с номером страницы);
  * заменяет изменяемые строки титула на {{заполнители}};
  * удаляет всё содержимое после титула (СОДЕРЖАНИЕ, текст, таблицы), sectPr сохраняется;
  * добавляет строку {{module}} под названием дисциплины (удаляется при рендере, если модуля нет).

Запуск один раз (или когда поменялся эталон):
    python -m reportgen.make_template "путь\\к\\эталон.docx"
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import docx
from docx.oxml.ns import qn

from . import profile
from .ooxml import set_paragraph_text

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "misis_report.docx"

# Тексты строк титула в эталоне -> заполнитель
TITLE_LINES = {
    "Практическая работа": "{{work_title}}",
    "«Введение в специальность»": "«{{discipline}}»",
    "«Оформление отчета по ГОСТу»": "«{{topic}}»",
    "38.03.05": "{{direction}}\n{{semester}}",
    "Москва": "{{city}} {{year}}",
    # в эталоне опечатка «учреждения»; в ЛР по ТИПУП уже исправлено
    "учреждения высшего образования": "учреждение высшего образования",
}
# Строки таблицы «Выполнил / Проверил» в эталоне: какие фамилии/группу/дату там искать,
# задаётся в profile.yaml (reference_markers) — в коде только заглушки.
_M = profile.get("reference_markers")
CELL_LINES = {
    _M["student"]: "{{student}}",
    _M["teacher"]: "{{teacher}}",
    _M["group"]: "{{group}}",
    _M["date"]: "{{date}}",
}


def _text(el) -> str:
    return "".join(t.text or "" for t in el.iter(qn("w:t")))


def build(src: Path, dst: Path = TEMPLATE_PATH) -> Path:
    d = docx.Document(str(src))
    body = d.element.body
    children = list(body)

    # 1. Конец титула — абзац «Москва 20xx»
    end = next(i for i, el in enumerate(children)
               if el.tag == qn("w:p") and _text(el).strip().startswith("Москва"))
    for el in children[end + 1:]:
        if el.tag != qn("w:sectPr"):
            body.remove(el)

    # 2. Заполнители в абзацах титула
    paras = {}
    for p in d.paragraphs:
        txt = p.text.strip()
        for prefix, repl in TITLE_LINES.items():
            if txt.startswith(prefix):
                set_paragraph_text(p._p, repl)
                paras[prefix] = p
                break

    # 3. Строка дисциплины в эталоне вставлена из браузера (стиль reacttray, 10,5 пт, заливка).
    #    Пересобираем её из строки темы, а строку модуля — из строки «по дисциплине».
    disc = paras["«Введение в специальность»"]
    clean = copy.deepcopy(paras["«Оформление отчета по ГОСТу»"]._p)
    set_paragraph_text(clean, "«{{discipline}}»")
    disc._p.addnext(clean)
    disc._p.getparent().remove(disc._p)
    tmpl = next(p for p in d.paragraphs if p.text.strip() == "по дисциплине")
    module = copy.deepcopy(tmpl._p)
    set_paragraph_text(module, "{{module}}")
    clean.addnext(module)

    # 4. Таблица «Выполнил / Проверил»
    for cell in (c for t in d.tables for r in t.rows for c in r.cells):
        for p in cell.paragraphs:
            txt = p.text.strip()
            for prefix, repl in CELL_LINES.items():
                if txt.startswith(prefix):
                    set_paragraph_text(p._p, repl)

    dst.parent.mkdir(parents=True, exist_ok=True)
    d.save(str(dst))
    return dst


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    print("Шаблон сохранён:", build(Path(sys.argv[1])))
