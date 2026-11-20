"""Рендер: report.json -> .docx по шаблону МИСИС. Никакого ИИ, результат детерминирован.

    python -m reportgen.render tasks\\tipup_lr6\\report.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import docx
from docx.oxml.ns import qn
from docx.shared import Cm

from .make_template import TEMPLATE_PATH
from .ooxml import _el, add_runs, add_seq_field, add_toc_field, ppr, set_paragraph_text
from .schema import BulletList, Figure, Paragraph, Report, Section, Table

H1, H2 = "1", "20"          # styleId «heading 1/2» в эталоне
TABLE_STYLE = "af8"         # «Table Grid» в эталоне
TEXT_WIDTH_TWIPS = 9355     # 21 см − 3 − 1,5 см
MAX_FIG_WIDTH = Cm(16.5)
REF_RE = re.compile(r"(?:(таблиц\w*|рисун\w*|схем\w*)\s+)?\[\[(table|figure):([\w\-]+)\]\]",
                    re.I)


class Renderer:
    def __init__(self, report: Report, base_dir: Path):
        self.r = report
        self.base = base_dir
        self.doc = docx.Document(str(TEMPLATE_PATH))
        # автор документа — студент с титула (в самом шаблоне автор пустой)
        self.doc.core_properties.author = report.meta.student
        self.doc.core_properties.last_modified_by = report.meta.student
        self.body = self.doc.element.body
        self.sect = self.body.find(qn("w:sectPr"))
        self.numbers: dict[tuple[str, str], int] = {}
        self.missing_figures: list[str] = []
        self._number_objects()

    # ---------------------------------------------------- нумерация заранее
    def _number_objects(self):
        cnt = {"table": 0, "figure": 0}
        for sec in self.r.sections:
            for b in _all_blocks(sec):
                if isinstance(b, (Table, Figure)):
                    cnt[b.type] += 1
                    self.numbers[(b.type, b.id)] = cnt[b.type]

    def _resolve_refs(self, text: str) -> str:
        def sub(m):
            before, kind, ident = m.groups()
            n = self.numbers.get((kind, ident)) or "??"
            if before:   # слово уже есть в тексте: «в таблице 1», «на рисунке 2»
                return f"{before} {n}"
            word = "Таблица" if kind == "table" else "Рисунок"
            return f"{word} {n}"
        return REF_RE.sub(sub, text)

    # ---------------------------------------------------- базовые операции
    def _p(self):
        p = _el("w:p")
        self.sect.addprevious(p)
        return p

    def heading(self, text, level=1, numbered=True, page_break=False, center=False):
        p = self._p()
        ppr(p, style=H1 if level == 1 else H2, keep_next=True, page_break=page_break,
            no_number=not numbered, jc="center" if center else None,
            spacing={"before": 0 if page_break else 480, "after": 480} if level == 1 else None)
        add_runs(p, text)

    def para(self, text, *, indent=True, jc=None, keep_next=False):
        p = self._p()
        ppr(p, keep_next=keep_next, jc=jc or "both", ind=None if indent else {"firstLine": 0})
        add_runs(p, self._resolve_refs(text))
        return p

    # ---------------------------------------------------- блоки
    def block(self, b):
        after_table = getattr(self, "_last_was_table", False)
        self._last_was_table = isinstance(b, Table)
        if isinstance(b, Paragraph):
            p = self.para(b.text)
            if after_table:
                ppr(p, spacing={"before": 240})
        elif isinstance(b, BulletList):
            for i, item in enumerate(b.items, 1):
                mark = f"{i})" if b.ordered else "–"
                end = "." if i == len(b.items) else ";"
                text = item.rstrip(".;")
                self.para(f"{mark} {text}{end}")
        elif isinstance(b, Table):
            self.table(b)
        elif isinstance(b, Figure):
            self.figure(b)

    def table(self, t: Table):
        cap = self._p()
        ppr(cap, keep_next=True, ind={"firstLine": 0}, jc="left")
        add_runs(cap, "Таблица ")
        add_seq_field(cap, "Таблица", self.numbers[("table", t.id)])
        add_runs(cap, f" – {t.caption.rstrip('.')}")

        ncol = len(t.columns)
        widths = _col_widths(t)
        tbl = _el("w:tbl")
        tp = _el("w:tblPr")
        tp.append(_el("w:tblStyle", **{"w:val": TABLE_STYLE}))
        tp.append(_el("w:tblW", **{"w:w": 5000, "w:type": "pct"}))
        tp.append(_el("w:jc", **{"w:val": "center"}))
        borders = _el("w:tblBorders")
        for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
            borders.append(_el(f"w:{side}", **{"w:val": "single", "w:sz": 4, "w:space": 0,
                                               "w:color": "000000"}))
        tp.append(borders)
        tp.append(_el("w:tblLayout", **{"w:type": "fixed"}))
        tbl.append(tp)
        grid = _el("w:tblGrid")
        for w in widths:
            grid.append(_el("w:gridCol", **{"w:w": w}))
        tbl.append(grid)
        all_rows = [t.columns] + [(r + [""] * ncol)[:ncol] for r in t.rows]
        for ri, row in enumerate(all_rows):
            tr = _el("w:tr")
            trp = _el("w:trPr")
            trp.append(_el("w:cantSplit"))
            if ri == 0:
                trp.append(_el("w:tblHeader"))   # шапка повторяется на новой странице
            tr.append(trp)
            for ci, val in enumerate(row):
                tc = _el("w:tc")
                tcp = _el("w:tcPr")
                tcp.append(_el("w:tcW", **{"w:w": widths[ci], "w:type": "dxa"}))
                tc.append(tcp)
                p = _el("w:p")
                ppr(p, keep_next=ri < 2,  # подпись+шапка+первая строка не разрываются
                    spacing={"line": 240, "lineRule": "auto"}, ind={"firstLine": 0},
                    jc="center" if ri == 0 else "left")
                add_runs(p, self._resolve_refs(str(val)), bold=ri == 0, size_pt=10)
                tc.append(p)
                tr.append(tc)
            tbl.append(tr)
        self.sect.addprevious(tbl)

    def figure(self, f: Figure):
        img = None
        for ext in (".png", ".jpg", ".jpeg"):
            cand = self.base / "figures" / f"{f.id}{ext}"
            if cand.exists():
                img = cand
                break
        holder = self._p()
        ppr(holder, keep_next=True, ind={"firstLine": 0}, jc="center",
            spacing={"before": 240, "line": 240, "lineRule": "auto"})
        if img:
            # python-docx умеет вставлять картинку только через свой Paragraph
            from docx.text.paragraph import Paragraph as DocxPar
            run = DocxPar(holder, self.doc._body).add_run()
            pic = run.add_picture(str(img))
            if pic.width > MAX_FIG_WIDTH:
                ratio = MAX_FIG_WIDTH / pic.width
                pic.width, pic.height = int(pic.width * ratio), int(pic.height * ratio)
        else:
            self.missing_figures.append(f.id)
            add_runs(holder, f"[ВСТАВИТЬ РИСУНОК: figures/{f.id}.png]", bold=True)
        cap = self._p()
        ppr(cap, ind={"firstLine": 0}, jc="center", spacing={"after": 240})
        add_runs(cap, "Рисунок ")
        add_seq_field(cap, "Рисунок", self.numbers[("figure", f.id)])
        add_runs(cap, f" – {f.caption.rstrip('.')}")

    # ---------------------------------------------------- документ
    def fill_title(self):
        m = self.r.meta
        values = {
            "work_title": m.work_title, "discipline": m.discipline, "module": m.module or "",
            "topic": m.topic, "direction": m.direction, "semester": f"Семестр {m.semester}",
            "city": m.city, "year": str(m.year), "student": m.student, "teacher": m.teacher,
            "group": m.group, "date": m.date,
        }
        for p in list(self.body.iter(qn("w:p"))):
            txt = "".join(t.text or "" for t in p.iter(qn("w:t")))
            if "{{" not in txt:
                continue
            if "{{module}}" in txt and not m.module:
                p.getparent().remove(p)
                continue
            new = re.sub(r"\{\{(\w+)\}\}", lambda mm: values[mm.group(1)], txt)
            # перенос строки «направление / семестр» сохраняем
            new = new.replace(f"{m.direction}Семестр", f"{m.direction}\nСеместр")
            set_paragraph_text(p, new)

    def build(self) -> docx.Document:
        m, r = self.r.meta, self.r
        self.fill_title()
        if m.toc:
            p = self._p()
            ppr(p, page_break=True, ind={"firstLine": 0}, jc="center", spacing={"after": 480})
            add_runs(p, "СОДЕРЖАНИЕ", bold=True)
            entries = []
            if m.intro and r.intro:
                entries.append((1, "ВВЕДЕНИЕ"))
            for si, sec in enumerate(r.sections, 1):
                entries.append((1, f"{si} {sec.title}"))
                entries += [(2, f"{si}.{ui} {sub.title}") for ui, sub in enumerate(sec.subsections, 1)]
            if m.conclusion and r.conclusion:
                entries.append((1, m.conclusion))
            if r.sources:
                entries.append((1, "СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ"))
            add_toc_field([self._p() for _ in entries or [0]], entries)
            st = self.doc.settings.element
            if st.find(qn("w:updateFields")) is None:
                st.append(_el("w:updateFields", **{"w:val": "true"}))

        first = True
        if m.intro and r.intro:
            self.heading("ВВЕДЕНИЕ", numbered=False, page_break=True, center=True)
            for t in r.intro:
                self.para(t)
            first = False

        for si, sec in enumerate(r.sections):
            self.heading(sec.title, page_break=m.h1_new_page or first)
            if si == 0 and not m.intro:
                goal = r.goal.rstrip(".")
                goal = goal[:1].lower() + goal[1:]
                self.para(f"Цель работы: {goal}.")
            for b in sec.blocks:
                self.block(b)
            for sub in sec.subsections:
                self.heading(sub.title, level=2)
                for b in sub.blocks:
                    self.block(b)
            first = False

        if m.conclusion and r.conclusion:
            self.heading(m.conclusion, numbered=False, page_break=True, center=True)
            for t in r.conclusion:
                self.para(t)
        if r.sources:
            self.heading("СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ", numbered=False,
                         page_break=True, center=True)
            for i, s in enumerate(r.sources, 1):
                self.para(f"{i}. {s}")
        return self.doc


def _all_blocks(sec: Section):
    yield from sec.blocks
    for sub in sec.subsections:
        yield from sub.blocks


def _col_widths(t: Table) -> list[int]:
    """Ширины столбцов: пропорционально средней длине текста, но не уже самого длинного слова
    (иначе Word рвёт слово: «Админ|истрато|р»)."""
    n = len(t.columns)
    twips_per_char = 115          # Times New Roman 10 пт, с запасом
    pad = 230                     # поля ячейки
    need, weight = [], []
    for ci in range(n):
        cells = [t.columns[ci]] + [r[ci] if ci < len(r) else "" for r in t.rows]
        longest_word = max((len(w) for c in cells for w in str(c).split()), default=4)
        need.append(longest_word * twips_per_char + pad)
        weight.append(max(sum(min(len(c), 120) for c in cells) / len(cells), 6))
    free = TEXT_WIDTH_TWIPS - sum(need)
    if free <= 0:                 # слов слишком много — делим по минимумам
        w = [int(TEXT_WIDTH_TWIPS * x / sum(need)) for x in need]
    else:                         # минимум каждому + остаток по весу текста
        extra = [max(x - nd / twips_per_char, 0) for x, nd in zip(weight, need)]
        tot = sum(extra) or 1
        w = [int(nd + free * e / tot) for nd, e in zip(need, extra)]
    w[-1] += TEXT_WIDTH_TWIPS - sum(w)
    return w


def render(report_path: Path, out_dir: Path | None = None) -> tuple[Path, list[str]]:
    report = Report.model_validate_json(report_path.read_text(encoding="utf-8"))
    rnd = Renderer(report, report_path.parent)
    doc = rnd.build()
    out_dir = out_dir or report_path.parent
    out = save_docx(doc, out_dir / report.meta.file_name)
    return out, rnd.missing_figures


def save_docx(doc, out: Path) -> Path:
    """Сохранить .docx; если старый файл открыт в Word (Windows его блокирует) —
    сохранить рядом как «имя (2).docx», «имя (3).docx»…"""
    try:
        doc.save(str(out))
        return out
    except PermissionError:
        for i in range(2, 100):
            alt = out.with_name(f"{out.stem} ({i}){out.suffix}")
            try:
                doc.save(str(alt))
                print(f"Файл {out.name} открыт в другой программе — сохранено как {alt.name}")
                return alt
            except PermissionError:
                continue
        raise PermissionError(f"Файл {out.name} открыт в другой программе — закрой его в Word и собери ещё раз")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    path, missing = render(Path(sys.argv[1]))
    print("Готово:", path)
    if missing:
        print("Нет файлов рисунков:", ", ".join(f"figures/{m}.png" for m in missing))
