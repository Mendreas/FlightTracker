"""Histórico de versões e e-mail de novidades (HTML pronto para Outlook)."""
from __future__ import annotations

import html
import json
from email.header import Header
import time
from pathlib import Path

from core.db import resource_path

REPO = "https://github.com/Mendreas/FlightTracker"
# Ligações fixas: a release "latest" é substituída em cada build, por isso os links nunca mudam.
LINK_WIN = f"{REPO}/releases/download/latest/FlightTracker-Setup.zip"      # .exe dentro de .zip: passa nos filtros de rede
LINK_PORT = f"{REPO}/releases/download/latest/FlightTracker-windows-portable.zip"
LINK_MAC = f"{REPO}/releases/download/latest/FlightTracker-macOS.dmg"
LINK_ALL = f"{REPO}/releases"


def changelog() -> list[dict]:
    p = resource_path("data") / "changelog.json"
    return json.loads(p.read_text(encoding="utf-8"))


def entry(version: str | None = None) -> dict:
    log = changelog()
    if version:
        for e in log:
            if e["version"] == version:
                return e
    return log[0]


def email_subject(e: dict) -> str:
    return f"FlightTracker {e['version']} — {e['title']}"


def email_html(e: dict) -> str:
    """E-mail em tabelas com estilos inline. Só fundos claros e texto escuro: o Outlook na web, ao colar,
    força a cor do texto para preto e retira fundos de links — este desenho fica igual no Outlook instalado,
    no Outlook na web (colado) e no Gmail."""
    h = html.escape
    secs = ""
    for s in e.get("sections", []):
        items = "".join(f'<li style="margin:0 0 6px;line-height:1.45;">{h(i)}</li>' for i in s["items"])
        secs += f"""
<tr><td style="padding:0 40px 18px;">
  <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #c7d7ea;border-radius:8px;border-collapse:separate;overflow:hidden;">
    <tr><td bgcolor="#dbeafe" style="background:#dbeafe;padding:10px 16px;font-weight:700;font-size:14px;color:#0f2744;"><b>{h(s['title'])}</b></td></tr>
    <tr><td bgcolor="#f6f9fd" style="background:#f6f9fd;padding:14px 16px 8px;color:#1e293b;font-size:13px;"><ul style="margin:0;padding-left:18px;">{items}</ul></td></tr>
  </table>
</td></tr>"""
    return f"""<!DOCTYPE html>
<html lang="pt"><head><meta charset="utf-8"><title>{h(email_subject(e))}</title></head>
<body style="margin:0;padding:0;background:#ffffff;font-family:Segoe UI,Arial,Helvetica,sans-serif;color:#1e293b;">
<table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:24px 12px;">
<table width="680" cellpadding="0" cellspacing="0" style="max-width:680px;background:#ffffff;border:1px solid #c7d7ea;border-radius:12px;overflow:hidden;border-collapse:separate;">

<tr><td bgcolor="#e8f1fb" style="background:#e8f1fb;padding:30px 40px 24px;text-align:center;border-bottom:3px solid #1d6fb8;">
  <div style="font-size:34px;">&#9992;</div>
  <h1 style="font-size:28px;margin:10px 0 12px;color:#0f2744;"><b>FlightTracker</b></h1>
  <table cellpadding="0" cellspacing="0" align="center"><tr><td bgcolor="#ffffff" style="background:#ffffff;border:2px solid #1d6fb8;border-radius:20px;padding:6px 18px;font-size:13px;letter-spacing:2px;"><b>VERS&Atilde;O {h(e['version'])}</b></td></tr></table>
  <p style="font-size:15px;margin:16px 0 0;"><b>{h(e['title'])}</b></p>
</td></tr>

<tr><td style="padding:26px 40px 14px;font-size:14px;line-height:1.55;">{h(e['summary'])}</td></tr>
{secs}
<tr><td bgcolor="#e8f1fb" style="background:#e8f1fb;padding:22px 40px;text-align:center;border-top:3px solid #1d6fb8;">
  <p style="font-size:13px;margin:0 0 14px;letter-spacing:1px;"><b>DOWNLOAD DA VERS&Atilde;O {h(e['version'])}</b></p>
  <table cellpadding="0" cellspacing="0" align="center"><tr>
    <td bgcolor="#ffffff" style="background:#ffffff;border:2px solid #1d6fb8;border-radius:8px;padding:10px 22px;font-size:14px;"><a href="{LINK_WIN}" style="text-decoration:none;font-weight:700;"><b>&#8595; Windows (instalador, .zip)</b></a></td>
    <td style="width:16px;"></td>
    <td bgcolor="#ffffff" style="background:#ffffff;border:2px solid #1d6fb8;border-radius:8px;padding:10px 22px;font-size:14px;"><a href="{LINK_MAC}" style="text-decoration:none;font-weight:700;"><b>&#8595; macOS (.dmg)</b></a></td>
  </tr></table>
  <p style="font-size:12px;margin:14px 0 0;line-height:1.5;"><b>Windows:</b> descarregar o zip, abrir e executar o <i>FlightTracker-Setup.exe</i> que est&aacute; l&aacute; dentro (o instalador vai dentro de um zip porque a rede bloqueia o download direto de .exe). Instala por cima da vers&atilde;o anterior &middot; a base de dados importada mant&eacute;m-se.<br>
  Sem permiss&otilde;es para instalar? <a href="{LINK_PORT}">vers&atilde;o port&aacute;til (zip)</a>: descompactar para uma pasta e abrir o FlightTracker.exe. &middot; <a href="{LINK_ALL}">todas as vers&otilde;es</a></p>
</td></tr>

<tr><td style="padding:14px 40px;text-align:center;">
  <p style="font-size:11px;margin:0;color:#64748b;">FlightTracker {h(e['version'])} &middot; NAV Portugal &middot; GOPLIS &middot; an&aacute;lise interna de trajet&oacute;rias radar &middot; <a href="{REPO}">p&aacute;gina do projeto</a></p>
</td></tr>
</table></td></tr></table></body></html>"""


def write_eml(e: dict, folder: Path) -> Path:
    """Guarda um .eml com X-Unsent: 1 — o Outlook abre-o como rascunho editável (só falta pôr os destinatários)."""
    body = email_html(e)
    subj = email_subject(e)
    eml = ("X-Unsent: 1\r\nMIME-Version: 1.0\r\n"
           f"Subject: {Header(subj, 'utf-8').encode()}\r\n"
           f"Date: {time.strftime('%a, %d %b %Y %H:%M:%S %z')}\r\n"
           "Content-Type: text/html; charset=UTF-8\r\nContent-Transfer-Encoding: 8bit\r\n\r\n" + body)
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / f"FlightTracker_{e['version']}_novidades.eml"
    p.write_bytes(eml.encode("utf-8"))
    return p
