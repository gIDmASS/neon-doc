"""Сборка рабочих документов.

* kind: build — документ собирается с нуля (описание робота): Word по «Требованиям к оформлению»
  и разметка Confluence wiki (Вставить → Разметка) + рисунки в zip.
* kind: fill  — берётся исходный template.docx (обложка, стили, подписи, поля REF сохраняются),
  в него вписываются таблицы, текст, рисунки и значения [заглушек].
"""
from __future__ import annotations

import copy
import io
import re
import time
import zipfile
from pathlib import Path

import docx
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Emu, Pt, RGBColor
from docx.text.paragraph import Paragraph

from . import wdocs

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
FONT = "Times New Roman"
MONO = "Consolas"

# ================================================================== разметка → блоки

LIST_RE = re.compile(r"^(\s*)(\d+[.)]|[a-zа-я][.)]|[ivx]+[.)]|[-*•])\s+(.*)$", re.I)
CODE_RE = re.compile(r"^\s*```\s*([\w+-]*)\s*(.*)$")
FIG_RE = re.compile(r"^\s*!\[([^\]]*)\]\(([^)]+)\)\s*$")
TCAP_RE = re.compile(r"^\s*Таблица\s*:\s*(.+?)\s*(?:\{#([\w-]+)\})?\s*$", re.I)
NOTIFY_RE = re.compile(r"^\s*Шаблон\s*:\s*(.+)$", re.I)
NOTE_RE = re.compile(r"^(\s*)>\s?(.*)$")


def _is_table_line(s: str) -> bool:
    return s.strip().startswith("|") and s.strip().count("|") >= 2


def _cells(line: str) -> list[str]:
    s = line.strip().strip("|")
    return [c.strip().replace("<br>", "\n").replace("\\n", "\n") for c in re.split(r"(?<!\\)\|", s)]


def parse(text: str) -> list[tuple]:
    """Блоки: ('p', t) ('h', t) ('li', level, ordered, t) ('note', level, t)
    ('table', caption, id, header, rows) ('code', lang, title, code) ('fig', caption, file) ('notify', title, lines)."""
    lines = (text or "").replace("\r\n", "\n").split("\n")
    out, i, para = [], 0, []
    indents: list[int] = []      # стек отступов текущего списка
    pending_caption = None

    def flush():
        nonlocal para
        if para:
            out.append(("p", " ".join(x.strip() for x in para)))
            para = []

    def level_of(ind: int) -> int:
        while indents and ind < indents[-1]:
            indents.pop()
        if not indents or ind > indents[-1]:
            indents.append(ind)
        return len(indents)

    while i < len(lines):
        ln = lines[i]
        st = ln.strip()
        if not st:
            flush()
            # пустая строка не обрывает список, если следом снова пункт
            i += 1
            continue
        m = CODE_RE.match(ln)
        if m and st.startswith("```"):
            flush()
            lang, title = m.group(1) or "text", (m.group(2) or "").strip()
            body = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                body.append(lines[i])
                i += 1
            i += 1
            out.append(("code", lang.lower(), title, "\n".join(body).rstrip()))
            continue
        m = TCAP_RE.match(st)
        if m and i + 1 < len(lines) and _is_table_line(lines[i + 1]):
            flush()
            pending_caption = (m.group(1).strip().strip("«»\"'"), m.group(2))
            i += 1
            continue
        if _is_table_line(ln):
            flush()
            rows = []
            while i < len(lines) and _is_table_line(lines[i]):
                if not re.fullmatch(r"\s*\|?[\s:|-]+\|?\s*", lines[i]):
                    rows.append(_cells(lines[i]))
                i += 1
            cap, tid = pending_caption or ("", None)
            pending_caption = None
            if rows:
                out.append(("table", cap, tid, rows[0], rows[1:]))
            continue
        m = FIG_RE.match(ln)
        if m:
            flush()
            out.append(("fig", m.group(1).strip().strip("«»\""), m.group(2).strip()))
            i += 1
            continue
        m = NOTIFY_RE.match(st)
        if m:
            flush()
            body = []
            i += 1
            while i < len(lines) and lines[i].strip() and not NOTIFY_RE.match(lines[i].strip()):
                body.append(lines[i].strip())
                i += 1
            out.append(("notify", m.group(1).strip().strip("«»\""), body))
            continue
        if st.startswith("#"):
            hm = re.match(r"^#{1,4}\s+(.+)$", st)
            if hm:
                flush()
                indents.clear()
                out.append(("h", hm.group(1).strip()))
                i += 1
                continue
        m = NOTE_RE.match(ln)
        if m:
            flush()
            ind = len(m.group(1).expandtabs(4))
            lvl = 0
            for k, v in enumerate(indents, 1):
                if ind >= v:
                    lvl = k
            out.append(("note", lvl, m.group(2).strip()))
            i += 1
            continue
        m = LIST_RE.match(ln)
        if m:
            flush()
            ind = len(m.group(1).expandtabs(4))
            ordered = not m.group(2) in ("-", "*", "•")
            out.append(["li", level_of(ind), ordered, m.group(3).strip()])
            i += 1
            # продолжение пункта — строки с отступом без маркера
            while i < len(lines) and lines[i].strip() and lines[i].startswith((" ", "\t")) \
                    and not LIST_RE.match(lines[i]) and not NOTE_RE.match(lines[i]) \
                    and not lines[i].strip().startswith(("```", "|", "![")):
                out[-1][3] += "\n" + lines[i].strip()
                i += 1
            continue
        if indents and ln.startswith((" ", "\t")) and out and out[-1][0] == "li":
            out[-1][3] += "\n" + st
            i += 1
            continue
        indents.clear()
        para.append(st)
        i += 1
    flush()
    return [tuple(b) for b in out]


# ------------------------------------------------------------------ инлайн

INLINE_RE = re.compile(r"(\*\*.+?\*\*|(?<![\w*])\*[^*\s][^*]*?\*(?![\w*])|#[^#\n]{1,60}#|\[\[(?:figure|table):[^\]]+\]\]"
                       r"|\b(?:Шаг|Пункт|Подпроцесс)\s+\d+(?:\.\d+)*\b)")


def inline_runs(text: str, refs: dict | None = None) -> list[tuple[str, bool, bool]]:
    """Текст -> [(кусок, жирный, курсив)]. #Переменная#, «Шаг N» и ссылки — жирным."""
    refs = refs or {}
    out = []
    pos = 0
    for m in INLINE_RE.finditer(text):
        if m.start() > pos:
            out.append((text[pos:m.start()], False, False))
        tok = m.group(0)
        if tok.startswith("**"):
            inner = tok[2:-2]
            out.append((inner, True, False))
        elif tok.startswith("[["):
            kind, key = tok[2:-2].split(":", 1)
            out.append((refs.get((kind, key.strip()), "[нет " + key.strip() + "]"), True, False))
        elif tok.startswith("*"):
            out.append((tok[1:-1], False, True))
        else:
            out.append((tok, True, False))
        pos = m.end()
    if pos < len(text):
        out.append((text[pos:], False, False))
    return [x for x in out if x[0]]


def bold_only(line: str) -> list[tuple[str, bool]]:
    """Для кода: выделяется только **атрибут**, остальное как есть."""
    parts = re.split(r"\*\*(.+?)\*\*", line)
    return [(x, i % 2 == 1) for i, x in enumerate(parts) if x] or [("", False)]


def plain(text: str, refs: dict | None = None) -> str:
    return "".join(t for t, _, _ in inline_runs(text, refs))


# ================================================================== проверка разметки (требования)

