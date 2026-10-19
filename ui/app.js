/* FlightTracker 4 — interface (fala com o Python via window.pywebview.api) */
'use strict';

const $ = id => document.getElementById(id);
const fmt = n => (n == null ? '—' : Number(n).toLocaleString('pt-PT'));
const CLS_COLOR = { arr: '#3b9cff', dep: '#ff9b2f', lvl: '#8a93a6' };
const CLS_NAME = { arr: 'Chegada', dep: 'Partida', lvl: 'Sobrevoo' };
const PALETTE = ['#4cc9f0', '#f72585', '#b5e48c', '#ffd166', '#c77dff', '#06d6a0', '#ff8fab', '#90e0ef', '#f9c74f', '#a0c4ff', '#ffadad', '#caffbf'];
const THR = { LPPT: { '02': [38.766428, -9.143903], '20': [38.792331, -9.130047] },
  LPFR: { '10': [37.017222, -7.985614], '28': [37.013450, -7.959042] },
  LPMA: { '05': [32.689932, -16.783751], '23': [32.705841, -16.765150] },
  LPPR: { '17': [41.260681, -8.684561], '35': [41.233886, -8.677536] } };
const AIRPORT_CENTER = { LPPT: [38.78, -9.14], LPFR: [37.02, -7.97], LPMA: [32.70, -16.77], LPPR: [41.25, -8.68] };

const state = {
  filters: null, airport: 'LPPT', airports: [], month: null, days: new Set(), blocks: new Set(), clsView: '',
  allFlights: [], flights: [], byId: new Map(), hidden: new Set(), selected: null,
  tracks: {}, layers: new Map(), points: null, sortKey: 'date', sortAsc: true,
};
const MONTHS = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'];
const WD = ['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb'];
const dateObj = d => new Date(2000 + +d.slice(0, 2), +d.slice(2, 4) - 1, +d.slice(4, 6));

/* ------------------------------------------------------------- API bridge */
const useHttp = location.protocol.startsWith('http');
function api() { return useHttp ? true : (window.pywebview && window.pywebview.api); }
async function call(name, ...args) {
  let r;
  if (useHttp) {
    const resp = await fetch('/api', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ method: name, args }) });
    if (!resp.ok) throw new Error('Erro de comunicação com o Python (HTTP ' + resp.status + ')');
    r = await resp.json();
  } else {
    const a = window.pywebview && window.pywebview.api;
    if (!a) throw new Error('Backend Python não disponível (a app tem de correr via app.py).');
    r = await a[name](...args);
  }
  if (!r || !r.ok) throw new Error((r && r.error) || 'Erro desconhecido');
  return r.data;
}

/* ------------------------------------------------------------- UI helpers */
let toastT;
function toast(msg, kind = '') {
  const t = $('toast'); t.textContent = msg; t.className = 'toast ' + kind;
  clearTimeout(toastT); toastT = setTimeout(() => t.classList.add('hidden'), kind === 'err' ? 9000 : 4500);
}
function status(msg, dot = 'on', time = '') { $('sTxt').textContent = msg; $('sDot').className = 'dot ' + dot; $('sTime').textContent = time; }
function haversineNm(a, b) {
  const R = 3440.065, d2r = Math.PI / 180;
  const dLat = (b[0] - a[0]) * d2r, dLon = (b[1] - a[1]) * d2r;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a[0] * d2r) * Math.cos(b[0] * d2r) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}
function nearestThr(airport, latlon) {
  const t = THR[airport] || THR.LPPT; let best = null;
  for (const k in t) { const d = haversineNm(latlon, t[k]); if (!best || d < best.d) best = { rwy: k, d }; }
  return best;
}

