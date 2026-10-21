"""Gera o guia de utilização (Word + PDF) a partir de docs/guia_utilizacao.md.

    python tools/build_guide.py            -> ui/Guia_FlightTracker.pdf + dist/Guia_FlightTracker_<versão>.docx

Formato: o de docs/guia_modelo.docx (capa com logótipo NAV/GOPLIS, Calibri, índice em página própria).
Precisa de: pandoc, python-docx, pypdf e LibreOffice (soffice) para o PDF.
Passos: pandoc (markdown -> docx com os estilos do modelo) -> python-docx (capa, índice, quebras de página)
-> LibreOffice (docx -> pdf) -> lê as páginas dos títulos no PDF e escreve o índice com números de página
-> LibreOffice outra vez.
"""
from __future__ import annotations

import copy
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from docx import Document
from docx.enum.text import WD_BREAK, WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "docs" / "guia_utilizacao.md"
MODEL = ROOT / "docs" / "guia_modelo.docx"
LOGO = ROOT / "docs" / "nav_goplis_logo.png"
OUT_PDF = ROOT / "ui" / "Guia_FlightTracker.pdf"
VERSION = re.search(r'^VERSION\s*=\s*"([^"]+)"', (ROOT / "app.py").read_text(encoding="utf-8"), re.M).group(1)
OUT_DOCX = ROOT / "dist" / f"Guia_FlightTracker_{VERSION}.docx"
BREAK_BEFORE = ("Índice", "1. ", "19. ")   # títulos de nível 1 que começam em página nova


def pandoc(md: Path, out: Path):
    text = md.read_text(encoding="utf-8").split("\n")
    title = text[0][2:].strip()
    body = "\n".join(text[1:])
    meta = f'---\ntitle: "{title}"\nsubtitle: "Versão {VERSION}"\nlang: pt-PT\n---\n'
    tmp = out.with_suffix(".md")
    tmp.write_text(meta + body, encoding="utf-8")
    subprocess.run(["pandoc", str(tmp), "--shift-heading-level-by=-1", f"--reference-doc={MODEL}", "-o", str(out)], check=True)
    tmp.unlink()


def page_break_before(p):
    br = p.insert_paragraph_before("")
    br.add_run().add_break(WD_BREAK.PAGE)


def add_cover(d):
    """Logótipo NAV + 'GOPLIS' antes do título, como no modelo."""
    title = next(p for p in d.paragraphs if p.style.name == "Title")
    cover = title.insert_paragraph_before("")
    cover.style = title.style
    run = cover.add_run()
    run.add_picture(str(LOGO), width=Cm(4.2))
    cover.add_run(" GOPLIS")


def add_toc(d, entries: list[tuple[int, str, int]] | None):
    """Índice: cabeçalho + (campo TOC para o Word) com o texto já preenchido com as páginas."""
    first = next(p for p in d.paragraphs if p.style.name == "Heading 1")
    h = first.insert_paragraph_before("Índice"); h.style = first.style
    page_break_before(h)
    styles = {1: d.styles["toc 1"], 2: d.styles["toc 2"]} if "toc 1" in [s.name for s in d.styles] else {1: d.styles["Normal"], 2: d.styles["Normal"]}
    right = d.sections[0].page_width - d.sections[0].left_margin - d.sections[0].right_margin
    for lvl, txt, page in (entries or [(1, "(índice: no Word, botão direito → Atualizar campo)", 0)]):
        p = first.insert_paragraph_before("")
        p.style = styles[lvl]
        p.paragraph_format.tab_stops.add_tab_stop(right, WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
        if lvl == 2: p.paragraph_format.left_indent = Cm(0.5)
        p.add_run(txt + ("\t" + str(page) if page else ""))


def style_tables(d):
    """Cabeçalho azul, grelha, 9 pt, linhas indivisíveis e tabela mantida junta (como no modelo)."""
    from docx.shared import RGBColor
    for t in d.tables:
        tblPr = t._tbl.tblPr
        b = OxmlElement("w:tblBorders")
        for e in ("top", "left", "bottom", "right", "insideH", "insideV"):
            el = OxmlElement(f"w:{e}"); el.set(qn("w:val"), "single"); el.set(qn("w:sz"), "4"); el.set(qn("w:color"), "999999"); b.append(el)
        tblPr.append(b)
        big = len(t.rows) > 25          # o glossário pode dividir-se; as pequenas ficam numa página
        for i, row in enumerate(t.rows):
            trPr = row._tr.get_or_add_trPr()
            cs = OxmlElement("w:cantSplit"); trPr.append(cs)
            if i == 0:
                th = OxmlElement("w:tblHeader"); trPr.append(th)
            for c in row.cells:
                if i == 0:
                    sh = OxmlElement("w:shd"); sh.set(qn("w:val"), "clear"); sh.set(qn("w:fill"), "1D4ED8"); c._tc.get_or_add_tcPr().append(sh)
                for para in c.paragraphs:
                    if not big and i < len(t.rows) - 1: para.paragraph_format.keep_with_next = True
                    for r in para.runs:
                        r.font.size = Pt(9)
                        if i == 0: r.bold = True; r.font.color.rgb = RGBColor(255, 255, 255)


def mark_breaks(d):
    for p in d.paragraphs:
        if p.style.name == "Heading 1" and p.text.startswith(BREAK_BEFORE[1:]):
            page_break_before(p)


def to_pdf(docx: Path, outdir: Path) -> Path:
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(outdir), str(docx)],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return outdir / (docx.stem + ".pdf")


def outline(pdf: Path) -> list[tuple[int, str, int]]:
    r = PdfReader(str(pdf)); out = []
    def walk(items, lvl):
        for x in items:
            if isinstance(x, list): walk(x, lvl + 1)
            else:
                if lvl <= 2 and x.title != "Índice": out.append((lvl, x.title, r.get_destination_page_number(x) + 1))
    walk(r.outline, 1)
    return out


def build():
    OUT_DOCX.parent.mkdir(exist_ok=True)
    tmpdir = Path(tempfile.mkdtemp())
    base = tmpdir / "guia.docx"
    pandoc(SRC, base)
    entries = None
    for _ in range(3):   # até as páginas do índice estabilizarem
        d = Document(str(base))
        add_cover(d); add_toc(d, entries); mark_breaks(d); style_tables(d)
        d.save(str(OUT_DOCX))
        pdf = to_pdf(OUT_DOCX, tmpdir)
        new = outline(pdf)
        if new == entries: break
        entries = new
    shutil.copyfile(pdf, OUT_PDF)
    print("OK", OUT_PDF, OUT_PDF.stat().st_size // 1024, "KB;", OUT_DOCX, "; páginas:", len(PdfReader(str(pdf)).pages))


if __name__ == "__main__":
    sys.exit(build())