def lint_markup(text: str, s: dict, figs: set, mats: set) -> list[dict]:
    out = []

    def add(level, msg):
        out.append({"level": level, "msg": msg})
    blocks = parse(text)
    steps_like = s["kind"] == "steps"
    # списки: не менее двух пунктов на уровне, не глубже трёх уровней
    i = 0
    while i < len(blocks):
        b = blocks[i]
        if b[0] == "li":
            j = i
            group = []
            while j < len(blocks) and blocks[j][0] in ("li", "note", "code", "table", "fig"):
                if blocks[j][0] == "li":
                    group.append(blocks[j])
                j += 1
            # считаем пункты на каждом уровне внутри каждого родителя
            counts: dict[tuple, int] = {}
            parents = [0, 0, 0, 0, 0]
            for k, li in enumerate(group):
                lvl = li[1]
                if lvl > 3:
                    add("err", f"уровень вложенности {lvl}: по требованиям максимум «1. a. i.» — «{plain(li[3])[:60]}»")
                parents[lvl] = k
                key = (lvl, tuple(parents[1:lvl]))
                counts[key] = counts.get(key, 0) + 1
            for (lvl, par), n in counts.items():
                if n < 2:
                    who = group[par[-1]][3][:50] if par else group[0][3][:50]
                    add("err", f"список уровня {lvl} из одного пункта (нужно ≥ 2) — под «{plain(who)}»")
            if steps_like:
                for li in group:
                    t = plain(li[3])
                    if li[1] == 1 and not re.search(r"робот", t, re.I):
                        add("warn", f"шаг не от лица робота: «{t[:70]}»")
                    if re.match(r"^\s*если\b", t) and not re.match(r"^\s*Если\b", t):
                        add("warn", f"условие должно начинаться с «Если» (с заглавной): «{t[:60]}»")
                    elif li[1] > 1 and re.search(r"\bесли\b", t, re.I) and not re.match(r"^\s*Если\b", t):
                        add("warn", f"условие в подпункте должно начинаться со слова «Если»: «{t[:60]}»")
                    if re.search(r"\b(пользователь|оператор|сотрудник)\s+(открывает|нажимает|вводит|переходит)", t, re.I):
                        add("warn", f"действие описано от лица человека: «{t[:60]}»")
                # переход в каждом пункте верхнего уровня (с учётом подпунктов)
                tops = [k for k, li in enumerate(group) if li[1] == 1]
                for n, k in enumerate(tops):
                    end = tops[n + 1] if n + 1 < len(tops) else len(group)
                    chunk = " ".join(plain(x[3]) for x in group[k:end])
                    if not re.search(r"переходит|Шаг\s+\d|Пункт\s+\d|заверш|следующ|возвращается|повторяет", chunk, re.I):
                        add("warn", f"пункт {n + 1}: нет перехода на следующий шаг («робот переходит на **Шаг N**»)")
            i = j
            continue
        i += 1
    for b in blocks:
        txt = b[3] if b[0] == "li" else b[1] if b[0] in ("p", "h") else b[2] if b[0] == "note" else ""
        if txt:
            if re.search(r"(?<![А-ЯA-Z*])\b(шаг|пункт)\s+\d", txt):
                ref = re.search(r"(шаг|пункт)\s+\d+", txt).group(0)
                add("warn", f"ссылка на шаг/пункт пишется с заглавной: «{ref}»")
            if re.search(r"запомина\w*|сохраня\w*\s+(значение|в переменную)", txt, re.I) and "#" not in txt:
                add("warn", f"сохраняемое значение объяви как #Переменная#: «{plain(txt)[:60]}»")
            if re.search(r"\bдат[аыуе]\b", txt, re.I) and not re.search(r"ДД\.|ММ\.|ГГ|ЧЧ:", txt) and re.search(r"(запомина|считыва|вводит|формир|указ)", txt, re.I):
                add("info", f"укажи формат даты (ДД.ММ.ГГГГ и т.п.): «{plain(txt)[:60]}»")
            if re.search(r"формул|рассчитыва|вычисля", txt, re.I) and not re.search(r"пример", txt, re.I):
                add("info", f"для формулы нужен пример расчёта: «{plain(txt)[:60]}»")
            for fm in re.finditer(r"[«\"]([^«»\"]{2,80})[»\"]", txt):
                name = fm.group(1)
                if re.search(r"\b(файл|отчет|отчёт|справочник|шаблон)\w*\s*$", txt[:fm.start()][-25:], re.I):
                    if not re.search(r"\.\w{2,5}$", name):
                        add("warn", f"файл «{name}» — указывай полное имя с расширением")
                    elif mats and name.lower() not in mats:
                        add("info", f"файл «{name}» не найден в «Материалах по роботу»")
        if b[0] == "note" and re.search(r"\bесли\b|\bиначе\b", b[2], re.I):
            add("err", f"примечание не должно содержать условий: «{b[2][:60]}»")
        if b[0] == "code":
            body = b[3]
            if not b[2]:
                add("warn", "у блока запроса нет заголовка («SQL-запрос для получения …»)")
            if re.search(r"\bcurl\b", body, re.I) and not re.search(r"requests\.", text):
                add("warn", "для cURL нужен ещё вариант на Python Requests")
            if b[1] in ("sql", "http", "bash", "python") and not re.search(r"ответ", text, re.I):
                add("info", "к запросу нужен пример ответа")
        if b[0] == "fig" and figs and b[2] not in figs:
            add("err", f"рисунок «{b[2]}» не приложен")
        if b[0] == "table" and s.get("numbered_captions") and not b[1]:
            add("warn", "таблица без подписи («Таблица: Краткое название» строкой выше)")
    for m in re.finditer(r"\[\[(figure|table):([^\]]+)\]\]", text):
        kind, key = m.group(1), m.group(2).strip()
        ok = any(b[0] == "fig" and b[2] == key for b in blocks) if kind == "figure" else \
            any(b[0] == "table" and b[2] == key for b in blocks)
        if not ok:
            add("warn", f"ссылка на {'рисунок' if kind == 'figure' else 'таблицу'} «{key}» — такого нет в разделе")
    if s.get("numbered_captions"):
        for b in blocks:
            if b[0] == "fig" and f"[[figure:{b[2]}]]" not in text:
                add("info", f"на рисунок «{b[1]}» нет ссылки в тексте ([[figure:{b[2]}]])")
            if b[0] == "table" and b[2] and f"[[table:{b[2]}]]" not in text:
                add("info", f"на таблицу «{b[1]}» нет ссылки в тексте ([[table:{b[2]}]])")
    return out


# ================================================================== общие помощники docx

def _shade(cell, color: str):
    tcPr = cell._tc.get_or_add_tcPr()
    sh = OxmlElement("w:shd")
    sh.set(qn("w:val"), "clear")
    sh.set(qn("w:color"), "auto")
    sh.set(qn("w:fill"), color)
    tcPr.append(sh)


def _add_runs(p, text: str, refs=None, size=None, font=None, bold=None, italic=None):
    for chunk, b, it in inline_runs(text, refs):
        parts = chunk.split("\n")
        for k, part in enumerate(parts):
            if k:
                p.add_run().add_break()
            r = p.add_run(part)
            r.bold = True if (b or bold) else None
            r.italic = True if (it or italic) else None
            if size:
                r.font.size = Pt(size)
            if font:
                r.font.name = font
                r._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), font)


def _border_picture(run):
    """Чёрная рамка у рисунка (требование к скриншотам)."""
    for spPr in run._element.iter(qn("pic:spPr")):
        ln = OxmlElement("a:ln")
        ln.set("w", "9525")
        fill = OxmlElement("a:solidFill")
        clr = OxmlElement("a:srgbClr")
        clr.set("val", "000000")
        fill.append(clr)
        ln.append(fill)
        spPr.append(ln)


