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
LINK_WIN = f"{REPO}/releases/download/latest/FlightTracker-Setup.exe"
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
    """E-mail em tabelas com estilos inline (o que o Outlook consegue mostrar)."""
    h = html.escape
    secs = ""
    for s in e.get("sections", []):
        items = "".join(f'<li style="margin:0 0 6px;line-height:1.45;">{h(i)}</li>' for i in s["items"])
        secs += f"""
<tr><td style="padding:0 40px 18px;">
  <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #dbe4f0;border-radius:8px;border-collapse:separate;overflow:hidden;">
    <tr><td bgcolor="#1d6fb8" style="background:#1d6fb8;color:#ffffff;padding:10px 16px;font-weight:700;font-size:14px;">{h(s['title'])}</td></tr>
    <tr><td bgcolor="#f3f8fd" style="background:#f3f8fd;padding:14px 16px 8px;color:#1e293b;font-size:13px;"><ul style="margin:0;padding-left:18px;">{items}</ul></td></tr>
  </table>
</td></tr>"""
    return f"""<!DOCTYPE html>
<html lang="pt"><head><meta charset="utf-8"><title>{h(email_subject(e))}</title></head>
<body style="margin:0;padding:0;background:#eef2f7;font-family:Segoe UI,Arial,Helvetica,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" bgcolor="#eef2f7"><tr><td align="center" style="padding:24px 12px;">
<table width="680" cellpadding="0" cellspacing="0" style="max-width:680px;background:#ffffff;border-radius:12px;overflow:hidden;border-collapse:separate;">

<tr><td bgcolor="#0f2744" style="background:#0f2744;padding:34px 40px 28px;text-align:center;">
  <div style="font-size:34px;color:#7cc4ff;">&#9992;</div>
  <h1 style="color:#ffffff;font-size:28px;margin:10px 0 12px;">FlightTracker</h1>
  <span style="display:inline-block;border:2px solid #3b82f6;color:#bfdbfe;border-radius:20px;padding:6px 18px;font-size:13px;letter-spacing:2px;">VERS&Atilde;O {h(e['version'])}</span>
  <p style="color:#cbd5e1;font-size:14px;margin:16px 0 0;">{h(e['title'])}</p>
</td></tr>

<tr><td style="padding:26px 40px 14px;color:#1e293b;font-size:14px;line-height:1.55;">{h(e['summary'])}</td></tr>
{secs}
<tr><td bgcolor="#0f2744" style="background:#0f2744;padding:24px 40px;text-align:center;">
  <p style="color:#94a3b8;font-size:12px;margin:0 0 16px;text-transform:uppercase;letter-spacing:1px;">Download da vers&atilde;o {h(e['version'])}</p>
  <table cellpadding="0" cellspacing="0" align="center"><tr>
    <td style="padding:0 8px;"><a href="{LINK_WIN}" style="display:inline-block;background:#3b82f6;color:#ffffff;text-decoration:none;padding:12px 24px;border-radius:8px;font-size:13px;font-weight:700;">&#8595; Windows (instalador .exe)</a></td>
    <td style="padding:0 8px;"><a href="{LINK_MAC}" style="display:inline-block;background:#6366f1;color:#ffffff;text-decoration:none;padding:12px 24px;border-radius:8px;font-size:13px;font-weight:700;">&#8595; macOS (.dmg)</a></td>
  </tr></table>
  <p style="color:#64748b;font-size:11px;margin:14px 0 0;">Instala por cima da vers&atilde;o anterior &middot; a base de dados importada mant&eacute;m-se &middot; <a href="{LINK_ALL}" style="color:#60a5fa;">todas as vers&otilde;es</a></p>
</td></tr>

<tr><td style="padding:16px 40px;text-align:center;border-top:1px solid #e2e8f0;">
  <p style="color:#9ca3af;font-size:11px;margin:0;">FlightTracker {h(e['version'])} &middot; NAV Portugal &middot; GOPLIS &middot; an&aacute;lise interna de trajet&oacute;rias radar</p>
  <p style="font-size:10px;margin:4px 0 0;"><a href="{REPO}" style="color:#60a5fa;text-decoration:none;">github.com/Mendreas/FlightTracker</a></p>
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
