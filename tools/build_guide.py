"""Gera ui/Guia_FlightTracker.pdf a partir de docs/guia_utilizacao.md (reportlab).

    python tools/build_guide.py

Subconjunto de Markdown suportado: # ## ### títulos, parágrafos, listas "- " e "1. ",
tabelas "| a | b |", **negrito** e `código`.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (KeepTogether, ListFlowable, ListItem, PageBreak, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)
from reportlab.platypus.tableofcontents import TableOfContents

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "docs" / "guia_utilizacao.md"
OUT = ROOT / "ui" / "Guia_FlightTracker.pdf"
VERSION = re.search(r'^VERSION\s*=\s*"([^"]+)"', (ROOT / "app.py").read_text(encoding="utf-8"), re.M).group(1)

BLUE = colors.HexColor("#1d4ed8")
GREY = colors.HexColor("#475569")

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
_FD = Path("/usr/share/fonts/truetype/dejavu")
FONT, FONTB = "Helvetica", "Helvetica-Bold"
if (_FD / "DejaVuSans.ttf").exists():
    pdfmetrics.registerFont(TTFont("DejaVu", str(_FD / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(_FD / "DejaVuSans-Bold.ttf")))
    from reportlab.pdfbase.pdfmetrics import registerFontFamily
    registerFontFamily("DejaVu", normal="DejaVu", bold="DejaVu-Bold", italic="DejaVu", boldItalic="DejaVu-Bold")
    FONT, FONTB = "DejaVu", "DejaVu-Bold"
# pictogramas (emoji) que nenhuma fonte PDF tem: retirados do texto
EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u24D8]")

ss = getSampleStyleSheet()
S = {
    "title": ParagraphStyle("t", parent=ss["Title"], fontSize=26, leading=32, textColor=BLUE, spaceAfter=6, alignment=TA_LEFT),
    "sub": ParagraphStyle("sub", parent=ss["Normal"], fontSize=11, leading=15, textColor=GREY, spaceAfter=18),
    "h1": ParagraphStyle("h1", parent=ss["Heading1"], fontSize=17, leading=22, textColor=BLUE, spaceBefore=16, spaceAfter=8),
    "h2": ParagraphStyle("h2", parent=ss["Heading2"], fontSize=13, leading=17, textColor=colors.HexColor("#0f172a"), spaceBefore=12, spaceAfter=5),
    "p": ParagraphStyle("p", parent=ss["Normal"], fontSize=9.8, leading=14, spaceAfter=6),
    "li": ParagraphStyle("li", parent=ss["Normal"], fontSize=9.8, leading=14),
    "cell": ParagraphStyle("cell", parent=ss["Normal"], fontSize=8.6, leading=11.5),
    "cellh": ParagraphStyle("cellh", parent=ss["Normal"], fontSize=8.6, leading=11.5, fontName="Helvetica-Bold", textColor=colors.white),
}
for _k, _st in S.items():
    _st.fontName = FONTB if _k in ("title", "h1", "h2", "cellh") else FONT


def inline(t: str) -> str:
    t = EMOJI.sub("", t).replace("  ", " ")
    t = re.sub(r"\*\*\s*\*\*", "", t)
    t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"`(.+?)`", r"<font face='Courier' size='8.8'>\1</font>", t)
    t = re.sub(r"\((https?://[^\s)]+)\)", r"(<link href='\1' color='#1d4ed8'>\1</link>)", t)
    return t


class Doc(SimpleDocTemplate):
    def afterFlowable(self, fl):
        if isinstance(fl, Paragraph) and fl.style.name in ("h1", "h2"):
            lvl = 0 if fl.style.name == "h1" else 1
            txt = re.sub(r"<[^>]+>", "", fl.getPlainText())
            key = f"h{self.seq.nextf('toc')}"
            self.canv.bookmarkPage(key)
            self.notify("TOCEntry", (lvl, txt, self.page, key))


def footer(canv, doc):
    canv.saveState()
    canv.setFont(FONT, 8); canv.setFillColor(GREY)
    canv.drawString(18 * mm, 10 * mm, f"FlightTracker {VERSION} — Guia de utilização · NAV Portugal / GOPLIS")
    canv.drawRightString(A4[0] - 18 * mm, 10 * mm, str(doc.page))
    canv.restoreState()


def table(rows: list[list[str]], widths):
    data = [[Paragraph(inline(c), S["cellh"]) for c in rows[0]]] + [[Paragraph(inline(c), S["cell"]) for c in r] for r in rows[1:]]
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BLUE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def build():
    lines = SRC.read_text(encoding="utf-8").splitlines()
    W = A4[0] - 36 * mm
    story, i = [], 0
    toc = TableOfContents()
    toc.levelStyles = [ParagraphStyle("toc1", fontSize=10.5, leading=15, leftIndent=0, fontName=FONTB),
                       ParagraphStyle("toc2", fontSize=9.5, leading=13, leftIndent=12, fontName=FONT)]
    first_h1 = True
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("# "):
            story += [Paragraph(inline(ln[2:]), S["title"])]
            if VERSION: story += [Paragraph(f"Versão {VERSION}", S["sub"])]
            i += 1; continue
        if ln.startswith("## "):
            if first_h1:
                story += [Paragraph("Índice", S["h1"]), toc, PageBreak()]; first_h1 = False
            story += [Paragraph(inline(ln[3:]), S["h1"])]; i += 1; continue
        if ln.startswith("### "):
            story += [Paragraph(inline(ln[4:]), S["h2"])]; i += 1; continue
        if ln.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r"-+", c) for c in cells): rows.append(cells)
                i += 1
            n = len(rows[0])
            widths = [W * 0.26, W * 0.74] if n == 2 else [W * 0.16, W * 0.17, W * 0.34, W * 0.33] if n == 4 else [W * 0.3, W * 0.37, W * 0.33] if n == 3 else [W / n] * n
            story += [table(rows, widths), Spacer(1, 6)]; continue
        m = re.match(r"^(\d+)\. (.*)", ln)
        if ln.startswith("- ") or m:
            items, numbered = [], bool(m)
            while i < len(lines) and (lines[i].startswith("- ") or re.match(r"^\d+\. ", lines[i])):
                items.append(ListItem(Paragraph(inline(re.sub(r"^(- |\d+\. )", "", lines[i])), S["li"]), leftIndent=14))
                i += 1
            kw = dict(bulletType="1", bulletFormat="%s.", bulletFontSize=9.8, bulletFontName=FONT) if numbered else dict(bulletType="bullet", bulletFontSize=7)
            story += [ListFlowable(items, leftIndent=16, **kw), Spacer(1, 5)]
            continue
        if ln.strip():
            story += [Paragraph(inline(ln.strip()), S["p"])]
        i += 1
    doc = Doc(str(OUT), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
              title=f"FlightTracker {VERSION} — Guia de utilização", author="NAV Portugal · GOPLIS")
    doc.multiBuild(story, onFirstPage=footer, onLaterPages=footer)
    print("OK", OUT, OUT.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    sys.exit(build())