def _pic_size(path: Path, max_w_cm: float, max_h_cm: float = 18.0):
    from PIL import Image
    with Image.open(path) as im:
        w, h = im.size
    k = min(max_w_cm / (w / 96 * 2.54), max_h_cm / (h / 96 * 2.54), 1.0)
    return Cm(w / 96 * 2.54 * k)


class Numbering:
    """Многоуровневые списки «1. a. i.» и маркированные — свои определения в numbering.xml."""

    def __init__(self, document):
        self.np = document.part.numbering_part.element
        self.abs_ord = self._abstract(900, ["decimal", "lowerLetter", "lowerRoman", "decimal"],
                                      ["%1.", "%2.", "%3.", "%4."])
        self.abs_bul = self._abstract(901, ["bullet"] * 4, ["•", "◦", "▪", "•"])
        self.next_id = 900

    def _abstract(self, aid, fmts, texts):
        a = OxmlElement("w:abstractNum")
        a.set(qn("w:abstractNumId"), str(aid))
        ml = OxmlElement("w:multiLevelType")
        ml.set(qn("w:val"), "hybridMultilevel")
        a.append(ml)
        for lvl, (f, t) in enumerate(zip(fmts, texts)):
            L = OxmlElement("w:lvl")
            L.set(qn("w:ilvl"), str(lvl))
            for tag, val in (("w:start", "1"), ("w:numFmt", f), ("w:lvlText", t), ("w:lvlJc", "left")):
                e = OxmlElement(tag)
                e.set(qn("w:val"), val)
                L.append(e)
            ppr = OxmlElement("w:pPr")
            ind = OxmlElement("w:ind")
            ind.set(qn("w:left"), str(360 + 360 * lvl + 0))
            ind.set(qn("w:hanging"), "360")
            ppr.append(ind)
            L.append(ppr)
            a.append(L)
        first_num = self.np.find(qn("w:num"))
        if first_num is not None:
            first_num.addprevious(a)
        else:
            self.np.append(a)
        return aid

    def new(self, ordered: bool) -> int:
        self.next_id += 1
        n = OxmlElement("w:num")
        n.set(qn("w:numId"), str(self.next_id))
        an = OxmlElement("w:abstractNumId")
        an.set(qn("w:val"), str(self.abs_ord if ordered else self.abs_bul))
        n.append(an)
        for lvl in range(4):
            ov = OxmlElement("w:lvlOverride")
            ov.set(qn("w:ilvl"), str(lvl))
            so = OxmlElement("w:startOverride")
            so.set(qn("w:val"), "1")
            ov.append(so)
            n.append(ov)
        self.np.append(n)
        return self.next_id

    @staticmethod
    def apply(p, num_id: int, lvl: int):
        pPr = p._p.get_or_add_pPr()
        numPr = OxmlElement("w:numPr")
        il = OxmlElement("w:ilvl")
        il.set(qn("w:val"), str(lvl))
        ni = OxmlElement("w:numId")
        ni.set(qn("w:val"), str(num_id))
        numPr.append(il)
        numPr.append(ni)
        pPr.insert(0, numPr) if pPr.find(qn("w:pStyle")) is None else pPr.find(qn("w:pStyle")).addnext(numPr)


# ================================================================== сборка «с нуля» (описание робота)

def _assign_numbers(t: dict, doc: dict) -> dict:
    """Первый проход: номера рисунков/таблиц/диаграмм/шаблонов для подписей и ссылок."""
    refs, cnt = {}, {"Рисунок": 0, "Таблица": 0, "Диаграмма": 0, "Шаблон": 0}
    for s in t["sections"]:
        sec = doc["sections"].get(s["id"], {})
        if not sec.get("enabled", True):
            continue
        if s["kind"] == "figures":
            word = s.get("caption_word", "Рисунок")
            for f in sec.get("figures") or []:
                cnt[word] += 1
                refs[("figure", f["file"])] = f"{word} {cnt[word]}"
        if s["kind"] in ("text", "steps"):
            for b in parse(sec.get("text") or ""):
                if b[0] == "fig" and s.get("numbered_captions"):
                    cnt["Рисунок"] += 1
                    refs[("figure", b[2])] = f"Рисунок {cnt['Рисунок']}"
                if b[0] == "table" and s.get("numbered_captions"):
                    cnt["Таблица"] += 1
                    if b[2]:
                        refs[("table", b[2])] = f"Таблица {cnt['Таблица']}"
                    refs[("tablecap", id(b))] = cnt["Таблица"]
    return refs