/* ------------------------------------------------------------- Map */
let map, tiles, trackGroup, pointGroup, overlayGroup;
function initMap() {
  map = L.map('map', { zoomControl: true, preferCanvas: true }).setView(AIRPORT_CENTER.LPPT, 10);
  window.BASES = {
    osm:  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '© OpenStreetMap', maxZoom: 19, className: 'tiles-dark' }),
    sat:  L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', { attribution: '© Esri', maxZoom: 18 }),
    ruas: L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}', { attribution: '© Esri', maxZoom: 18 }),
  };
  tiles = BASES.osm;
  Object.values(BASES).forEach(t => t.on('tileerror', () => { if (!t._warned) { t._warned = true; toast('Sem acesso ao mapa de fundo (sem internet?). As trajetórias continuam visíveis.', 'err'); } }));
  $('selBase').onchange = e => { map.removeLayer(tiles); tiles = BASES[e.target.value]; if ($('chkTiles').checked) tiles.addTo(map); };
  tiles.addTo(map);
  trackGroup = L.layerGroup().addTo(map);
  pointGroup = L.layerGroup().addTo(map);
  overlayGroup = L.layerGroup().addTo(map);
  // escala em NM
  L.control.scale({ imperial: false, nautical: true, metric: false }).addTo(map);
}
function drawPoints() {
  pointGroup.clearLayers();
  if (!state.points || !$('chkPoints').checked) return;
  const g = $('selGroup').value;
  let names = null;
  if (g && g !== 'ALL') names = new Set(state.points.groups[g] || []);
  const seen = new Set();
  for (const p of state.points.points) {
    if (names && !names.has(p.name)) continue;
    if (seen.has(p.name)) continue; seen.add(p.name);
    const isThr = p.name.startsWith('THR');
    L.circleMarker([p.lat, p.lon], { radius: isThr ? 4 : 3, color: isThr ? '#ffd166' : '#7fb3ff', weight: 1, fillOpacity: .9 })
      .bindTooltip(`${p.name}<br><span style="color:#8a93a6">${p.desc || ''}</span>`, { direction: 'top' })
      .addTo(pointGroup);
    L.marker([p.lat, p.lon], { icon: L.divIcon({ className: 'aip-lbl', html: p.name, iconAnchor: [-6, 6] }), interactive: false }).addTo(pointGroup);
  }
}
function colorFor(f) {
  if ($('chkColorCls').checked) return CLS_COLOR[f.cls] || CLS_COLOR.lvl;
  let h = 0; for (const ch of f.csn) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return PALETTE[h % PALETTE.length];
}
function drawTracks() {
  trackGroup.clearLayers(); state.layers.clear();
  let bounds = null;
  for (const f of state.flights) {
    if (state.hidden.has(f.flight_id)) continue;
    const pts = state.tracks[f.flight_id]; if (!pts || pts.length < 2) continue;
    const ll = pts.map(p => [p[0], p[1]]);
    const sel = state.selected === f.flight_id;
    const line = L.polyline(ll, { color: colorFor(f), weight: sel ? 4 : 1.6, opacity: sel ? 1 : .75 });
    line.bindTooltip(`<b>${f.csn}</b> ${f.actype || ''} · ${CLS_NAME[f.cls]}<br>${f.tod_first} → ${f.tod_last}`, { sticky: true });
    line.on('click', () => selectFlight(f.flight_id, false));
    line.addTo(trackGroup); state.layers.set(f.flight_id, line);
    const b = line.getBounds(); bounds = bounds ? bounds.extend(b) : b;
  }
  if (bounds && bounds.isValid() && !state.selected) map.fitBounds(bounds.pad(0.05));
}

