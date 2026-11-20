"""Выгрузка в Word / PDF / TXT.

* текст (ответ Qwen, расшифровка, конспект) -> .docx по ГОСТ-подобным правилам (Times New Roman 14,
  интервал 1,5, абзацный отступ 1,25 см, поля 30/15/20/20 мм), -> .pdf (через Word, иначе LibreOffice,
  иначе встроенный PyMuPDF), -> .txt;
* готовый .docx -> .pdf / .txt.
"""
from __future__ import annotations

import html
import re
import shutil
import sys
import tempfile
from pathlib import Path

FONT = "Times New Roman"


# ------------------------------------------------------------------ markdown -> блоки

def parse_md(text: str) -> list[tuple]:
    """Очень простой разбор: заголовки, списки, таблицы, абзацы, код."""
    lines = text.replace("\r\n", "\n").split("\n")
    out, i = [], 0
    while i < len(lines):
        ln = lines[i]
        s = ln.strip()
        if not s:
            i += 1
            continue
        if s.startswith("```"):
            buf = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            out.append(("code", "\n".join(buf)))
            i += 1
            continue
        m = re.match(r"^(#{1,4})\s+(.+)$", s)
        if m:
            out.append(("h", len(m.group(1)), m.group(2).strip()))
            i += 1
            continue
        if s.startswith("|") and i + 1 < len(lines) and re.match(r"^\|?\s*:?-{2,}", lines[i + 1].strip()):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                    rows.append(cells)
                i += 1
            if rows:
                out.append(("table", rows))
            continue
        if re.match(r"^([-*•]|\d+[.)])\s+", s):
            items, ordered = [], bool(re.match(r"^\d", s))
            while i < len(lines) and re.match(r"^\s*([-*•]|\d+[.)])\s+", lines[i]):
                items.append(re.sub(r"^\s*([-*•]|\d+[.)])\s+", "", lines[i]).strip())
                i += 1
            out.append(("list", ordered, items))
            continue
        buf = [s]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#{1,4}\s|[-*•]\s|\d+[.)]\s|\||```)", lines[i].strip()):
            buf.append(lines[i].strip())
            i += 1
        out.append(("p", " ".join(buf)))
    return out