class BuildDocx:
    def __init__(self, did: str):
        self.did = did
        self.doc = wdocs.get(did)
        self.t = wdocs.get_template(self.doc["template"])
        self.figdir = wdocs.ddir(did) / "figures"
        self.d = docx.Document()
        self.num = Numbering(self.d)
        self.refs = _assign_numbers(self.t, self.doc)
        self.cnt = {"Рисунок": 0, "Таблица": 0, "Диаграмма": 0, "Шаблон": 0}
        self.warnings: list[str] = []
        self._last_ordered = True
        self._setup()

    def _setup(self):
        sec = self.d.sections[0]
        sec.page_width, sec.page_height = Cm(21), Cm(29.7)
        sec.left_margin, sec.right_margin, sec.top_margin, sec.bottom_margin = Cm(2.5), Cm(1.5), Cm(2), Cm(2)
        st = self.d.styles["Normal"]
        st.font.name = FONT
        st.font.size = Pt(12)
        st.element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), FONT)
        pf = st.paragraph_format
        pf.space_after = Pt(6)
        pf.line_spacing = 1.15
        for name, size in (("Heading 1", 14), ("Heading 2", 12), ("Title", 16)):
            h = self.d.styles[name]
            h.font.name, h.font.size, h.font.bold = FONT, Pt(size), True
            h.font.color.rgb = RGBColor(0, 0, 0)
            rpr = h.element.get_or_add_rPr()
            rf = rpr.get_or_add_rFonts()
            for a in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
                rf.attrib.pop(qn(a), None)
            for a in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
                rf.set(qn(a), FONT)
            h.paragraph_format.space_before = Pt(14 if name == "Heading 1" else 10)
            h.paragraph_format.space_after = Pt(6)
            h.paragraph_format.keep_with_next = True

    @property
    def text_w_cm(self):
        return 17.0

    # --- элементы
    def para(self, text, align=None, italic=False, indent_lvl=0, size=None):
        p = self.d.add_paragraph()
        _add_runs(p, text, self.refs, size=size, italic=italic or None)
        if align:
            p.alignment = align
        if indent_lvl:
            p.paragraph_format.left_indent = Cm(0.635 * indent_lvl)
        return p

    def caption(self, word, title, align, before=False):
        self.cnt[word] += 1
        p = self.d.add_paragraph()
        r = p.add_run(f"{word} {self.cnt[word]}")
        r.bold = True
        p.add_run(f" – «{title.strip().strip('«»')}»" if title else "")
        p.alignment = align
        p.paragraph_format.keep_with_next = before
        p.paragraph_format.space_after = Pt(4 if before else 10)
        return p

    def table(self, header, rows, autonum=False, caption=None, numbered=False):
        if caption is not None and numbered:
            self.caption("Таблица", caption, WD_ALIGN_PARAGRAPH.LEFT, before=True)
        elif caption:
            p = self.para(caption)
            p.runs[0].bold = True if p.runs else None
            p.paragraph_format.keep_with_next = True
        rows = [r for r in rows if any(str(c).strip() for c in r)]
        if not rows:
            rows, autonum = [[""] * len(header)], False
        tb = self.d.add_table(rows=1 + len(rows), cols=len(header))
        tb.style = self.d.styles["Table Grid"]
        tb.alignment = WD_TABLE_ALIGNMENT.LEFT
        for j, h in enumerate(header):
            c = tb.rows[0].cells[j]
            c.text = ""
            _add_runs(c.paragraphs[0], str(h), self.refs, size=10, bold=True)
            _shade(c, "F2F2F2")
        trPr = tb.rows[0]._tr.get_or_add_trPr()
        th = OxmlElement("w:tblHeader")
        th.set(qn("w:val"), "true")
        trPr.append(th)
        for i, r in enumerate(rows, 1):
            for j in range(len(header)):
                val = str(i) if autonum and j == 0 else (str(r[j]) if j < len(r) else "")
                c = tb.rows[i].cells[j]
                c.text = ""
                _add_runs(c.paragraphs[0], val, self.refs, size=10)
        for row in tb.rows:
            for c in row.cells:
                for p in c.paragraphs:
                    p.paragraph_format.space_after = Pt(2)
                    p.paragraph_format.line_spacing = 1.0
        if autonum:
            for row in tb.rows:
                row.cells[0].width = Cm(1.0)
        self.d.add_paragraph().paragraph_format.space_after = Pt(2)
        return tb

    def code(self, lang, title, body):
        """Блок «раскрыть» → «информация»: заголовок и код в рамке."""
        tb = self.d.add_table(rows=1, cols=1)
        tb.style = self.d.styles["Table Grid"]
        c = tb.rows[0].cells[0]
        _shade(c, "E9F2FF")
        p = c.paragraphs[0]
        r = p.add_run("▾ " + (title or f"{lang.upper()}-запрос"))
        r.bold = True
        r.font.size = Pt(10)
        for line in body.split("\n"):
            q = c.add_paragraph()
            q.paragraph_format.space_after = Pt(0)
            q.paragraph_format.line_spacing = 1.0
            for chunk, b in bold_only(line):
                rr = q.add_run(chunk or " ")
                rr.font.name = MONO
                rr.font.size = Pt(9)
                rr.bold = True if b else None
        self.d.add_paragraph().paragraph_format.space_after = Pt(2)

    def figure(self, file, title, word="Рисунок", align=WD_ALIGN_PARAGRAPH.CENTER, numbered=True):
        path = self.figdir / file
        if not path.exists():
            self.para(f"[нет файла рисунка: {file}]")
            self.warnings.append(f"нет файла рисунка {file}")
            return
        p = self.d.add_paragraph()
        p.alignment = align
        p.paragraph_format.keep_with_next = True
        r = p.add_run()
        r.add_picture(str(path), width=_pic_size(path, self.text_w_cm))
        _border_picture(r)
        if numbered:
            self.caption(word, title, align)
        elif title:
            q = self.para(title, align=align, italic=True)
            q.paragraph_format.space_after = Pt(10)

    def blocks(self, text, s):
        numbered = bool(s.get("numbered_captions"))
        num_id = None
        for b in parse(text):
            k = b[0]
            if k in ("p", "h"):
                num_id = None
            if k == "p":
                self.para(b[1])
            elif k == "h":
                p = self.para(b[1])
                for r in p.runs:
                    r.bold = True
                p.paragraph_format.keep_with_next = True
            elif k == "li":
                lvl, ordered, txt = b[1], b[2], b[3]
                if num_id is None or (lvl == 1 and ordered != self._last_ordered):
                    num_id = self.num.new(ordered)
                self._last_ordered = ordered if lvl == 1 else getattr(self, "_last_ordered", ordered)
                p = self.d.add_paragraph()
                _add_runs(p, txt, self.refs)
                Numbering.apply(p, num_id, min(lvl, 4) - 1)
                p.paragraph_format.space_after = Pt(3)
            elif k == "note":
                self.para(b[2], italic=True, indent_lvl=max(b[1], 0))
            elif k == "table":
                self.table(b[3], b[4], caption=b[1] if numbered else (b[1] or None), numbered=numbered)
            elif k == "code":
                self.code(b[1], b[2], b[3])
            elif k == "fig":
                self.figure(b[2], b[1], "Рисунок", WD_ALIGN_PARAGRAPH.CENTER, numbered=numbered)
            elif k == "notify":
                self.caption("Шаблон", b[1], WD_ALIGN_PARAGRAPH.LEFT, before=True)
                tb = self.d.add_table(rows=1, cols=1)
                tb.style = self.d.styles["Table Grid"]
                c = tb.rows[0].cells[0]
                c.text = ""
                for n, line in enumerate(b[2] or [""]):
                    q = c.paragraphs[0] if n == 0 else c.add_paragraph()
                    q.paragraph_format.space_after = Pt(1)
                    _add_runs(q, line, self.refs, size=11)
                self.d.add_paragraph().paragraph_format.space_after = Pt(2)

    def build(self) -> Path:
        f = self.doc["fields"]
        title = " ".join(x for x in (f.get("code"), f.get("name")) if x) or self.doc["title"]
        self.d.add_paragraph(title, style="Title")
        meta = " · ".join(x for x in (f.get("version") and f"Версия {f['version']}", f.get("date"),
                                      f.get("customer"), f.get("author") and f"Аналитик: {f['author']}") if x)
        if meta:
            p = self.para(meta, size=10)
            p.runs[0].italic = True
        for s in self.t["sections"]:
            sec = self.doc["sections"].get(s["id"], {})
            if not sec.get("enabled", True):
                continue
            self.d.add_heading(s["title"], level=1 if s.get("level", 1) == 1 else 2)
            if s["kind"] == "heading":
                continue
            for para in wdocs.fmt(s.get("intro", ""), f).split("\n"):
                if para.strip():
                    self.para(" ".join(para.split()))
            if s["kind"] in ("text", "steps"):
                if (sec.get("text") or "").strip():
                    self.blocks(sec["text"], s)
            elif s["kind"] == "table":
                rows = [[wdocs.fmt(c, f) for c in r] for r in sec.get("rows") or []]
                self.table(s["columns"], rows, autonum=bool(s.get("autonum")))
            elif s["kind"] == "figures":
                align = WD_ALIGN_PARAGRAPH.LEFT if s.get("align") == "left" else WD_ALIGN_PARAGRAPH.CENTER
                for fg in sec.get("figures") or []:
                    self.figure(fg["file"], fg.get("caption", ""), s.get("caption_word", "Рисунок"), align)
            elif s["kind"] == "list":
                nid = self.num.new(False)
                for it in sec.get("items") or []:
                    p = self.d.add_paragraph()
                    _add_runs(p, it, self.refs)
                    Numbering.apply(p, nid, 0)
        from reportgen.render import save_docx
        return save_docx(self.d, out_path(self.did, self.doc, "docx"))


# ================================================================== Confluence wiki

_WIKI_ESC = re.compile(r"([{}\[\]|*_!^~+\\])")


def _wesc(s: str) -> str:
    s = _WIKI_ESC.sub(r"\\\1", s)
    return re.sub(r"(-{2,})", lambda m: "\\" + "\\".join(m.group(1)), s)


def wiki_inline(text: str, refs: dict) -> str:
    out = []
    for chunk, b, it in inline_runs(text, refs):
        c = _wesc(chunk).replace("\n", " \\\\ ")
        if b and c.strip():
            lead, core, trail = re.match(r"^(\s*)(.*?)(\s*)$", c, re.S).groups()
            c = f"{lead}*{core}*{trail}"
        elif it and c.strip():
            lead, core, trail = re.match(r"^(\s*)(.*?)(\s*)$", c, re.S).groups()
            c = f"{lead}_{core}_{trail}"
        out.append(c)
    return "".join(out)


CODE_LANG = {"sql": "sql", "json": "javascript", "js": "javascript", "javascript": "javascript", "xml": "xml",
             "python": "python", "py": "python", "bash": "bash", "sh": "bash", "powershell": "powershell",
             "http": "none", "text": "none", "": "none", "curl": "bash", "java": "java", "csharp": "csharp"}


