/* FlightTracker 4 — aba Solo: movimentos no solo (ficheiro da torre / A-SMGCS), rede de taxiways OSM,
   reconstrução do percurso stand ↔ pista e animação do dia; ROT e tempos de taxi. */
'use strict';
const Ground = (() => {
  const $ = id => document.getElementById(id);
  const { esc, fmt } = C;
  const call = (...a) => FP.call(...a);
  const toast = (m, k) => FP.toast(m, k);
  const COL = { DEPARTURE: '#ff9b2f', ARRIVAL: '#3b9cff' };

  let map = null, base = null, netGroup = null, lblGroup = null, standGroup = null, acGroup = null, routeGroup = null, trailGroup = null;
  let net = null;                 // rede (ways, stands, thr)
  let rows = [];                  // movimentos do dia
  let routes = {};                // gid -> {pts, t, t0, t1, kind, csn}
  let stats = null;
  let sel = null;                 // gid seleccionado
  let simT = 0, playing = false, lastFrame = 0, raf = null, sub = 'mov', dayEpoch = 0;
  const markers = new Map();      // gid -> marker
  const rmarkers = new Map();     // flight_id -> marker (radar)
  let radar = {};                 // flight_id -> {pts:[[lat,lon]], t:[epoch], alt:[], csn, cls, g0, g1}
  let linkByFid = {};             // flight_id -> gid (ligação torre↔radar)
  let loadedKey = '';

  /* ---------------------------------------------------------------- mapa */
  function ensureMap() {
    if (map) return;
    map = L.map('gdMap', { zoomControl: true, preferCanvas: true }).setView([38.781, -9.135], 14);
    setBase('osm');
    netGroup = L.layerGroup().addTo(map); lblGroup = L.layerGroup().addTo(map); standGroup = L.layerGroup();
    routeGroup = L.layerGroup().addTo(map); trailGroup = L.layerGroup().addTo(map); acGroup = L.layerGroup().addTo(map);
    map.on('zoomend', () => { if ($('gdLabels').checked) drawLabels(); });
    setTimeout(fitAirport, 100);
    $('gdBase').onchange = e => setBase(e.target.value);
    $('gdLabels').onchange = e => { e.target.checked ? drawLabels() : lblGroup.clearLayers(); };
    $('gdStands').onchange = e => { e.target.checked ? standGroup.addTo(map) : map.removeLayer(standGroup); };
  }
  function fitAirport() { if (map) map.fitBounds([[38.762, -9.150], [38.800, -9.120]], { padding: [10, 10] }); }
  function setBase(k) {
    if (base) { map.removeLayer(base); base = null; }
    if (k === 'sat') base = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', { attribution: '© Esri', maxZoom: 19 });
    else if (k === 'osm') base = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '© OpenStreetMap', maxZoom: 19 });
    if (base) base.addTo(map);
  }
  async function loadNetwork() {
    if (net) return;
    net = await call('ground_network');
    netGroup.clearLayers(); standGroup.clearLayers();
    for (const w of net.ways) {
      if (w.pts.length < 2) continue;
      L.polyline(w.pts, { color: w.type === 'runway' ? '#64748b' : '#d97706', weight: w.type === 'runway' ? 6 : 2, opacity: w.type === 'runway' ? .45 : .75, interactive: false }).addTo(netGroup);
    }
    for (const [name, p] of Object.entries(net.stands)) {
      L.circleMarker(p, { radius: 3, color: '#9fd1ff', fillOpacity: .9, weight: 1 }).bindTooltip(`Stand ${name}`).addTo(standGroup);
      L.marker(p, { icon: L.divIcon({ className: 'stand-lbl', html: name, iconSize: [24, 10], iconAnchor: [-4, 4] }), interactive: false }).addTo(standGroup);
    }
    if ($('gdLabels').checked) drawLabels();
  }
  function drawLabels() {
    lblGroup.clearLayers();
    if (!net || map.getZoom() < 14) return;
    const seen = new Set();
    for (const w of net.ways) {
      if (!w.ref || w.type === 'runway' || w.pts.length < 2) continue;
      const key = w.ref; if (seen.has(key) && map.getZoom() < 16) continue; seen.add(key);
      const m = w.pts[Math.floor(w.pts.length / 2)];
      L.marker(m, { icon: L.divIcon({ className: 'twy-lbl', html: esc(w.ref), iconSize: [30, 12], iconAnchor: [15, 6] }), interactive: false }).addTo(lblGroup);
    }
  }

  /* ---------------------------------------------------------------- dados */
  async function load(force) {
    const key = [...FP.state.days].sort().join(',') + '|' + FP.state.airport;
    if (!force && key === loadedKey) return;
    ensureMap();
    const body = $('gdBody');
    if (FP.state.airport !== 'LPPT') { body.innerHTML = '<div class="empty">A vista de solo está disponível só para Lisboa (LPPT) nesta versão.</div>'; rows = []; routes = {}; clearAnim(); return; }
    if (!FP.state.days.size) { body.innerHTML = '<div class="empty">Aplica um filtro com pelo menos um dia.</div>'; return; }
    body.innerHTML = '<div class="empty">⏳ A carregar movimentos no solo…</div>';
    try {
      await loadNetwork();
      const r = await call('ground_list');
      rows = r.rows; stats = r.stats; loadedKey = key;
      $('gdInfo').textContent = r.summary.rows ? `${fmt(r.summary.rows)} movimentos da torre na base (${fmtD(r.summary.from)} → ${fmtD(r.summary.to)})` : 'Sem ficheiro da torre importado';
      clearAnim();
      routes = rows.length ? await call('ground_routes', rows.filter(x => x.routable).map(x => x.gid)) : {};
      const days = [...FP.state.days].sort();
      dayEpoch = epochOf(days[0]);
      buildRadar();
      const rt = Object.values(radar).flatMap(r => [r.t[0], r.t[r.t.length - 1]]);
      const t0 = Math.min(...rows.map(x => x.t_ref || Infinity), ...rt), t1 = Math.max(...rows.map(x => x.t_ref || 0), ...rt);
      $('gdTime').min = Math.max(0, Math.floor(t0 - dayEpoch) - 900); $('gdTime').max = Math.ceil(t1 - dayEpoch) + 900;
      setSim(+$('gdTime').min);
      $('gdCount').textContent = `${rows.length} movimentos · ${Object.keys(routes).length} com percurso · ${Object.keys(radar).length} trajetórias radar`;
      if (!rows.length) body.innerHTML = `<div class="empty">Sem movimentos da torre para os dias seleccionados${r.summary.rows ? ' — o ficheiro importado cobre ' + fmtD(r.summary.from) + ' a ' + fmtD(r.summary.to) : ''}. A animação mostra só o radar.</div>`;
      else renderSub();
      fitAirport();
    } catch (e) { body.innerHTML = `<div class="empty">Erro: ${esc(e.message)}</div>`; toast(e.message, 'err'); }
  }
  const epochOf = d => Date.UTC(2000 + +d.slice(0, 2), +d.slice(2, 4) - 1, +d.slice(4, 6)) / 1000;
  const fmtD = d => d ? `${d.slice(4, 6)}/${d.slice(2, 4)}/20${d.slice(0, 2)}` : '—';
  const hms = t => { if (t == null) return '—'; const s = Math.round(t - dayEpoch); const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60; return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(x).padStart(2, '0')}`; };
  const dur = s => s == null ? '—' : s >= 120 ? `${Math.floor(s / 60)}m${String(Math.round(s % 60)).padStart(2, '0')}` : `${Math.round(s)} s`;

  /* ---------------------------------------------------------------- tabelas */
  function renderSub() {
    const body = $('gdBody');
    if (sub === 'mov') {
      body.innerHTML = C.table([
        { k: 'mt', label: 'Mov.', fmt: v => `<span class="badge ${v === 'DEPARTURE' ? 'dep' : 'arr'}">${v === 'DEPARTURE' ? 'DEP' : 'ARR'}</span>` },
        { k: 'csn', label: 'Voo', fmt: (v, r) => `<b>${esc(v)}</b>${r.ga ? ' <span class="badge lvl" title="Go-around">GA</span>' : ''}` },
        { k: 'actype', label: 'Tipo' }, { k: 'wtc', label: 'WTC' }, { k: 'rwy', label: 'RWY' },
        { k: 'stand', label: 'Stand', fmt: (v, r) => esc(r.mt === 'DEPARTURE' ? r.stand_d || '' : r.stand_a || '') },
        { k: 'route', label: 'Taxi', fmt: (v, r) => `<span class="mono">${esc(r.mt === 'DEPARTURE' ? r.taxi_out || '' : r.taxi_in || '')}</span>` },
        { k: 'hpep', label: 'HP / saída', fmt: (v, r) => esc(r.mt === 'DEPARTURE' ? r.hp || '' : r.ep || '') },
        { k: 'tA', label: 'Off/On-block', fmt: (v, r) => hms(r.mt === 'DEPARTURE' ? r.aobt : r.aibt) },
        { k: 'tB', label: 'RWY ent. / ALDT', fmt: (v, r) => hms(r.mt === 'DEPARTURE' ? r.rwy_ent : r.aldt) },
        { k: 'tC', label: 'ATOT / RWY vac.', fmt: (v, r) => hms(r.mt === 'DEPARTURE' ? r.atot : r.rwy_vac) },
        { k: 'taxi_s', label: 'Taxi', fmt: v => dur(v) }, { k: 'rot_s', label: 'ROT', fmt: v => v == null ? '—' : `<span class="${v > 90 ? 'sep-r' : v > 70 ? 'sep-o' : 'sep-g'}">${Math.round(v)} s</span>` },
        { k: 'adep', label: 'De / para', fmt: (v, r) => esc(r.mt === 'DEPARTURE' ? r.ades || '' : r.adep || '') },
        { k: 'flight_id', label: 'Radar', fmt: v => v ? `<a href="#" class="csn-link" data-fid="${v}">ver</a>` : '<span class="muted">—</span>' },
      ], rows, { id: 'gdTable', limit: 3000, rowClass: r => 'gd-row' + (r.gid === sel ? ' sel' : '') });
      body.onclick = ev => {
        if (ev.target.classList.contains('csn-link')) { ev.preventDefault(); FP.focusFlight(+ev.target.dataset.fid); return; }
        const tr = ev.target.closest('tr[data-i]'); if (tr) select(rows[+tr.dataset.i].gid);
      };
    } else { body.onclick = null; renderStats(); }
  }
  function renderStats() {
    const s = stats, body = $('gdBody'); if (!s) { body.innerHTML = '<div class="empty">Sem dados.</div>'; return; }
    const st = (o, unit = 's') => o && o.n ? `${Math.round(o.median)} ${unit}` : '—';
    const tbl = (list, keyLabel) => C.table([{ k: 'key', label: keyLabel }, { k: 'n', label: 'N' }, { k: 'median', label: 'Mediana (s)', fmt: v => v == null ? '—' : Math.round(v) },
      { k: 'mean', label: 'Média (s)', fmt: v => v == null ? '—' : Math.round(v) }, { k: 'p10', label: 'P10', fmt: v => v == null ? '—' : Math.round(v) }, { k: 'p90', label: 'P90', fmt: v => v == null ? '—' : Math.round(v) },
      { k: 'max', label: 'Máx', fmt: v => v == null ? '—' : Math.round(v) }], list.filter(x => x.n));
    const arrR = rows.filter(r => r.mt !== 'DEPARTURE'), depR = rows.filter(r => r.mt === 'DEPARTURE');
    const byRot = (list) => list.filter(r => r.rot_s != null).slice().sort((a, b) => b.rot_s - a.rot_s), byTaxi = list => list.filter(r => r.taxi_s != null).slice().sort((a, b) => b.taxi_s - a.taxi_s);
    Drill.scope('solo', { 'Chegadas': { title: 'Chegadas (torre)', rows: arrR }, 'Partidas': { title: 'Partidas (torre)', rows: depR }, 'Go-arounds': { title: 'Go-arounds (torre)', rows: rows.filter(r => r.ga) },
      'ROT chegada': { title: 'ROT por chegada (decrescente)', rows: byRot(arrR) }, 'ROT partida': { title: 'ROT por partida (decrescente)', rows: byRot(depR) }, 'Taxi-in': { title: 'Taxi-in por chegada (decrescente)', rows: byTaxi(arrR) }, 'Taxi-out': { title: 'Taxi-out por partida (decrescente)', rows: byTaxi(depR) },
      'Vel. na saída': { title: 'Velocidade na saída de pista por chegada', rows: arrR.filter(r => r.spd_vac != null).slice().sort((a, b) => b.spd_vac - a.spd_vac) } });
    let h = '<div class="kgrid">' + C.kcard('Chegadas', s.n_arr) + C.kcard('Partidas', s.n_dep) + C.kcard('Go-arounds', s.ga, '', s.ga ? 'warn' : '') +
      C.kcard('ROT chegada', st(s.rot_arr), `ALDT → saída de pista · mediana · n=${s.rot_arr.n}`) + C.kcard('ROT partida', st(s.rot_dep), `entrada na pista → ATOT · n=${s.rot_dep.n}`) +
      C.kcard('Taxi-in', s.taxi_in.n ? dur(s.taxi_in.median) : '—', `saída de pista → on-block · n=${s.taxi_in.n}`) + C.kcard('Taxi-out', s.taxi_out.n ? dur(s.taxi_out.median) : '—', `off-block → ATOT · n=${s.taxi_out.n}`) +
      (s.spd_vac.n ? C.kcard('Vel. na saída', `${Math.round(s.spd_vac.median)} kt`, `mediana · n=${s.spd_vac.n}`) : '') + '</div>';
    h += '<div class="grid2">' + C.card('ROT chegadas — distribuição (s)', C.bars(s.rot_arr_hist.counts, s.rot_arr_hist.labels, { color: C.BLUE })) +
      C.card('ROT partidas — distribuição (s)', C.bars(s.rot_dep_hist.counts, s.rot_dep_hist.labels, { color: C.ORANGE })) + '</div>';
    h += '<div class="grid2">' + C.card('ROT chegadas por saída de pista', tbl(s.rot_arr_by_ep, 'Saída')) + C.card('ROT chegadas por WTC', tbl(s.rot_arr_by_wtc, 'WTC')) +
      C.card('ROT partidas por ponto de espera', tbl(s.rot_dep_by_hp, 'HP')) + C.card('ROT partidas por WTC', tbl(s.rot_dep_by_wtc, 'WTC')) +
      C.card('ROT chegadas por pista', tbl(s.rot_arr_by_rwy, 'RWY')) + C.card('ROT partidas por pista', tbl(s.rot_dep_by_rwy, 'RWY')) +
      C.card('Taxi-in por stand (15 mais usados)', tbl(s.taxi_in_by_stand, 'Stand')) + C.card('Taxi-out por stand (15 mais usados)', tbl(s.taxi_out_by_stand, 'Stand')) + '</div>';
    h += '<p class="hint">ROT = tempo de ocupação de pista medido pelo A-SMGCS: chegadas ALDT → RWY_VAC; partidas RWY_ENT → ATOT. Valores &gt; 30 min ignorados. Fonte: export operacional da torre.</p>';
    body.innerHTML = h;
  }

  /* ---------------------------------------------------------------- selecção e animação */
  function select(gid, o = {}) {
    sel = gid === sel ? null : gid;
    document.querySelectorAll('#gdTable tr[data-i]').forEach(tr => {
      const on = rows[+tr.dataset.i].gid === sel; tr.classList.toggle('sel', on);
      if (on && o.scrollTable) tr.scrollIntoView({ block: 'center' });
    });
    if (o.scrollTable && sub !== 'mov') { sub = 'mov'; document.querySelectorAll('[data-gsub]').forEach(x => x.classList.toggle('active', x.dataset.gsub === 'mov')); renderSub(); }
    routeGroup.clearLayers();
    if (sel == null) return;
    const r = routes[sel], row = rows.find(x => x.gid === sel);
    if (!r) { toast('Sem percurso reconstruído para este movimento (sem sequência de taxi).', 'err'); return; }
    L.polyline(r.pts, { color: COL[r.mt] || '#fff', weight: 4, opacity: .9 }).addTo(routeGroup);
    L.circleMarker(r.pts[0], { radius: 5, color: '#35c46a', fillOpacity: 1 }).bindTooltip('início ' + hms(r.t0)).addTo(routeGroup);
    L.circleMarker(r.pts[r.pts.length - 1], { radius: 5, color: '#ff5d5d', fillOpacity: 1 }).bindTooltip('fim ' + hms(r.t1)).addTo(routeGroup);
    if (!o.keepTime) { map.fitBounds(L.latLngBounds(r.pts).pad(.3)); setSim(r.t0 - dayEpoch + 1); }
    else drawFrame();
  }
  function posAt(r, t) {
    const T = r.t, P = r.pts;
    if (t <= T[0]) return P[0]; if (t >= T[T.length - 1]) return P[P.length - 1];
    let lo = 0, hi = T.length - 1;
    while (hi - lo > 1) { const m = (lo + hi) >> 1; (T[m] <= t ? lo = m : hi = m); }
    const f = T[hi] > T[lo] ? (t - T[lo]) / (T[hi] - T[lo]) : 0;
    return [P[lo][0] + (P[hi][0] - P[lo][0]) * f, P[lo][1] + (P[hi][1] - P[lo][1]) * f];
  }
  function setSim(s) {
    simT = s; $('gdTime').value = Math.round(s); $('gdClock').textContent = hms(dayEpoch + s);
    drawFrame();
  }
  function drawFrame() {
    if (!map) return;
    const t = dayEpoch + simT, trails = $('gdTrails').checked;
    trailGroup.clearLayers();
    const active = new Set();
    for (const [gid, r] of Object.entries(routes)) {
      if (t < r.t0 - 5 || t > r.t1 + 20) continue;
      active.add(+gid);
      const p = posAt(r, t);
      let mk = markers.get(+gid);
      if (!mk) {
        mk = L.marker(p, { icon: L.divIcon({ className: 'gd-ac', html: `<div class="dot" style="background:${COL[r.mt]}"></div><div class="lbl">${esc(r.csn)}</div>`, iconSize: [10, 10], iconAnchor: [5, 5] }) });
        mk.on('click', () => select(+gid, { keepTime: true, scrollTable: true })); mk.addTo(acGroup); markers.set(+gid, mk);
      } else mk.setLatLng(p);
      mk.getElement()?.classList.toggle('sel', +gid === sel);
      if (trails) {
        const pts = []; for (let i = 0; i < r.t.length; i++) { if (r.t[i] > t) break; if (r.t[i] >= t - 90) pts.push(r.pts[i]); }
        pts.push(p);
        if (pts.length > 1) L.polyline(pts, { color: COL[r.mt], weight: 2, opacity: .7, interactive: false }).addTo(trailGroup);
      }
    }
    for (const [gid, mk] of markers) if (!active.has(gid)) { acGroup.removeLayer(mk); markers.delete(gid); }
    // radar (ar)
    const ractive = new Set();
    if ($('gdRadar').checked) {
      for (const [fid, r] of Object.entries(radar)) {
        if (t < r.t[0] || t > r.t[r.t.length - 1]) continue;
        if (r.g0 != null && t >= r.g0) continue;          // já está no solo (torre)
        if (r.g1 != null && t <= r.g1) continue;          // ainda no solo (torre)
        ractive.add(+fid);
        const p = posAt(r, t);
        let mk = rmarkers.get(+fid);
        const i = Math.max(0, r.t.findIndex(x => x >= t) - 1), alt = r.alt[i];
        if (!mk) {
          mk = L.marker(p, { icon: L.divIcon({ className: 'gd-ac radar', html: `<div class="dot" style="background:${r.cls === 'dep' ? '#ff9b2f' : r.cls === 'arr' ? '#3b9cff' : '#8a93a6'};border-radius:2px"></div><div class="lbl">${esc(r.csn)}<span class="alt"></span></div>`, iconSize: [10, 10], iconAnchor: [5, 5] }) });
          mk.on('click', () => FP.focusFlight(+fid)); mk.addTo(acGroup); rmarkers.set(+fid, mk);
        } else mk.setLatLng(p);
        const el = mk.getElement(); if (el) { const a = el.querySelector('.alt'); if (a) a.textContent = alt != null ? ` ${Math.round(alt / 100)}` : ''; }
        if (trails) { const pts = []; for (let k = 0; k < r.t.length; k++) { if (r.t[k] > t) break; if (r.t[k] >= t - 120) pts.push(r.pts[k]); } pts.push(p); if (pts.length > 1) L.polyline(pts, { color: r.cls === 'dep' ? '#ff9b2f' : '#3b9cff', weight: 1.5, opacity: .6, dashArray: '3 3', interactive: false }).addTo(trailGroup); }
      }
    }
    for (const [fid, mk] of rmarkers) if (!ractive.has(fid)) { acGroup.removeLayer(mk); rmarkers.delete(fid); }
  }
  /* trajetórias radar do dia (já carregadas pelo Mapa: FP.state.tracks com tod_sec no índice 8) */
  function buildRadar() {
    radar = {}; linkByFid = {};
    for (const r of rows) if (r.flight_id && routes[r.gid]) linkByFid[r.flight_id] = r.gid;
    for (const f of FP.state.allFlights) {
      if (f.airport !== FP.state.airport) continue;
      const pts = FP.state.tracks[f.flight_id]; if (!pts || pts.length < 2) continue;
      const base = epochOf(f.date);
      const g = linkByFid[f.flight_id] ? routes[linkByFid[f.flight_id]] : null;
      radar[f.flight_id] = { pts: pts.map(p => [p[0], p[1]]), t: pts.map(p => base + (p[8] ?? 0)), alt: pts.map(p => p[2]), csn: f.csn, cls: f.cls,
        g0: g && f.cls === 'arr' ? g.t0 : null, g1: g && f.cls === 'dep' ? g.t1 : null };   // handoff: chegada some ao aterrar (t0 do solo); partida só aparece após ATOT (t1 do solo)
    }
  }
  function clearAnim() { stop(); markers.forEach(m => acGroup && acGroup.removeLayer(m)); markers.clear(); rmarkers.forEach(m => acGroup && acGroup.removeLayer(m)); rmarkers.clear(); routeGroup && routeGroup.clearLayers(); trailGroup && trailGroup.clearLayers(); sel = null; }
  function tick(ts) {
    if (!playing) return;
    const dt = lastFrame ? (ts - lastFrame) / 1000 : 0; lastFrame = ts;
    let s = simT + dt * (+$('gdSpeed').value);
    if (s > +$('gdTime').max) { s = +$('gdTime').max; stop(); }
    setSim(s);
    if (playing) raf = requestAnimationFrame(tick);
  }
  function play() { if (!Object.keys(routes).length) return; playing = true; lastFrame = 0; $('gdPlay').textContent = '⏸'; raf = requestAnimationFrame(tick); }
  function stop() { playing = false; $('gdPlay').textContent = '▶'; if (raf) cancelAnimationFrame(raf); raf = null; }

  /* ---------------------------------------------------------------- ligações */
  function onTab() { const first = !map; ensureMap(); setTimeout(() => { map.invalidateSize(); if (first) fitAirport(); }, 80); load(false); }
  function onFilter() { loadedKey = ''; if (document.querySelector('.tab.active')?.dataset.tab === 'solo') load(true); }
  function initSplitter() {
    const h = $('gdHandle'), left = $('gdLeft'), split = $('gdSplit');
    try { const w = localStorage.getItem('fp.gdLeft'); if (w) left.style.width = w; } catch (e) {}
    let drag = false;
    h.onmousedown = e => { drag = true; h.classList.add('on'); e.preventDefault(); };
    document.addEventListener('mousemove', e => {
      if (!drag) return;
      const r = split.getBoundingClientRect(); const w = Math.max(260, Math.min(r.width - 320, e.clientX - r.left));
      left.style.width = w + 'px'; if (map) map.invalidateSize();
    });
    document.addEventListener('mouseup', () => { if (!drag) return; drag = false; h.classList.remove('on'); try { localStorage.setItem('fp.gdLeft', left.style.width); } catch (e) {} if (map) map.invalidateSize(); });
    h.ondblclick = () => { left.style.width = '46%'; try { localStorage.removeItem('fp.gdLeft'); } catch (e) {} if (map) map.invalidateSize(); };
  }
  document.addEventListener('DOMContentLoaded', () => {
    initSplitter();
    $('gdPlay').onclick = () => playing ? stop() : play();
    $('gdTime').oninput = e => { stop(); setSim(+e.target.value); };
    $('gdRadar').onchange = drawFrame;
    document.querySelectorAll('[data-gsub]').forEach(b => b.onclick = () => { document.querySelectorAll('[data-gsub]').forEach(x => x.classList.toggle('active', x === b)); sub = b.dataset.gsub; renderSub(); });
    $('gdImport').onclick = async () => {
      try {
        const r = await call('import_ground'); if (!r) return;
        toast(`${fmt(r.rows)} movimentos importados de ${r.files} ficheiro(s) (${fmtD(r.from)} → ${fmtD(r.to)}).`, 'ok');
        loadedKey = ''; load(true);
      } catch (e) { toast(e.message, 'err'); }
    };
    $('gdExport').onclick = async () => { try { const p = await call('export', 'ground', {}, null); if (p) toast('Exportado para ' + p, 'ok'); } catch (e) { toast(e.message, 'err'); } };
  });
  /* ================================================================ Cruzamento de fontes */
  let cross = null, crossKey = '';
  const hmsAbs = t => t == null ? '—' : new Date(t * 1000).toISOString().slice(11, 19);
  function crossRender() {
    const body = $('crBody'); if (!cross) return;
    const c = cross.coverage, filt = $('crFilter').value, q = ($('crCsn').value || '').trim().toUpperCase();
    let rows = cross.rows;
    if (filt === 'flags') rows = rows.filter(r => r.n_flags);
    else if (filt === 'noradar') rows = rows.filter(r => !r.src.includes('R'));
    else if (filt === 'notorre') rows = rows.filter(r => !r.src.includes('T'));
    else if (filt === 'noopdi') rows = rows.filter(r => !r.src.includes('O'));
    else if (filt === 'all3') rows = rows.filter(r => r.src.includes('R') && r.src.includes('T') && r.src.includes('O'));
    if (q) rows = rows.filter(r => r.csn.includes(q));
    const pct = (a, b) => b ? ` (${Math.round(a / b * 100)}%)` : '';
    const A = cross.rows, has = k => r => r.src.includes(k), only = k => r => r.src.replace('N', '') === k;
    const ccols = [{ k: 'date', label: 'Data', fmt: fmtD }, { k: 'csn', label: 'Voo', fmt: (v, r) => r.flight_id ? `<a href="#" class="csn-link" data-fid="${r.flight_id}"><b>${esc(v)}</b></a>` : `<b>${esc(v)}</b>` }, { k: 'cls', label: 'Mov.', fmt: v => v.toUpperCase() }, { k: 'src', label: 'Fontes' }, { k: 'flags', label: 'Discrepâncias', fmt: v => v.filter(f => !f.startsWith('sem ')).join('; ') || '—' },
      { k: 'n_type', label: 'Tipo NMIR', fmt: v => v || '—' }, { k: 't_type', label: 'Tipo torre', fmt: v => v || '—' }, { k: 'o_type', label: 'Tipo OPDI', fmt: v => v || '—' }, { k: 't_reg', label: 'Matrícula', fmt: (v, r) => v || r.o_reg || '—' }, { k: 't_rwy', label: 'RWY', fmt: v => v || '—' }, { k: 't_stand', label: 'Stand', fmt: v => v || '—' }];
    const cs = (title, f) => ({ title, cols: ccols, rows: A.filter(f) });
    Drill.scope('cross', { 'Movimentos': cs('Todos os movimentos (união das fontes)', () => true), 'Radar': cs('Movimentos com radar', has('R')), 'Torre': cs('Movimentos com torre', has('T')), 'OPDI': cs('Movimentos com OPDI', has('O')),
      'Radar ∩ Torre': cs('Radar e torre', r => has('R')(r) && has('T')(r)), 'Radar ∩ OPDI': cs('Radar e OPDI', r => has('R')(r) && has('O')(r)), 'Torre ∩ OPDI': cs('Torre e OPDI', r => has('T')(r) && has('O')(r)), 'Nas 3': cs('Nas três fontes', r => has('R')(r) && has('T')(r) && has('O')(r)),
      'Com NMIR': cs('Com registo NMIR', has('N')), 'Discrepâncias': cs('Movimentos com discrepâncias', r => r.n_flags), 'Só radar': cs('Só radar', only('R')), 'Só torre': cs('Só torre', only('T')), 'Só OPDI': cs('Só OPDI', only('O')),
      'Δt radar−torre': { title: 'Δt radar − torre por movimento', cols: [...ccols, { k: 'dt_radar_torre', label: 'Δt (s)' }], rows: A.filter(r => r.dt_radar_torre != null).sort((a, b) => Math.abs(b.dt_radar_torre) - Math.abs(a.dt_radar_torre)) },
      'Δt OPDI−torre': { title: 'Δt OPDI − torre por movimento', cols: [...ccols, { k: 'dt_opdi_torre', label: 'Δt (s)' }], rows: A.filter(r => r.dt_opdi_torre != null).sort((a, b) => Math.abs(b.dt_opdi_torre) - Math.abs(a.dt_opdi_torre)) } });
    let h = '<div class="kgrid">' + C.kcard('Movimentos', c.total, 'união das fontes') + C.kcard('Radar', c.radar) + C.kcard('Torre', c.torre) + C.kcard('OPDI', c.opdi) +
      C.kcard('Radar ∩ Torre', c.r_t + pct(c.r_t, c.radar)) + C.kcard('Radar ∩ OPDI', c.r_o + pct(c.r_o, c.radar)) + C.kcard('Torre ∩ OPDI', c.t_o + pct(c.t_o, c.torre)) + C.kcard('Nas 3', c.all3) +
      C.kcard('Com NMIR', c.nmir + pct(c.nmir, c.total)) + C.kcard('Discrepâncias', c.with_flags, `tipo ${c.type_mismatch} · ADEP/ADES ${c.apt_mismatch}`, c.with_flags ? 'warn' : 'ok') +
      C.kcard('Só radar', c.only_radar) + C.kcard('Só torre', c.only_torre) + C.kcard('Só OPDI', c.only_opdi) +
      (c.dt_radar_torre_med != null ? C.kcard('Δt radar−torre', `${c.dt_radar_torre_med} s`, 'mediana · 1º plot − ATOT / último plot − ALDT') : '') +
      (c.dt_opdi_torre_med != null ? C.kcard('Δt OPDI−torre', `${c.dt_opdi_torre_med} s`, 'mediana · evento de pista OPDI − ATOT/ALDT') : '') + '</div>';
    const srcB = s => ['R', 'N', 'T', 'O'].map(k => `<span class="src ${s.includes(k) ? 'on' : ''}">${k}</span>`).join('');
    h += C.table([
      { k: 'corr', label: '✎', fmt: (v, r) => `<button class="btn sm cr-fix" data-i="${rows.indexOf(r)}" title="Registar o valor correto / marcar como verificado">${v ? '✓ ' + esc([v.actype, v.apt, v.wtc && !v.actype ? 'WTC ' + v.wtc : ''].filter(Boolean).join(' ') || 'verificado') : '✎'}</button>` },
      { k: 'date', label: 'Data', fmt: v => fmtD(v) }, { k: 'csn', label: 'Voo', fmt: (v, r) => r.flight_id ? `<a href="#" class="csn-link" data-fid="${r.flight_id}"><b>${esc(v)}</b></a>` : `<b>${esc(v)}</b>` },
      { k: 'cls', label: 'Mov.', fmt: v => `<span class="badge ${v}">${v.toUpperCase()}</span>` }, { k: 'src', label: 'Fontes', fmt: srcB },
      { k: 'flags', label: 'Discrepâncias', fmt: v => v.filter(f => !f.startsWith('sem ')).map(f => `<span class="flag">${esc(f)}</span>`).join(' ') },
      { k: 'n_type', label: 'Tipo NMIR', fmt: (v, r) => v ? `${esc(v)}${r.n_src !== 'nmir' ? '<span class="muted" title="tipo herdado de outro dia">*</span>' : ''}` : '—' }, { k: 't_type', label: 'Tipo torre', fmt: v => v || '—' }, { k: 'o_type', label: 'Tipo OPDI', fmt: v => v || '—' },
      { k: 't_reg', label: 'Matrícula', fmt: (v, r) => esc(v || r.o_reg || '—') }, { k: 'o_icao24', label: 'icao24', fmt: v => v || '—' },
      { k: 'n_apt', label: 'ADEP/ADES', fmt: (v, r) => { const a = [r.cls === 'arr' ? r.n_adep : r.n_ades, r.t_apt, r.cls === 'arr' ? r.o_adep : r.o_ades].map(x => x || '·'); return `<span class="mono" title="NMIR / torre / OPDI">${a.join(' / ')}</span>`; } },
      { k: 't_rwy', label: 'RWY', fmt: v => v || '—' }, { k: 't_stand', label: 'Stand', fmt: v => v || '—' },
      { k: 'r_t_first', label: 'Radar 1º/últ.', fmt: (v, r) => r.flight_id ? `${hmsAbs(r.r_t_first)}–${hmsAbs(r.r_t_last)}` : '—' },
      { k: 't_atot', label: 'Torre ATOT/ALDT', fmt: (v, r) => hmsAbs(r.cls === 'dep' ? r.t_atot : r.t_aldt) },
      { k: 'o_rwy_in', label: 'OPDI pista', fmt: (v, r) => hmsAbs(r.cls === 'dep' ? r.o_rwy_out : r.o_rwy_in) },
      { k: 'dt_radar_torre', label: 'Δt R−T', fmt: v => v == null ? '—' : `${v > 0 ? '+' : ''}${v} s` }, { k: 'dt_opdi_torre', label: 'Δt O−T', fmt: v => v == null ? '—' : `${v > 0 ? '+' : ''}${v} s` },
      { k: 't_rot', label: 'ROT torre', fmt: v => v == null ? '—' : Math.round(v) + ' s' }, { k: 'o_rot', label: 'ROT OPDI', fmt: v => v == null ? '—' : Math.round(v) + ' s' },
      { k: 't_taxi', label: 'Taxi', fmt: v => dur(v) }, { k: 'o_tod', label: 'TOD', fmt: v => hmsAbs(v) }, { k: 'o_levels_low', label: 'Pat. <FL100', fmt: v => v == null ? '—' : v },
    ], rows, { id: 'crTable', limit: 4000 });
    body.innerHTML = h + `<p class="hint">R = radar CNS · N = NMIR · T = ficheiro da torre (A-SMGCS) · O = OPDI (OpenSky). Emparelhamento por callsign + data + tipo de movimento, com o instante mais próximo (janela 20 min). Tipo NMIR com * = herdado de outro dia (não conta como discrepância). O ROT do OPDI nas chegadas é aproximado (o evento de saída de pista é detetado tarde por falta de cobertura ADS-B no solo).</p>`;
    body.querySelectorAll('.csn-link').forEach(a => a.onclick = ev => { ev.preventDefault(); FP.focusFlight(+a.dataset.fid); });
    body.querySelectorAll('.cr-fix').forEach(b => b.onclick = ev => { ev.stopPropagation(); openFix(rows[+b.dataset.i]); });
    body.querySelectorAll('#crTable tbody tr').forEach(tr => { tr.classList.add('clk'); tr.onclick = ev => { if (ev.target.closest('a,button')) return; openDetail(rows[+tr.dataset.i]); }; });
    $('crInfo').textContent = `${rows.length} de ${cross.rows.length} linhas${c.corrected ? ` · ${c.corrected} corrigidas/verificadas` : ''}`;
  }
  function openDetail(r) {
    const T = t => hmsAbs(t), D = s => s == null ? '—' : dur(s), V = v => v == null || v === '' ? '—' : esc(String(v));
    const sec = (title, pairs, on) => `<div class="card ${on ? '' : 'off'}"><h3>${title}${on ? '' : ' <span class="muted">(sem dados)</span>'}</h3>` +
      (on ? `<table class="d-tbl"><tbody>${pairs.map(([k, v]) => `<tr><td class="muted">${k}</td><td><b>${v}</b></td></tr>`).join('')}</tbody></table>` : '') + '</div>';
    const o = r.cls === 'arr';
    $('modalTitle').textContent = `${r.csn} · ${fmtD(r.date)} · ${r.cls === 'arr' ? 'chegada' : 'partida'} · fontes ${r.src}`;
    $('modalBody').innerHTML = (r.flags.length ? `<p>${r.flags.map(f => `<span class="flag">${esc(f)}</span>`).join(' ')}</p>` : '') +
      (r.corr ? `<p class="hint">Correção: ${V(r.corr.actype)} / WTC ${V(r.corr.wtc)} / ${V(r.corr.apt)} — ${V(r.corr.note)} ${r.corr.verified ? '(verificado)' : ''}</p>` : '') +
      '<div class="grid2">' +
      sec('Radar (CNS)', [['1º plot', T(r.r_t_first)], ['último plot', T(r.r_t_last)], ['plots', V(r.r_n)], ['alt. máx (ft)', V(r.r_alt_max)], ['tipo (na tabela)', V(r.r_actype)]], r.src.includes('R')) +
      sec('NMIR', [['tipo', V(r.n_type) + (r.n_src && r.n_src !== 'nmir' ? ` <span class="muted">(${r.n_src})</span>` : '')], ['WTC', V(r.n_wtc)], ['ADEP', V(r.n_adep)], ['ADES', V(r.n_ades)]], r.src.includes('N')) +
      sec('Torre (A-SMGCS / CPPM)', [['tipo / WTC', `${V(r.t_type)} / ${V(r.t_wtc)}`], ['matrícula', V(r.t_reg)], ['operador', V(r.t_ao)], ['pista', V(r.t_rwy)], ['stand', V(r.t_stand)], [o ? 'ADEP' : 'ADES', V(r.t_apt)],
        ['AOBT', T(r.t_aobt)], ['RWY_ENT', T(r.t_rwy_ent)], ['ATOT', T(r.t_atot)], ['ALDT', T(r.t_aldt)], ['RWY_VAC', T(r.t_rwy_vac)], ['AIBT', T(r.t_aibt)], ['ROT', r.t_rot == null ? '—' : Math.round(r.t_rot) + ' s'], ['taxi', D(r.t_taxi)], ['go-around', r.t_ga ? 'sim' : 'não']], r.src.includes('T')) +
      sec('OPDI (OpenSky)', [['id', V(r.o_id)], ['icao24', V(r.o_icao24)], ['matrícula', V(r.o_reg)], ['tipo / modelo', `${V(r.o_type)} / ${V(r.o_model)}`], ['ADEP → ADES', `${V(r.o_adep)} → ${V(r.o_ades)}`],
        ['entrada na pista', T(r.o_rwy_in)], ['saída da pista', T(r.o_rwy_out)], ['ROT (aprox.)', r.o_rot == null ? '—' : Math.round(r.o_rot) + ' s'], ['TOC', T(r.o_toc)], ['TOD', T(r.o_tod)], ['último FL100 / FL50', `${T(r.o_lx100)} / ${T(r.o_lx50)}`], ['1º FL50 / FL100', `${T(r.o_fx50)} / ${T(r.o_fx100)}`], ['patamares < FL100', V(r.o_levels_low)]], r.src.includes('O')) +
      '</div>' + `<div class="row" style="gap:8px;margin-top:10px"><button class="btn primary" id="dtFix">✎ Corrigir / verificar</button>${r.flight_id ? `<button class="btn" id="dtMap">🗺 Ver no mapa</button>` : ''}</div>`;
    $('modal').classList.remove('hidden');
    $('dtFix').onclick = () => openFix(r);
    if ($('dtMap')) $('dtMap').onclick = () => { $('modal').classList.add('hidden'); FP.focusFlight(r.flight_id); };
  }
  function openFix(r) {
    const c = r.corr || {};
    const types = [...new Set([r.t_type, r.o_type, r.n_type].filter(Boolean))];
    const apts = [...new Set([r.t_apt, r.cls === 'arr' ? r.o_adep : r.o_ades, r.cls === 'arr' ? r.n_adep : r.n_ades].filter(Boolean))];
    const opts = (list, cur) => list.map(x => `<option value="${esc(x)}" ${x === cur ? 'selected' : ''}>${esc(x)}</option>`).join('');
    $('modalTitle').textContent = `Correção · ${r.csn} · ${fmtD(r.date)} · ${r.cls.toUpperCase()}`;
    $('modalBody').innerHTML = `
      <p class="hint">Fontes: NMIR ${esc(r.n_type || '—')} · torre ${esc(r.t_type || '—')} · OPDI ${esc(r.o_type || '—')} &nbsp;|&nbsp; ${r.cls === 'arr' ? 'ADEP' : 'ADES'}: NMIR ${esc((r.cls === 'arr' ? r.n_adep : r.n_ades) || '—')} · torre ${esc(r.t_apt || '—')} · OPDI ${esc((r.cls === 'arr' ? r.o_adep : r.o_ades) || '—')}</p>
      <div class="row wrap" style="gap:10px;align-items:flex-end">
        <label>Tipo correto <input id="fxType" class="inp tiny" list="fxTypes" value="${esc(c.actype || '')}" placeholder="ex.: A20N" style="width:100px"><datalist id="fxTypes">${opts(types, '')}</datalist></label>
        <label>WTC <select id="fxWtc" class="inp tiny"><option value="">auto</option>${['L', 'M', 'H', 'J'].map(w => `<option ${c.wtc === w ? 'selected' : ''}>${w}</option>`).join('')}</select></label>
        <label>${r.cls === 'arr' ? 'ADEP' : 'ADES'} correto <input id="fxApt" class="inp tiny" list="fxApts" value="${esc(c.apt || '')}" placeholder="ICAO" style="width:90px"><datalist id="fxApts">${opts(apts, '')}</datalist></label>
        <label class="chk"><input type="checkbox" id="fxVer" ${c.verified ? 'checked' : ''}> Verificado — ignorar discrepância</label>
      </div>
      <label class="chk" style="margin-top:8px"><input type="checkbox" id="fxAllType" checked> Aplicar a WTC a <b>todos os voos deste tipo</b> (${esc(types[0] || 'tipo')}), em todos os dias — e aos que vierem a ser importados</label>
      <label style="display:block;margin-top:10px">Nota <input id="fxNote" class="inp" value="${esc(c.note || '')}" placeholder="ex.: confirmado com a torre / matrícula CS-TSF é A21N"></label>
      <p class="hint">O tipo corrigido é aplicado ao movimento radar e ao NMIR desse dia (fica na base de dados; os ficheiros de origem não são alterados).</p>
      <div class="row" style="gap:8px;margin-top:12px"><button class="btn primary" id="fxSave">Guardar</button>${r.corr ? '<button class="btn" id="fxDel">Remover correção</button>' : ''}</div>`;
    $('modal').classList.remove('hidden');
    $('fxSave').onclick = async () => {
      try {
        await call('correction_set', r.csn, r.date, r.cls, $('fxType').value, $('fxWtc').value, $('fxApt').value, $('fxNote').value, $('fxVer').checked);
        if ($('fxAllType').checked && $('fxWtc').value) { const t = $('fxType').value || types[0]; if (t) { const n = await call('type_wtc_set', t, $('fxWtc').value, $('fxNote').value); toast(`WTC ${$('fxWtc').value} aplicada a ${fmt(n)} movimento(s) ${t}.`, 'ok'); } }
        $('modal').classList.add('hidden'); toast('Correção guardada.', 'ok'); crossRun(true);
      } catch (e) { toast(e.message, 'err'); }
    };
    if ($('fxDel')) $('fxDel').onclick = async () => { try { await call('correction_delete', r.csn, r.date, r.cls); $('modal').classList.add('hidden'); crossRun(true); } catch (e) { toast(e.message, 'err'); } };
  }
  async function crossRun(force) {
    const key = [...FP.state.days].sort().join(',') + '|' + FP.state.airport;
    if (!force && cross && key === crossKey) { crossRender(); return; }
    const body = $('crBody');
    if (!FP.state.days.size) { body.innerHTML = '<div class="empty">Aplica um filtro com pelo menos um dia.</div>'; return; }
    body.innerHTML = '<div class="empty">⏳ A cruzar radar, NMIR, torre e OPDI…</div>';
    try { cross = await call('crosscheck'); crossKey = key; crossRender(); }
    catch (e) { body.innerHTML = `<div class="empty">Erro: ${esc(e.message)}</div>`; toast(e.message, 'err'); }
  }
  function onTabCross() { crossRun(false); }
  function onFilterCross() { crossKey = ''; cross = null; }
  document.addEventListener('DOMContentLoaded', () => {
    $('crRun').onclick = () => crossRun(true);
    $('crFilter').onchange = crossRender; $('crCsn').oninput = crossRender;
    $('crImportOpdi').onclick = async () => {
      try { const r = await call('import_opdi'); if (!r) return; toast(`OPDI: ${fmt(r.rows)} eventos, ${fmt(r.flights)} voos de ${r.files} ficheiro(s).`, 'ok'); crossRun(true); }
      catch (e) { toast(e.message, 'err'); }
    };
    $('crImportGround').onclick = () => $('gdImport').click();
    $('crExport').onclick = async () => { try { const p = await call('export', 'cross', {}, null); if (p) toast('Exportado para ' + p, 'ok'); } catch (e) { toast(e.message, 'err'); } };
  });
  /* ================================================================ Painel diário */
  let panel = null;
  const DRILL_SRV = {};   // cartões cujos dados são pedidos ao servidor ao clicar
  window.DrillSrv = DRILL_SRV;
  document.addEventListener('click', async ev => {
    const k = ev.target.closest('.kcard[data-drill]'); if (!k) return;
    const d = DRILL_SRV[k.dataset.drill]; if (!d) return;
    try { const rows = await call('panel_details', d.key, d.d0, d.d1); Drill.set(k.dataset.drill, d.title, d.cols, rows); Drill.open(k.dataset.drill); } catch (e) { toast(e.message, 'err'); }
  }, true);
  const isoOf = d => `20${d.slice(0, 2)}-${d.slice(2, 4)}-${d.slice(4, 6)}`, ymd = iso => iso ? iso.slice(2, 4) + iso.slice(5, 7) + iso.slice(8, 10) : '';
  const addDays = (iso, n) => { const d = new Date(iso + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };
  function panelDefaults() {
    const days = [...FP.state.days].sort();
    const d0 = days.length ? isoOf(days[0]) : new Date().toISOString().slice(0, 10);
    const first = d0.slice(0, 8) + '01', last = addDays(addDays(first, 32).slice(0, 8) + '01', -1);
    if (!$('pnFrom').value) { $('pnFrom').value = first; $('pnTo').value = last; }
  }
  function refRange() {
    const f = $('pnFrom').value, t = $('pnTo').value, mode = $('pnRef').value;
    if (!f || !t || mode === 'none') return [null, null];
    if (mode === 'custom') return [$('pnRefFrom').value || null, $('pnRefTo').value || null];
    if (mode === 'prev_year') return [addDays(f, -365), addDays(t, -365)];
    const len = Math.round((new Date(t) - new Date(f)) / 86400000) + 1;
    return [addDays(f, -len), addDays(t, -len)];
  }
  const ma7 = v => v.map((_, i) => { const w = v.slice(Math.max(0, i - 6), i + 1).filter(x => x != null); return w.length >= 3 ? w.reduce((a, b) => a + b, 0) / w.length : null; });
  const agg = (rows, k, how) => { const v = rows.map(r => r[k]).filter(x => x != null); if (!v.length) return null; return how === 'sum' ? v.reduce((a, b) => a + b, 0) : v.reduce((a, b) => a + b, 0) / v.length; };
  async function panelRun() {
    panelDefaults();
    const f = $('pnFrom').value, t = $('pnTo').value; if (!f || !t) return;
    const [r0, r1] = refRange();
    const body = $('pnBody'); body.innerHTML = '<div class="empty">⏳ A calcular o painel…</div>';
    try { panel = await call('panel', ymd(f), ymd(t), r0 ? ymd(r0) : null, r1 ? ymd(r1) : null); panel._range = [f, t, r0, r1];
      if (heatApt && heatApt !== panel.airport) { try { panel.heatOther = await call('heatmap', heatApt, ymd(f), ymd(t)); } catch (e) { panel.heatOther = null; } } else heatApt = panel.airport;
      panelRender(); }
    catch (e) { body.innerHTML = `<div class="empty">Erro: ${esc(e.message)}</div>`; toast(e.message, 'err'); }
  }
  function panelRender() {
    if (!panel) return;
    const body = $('pnBody'), M = panel.main, R = panel.ref || [], useMa = $('pnMa').checked;
    if (!M.length) { body.innerHTML = '<div class="empty">Sem dados neste período.</div>'; return; }
    const lab = M.map(r => `${r.date.slice(4, 6)}/${r.date.slice(2, 4)}`);
    const mov = M.map(r => (r.g_dep + r.g_arr) || (r.arr + r.dep) || null), movR = R.map(r => (r.g_dep + r.g_arr) || (r.arr + r.dep) || null);
    const series = (vals, valsR, name, color) => [{ name, values: vals, color }, ...(useMa ? [{ name: 'média 7 d', values: ma7(vals), color, dash: true, width: 1.5 }] : []),
      ...(valsR.length ? [{ name: 'referência', values: valsR, color: C.GREY, width: 1.5, opacity: .8 }] : [])];
    const sum = (rows, k) => agg(rows, k, 'sum'), avg = (rows, k) => agg(rows, k, 'avg');
    const cmp = (label, a, b, fmtf, lowerBetter) => { const d = a != null && b != null ? a - b : null; const good = d == null ? '' : (lowerBetter ? d <= 0 : d >= 0) ? 'sep-g' : 'sep-r';
      return `<tr><td>${label}</td><td><b>${a == null ? '—' : fmtf(a)}</b></td><td>${b == null ? '—' : fmtf(b)}</td><td class="${good}">${d == null ? '—' : (d > 0 ? '+' : '') + fmtf(d)}${b ? ` (${d > 0 ? '+' : ''}${fmt(d / b * 100, 1)}%)` : ''}</td></tr>`; };
    const n0 = v => fmt(v, 0), n1 = v => fmt(v, 1), s0 = v => Math.round(v) + ' s', mn = v => fmt(v / 60, 1) + ' min';
    const [f, t, r0, r1] = panel._range;
    const movM = sum(M, 'n') ? M.map(r => (r.g_dep + r.g_arr) || (r.arr + r.dep)) : mov;
    const tot = rows => rows.reduce((a, r) => a + ((r.g_dep + r.g_arr) || (r.arr + r.dep) || 0), 0);
    // drill-down dos cartões: tabelas por dia (locais) e listas de voos (pedidas ao servidor ao clicar)
    const dayCols = [{ k: 'date', label: 'Dia', fmt: fmtD }, { k: 'mov', label: 'Movimentos' }, { k: 'g_arr', label: 'Chegadas (torre)' }, { k: 'g_dep', label: 'Partidas (torre)' }, { k: 'arr', label: 'Chegadas (radar)' }, { k: 'dep', label: 'Partidas (radar)' }, { k: 'ga', label: 'GA' },
      { k: 'rot_arr', label: 'ROT ARR (s)' }, { k: 'rot_dep', label: 'ROT DEP (s)' }, { k: 'taxi_out', label: 'Taxi-out (s)' }, { k: 'taxi_in', label: 'Taxi-in (s)' }, { k: 'atfm_min', label: 'ATFM (min)' }, { k: 'p_ok', label: 'Pont. ok' }, { k: 'p_n', label: 'Pont. n' }];
    const dayRows = M.map(r => ({ ...r, mov: (r.g_dep + r.g_arr) || (r.arr + r.dep) || 0 }));
    Drill.set('pn.days', `Valores por dia — ${f} → ${t}`, dayCols, dayRows);
    if (R.length) Drill.set('pn.ref', `Referência por dia — ${r0} → ${r1}`, dayCols, R.map(r => ({ ...r, mov: (r.g_dep + r.g_arr) || (r.arr + r.dep) || 0 })));
    const srv = (key, title, cols) => { Drill.set('pn.' + key, title, cols, []); DRILL_SRV['pn.' + key] = { key, title, cols, d0: ymd(f), d1: ymd(t) }; };
    const T = v => v == null ? '—' : new Date(v * 1000).toISOString().slice(11, 19);
    const csnC = { k: 'csn', label: 'Voo', fmt: (v, r) => r.flight_id ? `<a href="#" class="csn-link" data-fid="${r.flight_id}"><b>${esc(v)}</b></a>` : `<b>${esc(v || '')}</b>` };
    srv('ga', 'Go-arounds — torre e radar', window.GA_COLS(fmtD, csnC, T));
    srv('atfm', 'Partidas com atraso ATFM (torre)', [{ k: 'date', label: 'Data', fmt: fmtD }, csnC, { k: 'actype', label: 'Tipo' }, { k: 'ades', label: 'ADES' }, { k: 'ctot', label: 'CTOT', fmt: T }, { k: 'atot', label: 'ATOT', fmt: T }, { k: 'atfm_delay', label: 'Atraso (min)' }, { k: 'regulation', label: 'Regulação' }]);
    srv('otp', 'Pontualidade à partida (NMIR)', window.OTP_COLS(fmtD, { k: 'csn', label: 'Voo' }, T));
    let h = '<div class="kgrid">' + C.kcard('Movimentos', fmt(tot(M)), `${M.length} dias · ${fmt(tot(M) / M.length, 0)}/dia`, '', 'pn.days') +
      (R.length ? C.kcard('Referência', fmt(tot(R)), `${R.length} dias · ${fmt(tot(R) / R.length, 0)}/dia`, '', 'pn.ref') + C.kcard('Variação', (tot(R) ? (tot(M) / M.length) / (tot(R) / R.length) * 100 - 100 : 0).toFixed(1) + '%', 'média diária vs referência', (tot(M) / M.length) >= (tot(R) / R.length) ? 'ok' : 'warn', 'pn.days') : '') +
      C.kcard('Go-arounds', sum(M, 'ga') ?? 0, '', '', 'pn.ga') + C.kcard('ROT chegada', avg(M, 'rot_arr') ? s0(avg(M, 'rot_arr')) : '—', 'mediana diária média', '', 'pn.days') + C.kcard('ROT partida', avg(M, 'rot_dep') ? s0(avg(M, 'rot_dep')) : '—', '', '', 'pn.days') +
      C.kcard('Taxi-out', avg(M, 'taxi_out') ? mn(avg(M, 'taxi_out')) : '—', 'mediana diária média', '', 'pn.days') + C.kcard('Taxi-in', avg(M, 'taxi_in') ? mn(avg(M, 'taxi_in')) : '—', '', '', 'pn.days') +
      C.kcard('Atraso ATFM (torre)', sum(M, 'atfm_min') != null ? fmt(sum(M, 'atfm_min')) + ' min' : '—', `${sum(M, 'atfm_n') ?? 0} partidas atrasadas`, '', 'pn.atfm') +
      C.kcard('Pontualidade 15 min', sum(M, 'p_n') ? fmt(sum(M, 'p_ok') / sum(M, 'p_n') * 100, 1) + '%' : '—', `NMIR · ${fmt(sum(M, 'p_n') ?? 0)} partidas`, '', 'pn.otp') + '</div>';
    h += C.card(`Movimentos por dia — ${f} → ${t}${r0 ? ` · referência ${r0} → ${r1} (cinzento)` : ''}`, C.lines(series(mov, movR, 'movimentos (torre, ou radar se não houver)', C.BLUE), lab, { dots: true }));
    h += '<div class="grid2">' +
      C.card('ROT mediano por dia (s)', C.lines([{ name: 'chegadas', values: M.map(r => r.rot_arr), color: C.BLUE }, { name: 'partidas', values: M.map(r => r.rot_dep), color: C.ORANGE }, ...(R.length ? [{ name: 'ref. chegadas', values: R.map(r => r.rot_arr), color: C.GREY, dash: true }] : [])], lab, { dots: true, band: 60, bandLabel: 'alerta 60 s' })) +
      C.card('Taxi mediano por dia (min)', C.lines([{ name: 'taxi-out', values: M.map(r => r.taxi_out == null ? null : r.taxi_out / 60), color: C.ORANGE }, { name: 'taxi-in', values: M.map(r => r.taxi_in == null ? null : r.taxi_in / 60), color: C.BLUE }], lab, { dots: true, dec: 1 })) +
      C.card('Atraso ATFM por dia (min, torre)', C.bars(M.map(r => r.atfm_min || 0), lab, { color: C.RED })) +
      C.card('Pontualidade à partida por dia (%, NMIR)', C.lines([{ name: 'OTP15', values: M.map(r => r.p_n ? r.p_ok / r.p_n * 100 : null), color: C.GREEN }, ...(R.length ? [{ name: 'ref.', values: R.map(r => r.p_n ? r.p_ok / r.p_n * 100 : null), color: C.GREY, dash: true }] : [])], lab, { dots: true, min: 0, max: 100, band: 80, bandLabel: 'meta 80%' })) +
      C.card('Go-arounds por dia', C.bars(M.map(r => r.ga || 0), lab, { color: C.PURPLE })) +
      C.card('Chegadas / partidas por dia', C.lines([{ name: 'chegadas', values: M.map(r => r.g_arr || r.arr || null), color: C.BLUE }, { name: 'partidas', values: M.map(r => r.g_dep || r.dep || null), color: C.ORANGE }], lab, { dots: true })) + '</div>';
    if (R.length) {
      h += C.card('Comparação A (período) vs B (referência)', `<table><thead><tr><th>Indicador</th><th>Período</th><th>Referência</th><th>Δ</th></tr></thead><tbody>` +
        cmp('Movimentos / dia', tot(M) / M.length, tot(R) / R.length, n0, false) + cmp('Chegadas / dia', avg(M, 'g_arr') || avg(M, 'arr'), avg(R, 'g_arr') || avg(R, 'arr'), n0, false) + cmp('Partidas / dia', avg(M, 'g_dep') || avg(M, 'dep'), avg(R, 'g_dep') || avg(R, 'dep'), n0, false) +
        cmp('ROT chegada (s)', avg(M, 'rot_arr'), avg(R, 'rot_arr'), s0, true) + cmp('ROT partida (s)', avg(M, 'rot_dep'), avg(R, 'rot_dep'), s0, true) +
        cmp('Taxi-out (min)', avg(M, 'taxi_out') && avg(M, 'taxi_out') / 60, avg(R, 'taxi_out') && avg(R, 'taxi_out') / 60, n1, true) + cmp('Taxi-in (min)', avg(M, 'taxi_in') && avg(M, 'taxi_in') / 60, avg(R, 'taxi_in') && avg(R, 'taxi_in') / 60, n1, true) +
        cmp('Atraso ATFM / dia (min)', avg(M, 'atfm_min'), avg(R, 'atfm_min'), n0, true) + cmp('Pontualidade 15 min (%)', sum(M, 'p_n') ? sum(M, 'p_ok') / sum(M, 'p_n') * 100 : null, sum(R, 'p_n') ? sum(R, 'p_ok') / sum(R, 'p_n') * 100 : null, n1, false) +
        cmp('Go-arounds / dia', avg(M, 'ga'), avg(R, 'ga'), n1, true) + '</tbody></table>');
    }
    const top = panel.top, topR = panel.top_ref;
    const topTbl = (list, listR, label) => { const refMap = new Map((listR || []).map(([k, n]) => [k, n])); return C.table([{ k: 0, label }, { k: 1, label: 'Movimentos' }, ...(listR ? [{ k: 2, label: 'Referência', fmt: (v, r) => refMap.get(r[0]) ?? '—' }] : [])], list.map(r => [r[0], r[1], refMap.get(r[0])])); };
    h += '<div class="grid2">' + C.card('Top 10 operadores (radar)', topTbl(top.operators, topR && topR.operators, 'Operador')) + C.card('Top 10 tipos (radar)', topTbl(top.types, topR && topR.types, 'Tipo')) + C.card('Top 10 aeroportos origem/destino (NMIR)', topTbl(top.airports, topR && topR.airports, 'Aeroporto')) + '</div>';
    // mapa de calor hora × dia da semana
    h += C.card('Mapa de calor — hora × dia da semana', heatHtml(heatApt === panel.airport ? panel.heat : (panel.heatOther || null), heatApt, f, t));
    // qualidade de dados
    const dot = (ok, warn) => `<span class="dq ${ok ? 'ok' : warn ? 'warn' : 'bad'}"></span>`;
    h += C.card('Qualidade / cobertura dos dados por dia', C.table([
      { k: 'date', label: 'Dia', fmt: v => fmtD(v) },
      { k: 'blocks', label: 'Radar (blocos de 4 h)', fmt: (v, r) => `${dot(v >= 6, v >= 4)} ${v}/6 · ${fmt(r.n)} mov.` },
      { k: 'g_dep', label: 'Torre', fmt: (v, r) => `${dot(r.g_dep + r.g_arr > 0, false)} ${r.g_dep + r.g_arr ? fmt(r.g_dep + r.g_arr) + ' mov.' : 'sem ficheiro'}` },
      { k: 'n_dep', label: 'NMIR', fmt: (v, r) => `${dot(r.n_dep + r.n_arr > 0, false)} ${r.n_dep + r.n_arr ? fmt(r.n_dep + r.n_arr) + ' voos' : 'sem dados'}` },
      { k: 'o_n', label: 'OPDI', fmt: v => `${dot(v > 0, false)} ${v ? fmt(v) + ' voos' : 'sem dados'}` },
      { k: 'alert', label: 'Alertas', fmt: (v, r) => [r.rot_arr > 60 ? 'ROT chegada > 60 s' : '', r.ga >= 3 ? `${r.ga} go-arounds` : '', r.atfm_min > 600 ? `ATFM ${fmt(r.atfm_min)} min` : '', r.p_n && r.p_ok / r.p_n < .7 ? 'pontualidade < 70%' : ''].filter(Boolean).map(x => `<span class="flag">${x}</span>`).join(' ') },
    ], M, { limit: 400 }));
    body.innerHTML = h;
    $('pnInfo').textContent = `${M.length} dias${R.length ? ` · referência ${R.length} dias` : ''}`;
  }
  const HEAT_DOW = ['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb'];
  let heatKind = 'all', heatApt = null;
  const APT_NAMES = { LPPT: 'Lisboa (LPPT)', LPPR: 'Porto (LPPR)', LPFR: 'Faro (LPFR)', LPMA: 'Madeira (LPMA)' };
  function heatHtml(heat, apt, f, t) {
    const aptSel = `<label>Aeroporto <select id="heatApt" class="inp tiny">${Object.keys(APT_NAMES).map(a => `<option value="${a}"${a === apt ? ' selected' : ''}>${APT_NAMES[a]}</option>`).join('')}</select></label>`;
    if (!heat) return `<div class="heat-tools">${aptSel}</div><div class="empty">Sem dados.</div>`;
    const G = heat.grid[heatKind]; const max = Math.max(1, ...G.flat());
    const total = G.flat().reduce((a, b) => a + b, 0);
    const lbl = { all: 'movimentos', arr: 'chegadas', dep: 'partidas' }[heatKind];
    const color = v => { if (!v) return ''; const x = v / max; // amarelo → laranja → vermelho escuro
      const stops = [[255, 237, 160], [254, 178, 76], [240, 59, 32], [128, 0, 38]]; const i = Math.min(2, Math.floor(x * 3)); const k = x * 3 - i;
      const c = stops[i].map((a, j) => Math.round(a + (stops[i + 1][j] - a) * k)); return `background:rgb(${c.join(',')})`; };
    let h = `<div class="heat-tools">${aptSel}<label>Mostrar <select id="heatKind" class="inp tiny"><option value="all"${heatKind === 'all' ? ' selected' : ''}>movimentos</option><option value="arr"${heatKind === 'arr' ? ' selected' : ''}>chegadas</option><option value="dep"${heatKind === 'dep' ? ' selected' : ''}>partidas</option></select></label>` +
      `<span class="muted">Aeroporto ${esc(apt)} · ${fmt(total)} ${lbl} no período · ${heat.tower_days} dia(s) torre, ${heat.radar_days} dia(s) só radar · mais escuro = mais voos · clica numa célula para ver os voos</span></div>`;
    h += '<table class="heat"><thead><tr><th></th>' + Array.from({ length: 24 }, (_, i) => `<th>${String(i).padStart(2, '0')}</th>`).join('') + '</tr></thead><tbody>';
    for (let d = 0; d < 7; d++) {
      h += `<tr><th>${HEAT_DOW[d]}</th>` + G[d].map((v, hh) => `<td class="${v / max > .55 ? 'dk' : ''}" style="${color(v)}" data-dow="${d}" data-h="${hh}" title="${HEAT_DOW[d]} ${String(hh).padStart(2, '0')}:00 UTC · ${v} ${lbl} em ${heat.days[d]} dia(s)">${v || ''}</td>`).join('') + '</tr>';
    }
    return h + '</tbody></table>';
  }
  document.addEventListener('change', async ev => {
    if (ev.target.id === 'heatKind') { heatKind = ev.target.value; panelRender(); }
    if (ev.target.id === 'heatApt') {
      heatApt = ev.target.value; const [f, t] = panel._range;
      try { panel.heatOther = heatApt === panel.airport ? null : await call('heatmap', heatApt, ymd(f), ymd(t)); } catch (e) { toast(e.message, 'err'); }
      panelRender();
    }
  });
  document.addEventListener('click', async ev => {
    const td = ev.target.closest('.heat td'); if (!td || !panel) return;
    const [f, t] = panel._range; const dow = +td.dataset.dow, hh = +td.dataset.h; const apt = heatApt || panel.airport;
    const lbl = { all: 'Movimentos', arr: 'Chegadas', dep: 'Partidas' }[heatKind];
    const T = v => v == null ? '—' : new Date(v * 1000).toISOString().slice(11, 19);
    const cols = [{ k: 'date', label: 'Data', fmt: fmtD }, { k: 'csn', label: 'Voo', fmt: (v, r) => r.flight_id ? `<a href="#" class="csn-link" data-fid="${r.flight_id}"><b>${esc(v)}</b></a>` : `<b>${esc(v || '')}</b>` },
      { k: 'src', label: 'Fonte' }, { k: 'mt', label: 'Tipo mov.', fmt: (v, r) => v ? (v === 'DEPARTURE' ? 'partida' : 'chegada') : (r.cls === 'dep' ? 'partida' : 'chegada') }, { k: 'actype', label: 'Tipo' }, { k: 'rwy', label: 'RWY' }, { k: 't_ref', label: 'Hora (UTC)', fmt: T }, { k: 'adep', label: 'ADEP' }, { k: 'ades', label: 'ADES' }];
    const key = `pn.heat.${apt}.${dow}.${hh}.${heatKind}`;
    try { const rows = await call('panel_details', `heat:${dow}:${hh}:${heatKind}:${apt}`, ymd(f), ymd(t)); Drill.set(key, `${lbl} ${apt} — ${HEAT_DOW[dow]} ${String(hh).padStart(2, '0')}:00–${String(hh + 1).padStart(2, '0')}:00 UTC · ${f} → ${t}`, cols, rows); Drill.open(key); } catch (e) { toast(e.message, 'err'); }
  });
  function onTabPanel() { panelDefaults(); if (!panel) panelRun(); }
  document.addEventListener('DOMContentLoaded', () => {
    $('pnRun').onclick = panelRun; $('pnMa').onchange = panelRender;
    $('pnRef').onchange = () => { $('pnRefCustom').classList.toggle('hidden', $('pnRef').value !== 'custom'); };
    $('pnExport').onclick = async () => { try { const p = await call('export', 'panel', { d0: ymd($('pnFrom').value), d1: ymd($('pnTo').value) }, null); if (p) toast('Exportado para ' + p, 'ok'); } catch (e) { toast(e.message, 'err'); } };
  });
  function resize() { if (map) map.invalidateSize(); }
  /* seleção vinda da lista de voos (radar): escolhe o movimento da torre ligado a esse flight_id */
  function selectByFlight(fid) {
    if (!map) return;
    if (fid == null) { if (sel != null) select(sel); return; }
    const row = rows.find(r => r.flight_id === fid);
    if (!row) { toast('Este voo não tem movimento correspondente no ficheiro da torre.', 'err'); return; }
    if (row.gid !== sel) select(row.gid, { scrollTable: true });
  }
  return { onTab, onFilter, onTabCross, onFilterCross, onTabPanel, resize, selectByFlight };
})();
window.Ground = Ground;