/* ------------------------------------------------------------- Filters UI */
function dayInfo() { // agrega todos os aeroportos por dia
  const m = new Map();
  for (const d of state.filters.dates) { const e = m.get(d.date) || { date: d.date, files: 0, rows: 0, airports: new Set() }; e.files += d.files; e.rows += d.rows; e.airports.add(d.airport); m.set(d.date, e); }
  return m;
}
function renderFilters() {
  const f = state.filters;
  const months = [...new Set(f.dates.map(d => d.date.slice(0, 4)))].sort();
  const sel = $('selMonth'); sel.innerHTML = months.map(m => `<option value="${m}">${MONTHS[+m.slice(2, 4) - 1]} 20${m.slice(0, 2)}</option>`).join('');
  if (!months.includes(state.month)) state.month = months[months.length - 1] || null;
  if (state.month) sel.value = state.month;
  renderCalendar(); renderBlocks();
}
function renderCalendar() {
  const grid = $('calGrid'); grid.innerHTML = '';
  if (!state.month) { grid.innerHTML = '<div class="empty" style="grid-column:1/-1">Sem dados importados.</div>'; $('wdBtns').innerHTML = ''; return; }
  const info = dayInfo(), yy = +state.month.slice(0, 2), mm = +state.month.slice(2, 4);
  const first = new Date(2000 + yy, mm - 1, 1), nDays = new Date(2000 + yy, mm, 0).getDate();
  for (let i = 0; i < first.getDay(); i++) grid.insertAdjacentHTML('beforeend', '<div class="d pad"></div>');
  for (let day = 1; day <= nDays; day++) {
    const key = state.month + String(day).padStart(2, '0'), e = info.get(key);
    const el = document.createElement('div'); el.className = 'd' + (e ? (state.days.has(key) ? ' on' : '') : ' off');
    el.innerHTML = `<b>${day}</b><i>${e ? e.files : ''}</i>`;
    if (e) { el.title = `${fmt(e.rows)} plots · ${[...e.airports].join(', ')}`; el.onclick = () => { state.days.has(key) ? state.days.delete(key) : state.days.add(key); el.classList.toggle('on'); updDayCount(); }; }
    grid.appendChild(el);
  }
  $('wdBtns').innerHTML = WD.map((w, i) => `<span class="chip" data-wd="${i}">${w}</span>`).join('');
  $('wdBtns').querySelectorAll('.chip').forEach(c => c.onclick = () => {
    const keys = [...info.keys()].filter(k => k.startsWith(state.month) && dateObj(k).getDay() === +c.dataset.wd);
    const allOn = keys.length && keys.every(k => state.days.has(k)); keys.forEach(k => allOn ? state.days.delete(k) : state.days.add(k)); renderCalendar();
  });
  updDayCount();
}
function updDayCount() { const n = state.days.size; document.querySelector('#sidebar .box-h').innerHTML = `Filtro de datas <span class="mini">${n ? `(${n} dia${n > 1 ? 's' : ''} selecionado${n > 1 ? 's' : ''})` : ''}</span>`; }
function renderBlocks() {
  const c = $('blockChips'); c.innerHTML = '';
  for (const b of state.filters.blocks) {
    const el = document.createElement('span'); el.className = 'chip blk' + (state.blocks.has(b) ? ' on' : ''); el.textContent = b;
    el.onclick = () => { state.blocks.has(b) ? state.blocks.delete(b) : state.blocks.add(b); el.classList.toggle('on'); };
    c.appendChild(el);
  }
}
const AIRPORT_NAMES = { LPPT: 'Lisboa (LPPT)', LPPR: 'Porto (LPPR)', LPFR: 'Faro (LPFR)', LPMA: 'Funchal (LPMA)' };
function renderAirports() {
  const sel = $('selAirportTop');
  const counts = new Map(); state.allFlights.forEach(f => counts.set(f.airport, (counts.get(f.airport) || 0) + 1));
  const inDb = new Set(state.filters ? state.filters.airports : []);
  sel.innerHTML = ['LPPT', 'LPPR', 'LPFR', 'LPMA'].map(a => `<option value="${a}">${AIRPORT_NAMES[a]}${counts.has(a) ? ` — ${fmt(counts.get(a))} mov.` : inDb.has(a) ? '' : ' — sem dados'}</option>`).join('');
  sel.value = state.airport;
}
async function switchAirport(a) {
  if (a === state.airport) return;
  state.airport = a; renderAirports();
  if (state.allFlights.length) { try { await call('set_airport', a); } catch (e) { toast(e.message, 'err'); } }
  applyAirportView();
  map.setView(AIRPORT_CENTER[a] || AIRPORT_CENTER.LPPT, 10);
  if (window.Analyses) Analyses.onFilter();
}
function applyAirportView() {
  state.flights = state.allFlights.filter(f => f.airport === state.airport);
  state.byId = new Map(state.flights.map(f => [f.flight_id, f]));
  state.hidden.clear(); state.selected = null; closeDetail();
  applyClsView(); renderFlightList(); renderTable(); drawTracks();
  const arr = state.flights.filter(f => f.cls === 'arr').length, dep = state.flights.filter(f => f.cls === 'dep').length;
  status(`${state.airport}: ${state.flights.length} movimento(s) · ${arr} chegadas · ${dep} partidas · ${state.days.size} dia(s) · ${fmt(state.allFlights.length)} no total (todos os aeroportos)`, 'on', $('sTime').textContent);
  $('tblInfo').textContent = `${state.flights.length} movimentos em ${state.airport}`;
}
function applyClsView() { state.hidden.clear(); const q = ($('inpCsn').value || '').trim().toLowerCase(); state.flights.forEach(f => { if ((state.clsView && f.cls !== state.clsView) || (q && !f.csn.toLowerCase().includes(q))) state.hidden.add(f.flight_id); }); }