class Wiki:
    def __init__(self, did: str):
        self.doc = wdocs.get(did)
        self.t = wdocs.get_template(self.doc["template"])
        self.refs = _assign_numbers(self.t, self.doc)
        self.cnt = {"Рисунок": 0, "Таблица": 0, "Диаграмма": 0, "Шаблон": 0}
        self.lines: list[str] = []
        self.images: set[str] = set()

    def cap(self, word, title):
        self.cnt[word] += 1
        return f"*{word} {self.cnt[word]}* – «{_wesc(title.strip().strip('«»'))}»" if title else f"*{word} {self.cnt[word]}*"

    def table(self, header, rows, autonum=False):
        rows = [r for r in rows if any(str(c).strip() for c in r)]
        if not rows:
            rows, autonum = [[""] * len(header)], False
        self.lines.append("||" + "||".join(wiki_inline(str(h), self.refs) or " " for h in header) + "||")
        for i, r in enumerate(rows, 1):
            cells = [str(i) if autonum and j == 0 else (str(r[j]) if j < len(r) else "") for j in range(len(header))]
            self.lines.append("|" + "|".join(wiki_inline(c, self.refs) or " " for c in cells) + "|")
        self.lines.append("")

    def code(self, lang, title, body):
        t = _wesc(title or f"{lang.upper()}-запрос").replace("|", "")
        self.lines.append("{expand:" + t.replace(":", " ") + "}")
        self.lines.append("{info}")
        if "**" in body:   # выделенные атрибуты: в {code} жирного нет — моноширинные строки
            for line in body.split("\n"):
                parts = []
                for chunk, b in bold_only(line):
                    chunk = chunk.replace(" ", "\u00a0")
                    if not chunk:
                        continue
                    seg = "{{" + _wesc(chunk) + "}}"
                    parts.append(f"*{seg}*" if b else seg)
                self.lines.append("".join(parts) or " ")
        else:
            self.lines.append("{code:language=" + CODE_LANG.get(lang, "none") + "}")
            self.lines.append(body)
            self.lines.append("{code}")
        self.lines.append("{info}")
        self.lines.append("{expand}")
        self.lines.append("")

    def fig(self, file, title, word, left=False, numbered=True):
        self.images.add(file)
        self.lines.append(f"!{file}|border=1{'' if left else ',align=center'}!")
        if numbered:
            c = self.cap(word, title)
            self.lines.append(c)
        elif title:
            self.lines.append("_" + _wesc(title) + "_")
        self.lines.append("")

    def blocks(self, text, s):
        """Список в wiki обрывается любой строкой без маркера, поэтому рисунки, примечания и запросы
        внутри шагов вписываются в сам пункт (через перенос строки), а таблицы — сразу после списка."""
        numbered = bool(s.get("numbered_captions"))
        stack: list[str] = []
        deferred: list[tuple] = []

        def end_list():
            nonlocal stack, deferred
            if stack:
                stack = []
                self.lines.append("")
            for d in deferred:
                self._table_block(d, numbered)
            deferred = []

        for b in parse(text):
            k = b[0]
            in_list = bool(stack)
            if k in ("p", "h"):
                end_list()
            if k == "p":
                self.lines.append(wiki_inline(b[1], self.refs))
                self.lines.append("")
            elif k == "h":
                self.lines.append("h4. " + _wesc(b[1]))
            elif k == "li":
                lvl, ordered, txt = b[1], b[2], b[3]
                stack = stack[:lvl - 1] + ["#" if ordered else "*"]
                while len(stack) < lvl:
                    stack.insert(0, "#")
                self.lines.append("".join(stack) + " " + wiki_inline(txt, self.refs))
            elif k == "note":
                note = "_" + _wesc(b[2]).replace("\n", " ") + "_"
                if in_list:
                    self.lines[-1] += " \\\\ " + note
                else:
                    self.lines += [note, ""]
            elif k == "fig":
                if in_list:
                    self.images.add(b[2])
                    cap = self.cap("Рисунок", b[1]) if numbered else ("_" + _wesc(b[1]) + "_" if b[1] else "")
                    self.lines[-1] += f" \\\\ !{b[2]}|border=1! \\\\ {cap}"
                else:
                    self.fig(b[2], b[1], "Рисунок", numbered=numbered)
            elif k == "code":
                if in_list:
                    start = len(self.lines)
                    self.code(b[1], b[2], b[3])
                    block = self.lines[start:]
                    del self.lines[start:]
                    while block and not block[-1].strip():
                        block.pop()
                    self.lines[-1] += " " + "\n".join(block)
                else:
                    self.code(b[1], b[2], b[3])
            elif k == "table":
                if in_list:
                    deferred.append(b)
                else:
                    self._table_block(b, numbered)
            elif k == "notify":
                end_list()
                self.lines.append(self.cap("Шаблон", b[1]))
                self.lines.append("{panel}")
                self.lines += [wiki_inline(x, self.refs) for x in b[2]] or [" "]
                self.lines.append("{panel}")
                self.lines.append("")
        end_list()

    def _table_block(self, b, numbered):
        if numbered:
            self.lines.append(self.cap("Таблица", b[1]))
        elif b[1]:
            self.lines.append("*" + _wesc(b[1]) + "*")
        self.table(b[3], b[4])

    def build(self) -> str:
        f = self.doc["fields"]
        for s in self.t["sections"]:
            sec = self.doc["sections"].get(s["id"], {})
            if not sec.get("enabled", True):
                continue
            self.lines.append(("h2. " if s.get("level", 1) == 1 else "h3. ") + _wesc(s["title"]))
            if s["kind"] == "heading":
                continue
            for para in wdocs.fmt(s.get("intro", ""), f).split("\n"):
                if para.strip():
                    self.lines.append(_wesc(" ".join(para.split())))
                    self.lines.append("")
            if s["kind"] in ("text", "steps"):
                self.blocks(sec.get("text") or "", s)
            elif s["kind"] == "table":
                self.table(s["columns"], [[wdocs.fmt(c, f) for c in r] for r in sec.get("rows") or []],
                           autonum=bool(s.get("autonum")))
            elif s["kind"] == "figures":
                for fg in sec.get("figures") or []:
                    self.fig(fg["file"], fg.get("caption", ""), s.get("caption_word", "Рисунок"),
                             left=s.get("align") == "left")
            elif s["kind"] == "list":
                self.lines += ["* " + wiki_inline(x, self.refs) for x in sec.get("items") or []]
                self.lines.append("")
        txt = "\n".join(self.lines)
        return re.sub(r"\n{3,}", "\n\n", txt).strip() + "\n"


def confluence_zip(did: str) -> Path:
    w = Wiki(did)
    markup = w.build()
    doc = w.doc
    out = out_path(did, doc, "zip", suffix=" (Confluence)")
    figdir = wdocs.ddir(did) / "figures"
    howto = ("Как перенести в Confluence:\n"
             "1. Создай страницу, заголовок — название робота.\n"
             "2. Прикрепи к странице все картинки из папки images (Вложения → Прикрепить файлы).\n"
             "3. В редакторе: «+» → «Разметка» (Insert → Markup), формат Confluence wiki, вставь page.txt.\n"
             "4. Схему BPMN после вставки замени макросом BPMN Modeler (требование — редактируемая схема).\n"
             "5. Таблицы, стоявшие внутри шагов, в wiki-разметке идут сразу после списка шагов "
             "(в wiki список нельзя прервать таблицей без сброса нумерации). Номера и ссылки сохранены.\n\n"
             "Другой путь: «Инструменты страницы → Импорт документа Word» и файл .docx из этого архива — "
             "нумерация и картинки перенесутся, но блоки «раскрыть/информация» придётся сделать макросами вручную.\n")
    dx = BuildDocx(did).build()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("page.txt", markup)
        z.write(dx, dx.name)
        z.writestr("КАК ВСТАВИТЬ.txt", howto)
        for name in sorted(w.images):
            p = figdir / name
            if p.exists():
                z.write(p, "images/" + name)
    return out