def _runs(par, text: str):
    """**полужирный** и `код` внутри абзаца."""
    from docx.shared import Pt
    for part in re.split(r"(\*\*[^*]+\*\*|`[^`]+`)", text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            r = par.add_run(part[2:-2])
            r.bold = True
        elif part.startswith("`") and part.endswith("`"):
            r = par.add_run(part[1:-1])
            r.font.name = "Consolas"
            r.font.size = Pt(12)
        else:
            par.add_run(part)


def text_to_docx(title: str, text: str, out: Path, subtitle: str = "") -> Path:
    import docx
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt

    d = docx.Document()
    sec = d.sections[0]
    sec.left_margin, sec.right_margin, sec.top_margin, sec.bottom_margin = Cm(3), Cm(1.5), Cm(2), Cm(2)
    st = d.styles["Normal"]
    st.font.name, st.font.size = FONT, Pt(14)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    pf = st.paragraph_format
    pf.line_spacing, pf.space_after, pf.space_before = 1.5, Pt(0), Pt(0)
    for name in ("Heading 1", "Heading 2", "Heading 3"):
        hs = d.styles[name]
        hs.font.name, hs.font.color.rgb = FONT, None
        rf = hs.element.rPr.rFonts
        for a in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
            rf.attrib.pop(qn(a), None)
        rf.set(qn("w:eastAsia"), FONT)
        hs.font.size = Pt(14)
        hs.font.bold = True
        hs.paragraph_format.space_before, hs.paragraph_format.space_after = Pt(12), Pt(6)

    if title:
        p = d.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(6)
        r = p.add_run(title)
        r.bold, r.font.size = True, Pt(16)
    if subtitle:
        p = d.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(subtitle)
        r.italic = True
        r.font.size = Pt(12)

    for b in parse_md(text):
        if b[0] == "h":
            d.add_heading(b[2], level=min(b[1], 3))
        elif b[0] == "p":
            p = d.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            p.paragraph_format.first_line_indent = Cm(1.25)
            _runs(p, b[1])
        elif b[0] == "list":
            for k, it in enumerate(b[2], 1):
                p = d.add_paragraph()
                p.paragraph_format.first_line_indent = Cm(1.25)
                end = "" if it.endswith((".", ";", ":", "!", "?")) else (";" if k < len(b[2]) else ".")
                _runs(p, (f"{k}) " if b[1] else "– ") + it + end)
        elif b[0] == "code":
            for ln in b[1].split("\n"):
                p = d.add_paragraph()
                r = p.add_run(ln)
                r.font.name, r.font.size = "Consolas", Pt(11)
                p.paragraph_format.line_spacing = 1.0
        elif b[0] == "table":
            rows = b[1]
            ncol = max(len(r) for r in rows)
            t = d.add_table(rows=len(rows), cols=ncol)
            t.style = "Table Grid"
            for ri, row in enumerate(rows):
                for ci in range(ncol):
                    cell = t.cell(ri, ci)
                    cell.text = ""
                    par = cell.paragraphs[0]
                    par.paragraph_format.line_spacing = 1.0
                    _runs(par, row[ci] if ci < len(row) else "")
                    for r in par.runs:
                        r.font.size = Pt(12)
                        if ri == 0:
                            r.bold = True
            d.add_paragraph()
    out.parent.mkdir(parents=True, exist_ok=True)
    d.save(str(out))
    return out


# ------------------------------------------------------------------ PDF

def _win_font() -> str | None:
    for f in (r"C:\Windows\Fonts\times.ttf", r"C:\Windows\Fonts\arial.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if Path(f).exists():
            return f
    return None


def md_to_html(text: str) -> str:
    def inl(s):
        s = html.escape(s)
        s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
        return re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    parts = []
    for b in parse_md(text):
        if b[0] == "h":
            parts.append(f"<h{min(b[1] + 1, 4)}>{inl(b[2])}</h{min(b[1] + 1, 4)}>")
        elif b[0] == "p":
            parts.append(f"<p>{inl(b[1])}</p>")
        elif b[0] == "list":
            tag = "ol" if b[1] else "ul"
            parts.append(f"<{tag}>" + "".join(f"<li>{inl(x)}</li>" for x in b[2]) + f"</{tag}>")
        elif b[0] == "code":
            parts.append(f"<pre>{html.escape(b[1])}</pre>")
        elif b[0] == "table":
            rows = b[1]
            parts.append("<table>" + "".join("<tr>" + "".join(
                f"<{'th' if i == 0 else 'td'}>{inl(c)}</{'th' if i == 0 else 'td'}>" for c in r) + "</tr>"
                for i, r in enumerate(rows)) + "</table>")
    return "\n".join(parts)


def text_to_pdf_builtin(title: str, text: str, out: Path, subtitle: str = "") -> Path:
    """Запасной путь без Word: PyMuPDF Story (HTML -> PDF) со шрифтом с кириллицей."""
    import pymupdf
    font = _win_font()
    css = ("* {font-family: body;} body {font-size: 12pt; line-height: 1.45;} h1 {font-size: 16pt; text-align:center;}"
           " h2,h3,h4 {font-size: 13pt;} p {text-align: justify; text-indent: 1.25cm; margin: 0 0 4pt 0;}"
           " table {border-collapse: collapse; width: 100%;} td, th {border: 0.5pt solid #000; padding: 3pt; font-size: 10.5pt;}"
           " pre, code {font-size: 9.5pt;} .sub {text-align:center; font-style: italic; font-size: 10pt;}")
    if font:
        css = f"@font-face {{font-family: body; src: url({Path(font).name});}} " + css
    body = (f"<h1>{html.escape(title)}</h1>" if title else "") + \
           (f"<p class='sub'>{html.escape(subtitle)}</p>" if subtitle else "") + md_to_html(text)
    archive = pymupdf.Archive(str(Path(font).parent)) if font else None
    story = pymupdf.Story(html=body, user_css=css, archive=archive)
    w = pymupdf.DocumentWriter(str(out))
    page = pymupdf.paper_rect("a4")
    where = page + (85, 57, -43, -57)   # поля 30/20/15/20 мм
    more = True
    while more:
        dev = w.begin_page(page)
        more, _ = story.place(where)
        story.draw(dev)
        w.end_page()
    w.close()
    return out


def docx_to_pdf(src: Path, out: Path) -> Path:
    from .previews import docx_to_pdf as _conv
    with tempfile.TemporaryDirectory() as tmp:
        local = Path(tmp) / "doc.docx"
        shutil.copy(src, local)
        pdf = _conv(local, Path(tmp))
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(pdf, out)
    return out


def text_to_pdf(title: str, text: str, out: Path, subtitle: str = "") -> Path:
    """Сначала через Word (так же, как будет печататься), иначе встроенный способ."""
    with tempfile.TemporaryDirectory() as tmp:
        dx = text_to_docx(title, text, Path(tmp) / "t.docx", subtitle)
        try:
            return docx_to_pdf(dx, out)
        except Exception:
            return text_to_pdf_builtin(title, text, out, subtitle)


def text_to_txt(title: str, text: str, out: Path, subtitle: str = "") -> Path:
    head = (title + "\n" + "=" * min(len(title), 80) + "\n" if title else "") + (subtitle + "\n" if subtitle else "")
    out.write_text((head + "\n" if head else "") + text.strip() + "\n", encoding="utf-8-sig")
    return out


def export_text(title: str, text: str, fmt: str, out_dir: Path, base: str, subtitle: str = "") -> Path:
    from .files import safe_name, unique
    out_dir.mkdir(parents=True, exist_ok=True)
    out = unique(out_dir / f"{safe_name(base)}.{fmt}")
    fn = {"docx": text_to_docx, "pdf": text_to_pdf, "txt": text_to_txt}[fmt]
    return fn(title, text, out, subtitle)


def convert_file(src: Path, fmt: str, out_dir: Path) -> Path:
    """Готовый файл -> другой формат (docx->pdf/txt, pdf->txt, txt/md->docx/pdf)."""
    from .extract import file_text
    from .files import unique
    ext = src.suffix.lower()
    out = unique(out_dir / f"{src.stem}.{fmt}")
    if ext == ".docx" and fmt == "pdf":
        return docx_to_pdf(src, out)
    if fmt == "txt":
        out.write_text(file_text(src) or "", encoding="utf-8-sig")
        return out
    txt = file_text(src) or ""
    return {"docx": text_to_docx, "pdf": text_to_pdf}[fmt](src.stem, txt, out)
