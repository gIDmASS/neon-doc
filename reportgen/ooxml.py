"""Низкоуровневые помощники для OOXML поверх python-docx."""
from __future__ import annotations

import copy
import re

from docx.oxml import OxmlElement
from docx.oxml.ns import qn


def _el(tag: str, **attrs) -> OxmlElement:
    el = OxmlElement(tag)
    for k, v in attrs.items():
        el.set(qn(k), str(v))
    return el


def set_paragraph_text(p, text: str) -> None:
    """Заменить текст абзаца, сохранив pPr и оформление первого фрагмента. \n -> перенос строки."""
    first_rpr = None
    for r in p.iter(qn("w:r")):
        rpr = r.find(qn("w:rPr"))
        if rpr is not None:
            first_rpr = copy.deepcopy(rpr)
        break
    for child in list(p):
        if child.tag != qn("w:pPr"):
            p.remove(child)
    for i, line in enumerate(text.split("\n")):
        r = _el("w:r")
        if first_rpr is not None:
            r.append(copy.deepcopy(first_rpr))
        if i:
            r.append(_el("w:br"))
        t = _el("w:t")
        t.text = line
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        r.append(t)
        p.append(r)


# ---------- runs ----------

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*|(\[уточнить:[^\]]*\])")


def add_runs(p, text: str, *, bold=False, size_pt: float | None = None) -> None:
    """Добавить текст в абзац. Поддерживается только **полужирный** — остальную разметку модель не пишет."""
    pos = 0
    for m in _BOLD_RE.finditer(text):
        if m.start() > pos:
            _add_run(p, text[pos:m.start()], bold=bold, size_pt=size_pt)
        if m.group(1):
            _add_run(p, m.group(1), bold=True, size_pt=size_pt)
        else:  # [уточнить: …] — жёлтым, чтобы не пропустить при вычитке
            _add_run(p, m.group(2), bold=bold, size_pt=size_pt, highlight=True)
        pos = m.end()
    if pos < len(text):
        _add_run(p, text[pos:], bold=bold, size_pt=size_pt)


def _add_run(p, text, *, bold=False, size_pt=None, highlight=False):
    r = _el("w:r")
    rpr = _el("w:rPr")
    if bold:
        rpr.append(_el("w:b"))
    if size_pt:
        rpr.append(_el("w:sz", **{"w:val": int(size_pt * 2)}))
        rpr.append(_el("w:szCs", **{"w:val": int(size_pt * 2)}))
    if highlight:
        rpr.append(_el("w:highlight", **{"w:val": "yellow"}))
    if len(rpr):
        r.append(rpr)
    t = _el("w:t")
    t.text = text
    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    r.append(t)
    p.append(r)
    return r


def add_seq_field(p, name: str, number: int) -> None:
    """Поле SEQ с уже проставленным номером — правильно выглядит и без обновления полей."""
    def fld(kind):
        r = _el("w:r")
        r.append(_el("w:fldChar", **{"w:fldCharType": kind}))
        return r
    p.append(fld("begin"))
    r = _el("w:r")
    it = _el("w:instrText")
    it.text = f" SEQ {name} \\* ARABIC "
    it.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    r.append(it)
    p.append(r)
    p.append(fld("separate"))
    _add_run(p, str(number))
    p.append(fld("end"))


def add_toc_field(paragraphs: list, entries: list[tuple[int, str]], tab_pos: int = 9355) -> None:
    """Поле TOC с заранее заполненными строками (без номеров страниц): документ сразу выглядит
    как надо, а Word при открытии обновит поле и проставит страницы."""
    def fld(kind):
        r = _el("w:r")
        r.append(_el("w:fldChar", **{"w:fldCharType": kind}))
        return r
    entries = entries or [(1, "Оглавление обновится при открытии в Word (F9)")]
    for i, (p, (level, text)) in enumerate(zip(paragraphs, entries)):
        pp = _el("w:pPr")
        tabs = _el("w:tabs")
        tabs.append(_el("w:tab", **{"w:val": "right", "w:leader": "dot", "w:pos": tab_pos}))
        pp.append(tabs)
        pp.append(_el("w:spacing", **{"w:after": 0}))
        pp.append(_el("w:ind", **{"w:left": (level - 1) * 357, "w:firstLine": 0}))
        pp.append(_el("w:jc", **{"w:val": "left"}))
        p.insert(0, pp)
        if i == 0:
            p.append(fld("begin"))
            r = _el("w:r")
            it = _el("w:instrText")
            it.text = ' TOC \\o "1-3" \\h \\z \\u '
            it.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            r.append(it)
            p.append(r)
            p.append(fld("separate"))
        _add_run(p, text)
        r = _el("w:r")
        r.append(_el("w:tab"))
        p.append(r)
        if i == len(entries) - 1:
            p.append(fld("end"))


# ---------- paragraph properties ----------

_PPR_ORDER = ["w:pStyle", "w:keepNext", "w:keepLines", "w:pageBreakBefore", "w:numPr",
              "w:spacing", "w:ind", "w:jc", "w:rPr"]


def ppr(p, *, style=None, keep_next=False, page_break=False, no_number=False,
        spacing: dict | None = None, ind: dict | None = None, jc: str | None = None):
    """Задать свойства абзаца в порядке, который требует схема OOXML."""
    pp = p.find(qn("w:pPr"))
    if pp is None:
        pp = _el("w:pPr")
        p.insert(0, pp)
    items = {}
    if style:
        items["w:pStyle"] = _el("w:pStyle", **{"w:val": style})
    if keep_next:
        items["w:keepNext"] = _el("w:keepNext")
    if page_break:
        items["w:pageBreakBefore"] = _el("w:pageBreakBefore")
    if no_number:
        np_ = _el("w:numPr")
        np_.append(_el("w:ilvl", **{"w:val": 0}))
        np_.append(_el("w:numId", **{"w:val": 0}))
        items["w:numPr"] = np_
    if spacing:
        items["w:spacing"] = _el("w:spacing", **{f"w:{k}": v for k, v in spacing.items()})
    if ind:
        items["w:ind"] = _el("w:ind", **{f"w:{k}": v for k, v in ind.items()})
    if jc:
        items["w:jc"] = _el("w:jc", **{"w:val": jc})
    for tag, el in items.items():
        old = pp.find(qn(tag))
        if old is not None:
            pp.remove(old)
    existing = {c.tag: c for c in pp}
    for c in list(pp):
        pp.remove(c)
    merged = {**{k: v for k, v in existing.items()}, **{qn(k): v for k, v in items.items()}}
    for tag in _PPR_ORDER:
        if qn(tag) in merged:
            pp.append(merged.pop(qn(tag)))
    for el in merged.values():  # всё прочее — в конец
        pp.append(el)
    return pp