def confluence_text(did: str) -> str:
    return Wiki(did).build()


# ================================================================== заполнение template.docx

def _p_texts(p_el):
    """w:t, принадлежащие именно этому абзацу (без вложенных надписей)."""
    return [t for t in p_el.iter(qn("w:t")) if _owner_p(t) is p_el]


def _owner_p(el):
    e = el.getparent()
    while e is not None and e.tag != qn("w:p"):
        e = e.getparent()
    return e


def _unhighlight(r_el):
    rpr = r_el.find(qn("w:rPr"))
    if rpr is not None:
        for h in rpr.findall(qn("w:highlight")):
            rpr.remove(h)


def replace_in_p(p_el, mapping: list[tuple[str, str]]) -> int:
    """Замена с учётом того, что заглушка разбита на несколько w:r. Подсветка с замен снимается."""
    ts = _p_texts(p_el)
    if not ts:
        return 0
    n = 0
    for old, new in mapping:
        while True:
            full = "".join(t.text or "" for t in ts)
            i = full.find(old)
            if i < 0:
                break
            n += 1
            pos, start_done = 0, False
            end = i + len(old)
            for t in ts:
                s = t.text or ""
                a, b = pos, pos + len(s)
                pos = b
                if b <= i or a >= end:
                    continue
                lo, hi = max(i, a) - a, min(end, b) - a
                if not start_done:
                    t.text = s[:lo] + new + s[hi:]
                    start_done = True
                else:
                    t.text = s[:lo] + s[hi:]
                t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
                _unhighlight(t.getparent())
    return n


def _set_p_text(p_el, text: str, bold_inline=True):
    """Оставить формат первого run абзаца, заменить весь текст (с **жирным**)."""
    runs = [r for r in p_el.findall(qn("w:r"))]
    proto = None
    for r in runs:
        if r.find(qn("w:t")) is not None:
            proto = r
            break
    proto = copy.deepcopy(proto if proto is not None else (runs[0] if runs else OxmlElement("w:r")))
    for t in list(proto):
        if t.tag != qn("w:rPr"):
            proto.remove(t)
    _unhighlight(proto)
    for ch in list(p_el):
        if ch.tag in (qn("w:r"), qn("w:hyperlink"), qn("w:proofErr"), qn("w:bookmarkStart"), qn("w:bookmarkEnd"),
                      qn("w:fldSimple"), qn("w:ins"), qn("w:del")):
            p_el.remove(ch)
    pieces = inline_runs(text) if bold_inline else [(text, False, False)]
    for chunk, b, it in pieces:
        for k, line in enumerate(chunk.split("\n")):
            r = copy.deepcopy(proto)
            if k:
                br = OxmlElement("w:br")
                r.append(br)
            t = OxmlElement("w:t")
            t.text = line
            t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            r.append(t)
            rpr = r.find(qn("w:rPr"))
            if rpr is None:
                rpr = OxmlElement("w:rPr")
                r.insert(0, rpr)
            if b:
                rpr.append(OxmlElement("w:b"))
            if it:
                rpr.append(OxmlElement("w:i"))
            p_el.append(r)


def _has_page_break(el) -> bool:
    return any(br.get(qn("w:type")) == "page" for br in el.iter(qn("w:br")))


def _strip_page_breaks(el):
    for br in list(el.iter(qn("w:br"))):
        if br.get(qn("w:type")) == "page":
            br.getparent().remove(br)


def _clone_p(proto, text):
    p = copy.deepcopy(proto)
    _strip_page_breaks(p)
    for d in list(p.iter(qn("w:drawing"))) + list(p.iter(qn("w:object"))) + list(p.iter(qn("w:pict"))):
        d.getparent().remove(d)
    _set_p_text(p, text)
    return p


def _page_break_p():
    p = OxmlElement("w:p")
    r = OxmlElement("w:r")
    br = OxmlElement("w:br")
    br.set(qn("w:type"), "page")
    r.append(br)
    p.append(r)
    return p


def _set_cell(cell, text: str):
    tc = cell._tc
    ps = tc.findall(qn("w:p"))
    proto = ps[0]
    for p in ps[1:]:
        tc.remove(p)
    lines = str(text).split("\n") if str(text) else [""]
    _set_p_text(proto, lines[0])
    prev = proto
    for line in lines[1:]:
        p = copy.deepcopy(proto)
        _set_p_text(p, line)
        prev.addnext(p)
        prev = p


def _fill_table(tb, s: dict, rows: list[list[str]], fields: dict):
    rows = [[wdocs.fmt(c, fields) for c in r] for r in rows]
    ncol = len(tb.columns)
    if s.get("fixed_rows"):
        for i, r in enumerate(rows[: len(tb.rows) - 1]):
            for j in range(min(ncol, len(r))):
                if j == s.get("fixed_col", 0) or (s.get("autonum") and j == 0):
                    continue
                if j in wdocs.table_ai_cols(s) or j == (s.get("target") or {}).get("value_col"):
                    _set_cell(tb.rows[i + 1].cells[j], r[j])
        return
    rows = [r for r in rows if any(str(c).strip() for c in r)] or [[""] * ncol]
    data = tb.rows[1:]
    proto = copy.deepcopy(data[0]._tr) if data else copy.deepcopy(tb.rows[0]._tr)
    for r in data:
        tb._tbl.remove(r._tr)
    from docx.table import _Row
    for i, r in enumerate(rows, 1):
        tr = copy.deepcopy(proto)
        tb._tbl.append(tr)
        row = _Row(tr, tb)
        for j in range(min(ncol, len(row.cells))):
            val = str(i) if s.get("autonum") and j == 0 else (r[j] if j < len(r) else "")
            _set_cell(row.cells[j], val)


def _drop_column(tb, idx: int):
    grid = tb._tbl.tblGrid
    cols = grid.findall(qn("w:gridCol"))
    if idx < len(cols):
        w = int(cols[idx].get(qn("w:w")) or 0)
        grid.remove(cols[idx])
        if idx - 1 >= 0 and w:
            cols[idx - 1].set(qn("w:w"), str(int(cols[idx - 1].get(qn("w:w")) or 0) + w))
    for tr in tb._tbl.findall(qn("w:tr")):
        tcs = tr.findall(qn("w:tc"))
        if idx < len(tcs):
            tcw = tcs[idx].find(qn("w:tcPr") + "/" + qn("w:tcW"))
            extra = int(tcw.get(qn("w:w")) or 0) if tcw is not None else 0
            tr.remove(tcs[idx])
            if idx - 1 >= 0 and extra:
                pw = tcs[idx - 1].find(qn("w:tcPr") + "/" + qn("w:tcW"))
                if pw is not None:
                    pw.set(qn("w:w"), str(int(pw.get(qn("w:w")) or 0) + extra))


def _text_paragraphs(text: str) -> list[tuple[str, str]]:
    """Текст раздела -> [('p'|'li', текст)] для заполняемых шаблонов."""
    out = []
    for b in parse(text):
        if b[0] == "p":
            out.append(("p", b[1]))
        elif b[0] == "li":
            out.append(("li", b[3]))
        elif b[0] == "note":
            out.append(("p", b[2]))
        elif b[0] == "h":
            out.append(("p", "**" + b[1] + "**"))
        elif b[0] == "table":
            for r in [b[3]] + b[4]:
                out.append(("p", " | ".join(r)))
        elif b[0] == "code":
            out += [("p", x) for x in b[3].split("\n")]
    return out


