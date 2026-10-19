/* Gráficos SVG leves (sem dependências) + tabelas ordenáveis */
'use strict';
const C = (() => {
  const esc = s => String(s == null ? '—' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const fmt = (v, d = 0) => (v == null || Number.isNaN(v)) ? '—' : Number(v).toLocaleString('pt-PT', { minimumFractionDigits: d, maximumFractionDigits: d });
  const BLUE = '#3b9cff', RED = '#ff5d5d', ORANGE = '#ff9b2f', GREEN = '#35c46a', GREY = '#8a93a6', YEL = '#ffcf4a', PURPLE = '#c77dff';

  function bars(values, labels, o = {}) {
    const w = o.w || 720, h = o.h || 170, pad = { l: 34, r: 10, t: 18, b: 34 };
    if (!values.length) return '<div class="hint">Sem dados.</div>';
    const mx = Math.max(...values, o.max || 0) || 1, n = values.length, bw = (w - pad.l - pad.r) / n;
    let s = `<svg viewBox="0 0 ${w} ${h}" class="chart-svg">`;
    for (let i = 0; i <= 4; i++) { const y = pad.t + (h - pad.t - pad.b) * (1 - i / 4); s += `<line x1="${pad.l}" x2="${w - pad.r}" y1="${y}" y2="${y}" class="ax"/><text x="${pad.l - 4}" y="${y + 3}" text-anchor="end" class="lbl">${fmt(mx * i / 4, o.dec || 0)}</text>`; }
    values.forEach((v, i) => {
      const bh = (h - pad.t - pad.b) * v / mx, x = pad.l + i * bw;
      const col = o.colors ? o.colors[i] : (o.red && o.red[i]) ? RED : (o.color || BLUE);
      s += `<rect x="${(x + 2).toFixed(1)}" y="${(h - pad.b - bh).toFixed(1)}" width="${Math.max(1, bw - 4).toFixed(1)}" height="${bh.toFixed(1)}" fill="${col}" rx="2"><title>${esc(labels[i])}: ${fmt(v, o.dec || 0)}${o.tips ? ' — ' + esc(o.tips[i]) : ''}</title></rect>`;
      if (v && n <= 40) s += `<text x="${(x + bw / 2).toFixed(1)}" y="${(h - pad.b - bh - 3).toFixed(1)}" text-anchor="middle" class="lbl">${fmt(v, o.dec || 0)}</text>`;
      if (n <= 32 || i % Math.ceil(n / 32) === 0) s += `<text x="${(x + bw / 2).toFixed(1)}" y="${h - pad.b + 12}" text-anchor="middle" class="lbl" ${n > 12 ? `transform="rotate(-35 ${(x + bw / 2).toFixed(1)} ${h - pad.b + 12})"` : ''}>${esc(labels[i])}</text>`;
    });
    return s + '</svg>';
  }
  function grouped(series, labels, o = {}) {
    const w = o.w || 720, h = o.h || 180, pad = { l: 34, r: 10, t: 18, b: 40 };
    if (!labels.length) return '<div class="hint">Sem dados.</div>';
    const mx = Math.max(...series.flatMap(s => s.values), 1), n = labels.length, gw = (w - pad.l - pad.r) / n, bw = (gw - 6) / series.length;
    let s = `<svg viewBox="0 0 ${w} ${h}" class="chart-svg">`;
    for (let i = 0; i <= 4; i++) { const y = pad.t + (h - pad.t - pad.b) * (1 - i / 4); s += `<line x1="${pad.l}" x2="${w - pad.r}" y1="${y}" y2="${y}" class="ax"/><text x="${pad.l - 4}" y="${y + 3}" text-anchor="end" class="lbl">${fmt(mx * i / 4, o.dec || 0)}</text>`; }
    labels.forEach((lb, i) => {
      series.forEach((sr, j) => { const v = sr.values[i] || 0, bh = (h - pad.t - pad.b) * v / mx, x = pad.l + i * gw + 3 + j * bw;
        s += `<rect x="${x.toFixed(1)}" y="${(h - pad.b - bh).toFixed(1)}" width="${Math.max(1, bw - 1).toFixed(1)}" height="${bh.toFixed(1)}" fill="${sr.color}" rx="1"><title>${esc(lb)} · ${esc(sr.name)}: ${fmt(v, o.dec || 0)}</title></rect>`; });
      s += `<text x="${(pad.l + i * gw + gw / 2).toFixed(1)}" y="${h - pad.b + 12}" text-anchor="middle" class="lbl">${esc(lb)}</text>`;
    });
    let lx = pad.l; series.forEach(sr => { s += `<rect x="${lx}" y="${h - 10}" width="10" height="8" fill="${sr.color}"/><text x="${lx + 13}" y="${h - 2}" class="lbl">${esc(sr.name)}</text>`; lx += 20 + sr.name.length * 6.5; });
    return s + '</svg>';
  }
  function hbars(items, o = {}) { // [{label, value, sub}]
    if (!items.length) return '<div class="hint">Sem dados.</div>';
    const mx = Math.max(...items.map(i => i.value)) || 1;
    return '<div class="hbars">' + items.map(i => `<div class="hb"><span class="hb-l" title="${esc(i.title || '')}">${esc(i.label)}</span><span class="hb-bar"><i style="width:${(i.value / mx * 100).toFixed(1)}%;background:${i.color || BLUE}"></i></span><span class="hb-v">${esc(i.text != null ? i.text : fmt(i.value, o.dec || 0))}</span></div>`).join('') + '</div>';
  }
  function stackedHist(hst, tol) { // {bins:[{lo,y,g,r}], limit, n, mean, median}
    if (!hst.bins.length) return '<div class="hint">Sem amostras com IAS ao CPA neste fix</div>';
    const w = 760, h = 220, pad = { l: 30, r: 10, t: 14, b: 30 }, n = hst.bins.length, bw = (w - pad.l - pad.r) / n;
    const mx = Math.max(...hst.bins.map(b => b.y + b.g + b.r)) || 1;
    let s = `<svg viewBox="0 0 ${w} ${h}" class="chart-svg">`;
    hst.bins.forEach((b, i) => { const x = pad.l + i * bw; let y = h - pad.b;
      [['y', YEL, 'Abaixo'], ['g', GREEN, 'Conforme'], ['r', RED, 'Acima']].forEach(([k, col, nm]) => { const bh = (h - pad.t - pad.b) * b[k] / mx; y -= bh;
        if (b[k]) s += `<rect x="${(x + 1).toFixed(1)}" y="${y.toFixed(1)}" width="${(bw - 2).toFixed(1)}" height="${bh.toFixed(1)}" fill="${col}"><title>${b.lo}-${b.lo + 5} kt · ${nm}: ${b[k]}</title></rect>`; });
      if (i % Math.max(1, Math.round(n / 8)) === 0) s += `<text x="${(x + bw / 2).toFixed(1)}" y="${h - pad.b + 12}" text-anchor="middle" class="lbl">${b.lo}</text>`; });
    const lx = pad.l + (hst.limit - hst.xmin) / (hst.xmax - hst.xmin) * (w - pad.l - pad.r);
    if (lx >= pad.l && lx <= w - pad.r) s += `<line x1="${lx}" x2="${lx}" y1="${pad.t}" y2="${h - pad.b}" stroke="${RED}" stroke-dasharray="5 4" stroke-width="2"/><text x="${lx + 4}" y="${pad.t + 10}" fill="${RED}">limite ${hst.limit}</text>`;
    s += `<text x="${pad.l}" y="${h - 4}" class="lbl">n=${hst.n} · média ${fmt(hst.mean)} kt · mediana ${fmt(hst.median)} kt · tolerância ±${tol} kt</text>`;
    return s + '</svg>';
  }
  function scatter(points, o = {}) { // [{x,y,color,stroke,title}]
    const w = o.w || 720, h = o.h || 240, pad = { l: 40, r: 12, t: 14, b: 30 };
    if (!points.length) return '<div class="hint">Sem dados.</div>';
    const xmax = o.xmax || Math.max(...points.map(p => p.x)) * 1.05, ymax = o.ymax || Math.max(...points.map(p => p.y)) * 1.1;
    const X = x => pad.l + (w - pad.l - pad.r) * x / xmax, Y = y => h - pad.b - (h - pad.t - pad.b) * y / ymax;
    let s = `<svg viewBox="0 0 ${w} ${h}" class="chart-svg">`;
    (o.ygrid || []).forEach(g => s += `<line x1="${pad.l}" x2="${w - pad.r}" y1="${Y(g)}" y2="${Y(g)}" class="ax"/><text x="${pad.l - 4}" y="${Y(g) + 3}" text-anchor="end" class="lbl">${g}</text>`);
    for (let i = 0; i <= 6; i++) { const x = pad.l + (w - pad.l - pad.r) * i / 6; s += `<text x="${x}" y="${h - pad.b + 12}" text-anchor="middle" class="lbl">${fmt(xmax * i / 6)}</text>`; }
    if (o.vline != null) s += `<line x1="${X(o.vline)}" x2="${X(o.vline)}" y1="${pad.t}" y2="${h - pad.b}" stroke="${RED}" stroke-dasharray="5 4"/>`;
    points.forEach(p => s += `<circle cx="${X(p.x).toFixed(1)}" cy="${Y(p.y).toFixed(1)}" r="4" fill="${p.color}" stroke="${p.stroke || 'none'}" stroke-width="2"><title>${esc(p.title)}</title></circle>`);
    s += `<text x="${w - pad.r}" y="${h - 4}" text-anchor="end" class="lbl">${esc(o.xlabel || '')}</text><text x="${pad.l}" y="${pad.t - 3}" class="lbl">${esc(o.ylabel || '')}</text>`;
    return s + '</svg>';
  }
  function percentiles(buckets, o = {}) { // [{label, p0,p25,p50,p75,p100,n}]
    const w = 760, h = 220, pad = { l: 40, r: 12, t: 14, b: 30 };
    if (!buckets.length) return '<div class="hint">Sem dados.</div>';
    const mn = Math.min(...buckets.map(b => b.p0)), mx = Math.max(...buckets.map(b => b.p100)) || 1, n = buckets.length;
    const X = i => pad.l + (w - pad.l - pad.r) * (n === 1 ? .5 : i / (n - 1)), Y = v => h - pad.b - (h - pad.t - pad.b) * (v - mn) / ((mx - mn) || 1);
    let s = `<svg viewBox="0 0 ${w} ${h}" class="chart-svg">`;
    for (let i = 0; i <= 4; i++) { const v = mn + (mx - mn) * i / 4; s += `<line x1="${pad.l}" x2="${w - pad.r}" y1="${Y(v)}" y2="${Y(v)}" class="ax"/><text x="${pad.l - 4}" y="${Y(v) + 3}" text-anchor="end" class="lbl">${fmt(v)}</text>`; }
    const poly = k => buckets.map((b, i) => `${X(i).toFixed(1)},${Y(b[k]).toFixed(1)}`).join(' ');
    s += `<polygon points="${poly('p25')} ${buckets.map((b, i) => `${X(i).toFixed(1)},${Y(b.p75).toFixed(1)}`).reverse().join(' ')}" fill="${BLUE}" opacity=".18"/>`;
    s += `<polyline points="${poly('p0')}" fill="none" stroke="${RED}" stroke-dasharray="4 3"/><polyline points="${poly('p100')}" fill="none" stroke="${ORANGE}" stroke-dasharray="4 3"/><polyline points="${poly('p50')}" fill="none" stroke="${BLUE}" stroke-width="2.5"/>`;
    buckets.forEach((b, i) => s += `<circle cx="${X(i)}" cy="${Y(b.p50)}" r="3.5" fill="${BLUE}"><title>${esc(b.label)} | n=${b.n} | mín=${fmt(b.p0)} | Q1=${fmt(b.p25)} | med=${fmt(b.p50)} | Q3=${fmt(b.p75)} | máx=${fmt(b.p100)}</title></circle><text x="${X(i)}" y="${h - pad.b + 12}" text-anchor="middle" class="lbl">${esc(b.label)}</text>`);
    s += `<text x="${pad.l}" y="${h - 4}" class="lbl">mediana (azul) · banda Q1–Q3 · mín (vermelho) · máx (laranja) — ${esc(o.unit || '')}</text>`;
    return s + '</svg>';
  }
  function profile(cols, flights, o = {}) { // cols:[{label,lim}], flights:[{csn, vals:[ias|null], color}]
    const w = 760, h = 230, pad = { l: 40, r: 14, t: 16, b: 46 }, n = cols.length;
    if (!n) return '<div class="hint">Sem pontos.</div>';
    const all = flights.flatMap(f => f.vals.filter(v => v != null)).concat(cols.map(c => c.lim));
    const rmin = Math.min(...all), rmax = Math.max(...all), p5 = Math.max(5, (rmax - rmin) * .12);
    const ymin = Math.max(80, Math.round((rmin - p5) / 5) * 5), ymax = Math.min(320, Math.round((rmax + p5) / 5) * 5) || ymin + 40;
    const X = i => pad.l + (w - pad.l - pad.r) * (n === 1 ? .5 : i / (n - 1)), Y = v => h - pad.b - (h - pad.t - pad.b) * (v - ymin) / ((ymax - ymin) || 1);
    let s = `<svg viewBox="0 0 ${w} ${h}" class="chart-svg">`;
    const ny = Math.min(6, Math.round((ymax - ymin) / 10)) || 1;
    for (let i = 0; i <= ny; i++) { const v = ymin + (ymax - ymin) * i / ny; s += `<line x1="${pad.l}" x2="${w - pad.r}" y1="${Y(v)}" y2="${Y(v)}" class="ax"/><text x="${pad.l - 4}" y="${Y(v) + 3}" text-anchor="end" class="lbl">${fmt(v)}</text>`; }
    cols.forEach((c, i) => s += `<text x="${X(i)}" y="${h - pad.b + 12}" text-anchor="middle" class="lbl" ${c.named ? 'font-weight="700"' : ''} transform="rotate(-35 ${X(i)} ${h - pad.b + 12})">${esc(c.label)}</text>`);
    flights.slice(0, 100).forEach(f => { const pts = f.vals.map((v, i) => v == null ? null : `${X(i).toFixed(1)},${Y(v).toFixed(1)}`).filter(Boolean); if (pts.length > 1) s += `<polyline points="${pts.join(' ')}" fill="none" stroke="${f.color}" stroke-width="${f.viol ? 2 : 1}" opacity="${f.viol ? .6 : .25}"><title>${esc(f.csn)}</title></polyline>`; });
    s += `<polyline points="${cols.map((c, i) => `${X(i).toFixed(1)},${Y(c.lim).toFixed(1)}`).join(' ')}" fill="none" stroke="${RED}" stroke-width="2" stroke-dasharray="6 4"/>`;
    s += `<text x="${pad.l}" y="${pad.t - 4}" class="lbl">kt · ${flights.length} voo(s) · tracejado = perfil de limite</text>`;
    return s + '</svg>';
  }
  function timeline(events, o = {}) { // [{rwy,tLead,tTrail,lead,trail,deps:[{t,csn}],crit}] tempos em segundos do dia
    if (!events.length) return '<div class="hint">Sem pares.</div>';
    const pxh = o.pxPerHour || 1500, hours = o.hours || 2, h = 300;
    const ts = events.flatMap(e => [e.tLead, e.tTrail]);
    const focus = o.focusHour != null ? o.focusHour : Math.floor(ts.reduce((a, b) => a + b, 0) / ts.length / 3600);
    const t0 = o.all ? 0 : Math.max(0, (focus - hours / 2 + .5) * 3600), t1 = o.all ? 86400 : t0 + hours * 3600;
    const w = Math.max(900, (t1 - t0) / 3600 * (o.all ? 900 : pxh));
    const X = t => 60 + (w - 80) * (t - t0) / (t1 - t0), lanes = { '02': 110, '20': 220 };
    let s = `<svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" class="chart-svg">`;
    for (let t = Math.ceil(t0 / 600) * 600; t <= t1; t += 600) { const x = X(t); s += `<line x1="${x}" x2="${x}" y1="40" y2="${h - 30}" class="ax"/>`; if (t % 1800 === 0) s += `<text x="${x}" y="30" text-anchor="middle" class="lbl">${String(Math.floor(t / 3600) % 24).padStart(2, '0')}:${String(Math.floor(t % 3600 / 60)).padStart(2, '0')}</text>`; }
    Object.entries(lanes).forEach(([r, y]) => s += `<line x1="60" x2="${w - 20}" y1="${y}" y2="${y}" stroke="${GREY}" stroke-width="6" opacity=".3"/><text x="8" y="${y + 4}" class="lbl">RWY ${r}</text>`);
    events.forEach(e => { if (e.tTrail < t0 || e.tLead > t1) return; const y = lanes[e.rwy] || 165;
      s += `<line x1="${X(e.tLead)}" x2="${X(e.tTrail)}" y1="${y}" y2="${y}" stroke="${e.crit ? RED : GREY}" stroke-width="${e.crit ? 4 : 2}"/>`;
      s += `<circle cx="${X(e.tLead)}" cy="${y - 16}" r="5" fill="#0b5cad" stroke="${e.crit ? RED : 'none'}" stroke-width="2"><title>Precedente ${esc(e.lead)} na THR</title></circle>`;
      s += `<circle cx="${X(e.tTrail)}" cy="${y + 16}" r="5" fill="#7c3aed" stroke="${e.crit ? RED : 'none'}" stroke-width="2"><title>Seguidor ${esc(e.trail)} na THR</title></circle>`;
      e.deps.forEach(d => s += `<rect x="${X(d.t) - 4}" y="${y - 4}" width="8" height="8" fill="${ORANGE}"><title>DEP ${esc(d.csn)}</title></rect>`);
      if (e.crit || o.labels === 'all') s += `<text x="${X(e.tLead)}" y="${y - 24}" text-anchor="middle" class="lbl">${esc(e.lead)}</text><text x="${X(e.tTrail)}" y="${y + 30}" text-anchor="middle" class="lbl">${esc(e.trail)}</text>`; });
    s += `<g transform="translate(60,${h - 12})" class="lbl"><circle cx="0" cy="-4" r="4" fill="#0b5cad"/><text x="8">Precedente na THR</text><rect x="130" y="-8" width="8" height="8" fill="${ORANGE}"/><text x="142">DEP intermédio</text><circle cx="250" cy="-4" r="4" fill="#7c3aed"/><text x="258">Seguidor na THR</text><line x1="370" x2="400" y1="-4" y2="-4" stroke="${RED}" stroke-width="4"/><text x="406">Par abaixo do limite</text></g>`;
    return s + '</svg>';
  }
  // tabela ordenável: cols [{k,label,fmt?,cls?}], rows objetos
  function table(cols, rows, o = {}) {
    const id = o.id || ('t' + Math.random().toString(36).slice(2, 8));
    const render = (sortK, asc) => {
      let rs = rows.slice();
      if (sortK) rs.sort((a, b) => { const va = a[sortK], vb = b[sortK]; if (va == null) return 1; if (vb == null) return -1; return (typeof va === 'number' && typeof vb === 'number' ? va - vb : String(va).localeCompare(String(vb), 'pt')) * (asc ? 1 : -1); });
      if (o.limit) rs = rs.slice(0, o.limit);
      return `<table class="sortable" id="${id}"><thead><tr>${cols.map(c => `<th data-k="${c.k}" class="${sortK === c.k ? (asc ? 'asc' : 'desc') : ''}" title="${esc(c.title || '')}">${esc(c.label)}</th>`).join('')}</tr></thead><tbody>` +
        rs.map((r, i) => `<tr class="${o.rowClass ? o.rowClass(r) : ''} ${o.onRow ? 'clk' : ''}" data-i="${rows.indexOf(r)}">${cols.map(c => `<td class="${c.cls ? c.cls(r) : ''}">${c.fmt ? c.fmt(r[c.k], r, i) : esc(r[c.k])}</td>`).join('')}</tr>`).join('') + '</tbody></table>' +
        (o.limit && rows.length > o.limit ? `<div class="hint">A mostrar ${o.limit} de ${rows.length} linhas (a exportação inclui todas).</div>` : '');
    };
    setTimeout(() => {
      const el = document.getElementById(id); if (!el) return;
      let sk = o.sortKey || null, asc = o.sortAsc !== false;
      const wire = () => { const t = document.getElementById(id); if (!t) return;
        t.querySelectorAll('th').forEach(th => th.onclick = () => { const k = th.dataset.k; asc = sk === k ? !asc : true; sk = k; t.outerHTML = render(sk, asc); wire(); });
        if (o.onRow) t.querySelectorAll('tbody tr').forEach(tr => tr.onclick = ev => o.onRow(rows[+tr.dataset.i], tr, ev)); };
      wire();
    }, 0);
    return render(o.sortKey || null, o.sortAsc !== false);
  }
  const kcard = (label, value, sub = '', cls = '') => `<div class="kcard ${cls}"><b>${esc(value)}</b><span>${esc(label)}</span>${sub ? `<div class="s">${esc(sub)}</div>` : ''}</div>`;
  const card = (title, body, note = '') => `<section class="card"><h3>${esc(title)}</h3>${note ? `<p class="note">${esc(note)}</p>` : ''}<div class="chart">${body}</div></section>`;
  return { esc, fmt, bars, grouped, hbars, stackedHist, scatter, percentiles, profile, timeline, table, kcard, card, BLUE, RED, ORANGE, GREEN, GREY, YEL, PURPLE };
})();