/* ------------------------------------------------------------- Flights */
async function applyFilter() {
  if (!state.days.size) { toast('Seleciona pelo menos um dia no calendário.', 'err'); return; }
  const t0 = performance.now();
  status('A consultar…', 'busy');
  try {
    const dates = [...state.days], blocks = [...state.blocks];
    const r = await call('get_flights', dates, blocks, '', '', state.airport);
    state.allFlights = r.flights; state.airports = r.airports; state.airport = r.airport;
    const t1 = performance.now();
    const tr = await call('get_tracks', state.allFlights.map(f => f.flight_id));
    state.tracks = tr.tracks;
    const t2 = performance.now();
    renderAirports(); applyAirportView();
    status($('sTxt').textContent + (tr.step > 1 ? ` · trajetórias 1 em cada ${tr.step} plots` : ''), 'on',
      `consulta ${Math.round(t1 - t0)} ms · trajetórias ${Math.round(t2 - t1)} ms · total ${Math.round(performance.now() - t0)} ms`);
    if (window.Analyses) Analyses.onFilter();
  } catch (e) { status('Erro: ' + e.message, 'err'); toast(e.message, 'err'); }
}
function renderFlightList() {
  const list = $('flList'); list.innerHTML = '';
  const vis = state.flights.filter(f => !state.hidden.has(f.flight_id));
  $('flCount').textContent = `(${vis.length}${vis.length !== state.flights.length ? ' de ' + state.flights.length : ''})`;
  if (!state.flights.length) { list.innerHTML = '<div class="empty">Nenhum movimento com estes filtros.</div>'; return; }
  const frag = document.createDocumentFragment();
  for (const f of state.flights) {
    const hid = state.hidden.has(f.flight_id);
    if (hid && (state.clsView && f.cls !== state.clsView)) continue;
    const q = ($('inpCsn').value || '').trim().toLowerCase(); if (hid && q && !f.csn.toLowerCase().includes(q)) continue;
    const el = document.createElement('div');
    el.className = 'fl card2' + (state.selected === f.flight_id ? ' sel' : '') + (hid ? ' off' : '');
    el.dataset.id = f.flight_id;
    const arrow = f.cls === 'arr' ? '▼' : f.cls === 'dep' ? '▲' : '—';
    el.innerHTML = `<div class="top"><span class="sw" style="background:${colorFor(f)}"></span><span class="csn">${f.csn}</span><span class="badge ${f.cls}">${arrow} ${f.cls.toUpperCase()}</span>${f.actype ? `<span class="typ">${f.actype}</span>` : ''}<input type="checkbox" ${hid ? '' : 'checked'} title="Mostrar no mapa"></div>` +
      `<div class="meta">${f.n} pts · ${f.tod_first} → ${f.tod_last}${state.days.size > 1 ? ' · ' + f.date.slice(4, 6) + '/' + f.date.slice(2, 4) : ''}</div>`;
    el.querySelector('input').onclick = ev => { ev.stopPropagation(); toggleHidden(f.flight_id); };
    el.onclick = () => selectFlight(f.flight_id, true);
    frag.appendChild(el);
  }
  list.appendChild(frag);
}
function toggleHidden(id) { state.hidden.has(id) ? state.hidden.delete(id) : state.hidden.add(id); renderFlightList(); drawTracks(); }
function renderTable() {
  const tb = $('flTable').querySelector('tbody'); tb.innerHTML = '';
  const k = state.sortKey, asc = state.sortAsc ? 1 : -1;
  const rows = [...state.flights].sort((a, b) => (a[k] > b[k] ? 1 : a[k] < b[k] ? -1 : 0) * asc);
  const frag = document.createDocumentFragment();
  for (const f of rows) {
    const tr = document.createElement('tr'); tr.dataset.id = f.flight_id;
    tr.innerHTML = `<td>${f.date}</td><td><b>${f.csn}</b></td><td>${f.actype || ''}</td><td>${f.wtc || ''}</td>` +
      `<td><span class="badge ${f.cls}">${f.cls.toUpperCase()}</span></td><td>${f.tod_first}</td><td>${f.tod_last}</td>` +
      `<td>${fmt(f.alt_first)}</td><td>${fmt(f.alt_last)}</td><td>${fmt(f.alt_max)}</td><td>${f.n}</td><td>${f.blocks}</td>`;
    tr.onclick = () => { showTab('map'); selectFlight(f.flight_id, true); };
    frag.appendChild(tr);
  }
  tb.appendChild(frag);
}