def _gost_list(items: list[str]) -> list[str]:
    items = [re.sub(r"[;.,]\s*$", "", x.strip()) for x in items if x.strip()]
    return [x + (";" if i < len(items) - 1 else ".") for i, x in enumerate(items)]


class FillDocx:
    def __init__(self, did: str):
        self.did = did
        self.doc = wdocs.get(did)
        self.t = wdocs.get_template(self.doc["template"])
        self.d = docx.Document(str(wdocs.tpl_dir(self.doc["template"]) / "template.docx"))
        self.f = self.doc["fields"]
        self.body = self.d.element.body
        self.tables = list(self.d.tables)
        self.warnings: list[str] = []
        lp = [p for p in self.d.paragraphs if p.style.name == "List Paragraph" and p._p.pPr is not None
              and p._p.pPr.numPr is not None]
        self.list_proto = lp[0]._p if lp else None
        tp = [p for p in self.d.paragraphs if p.style.name == "Normal" and len(p.text) > 60 and p._p.pPr is not None
              and p._p.pPr.numPr is None]
        self.text_proto = tp[0]._p if tp else None

    def _paras(self):
        return [p for p in self.body if p.tag == qn("w:p")]

    def _find(self, rx: str, start=None):
        pat = re.compile(rx)
        seen = start is None
        for p in self._paras():
            if not seen:
                seen = p is start
                continue
            if pat.search(Paragraph(p, self.d).text.strip()):
                return p
        return None

    def _replace_paras(self, anchor, count: int, new_items: list[tuple[str, str]], to_el=None):
        """Убрать count абзацев от anchor (или до to_el) и вставить новые на их место."""
        olds, el = [], anchor
        while el is not None and (len(olds) < count if to_el is None else True):
            if el.tag == qn("w:p"):
                olds.append(el)
            if to_el is not None and el is to_el:
                break
            el = el.getnext()
        pb = any(_has_page_break(o) for o in olds)
        proto_p = anchor
        anchor_is_list = anchor.find(qn("w:pPr") + "/" + qn("w:numPr")) is not None
        li_proto = anchor if anchor_is_list else self.list_proto
        new_els = []
        for kind, txt in new_items:
            if kind == "li" and li_proto is not None:
                new_els.append(_clone_p(li_proto, txt))
            elif anchor_is_list and self.text_proto is not None:
                new_els.append(_clone_p(self.text_proto, txt))
            else:
                new_els.append(_clone_p(proto_p, txt))
        if pb:
            new_els.append(_page_break_p())
        for e in new_els:
            anchor.addprevious(e)
        for o in olds:
            o.getparent().remove(o)
        return new_els

    # --- разделы
    def sec_table(self, s, sec):
        tg = s.get("target") or {}
        if "table" not in tg:
            return
        tb = self.tables[tg["table"]]
        rows = sec.get("rows") or []
        if s["id"] == "techcard" and self.f.get("drop_example_col", True) and len(tb.columns) > 2:
            _drop_column(tb, 2)
        _fill_table(tb, s, rows, self.f)
        if tg.get("list_paras"):     # список над таблицей рисков — из первого столбца
            anchor = self._find(tg["list_paras"])
            if anchor is not None:
                names = [re.sub(r"\s*\(.*?\)\s*$", "", r[0]).strip() for r in rows if r and str(r[0]).strip()]
                self._replace_paras(anchor, tg.get("list_count", 1), [("li", x) for x in _gost_list(names)])
            else:
                self.warnings.append(f"{s['title']}: не найден список над таблицей")

    def sec_text(self, s, sec):
        tg = s.get("target") or {}
        anchor = self._find(tg.get("paras", "^$"))
        if anchor is None:
            self.warnings.append(f"{s['title']}: в шаблоне не найдено место для текста")
            return
        items = _text_paragraphs(sec.get("text") or "")
        items = [(k, x) for k, x in items]
        lis = [i for i, (k, _) in enumerate(items) if k == "li"]
        if lis:
            fixed = _gost_list([items[i][1] for i in lis])
            for i, v in zip(lis, fixed):
                items[i] = ("li", v)
        if not items:
            items = [("p", "[уточнить: " + s["title"].lower() + "]")]
        self._replace_paras(anchor, tg.get("count", 1), items)

    def sec_list(self, s, sec):
        tg = s.get("target") or {}
        anchor = self._find(tg.get("paras", "^$"))
        if anchor is None:
            self.warnings.append(f"{s['title']}: не найден список в шаблоне")
            return
        items = _gost_list(sec.get("items") or [])
        olds, el = [], anchor
        while el is not None and len(olds) < tg.get("count", 1):
            if el.tag == qn("w:p"):
                olds.append(el)
            el = el.getnext()
        for txt in items:
            anchor.addprevious(_clone_p(anchor, txt))
        for o in olds:
            o.getparent().remove(o)

    def sec_choice(self, s, sec):
        tg = s.get("target") or {}
        p = self._find(re.escape(tg.get("paras", "")))
        if p is None:
            self.warnings.append(f"{s['title']}: не найдена фраза в шаблоне")
            return
        replace_in_p(p, [(tg["placeholder"], sec.get("value") or "")])
        txt = (sec.get("text") or "").strip()
        if txt:
            last = p
            for kind, line in _text_paragraphs(txt):
                np_ = _clone_p(p, line)
                last.addnext(np_)
                last = np_

    def sec_asis(self, s, sec):
        tg = s.get("target") or {}
        steps = sec.get("steps") or []
        tb = self.tables[tg["table"]]
        _fill_table(tb, {"columns": ["Шаг", "Описание действия", "Роль"]},
                    [[str(i), st.get("title", ""), st.get("role", "")] for i, st in enumerate(steps, 1)], self.f)
        a = self._find(tg["from"])
        b = self._find(tg["to"], start=a) if a is not None else None
        if a is None or b is None:
            self.warnings.append(f"{s['title']}: не найдено место пошагового описания")
            return
        # прототипы: заголовок шага и строка действия
        act_proto = b
        olds, el = [], a
        while el is not None:
            if el.tag == qn("w:p"):
                olds.append(el)
            if el is b:
                break
            el = el.getnext()
        pb = any(_has_page_break(o) for o in olds)
        for i, st in enumerate(steps or [{"title": "[уточнить: шаги процесса]", "actions": []}], 1):
            h = _clone_p(a, f"Шаг {i}.\t{st.get('title', '')}")
            a.addprevious(h)
            for k, act in enumerate(st.get("actions") or [], 1):
                a.addprevious(_clone_p(act_proto, f"{k}. {act}"))
        if pb:
            a.addprevious(_page_break_p())
        for o in olds:
            o.getparent().remove(o)

    def sec_figures(self, s, sec):
        tg = s.get("target") or {}
        head = self._find(tg.get("image_after", "^$"))
        if head is None:
            self.warnings.append(f"{s['title']}: не найдено место рисунка")
            return
        el, pic_p = head, None
        while el is not None:
            if el.tag == qn("w:p") and list(el.iter(qn("a:blip"))):
                pic_p = el
                break
            el = el.getnext()
        if tg.get("drop_objects"):
            el = head.getnext()
            while el is not None and not (el.tag == qn("w:p") and Paragraph(el, self.d).style.name == "Буквенные заголовки"):
                nxt = el.getnext()
                if el.tag == qn("w:p") and list(el.iter(qn("w:object"))):
                    el.getparent().remove(el)
                el = nxt
        if pic_p is None:
            self.warnings.append(f"{s['title']}: в шаблоне нет картинки для замены")
            return
        figs = sec.get("figures") or []
        path = wdocs.ddir(self.did) / "figures" / figs[0]["file"] if figs else None
        if not path or not path.exists():
            # пример из шаблона не оставляем — вместо него видная заглушка
            ph = _clone_p(pic_p, f"[Вставить: {s['title'].lower()}]")
            for r in ph.findall(qn("w:r")):
                rpr = r.find(qn("w:rPr"))
                if rpr is None:
                    rpr = OxmlElement("w:rPr")
                    r.insert(0, rpr)
                hl = OxmlElement("w:highlight")
                hl.set(qn("w:val"), "yellow")
                rpr.append(hl)
            pic_p.addprevious(ph)
            pic_p.getparent().remove(pic_p)
            return
        rid, _ = self.d.part.get_or_add_image(str(path))
        from PIL import Image
        with Image.open(path) as im:
            w, h = im.size
        for blip in pic_p.iter(qn("a:blip")):
            blip.set(qn("r:embed"), rid)
        ext = next(pic_p.iter(qn("wp:extent")), None)
        max_cx = Cm(16.5)
        cx = min(int(ext.get("cx")) if ext is not None else max_cx, max_cx)
        cx = max(cx, Cm(12))
        cy = int(cx * h / w)
        if cy > Cm(22):
            cy = Cm(22)
            cx = int(cy * w / h)
        for e in list(pic_p.iter(qn("wp:extent"))) + list(pic_p.iter(qn("a:ext"))):
            if e.get("cx") is not None:
                e.set("cx", str(int(cx)))
                e.set("cy", str(int(cy)))

    def _highlights(self):
        """Жёлтым остаются только незаполненные [заглушки] и [уточнить: …]; остальное — без подсветки."""
        roots = [self.body] + [s.header._element for s in self.d.sections]
        for root in roots:
            for p in root.iter(qn("w:p")):
                full = "".join(t.text or "" for t in _p_texts(p))
                open_ph = re.search(r"\[[^\]]{2,}\]", full)
                for r in p.findall(qn("w:r")):
                    txt = "".join(t.text or "" for t in r.findall(qn("w:t")))
                    if not txt:
                        continue
                    if "уточнить" in txt or (open_ph and ("[" in txt or "]" in txt)):
                        rpr = r.find(qn("w:rPr"))
                        if rpr is None:
                            rpr = OxmlElement("w:rPr")
                            r.insert(0, rpr)
                        if rpr.find(qn("w:highlight")) is None:
                            hl = OxmlElement("w:highlight")
                            hl.set(qn("w:val"), "yellow")
                            rpr.append(hl)
                    else:
                        _unhighlight(r)

    def build(self) -> Path:
        for s in self.t["sections"]:
            sec = self.doc["sections"].get(s["id"], {})
            k = s["kind"]
            try:
                if k == "table":
                    self.sec_table(s, sec)
                elif k == "text":
                    self.sec_text(s, sec)
                elif k == "list":
                    self.sec_list(s, sec)
                elif k == "choice":
                    self.sec_choice(s, sec)
                elif k == "asis_steps":
                    self.sec_asis(s, sec)
                elif k == "figures":
                    self.sec_figures(s, sec)
            except Exception as e:  # noqa — один раздел не валит всю сборку
                self.warnings.append(f"{s['title']}: {e}")
        mapping = sorted(((k, wdocs.fmt(v, self.f, strip=False)) for k, v in (self.t.get("replace") or {}).items()),
                         key=lambda kv: -len(kv[0]))
        mapping = [(k, v) for k, v in mapping if v != "" or k.startswith("[АКТУАЛ")]
        parts = [self.body] + [s.header._element for s in self.d.sections] + [s.footer._element for s in self.d.sections]
        for root in parts:
            for p in list(root.iter(qn("w:p"))):
                replace_in_p(p, mapping)
        # версия в карточке и истории
        ver = str(self.f.get("version") or "").strip()
        if ver and ver != "1.0":
            for tb in self.tables[1:3]:
                for row in tb.rows:
                    for c in row.cells:
                        for p in c.paragraphs:
                            if p.text.strip() == "1.0":
                                replace_in_p(p._p, [("1.0", ver)])
        self._highlights()
        _update_fields_on_open(self.d)
        from reportgen.render import save_docx
        return save_docx(self.d, out_path(self.did, self.doc, "docx"))


