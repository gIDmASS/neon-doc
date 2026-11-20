"""Картинки страниц для галереи шаблонов: .docx -> PDF -> PNG.

На Windows PDF делает сам Word (docx2pdf, через COM) — так превью совпадает с тем, что увидит
преподаватель. Если Word недоступен, пробуем LibreOffice (soffice в PATH).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def docx_to_pdf(docx: Path, out_dir: Path) -> Path:
    pdf = out_dir / (docx.stem + ".pdf")
    has_word = sys.platform == "win32" or Path("/Applications/Microsoft Word.app").exists()
    if has_word:
        if sys.platform == "win32":
            try:
                import pythoncom  # noqa — нужен для COM в потоке
                pythoncom.CoInitialize()
            except Exception:
                pass
        try:
            from docx2pdf import convert
            convert(str(docx), str(pdf))
            if pdf.exists():
                return pdf
        except Exception as e:
            err = e
        else:
            err = None
    else:
        err = None
    from .osutil import soffice_path
    soffice = soffice_path()
    if soffice:
        subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", str(out_dir), str(docx)],
                       check=True, capture_output=True, timeout=180)
        if pdf.exists():
            return pdf
    raise RuntimeError(f"Не удалось сделать PDF (нужен Word или LibreOffice): {err}")


def pages_to_png(pdf: Path, dest: Path, max_pages: int = 8, width_px: int = 620) -> list[Path]:
    import pymupdf
    dest.mkdir(parents=True, exist_ok=True)
    for old in dest.glob("*.png"):
        old.unlink()
    out = []
    with pymupdf.open(str(pdf)) as doc:
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            zoom = width_px / page.rect.width
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
            p = dest / f"{i + 1:02d}.png"
            pix.save(str(p))
            out.append(p)
    return out


def make_previews(docx: Path, dest: Path, max_pages: int = 8) -> list[Path]:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        local = tmp / "src.docx"
        shutil.copy(docx, local)
        pdf = docx_to_pdf(local, tmp)
        return pages_to_png(pdf, dest, max_pages)