/* ------------------------------------------------------------- Detail */
async function selectFlight(id, zoom) {
  state.selected = (state.selected === id) ? null : id;
  renderFlightList();
  state.layers.forEach((l, fid) => l.setStyle({ weight: fid === state.selected ? 4 : 1.6, opacity: fid === state.selected ? 1 : .75 }));
  if (state.selected == null) { closeDetail(); return; }
  const l = state.layers.get(id); if (l) { l.bringToFront(); if (zoom) map.fitBounds(l.getBounds().pad(0.2)); }
  const f = state.byId.get(id);
  try {
    const d = await call('flight_detail', id);
    openDetail(f, d.points, d);
  } catch (e) { toast(e.message, 'err'); }
}
function closeDetail() { $('detail').classList.add('hidden'); }
function openDetail(f, pts, d) {
  $('detail').classList.remove('hidden');
  $('dCsn').textContent = f.csn;
  $('dSub').textContent = `${f.date} · ${CLS_NAME[f.cls]} · ${f.actype || 'tipo ?'}${f.wtc ? ' / ' + f.wtc : ''} · Mode S ${f.modes || '—'}`;
  const dur = f.t_last - f.t_first;
  const thr = nearestThr(f.airport, [pts[pts.length - 1].lat, pts[pts.length - 1].lon]);
  const thr0 = nearestThr(f.airport, [pts[0].lat, pts[0].lon]);
  const ref = f.cls === 'dep' ? thr0 : thr;
  const refLL = (THR[f.airport] || THR.LPPT)[ref.rwy];
  const ias = pts.map(p => p.ias).filter(v => v != null);
  const kp = [[f.n, 'plots'], [`${Math.floor(dur / 60)}m${String(Math.round(dur % 60)).padStart(2, '0')}`, 'duração'],
    [`RWY ${ref.rwy}`, f.cls === 'dep' ? 'descolagem' : 'pista provável'],
    [fmt(f.alt_max), 'alt máx ft'], [ias.length ? Math.round(Math.max(...ias)) : '—', 'IAS máx kt'], [ias.length ? Math.round(Math.min(...ias)) : '—', 'IAS mín kt']];
  $('dKpis').innerHTML = kp.map(k => `<div class="kpi"><b>${k[0]}</b><span>${k[1]}</span></div>`).join('');
  const tb = $('dTbl').querySelector('tbody'); tb.innerHTML = '';
  const rows = [];
  for (const p of pts) {
    const d = haversineNm([p.lat, p.lon], refLL);
    rows.push({ d, alt: p.alt });
    tb.insertAdjacentHTML('beforeend', `<tr><td>${p.tod}</td><td>${fmt(p.alt)}</td><td>${p.ias == null ? '—' : Math.round(p.ias)}</td><td>${p.gs == null ? '—' : Math.round(p.gs)}</td><td>${p.roc == null ? '—' : Math.round(p.roc)}</td><td>${d.toFixed(1)} NM</td></tr>`);
  }
  drawProfile(rows, f);
  renderDetailViol(d);
}
function renderDetailViol(d) {
  const el = $('dViol'); if (!el) return; let h = '';
  if (d && d.final && d.final.length) h += d.final.map(r => `<div>🛬 Aterragem RWY ${r.rwy} · THR ${r.tTHRstr} · FAF ${r.tFAFstr} · IAS FAF ${C.fmt(r.iasFAF)} kt · ${r.stab ? 'estabilizada' : '<span class="bad">não estabilizada</span>'}</div>`).join('');
  if (d && d.app) { const v = d.app.points.filter(p => p.ias != null); h += '<div style="margin-top:4px"><b>Velocidades APP</b> RWY ' + d.app.rwy + ': ' + v.map(p => `${p.point} ${C.fmt(p.ias)}/${p.limit} <span class="${Math.abs(p.deviation) > d.tol && !/^THR/i.test(p.point) ? 'bad' : ''}">${p.deviation >= 0 ? '+' : ''}${C.fmt(p.deviation)}</span>`).join(' · ') + '</div>'; }
  if (d && d.star && d.star.length) h += '<div style="margin-top:4px"><b>Velocidades STAR</b>: ' + d.star.map(v => `<span class="bad">${v.wp} ${C.fmt(v.ias)}/${v.limit} (+${C.fmt(v.excess)})</span>`).join(' · ') + '</div>';
  el.innerHTML = h || '<span class="muted">Corre as análises (Final, STAR, APP) para ver avaliações deste voo.</span>';
}
function drawProfile(rows, f) {
  const c = $('dChart'), ctx = c.getContext('2d');
  const W = c.width = c.clientWidth * 2, H = c.height = 300; ctx.scale(1, 1);
  ctx.clearRect(0, 0, W, H);
  const valid = rows.filter(r => r.alt != null && r.d <= 40);
  if (valid.length < 2) return;
  const maxD = Math.max(...valid.map(r => r.d)), maxA = Math.max(...valid.map(r => r.alt), 1000);
  const px = 60, py = 20, pw = W - px - 20, ph = H - py - 40;
  ctx.strokeStyle = '#24314d'; ctx.lineWidth = 1; ctx.font = '20px Consolas,monospace'; ctx.fillStyle = '#8a93a6';
  for (let i = 0; i <= 4; i++) {
    const y = py + ph - ph * i / 4; ctx.beginPath(); ctx.moveTo(px, y); ctx.lineTo(px + pw, y); ctx.stroke();
    ctx.fillText(Math.round(maxA * i / 4 / 100) * 100, 4, y + 6);
  }
  for (let i = 0; i <= 4; i++) { const x = px + pw * i / 4; ctx.fillText((maxD * i / 4).toFixed(0) + ' NM', x - 20, H - 10); }
  // perfil 3° de referência (318 ft/NM)
  ctx.strokeStyle = '#ffd16688'; ctx.setLineDash([8, 8]); ctx.beginPath();
  ctx.moveTo(px, py + ph); ctx.lineTo(px + pw, py + ph - Math.min(ph, ph * (maxD * 318) / maxA)); ctx.stroke(); ctx.setLineDash([]);
  ctx.strokeStyle = CLS_COLOR[f.cls]; ctx.lineWidth = 3; ctx.beginPath();
  valid.forEach((r, i) => { const x = px + pw * r.d / maxD, y = py + ph - ph * r.alt / maxA; i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
  ctx.stroke();
  ctx.fillStyle = '#8a93a6'; ctx.fillText('Altitude (ft) vs distância à THR — tracejado: 3°', px, 16);
}

/* ------------------------------------------------------------- Import */
window.onImportProgress = (done, total, name) => {
  $('progress').classList.remove('hidden');
  $('progressBar').style.width = total ? (done / total * 100).toFixed(1) + '%' : '100%';
  $('progressTxt').textContent = (done ? `A importar ${done} / ${total} — ${name}` : name) + ' · podes continuar a usar a app entretanto';
};
window.onImportDone = async r => {
  $('progress').classList.add('hidden');
  if (!r.ok) { toast('Erro na importação: ' + r.error, 'err'); status('Erro na importação', 'err'); return; }
  const d = r.data;
  let msg = d.new === 0 ? `Nada de novo: os ${d.found} ficheiros já estavam importados.`
    : `${d.imported} ficheiro(s) novos importados (${fmt(d.rows)} plots) em ${(d.ms / 1000).toFixed(1)} s.`;
  if (d.errors) msg += `\n${d.errors} com erro:\n` + d.error_list.join('\n');
  toast(msg, d.errors ? 'err' : 'ok');
  await refreshState(); await loadFilters();
  if (d.new > 0 && !state.days.size) { selectLastDay(); applyFilter(); } else if (d.new > 0) renderFilters();
};
let pollT = null;
async function pollImport() {
  clearTimeout(pollT);
  try {
    const st = await call('import_status');
    if (st.result) { window.onImportDone(st.result); return; }
    if (st.importing) { window.onImportProgress(st.done, st.total, st.name); pollT = setTimeout(pollImport, 800); return; }
    $('progress').classList.add('hidden');
  } catch (e) { pollT = setTimeout(pollImport, 2000); }
}
async function importFolder(useLast) {
  try {
    let folder = null;
    if (!useLast) { folder = await call('choose_folder'); if (!folder) return; }
    const f = await call('import_folder', folder);
    $('progress').classList.remove('hidden'); $('progressBar').style.width = '0%';
    $('progressTxt').textContent = 'A procurar ficheiros CSV em ' + f + ' …';
    pollImport();
  } catch (e) { toast(e.message, 'err'); }
}

/* ------------------------------------------------------------- State */
async function refreshState() {
  const s = await call('get_state');
  $('ver').textContent = 'v' + s.version;
  $('dbFiles').textContent = fmt(s.files); $('dbRows').textContent = fmt(s.rows); $('dbFlights').textContent = fmt(s.flights);
  $('dbSize').textContent = `base ${(s.db_bytes / 1048576).toFixed(0)} MB`;
  $('dbSize').title = s.db_path + (s.log_path ? '\nRegisto: ' + s.log_path : '');
  $('btnReimport').disabled = !s.last_folder;
  if (s.last_folder) $('btnReimport').title = 'Procurar ficheiros novos em ' + s.last_folder;
  return s;
}
async function loadFilters() { state.filters = await call('get_filters'); renderFilters(); }
function selectLastDay() {
  const days = [...dayInfo().keys()].sort();
  const last = days[days.length - 1];
  state.days = new Set(last ? [last] : []); if (last) state.month = last.slice(0, 4);
  state.blocks = new Set(state.filters.blocks);
  renderFilters();
}
function showTab(name) {
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === name));
  document.querySelectorAll('.tabpane').forEach(p => p.classList.toggle('active', p.id === 'tab-' + name));
  $('mapTools').style.visibility = name === 'map' ? 'visible' : 'hidden';
  if (name === 'map') setTimeout(() => map.invalidateSize(), 50);
  if (window.Analyses) Analyses.onTab(name);
}