def _update_fields_on_open(d):
    """Word обновит номера таблиц/рисунков в ссылках при открытии (поля REF в исходном шаблоне)."""
    st = d.settings.element
    if st.find(qn("w:updateFields")) is None:
        e = OxmlElement("w:updateFields")
        e.set(qn("w:val"), "true")
        st.append(e)


# ================================================================== выход

def out_path(did: str, doc: dict, ext: str, suffix: str = "") -> Path:
    from .files import safe_name
    t = wdocs.get_template(doc["template"])
    base = wdocs.fmt(t.get("file_name") or doc.get("title") or "документ", doc.get("fields") or {})
    base = re.sub(r"\s+", " ", base).strip() or "документ"
    d = wdocs.ddir(did) / "out"
    d.mkdir(exist_ok=True)
    return d / f"{safe_name(base + suffix)}.{ext}"


def docx_text(path: Path) -> str:
    d = docx.Document(str(path))
    out = []
    from docx.table import Table
    for el in d.element.body:
        if el.tag == qn("w:p"):
            t = Paragraph(el, d).text.strip()
            if t:
                out.append(t)
        elif el.tag == qn("w:tbl"):
            tb = Table(el, d)
            for r in tb.rows:
                cells = []
                for c in r.cells:
                    v = c.text.strip().replace("\n", " / ")
                    if not cells or cells[-1] != v:
                        cells.append(v)
                out.append(" | ".join(cells))
            out.append("")
    return "\n".join(out)


def build(did: str, fmt: str = "docx", emit=lambda s: None) -> dict:
    """fmt: docx | pdf | txt | confluence. Возвращает {path, warnings}."""
    from . import export
    doc = wdocs.get(did)
    t = wdocs.get_template(doc["template"])
    if fmt == "confluence":
        if t["kind"] != "build":
            raise ValueError("Разметка Confluence есть только у описания робота")
        p = confluence_zip(did)
        return {"path": p, "warnings": []}
    b = BuildDocx(did) if t["kind"] == "build" else FillDocx(did)
    path = b.build()
    emit(f"Word: {path.name}")
    warnings = list(b.warnings)
    if fmt == "pdf":
        pdf = path.with_suffix(".pdf")
        try:
            export.docx_to_pdf(path, pdf)
        except Exception as e:  # нет ни Word, ни LibreOffice — простой PDF из текста
            export.text_to_pdf_builtin(doc.get("title", ""), docx_text(path), pdf)
            warnings.append(f"PDF сделан упрощённо (нет Word/LibreOffice: {e})")
        path = pdf
        emit(f"PDF: {pdf.name}")
    elif fmt == "txt":
        txt = path.with_suffix(".txt")
        txt.write_text(docx_text(path), encoding="utf-8-sig")
        path = txt
    raw = wdocs._read(did)
    raw["last_build"] = time.strftime("%Y-%m-%d %H:%M")
    wdocs._write(did, raw)
    return {"path": path, "warnings": warnings}


def file_to_storage(did: str, path: Path) -> str | None:
    """Копия сборки в Хранилище/Работа/<папка шаблона> (перезаписывает прошлую)."""
    from . import files
    doc = wdocs.get(did)
    t = wdocs.get_template(doc["template"])
    folder = t.get("storage_folder") or "Работа"
    dest_dir = files.resolve(folder)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / path.name
    dest.write_bytes(path.read_bytes())
    return files.rel_of(dest)