/* ------------------------------------------------------------- Boot */
async function boot() {
  initMap();
  try {
    const s = await refreshState();
    await loadFilters();
    const pts = await call('get_points'); state.points = pts;
    const sg = $('selGroup'); sg.innerHTML = '<option value="ALL">Todos os pontos</option>';
    for (const g of Object.keys(pts.groups)) sg.insertAdjacentHTML('beforeend', `<option value="${g}">${g}</option>`);
    drawPoints(); renderAirports();
    if (s.importing) pollImport();
    if (s.files > 0) { selectLastDay(); applyFilter(); }
    else status('Sem dados. Clica "Importar pasta…" e escolhe a pasta com os CSV do CNS.', 'on');
  } catch (e) { status(e.message, 'err'); toast(e.message, 'err'); }
}

function applyTheme(t) {
  document.documentElement.dataset.theme = t; try { localStorage.setItem('fp.theme', t); } catch (e) {}
  const b = $('btnTheme'); if (b) b.textContent = t === 'light' ? '☀' : '🌙';
}
(function () { let t = 'dark'; try { t = localStorage.getItem('fp.theme') || 'dark'; } catch (e) {} document.documentElement.dataset.theme = t; })();
window.FP = { state, call, toast, status, showTab, selectFlight, get map() { return map; }, get overlay() { return overlayGroup; }, THR, AIRPORT_CENTER, fmt };
document.addEventListener('DOMContentLoaded', () => {
  $('btnImport').onclick = () => importFolder(false);
  $('btnReimport').onclick = () => importFolder(true);
  $('btnNmir').onclick = async () => { try { const n = await call('import_nmir'); if (n != null) { toast(`${fmt(n)} registo(s) NMIR adicionados.`, 'ok'); await refreshState(); applyFilter(); } } catch (e) { toast(e.message, 'err'); } };
  $('btnFolder').onclick = () => call('open_data_folder').catch(e => toast(e.message, 'err'));
  applyTheme(document.documentElement.dataset.theme || 'dark');
  $('btnTheme').onclick = () => applyTheme(document.documentElement.dataset.theme === 'light' ? 'dark' : 'light');
  $('btnApply').onclick = applyFilter;
  $('inpCsn').oninput = () => { applyClsView(); renderFlightList(); drawTracks(); };
  $('clsBtns').querySelectorAll('.tog').forEach(b => b.onclick = () => { state.clsView = b.dataset.v; $('clsBtns').querySelectorAll('.tog').forEach(x => x.classList.toggle('on', x === b)); applyClsView(); renderFlightList(); drawTracks(); });
  $('selMonth').onchange = e => { state.month = e.target.value; renderCalendar(); };
  $('selAirportTop').onchange = e => switchAirport(e.target.value);
  $('daysAll').onclick = () => { [...dayInfo().keys()].filter(k => k.startsWith(state.month)).forEach(k => state.days.add(k)); renderCalendar(); };
  $('daysNone').onclick = () => { state.days.clear(); renderCalendar(); };
  $('blocksAll').onclick = () => { state.filters.blocks.forEach(b => state.blocks.add(b)); renderBlocks(); };
  $('blocksNone').onclick = () => { state.blocks.clear(); renderBlocks(); };
  $('flShowAll').onclick = () => { state.hidden.clear(); renderFlightList(); drawTracks(); };
  $('flHideAll').onclick = () => { state.flights.forEach(f => state.hidden.add(f.flight_id)); renderFlightList(); drawTracks(); };
  $('chkPoints').onchange = drawPoints; $('selGroup').onchange = drawPoints;
  $('chkColorCls').onchange = () => { renderFlightList(); drawTracks(); };
  $('chkTiles').onchange = e => { e.target.checked ? tiles.addTo(map) : map.removeLayer(tiles); };
  $('dClose').onclick = () => selectFlight(state.selected, false);
  $('dReport').onclick = () => { if (state.selected != null) call('report', 'voo', { flight_id: state.selected }).catch(e => toast(e.message, 'err')); };
  $('btnExport').onclick = async () => { try { const p = await call('export_flights_csv', state.airport, [...state.days], [...state.blocks], $('inpCsn').value.trim(), $('selCls').value); if (p) toast('Exportado para ' + p, 'ok'); } catch (e) { toast(e.message, 'err'); } };
  document.querySelectorAll('.tab').forEach(t => t.onclick = () => showTab(t.dataset.tab));
  document.querySelectorAll('.subtab').forEach(t => t.onclick = () => { const par = t.parentElement; par.querySelectorAll('.subtab').forEach(x => x.classList.toggle('active', x === t)); par.parentElement.querySelectorAll('.subpane').forEach(p => p.classList.toggle('active', p.id === 'sub-' + t.dataset.sub)); if (window.Analyses) Analyses.onSub(t.dataset.sub); });
  document.querySelectorAll('#flTable th').forEach(th => th.onclick = () => { const k = th.dataset.k; state.sortAsc = state.sortKey === k ? !state.sortAsc : true; state.sortKey = k; renderTable(); });
  if (useHttp || api()) boot(); else window.addEventListener('pywebviewready', boot);
});
