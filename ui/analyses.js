/* FlightTracker 4 — abas de análise (Final, Velocidades, Análise Op., KPIs, Pontos, IA, Preferências) */
'use strict';
/* colunas do modal de go-arounds (KPIs e Painel): torre + radar cruzados */
window.GA_COLS = (fd, csnCol, T) => [{ k: 'date', label: 'Data', fmt: fd }, csnCol, { k: 'actype', label: 'Tipo' }, { k: 'rwy', label: 'RWY' }, { k: 't_ga', label: 'Borrego (UTC)', fmt: T }, { k: 't_land', label: 'Aterragem real', fmt: T },
  { k: 'src', label: 'Fonte', fmt: v => v === 'torre+radar' ? '<span class="sep-g">torre + radar</span>' : v === 'só radar' ? '<span class="sep-g">só radar</span>' : `<span class="sep-r">${v}</span>` }, { k: 'radar', label: 'Radar' }, { k: 'adep', label: 'ADEP' }];
const Analyses = (() => {
  const { esc, fmt } = C;
  const $ = id => document.getElementById(id);
  const call = (...a) => FP.call(...a);
  const toast = (m, k) => FP.toast(m, k);
  const busy = (el, msg = 'A calcular…') => { if (el) el.innerHTML = `<div class="empty">⏳ ${esc(msg)}</div>`; };
  const empty = (el, msg) => { if (el) el.innerHTML = `<div class="empty">${esc(msg)}</div>`; };
  const R = { pru: null, final: null, star: null, app: null, ad: null, fast: null, dados: null, diaria: null, rrms: null, rot: null, kpis: null, pt: null, seq: null };
  const hasFlights = () => FP.state.flights.length > 0;
  const sec = v => v == null ? '—' : fmt(Math.round(v));
  const rwyBadge = r => `<span class="badge rwy ${r === '02' || r === '17' || r === '10' || r === '05' ? 'a' : 'b'}">RWY ${esc(r)}</span>`;
  const csnLink = (csn, fid) => `<a href="#" class="csn-link" data-fid="${fid}"><b>${esc(csn)}</b></a>`;
  const wireCsn = root => root.querySelectorAll('.csn-link').forEach(a => a.onclick = ev => { ev.preventDefault(); FP.focusFlight(+a.dataset.fid); });
  const sepCls = (s, thr) => s < 120 ? 'sep-r' : s < thr ? 'sep-o' : 'sep-g';
  const seqPill = q => `<span class="pill-seq ${q === 'AD…A' ? 'ADxA' : q}">${esc(q)}</span>`;
  let modalEl;
  function modal(title, html) { $('modalTitle').textContent = title; $('modalBody').innerHTML = html; $('modal').classList.remove('hidden'); wireCsn($('modalBody')); }
  const closeModal = () => $('modal').classList.add('hidden');

  /* ================================================================ FINAL */
  async function runFinal(force) {
    const el = $('finBody');
    if (!hasFlights()) { empty(el, 'Sem dados. Aplica um filtro primeiro.'); return null; }
    if (R.final && !force) return R.final;
    busy(el, 'A detectar aterragens…');
    try {
      R.final = await call('run_final', $('finRwy').value, +$('finFaf').value || 7, +$('finCorr').value || 2, +$('finAlt').value || 1000);
      renderFinal(); drawFinalOverlay();
      return R.final;
    } catch (e) { empty(el, 'Erro: ' + e.message); toast(e.message, 'err'); return null; }
  }
  function renderFinal() {
    const d = R.final, el = $('finBody'); if (!d) return;
    const s = d.summary, rs = d.results;
    $('finCount').textContent = `${rs.length} aterragem(ns) detectada(s)`;
    const sel = $('finRwy'); const cur = sel.value; sel.innerHTML = '<option value="BOTH">Ambas</option>' + d.rwys.map(r => `<option value="${r}">RWY ${r}</option>`).join(''); sel.value = cur;
    if (!rs.length) { empty(el, 'Nenhuma aterragem detectada nos parâmetros actuais'); return; }
    const bySep = rs.filter(x => x.sepTimeS != null).slice().sort((a, b) => a.sepTimeS - b.sepTimeS);
    drillScope('final', { 'Aterragens': rs, 'Estabilizadas': { title: 'Aproximações estabilizadas / não estabilizadas', rows: rs.slice().sort((a, b) => (a.stab ? 1 : 0) - (b.stab ? 1 : 0)) },
      'IAS@FAF méd': { title: 'IAS no FAF por aterragem', rows: rs.slice().sort((a, b) => (b.iasFAF || 0) - (a.iasFAF || 0)) }, 'Tempo FAF→THR méd': { title: 'Tempo FAF→THR por aterragem', rows: rs.slice().sort((a, b) => b.durS - a.durS) },
      'Sep. temporal méd': { title: 'Separação temporal entre aterragens consecutivas', rows: bySep }, 'Sep. temporal mín': { title: 'Separações (da menor para a maior)', rows: bySep },
      ...Object.fromEntries(Object.keys(s.byRwy).map(r => ['RWY ' + r, { title: 'Aterragens RWY ' + r, rows: rs.filter(x => x.rwy === r) }])) });
    let h = '<div class="kgrid">' + C.kcard('Aterragens', s.n) + C.kcard('Estabilizadas', `${s.stab} (${Math.round(s.stab / s.n * 100)}%)`, '', s.stab === s.n ? 'ok' : 'warn') +
      C.kcard('IAS@FAF méd', fmt(s.iasFAF) + ' kt') + C.kcard('Tempo FAF→THR méd', fmt(s.durS) + ' s') + C.kcard('Sep. temporal méd', sec(s.sepMean) + ' s') + C.kcard('Sep. temporal mín', sec(s.sepMin) + ' s') +
      Object.entries(s.byRwy).map(([r, n]) => C.kcard('RWY ' + r, n)).join('') + '</div>';
    h += C.table([{ k: 'idx', label: '#' }, { k: 'rwy', label: 'RWY', fmt: v => rwyBadge(v) }, { k: 'csn', label: 'Voo', fmt: (v, r) => csnLink(v, r.flight_id) }, { k: 'actype', label: 'Tipo' },
      { k: 'date', label: 'Data' }, { k: 'tFAFstr', label: 'Hora FAF' }, { k: 'tTHRstr', label: 'Hora THR' }, { k: 'durS', label: 'FAF→THR (s)', fmt: sec },
      { k: 'trackNM', label: 'Dist (NM)', fmt: v => fmt(v, 2) }, { k: 'sepTimeS', label: 'ΔT ant (s)', fmt: sec }, { k: 'altFAF', label: 'Alt FAF (ft)', fmt: v => fmt(v) },
      { k: 'iasFAF', label: 'IAS FAF', fmt: v => fmt(v) }, { k: 'ias4', label: 'IAS@4NM', fmt: v => fmt(v) }, { k: 'iasTHR', label: 'IAS THR', fmt: v => fmt(v) },
      { k: 'crossFAF', label: 'Desvio eixo (NM)', fmt: v => fmt(v, 2), title: 'negativo = esquerda' }, { k: 'stab', label: 'Estab.', fmt: v => v ? '<span class="sep-g">✓</span>' : '<span class="sep-r">✗</span>' }], rs, { id: 'finTable' });
    el.innerHTML = h; wireCsn(el);
  }
  function drawFinalOverlay() {
    const g = FP.overlay; g.clearLayers();
    if (!$('finOverlay').checked || !R.final) return;
    const [, faf, corr] = R.final.params; const cfg = FP.THR[FP.state.airport] || FP.THR.LPPT;
    const brgs = { LPPT: { '02': 32, '20': 212 }, LPPR: { '17': 171, '35': 351 }, LPFR: { '10': 101, '28': 281 }, LPMA: { '05': 47, '23': 227 } }[FP.state.airport] || { '02': 32, '20': 212 };
    const dest = (lat, lon, brg, d) => { const Rn = 3440.065, b = brg * Math.PI / 180, la1 = lat * Math.PI / 180, lo1 = lon * Math.PI / 180;
      const la2 = Math.asin(Math.sin(la1) * Math.cos(d / Rn) + Math.cos(la1) * Math.sin(d / Rn) * Math.cos(b));
      const lo2 = lo1 + Math.atan2(Math.sin(b) * Math.sin(d / Rn) * Math.cos(la1), Math.cos(d / Rn) - Math.sin(la1) * Math.sin(la2)); return [la2 * 180 / Math.PI, lo2 * 180 / Math.PI]; };
    for (const r in cfg) {
      const thr = cfg[r], app = (brgs[r] + 180) % 360, len = faf + 5;
      const far = dest(...thr, app, len), p1 = dest(...thr, app + 90, corr), p2 = dest(...thr, app - 90, corr), p3 = dest(...far, app - 90, corr), p4 = dest(...far, app + 90, corr);
      L.polygon([p1, p2, p3, p4], { color: '#ffd166', weight: 1, fillOpacity: .08, dashArray: '4 4' }).addTo(g);
      L.polyline([thr, far], { color: '#ffd166', weight: 1, dashArray: '6 6' }).addTo(g);
      L.circleMarker(dest(...thr, app, faf), { radius: 5, color: '#ffd166', fillOpacity: 1 }).bindTooltip(`FAF ${faf} NM · RWY ${r}`).addTo(g);
    }
  }

  /* ================================================================ STAR */
  async function runStar(force) {
    const el = $('starBody');
    if (!hasFlights()) { empty(el, 'Sem dados carregados.'); return null; }
    if (R.star && !force) return R.star;
    busy(el, 'A analisar IAS nos pontos STAR…');
    try { R.star = await call('run_star', +$('starRadius').value || 1, +$('starTol').value || 0); renderStar(); return R.star; }
    catch (e) { empty(el, 'Erro: ' + e.message); toast(e.message, 'err'); return null; }
  }
  function renderStar() {
    const r = R.star, el = $('starBody'); if (!r) return;
    $('starCount').textContent = `${r.totalPasses} passagens · ${r.totalViol} violações`;
    const pct = r.pct; const cls = pct == null ? '' : pct >= 95 ? 'ok' : pct < 85 ? 'bad' : '';
    drillScope('star', { 'Voos ARR analisados': { title: 'Chegadas do filtro', rows: FP.state.flights.filter(f => f.cls === 'arr') }, 'Passagens detectadas': { title: 'Passagens por waypoint', rows: r.perWp }, 'Conformes': { title: 'Conformidade por waypoint', rows: r.perWp },
      'Violações': { title: 'Violações de IAS nos waypoints STAR', rows: r.violations }, 'Taxa de cumprimento': { title: 'Cumprimento por waypoint', rows: r.perWp }, 'Waypoints sem coordenadas': { title: 'Waypoints sem coordenadas', rows: r.missing.map(w => ({ wp: w })) } });
    let h = '<div class="kgrid">' + C.kcard('Voos ARR analisados', `${r.flightsAnalysed}/${r.flightsTotal}`) + C.kcard('Passagens detectadas', r.totalPasses) + C.kcard('Conformes', r.totalComp, '', 'ok') +
      C.kcard('Violações', r.totalViol, '', r.totalViol ? 'bad' : 'ok') + C.kcard('Taxa de cumprimento', pct == null ? '—' : fmt(pct, 1) + '%', `Raio ${r.radius} NM · Tol +${r.tol} kt`, cls) +
      (r.missing.length ? C.kcard('Waypoints sem coordenadas', r.missing.length, r.missing.join(', '), 'warn') : '') + '</div>';
    h += '<h3 class="mini">Por waypoint</h3>' + C.table([{ k: 'wp', label: 'Waypoint' }, { k: 'limit', label: 'Limite (kt)' }, { k: 'total', label: 'Passagens' }, { k: 'compliant', label: 'Conformes', cls: () => 'sep-g' },
      { k: 'violations', label: 'Violações', cls: v => v.violations ? 'sep-r' : '' }, { k: 'pct', label: '% Cumprim.', fmt: (v, w) => { const p = w.compliant / w.total * 100; return `<span class="${p >= 95 ? 'sep-g' : p < 85 ? 'sep-r' : ''}">${fmt(p, 1)}%</span>`; } },
      { k: 'iasSum', label: 'IAS méd.', fmt: (v, w) => fmt(v / w.total) }, { k: 'iasMax', label: 'IAS máx.', fmt: v => v || '—' }, { k: 'iasMin', label: 'IAS mín.', fmt: v => v == null ? '—' : fmt(v) },
      { k: 'excessSum', label: 'Excesso méd.', fmt: (v, w) => w.violations ? '+' + fmt(v / w.violations) : '—' }, { k: 'excessMax', label: 'Excesso máx.', fmt: (v, w) => w.violations ? '+' + fmt(v) : '—' }],
      r.perWp.map(w => ({ ...w, pct: w.compliant / w.total })), { id: 'starWp' });
    h += `<h3 class="mini">Violações (${r.violations.length})</h3>` + (r.violations.length ? C.table([{ k: 'i', label: '#', fmt: (v, x, i) => i + 1 }, { k: 'tod', label: 'Hora' }, { k: 'date', label: 'Data' }, { k: 'csn', label: 'Voo', fmt: (v, x) => csnLink(v, x.flight_id) },
      { k: 'actype', label: 'Tipo' }, { k: 'wp', label: 'Waypoint' }, { k: 'ias', label: 'IAS (kt)', fmt: v => `<span class="sep-r">${fmt(v)}</span>` }, { k: 'limit', label: 'Limite' }, { k: 'excess', label: 'Excesso', fmt: v => `<span class="sep-r">+${fmt(v)}</span>` },
      { k: 'dCpa', label: 'CPA (NM)', fmt: v => fmt(v, 1) }], r.violations, { id: 'starViol', limit: 3000 }) : '<div class="hint sep-g">✓ Sem violações</div>');
    if (r.operators.length) h += C.card('Cumprimento IAS por operador (top 10 pior)', C.table([{ k: 'op', label: 'Operador' }, { k: 'arrFlights', label: 'Voos ARR' }, { k: 'violations', label: 'Violações' },
      { k: 'rate', label: 'Inc./voo', fmt: v => `<span class="${v <= .1 ? 'sep-g' : v >= .5 ? 'sep-r' : ''}">${fmt(v * 100, 1)}%</span>` }], r.operators), 'Ordenado por nº de violações. Indicador: violações por voo ARR no filtro activo.');
    el.innerHTML = h; wireCsn(el);
  }
  async function manageLimits() {
    const lim = await call('star_limits');
    const rows = Object.entries(lim).sort((a, b) => a[0].localeCompare(b[0]));
    const pts = new Set((await call('points_list')).map(p => p.name.toUpperCase()));
    modal('Restrições IAS publicadas (STAR) — edita, adiciona ou remove waypoints',
      `<div class="toolbar wrap" style="border:0;padding:0 0 10px"><input id="lmWp" class="inp small" placeholder="WAYPOINT" style="text-transform:uppercase"><input id="lmVal" class="inp num" type="number" placeholder="IAS máx" min="80" max="400"><button class="btn primary" id="lmAdd">+ Adicionar</button>
       <span class="spacer"></span><button class="btn" id="lmReset">↻ Repor defaults</button><button class="btn" id="lmExp">↓ JSON</button><button class="btn" id="lmImp">↑ JSON</button><button class="btn primary" id="lmSave">💾 Guardar</button></div>
       <div class="kgrid" id="lmList">${rows.map(([w, v]) => `<div class="kcard" data-wp="${esc(w)}"><span>${esc(w)} ${pts.has(w) ? '' : '<span class="sep-o" title="Sem coordenadas — não será analisado">⚠</span>'}</span>
         <div class="row"><input class="inp num lm-v" type="number" min="80" max="400" value="${v}"><button class="btn ghost lm-x" title="Remover">✖</button></div></div>`).join('')}</div>
       <textarea id="lmJson" class="inp hidden" rows="6" placeholder="Cola aqui o JSON {\"WP\": kt, …}"></textarea>`);
    const collect = () => { const o = {}; $('lmList').querySelectorAll('.kcard').forEach(c => { const v = parseInt(c.querySelector('.lm-v').value); if (v >= 80 && v <= 400) o[c.dataset.wp] = v; }); return o; };
    $('lmList').querySelectorAll('.lm-x').forEach(b => b.onclick = () => { if (confirm(`Remover restrição para ${b.closest('.kcard').dataset.wp}?`)) b.closest('.kcard').remove(); });
    $('lmAdd').onclick = () => { const w = $('lmWp').value.trim().toUpperCase(), v = parseInt($('lmVal').value); if (!w || !(v >= 80 && v <= 400)) { alert('Waypoint e IAS válida (80–400) são obrigatórios.'); return; }
      const ex = $('lmList').querySelector(`[data-wp="${w}"]`); if (ex) ex.querySelector('.lm-v').value = v; else $('lmList').insertAdjacentHTML('afterbegin', `<div class="kcard" data-wp="${w}"><span>${w}</span><div class="row"><input class="inp num lm-v" type="number" min="80" max="400" value="${v}"><button class="btn ghost lm-x">✖</button></div></div>`); $('lmWp').value = ''; $('lmVal').value = ''; };
    $('lmSave').onclick = async () => { await call('star_limits_set', collect()); toast('Limites guardados.', 'ok'); closeModal(); R.star = null; if ($('tab-star').classList.contains('active')) runStar(true); };
    $('lmReset').onclick = async () => { if (confirm('Repor os limites default das STAR de LPPT? Serão descartadas todas as alterações.')) { await call('star_limits_reset'); closeModal(); R.star = null; toast('Limites repostos.', 'ok'); } };
    $('lmExp').onclick = () => { const ta = $('lmJson'); ta.classList.remove('hidden'); ta.value = JSON.stringify(collect(), null, 2); ta.select(); toast('JSON seleccionado — copia com Ctrl+C.'); };
    $('lmImp').onclick = () => { const ta = $('lmJson'); if (ta.classList.contains('hidden')) { ta.classList.remove('hidden'); ta.value = ''; ta.placeholder = 'Cola aqui o JSON e clica ↑ JSON outra vez'; ta.focus(); return; }
      try { const o = JSON.parse(ta.value); const vals = Object.entries(o).filter(([k, v]) => parseInt(v) >= 80 && parseInt(v) <= 400); if (!vals.length) { alert('Nenhuma restrição válida no texto.'); return; }
        $('lmList').innerHTML = vals.map(([w, v]) => `<div class="kcard" data-wp="${esc(w.toUpperCase())}"><span>${esc(w.toUpperCase())}</span><div class="row"><input class="inp num lm-v" type="number" min="80" max="400" value="${parseInt(v)}"><button class="btn ghost lm-x">✖</button></div></div>`).join(''); toast(`Importadas ${vals.length} restrições (clica Guardar).`); } catch (e) { alert('JSON inválido: ' + e.message); } };
  }

  /* ================================================================ APP (pontos) */
  let appRwyFilter = 'ALL', appSel = new Set();
  async function runApp(force) {
    const el = $('appBody');
    if (!hasFlights()) { empty(el, 'Sem dados carregados.'); return null; }
    if (R.app && !force) return R.app;
    busy(el, 'A analisar IAS nos pontos de aproximação…');
    try { R.app = await call('run_app', +$('appRadius').value || 1, +$('appTol').value || 0); appSel = new Set(R.app.records.length ? [R.app.records[0].flight_id + '|' + R.app.records[0].rwy] : []); renderApp(); return R.app; }
    catch (e) { empty(el, 'Erro: ' + e.message); toast(e.message, 'err'); return null; }
  }
  function renderApp() {
    const r = R.app, el = $('appBody'); if (!r) return;
    if (r.message) { empty(el, r.message); $('appCount').textContent = ''; return; }
    const rwys = r.modes.map(m => m.slice(-2));
    $('appRwyBtns').innerHTML = `<button class="tog ${appRwyFilter === 'ALL' ? 'on' : ''}" data-v="ALL">Todas</button>` + rwys.map(x => `<button class="tog ${appRwyFilter === x ? 'on' : ''}" data-v="${x}">RWY ${x}</button>`).join('');
    $('appRwyBtns').querySelectorAll('.tog').forEach(b => b.onclick = () => { appRwyFilter = b.dataset.v; renderApp(); });
    const recs = r.records.filter(x => appRwyFilter === 'ALL' || x.rwy === appRwyFilter);
    $('appCount').textContent = `${recs.length} voo(s) com violações${appRwyFilter !== 'ALL' ? ' (RWY ' + appRwyFilter + ')' : ''}`;
    const appRows = recs.map(x => ({ ...x, pontos: (x.points || []).map(pt => `${pt.point} ${pt.ias == null ? '—' : Math.round(pt.ias)}/${Math.round(pt.limit)}`).join(' · ') }));
    drillScope('app', { 'Pistas': { title: 'Voos com violações na final', rows: appRows }, 'Voos ARR analisados': { title: 'Chegadas analisadas', rows: FP.state.flights.filter(f => f.cls === 'arr') }, 'Voos com violações': { title: 'Voos com violações na final (IAS por ponto / limite)', rows: appRows } });
    let h = '<div class="kgrid">' + C.kcard('Pistas', appRwyFilter === 'ALL' ? rwys.map(x => 'RWY ' + x).join(' + ') : 'RWY ' + appRwyFilter) + C.kcard('Voos ARR analisados', `${r.arrAnalysed}/${r.flightsTotal}`) +
      C.kcard('Raio CPA', r.radius + ' NM') + C.kcard('Tolerância', '±' + r.tol + ' kt') + C.kcard('Voos com violações', recs.length, '', recs.length ? 'bad' : 'ok') + '</div>';
    h += '<h3 class="mini">Violações por voo (ordem temporal) — clica para seleccionar</h3>' + (recs.length ? C.table([{ k: 'i', label: '#', fmt: (v, x, i) => i + 1 }, { k: 'tod', label: 'Hora' }, { k: 'date', label: 'Data' },
      { k: 'csn', label: 'Voo', fmt: (v, x) => csnLink(v, x.flight_id) }, { k: 'actype', label: 'Tipo' }, { k: 'rwy', label: 'Pista', fmt: v => 'RWY ' + v }, { k: 'violCount', label: 'Violações', cls: () => 'sep-r' },
      { k: 'maxAbsDeviation', label: 'Desvio máx', fmt: v => `<span class="sep-r">${fmt(v)} kt</span>` }], recs, { id: 'appViol', sortKey: 'epoch', rowClass: x => appSel.has(x.flight_id + '|' + x.rwy) ? 'rowsel' : '',
      onRow: (x, tr, ev) => { const k = x.flight_id + '|' + x.rwy; if (ev.target.closest('a')) return; appSel.has(k) ? appSel.delete(k) : appSel.add(k); tr.classList.toggle('rowsel'); renderAppDetail(); } }) : '<div class="hint sep-g">✓ Sem violações</div>');
    h += '<h3 class="mini">Detalhe do(s) voo(s) seleccionado(s)</h3><div id="appDetail"></div>';
    el.innerHTML = h; wireCsn(el); renderAppDetail();
  }
  function renderAppDetail() {
    const r = R.app, el = $('appDetail'); if (!r || !el) return;
    const sel = r.records.filter(x => appSel.has(x.flight_id + '|' + x.rwy));
    if (!sel.length) { el.innerHTML = '<div class="hint">Selecciona um voo na tabela de violações</div>'; return; }
    const head = ['Hora', 'Data', 'Voo', 'Pista'].concat([1, 2, 3, 4].flatMap(i => [`PONTO${i}`, `IAS${i}`, 'LIMITE', 'DESVIO']));
    const rows = sel.map(x => { const cells = [x.tod, x.date, `<b>${esc(x.csn)}</b>`, 'RWY ' + x.rwy];
      for (let i = 0; i < 4; i++) { const p = x.points[i]; if (!p) { cells.push('—', '—', '—', '—'); continue; }
        cells.push(esc(p.point), p.ias == null ? '—' : fmt(p.ias), fmt(p.limit), p.deviation == null ? '—' : `<span class="${Math.abs(p.deviation) > r.tol ? 'sep-r' : ''}">${p.deviation >= 0 ? '+' : ''}${fmt(p.deviation)}</span>`); }
      return `<tr>${cells.map(c => `<td>${c}</td>`).join('')}</tr>`; });
    el.innerHTML = `<table><thead><tr>${head.map(c => `<th>${c}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table>`;
  }
  async function appCharts() {
    const r = await runApp(false); if (!r || !r.histograms) return;
    const cap = `Dias: ${[...FP.state.days].length} · ${FP.state.flights.length} movimento(s) (${r.arrAnalysed} ARR) · Raio CPA ${r.radius} NM · tolerância ±${r.tol} kt`;
    modal('📊 Análise visual — IAS na final (APP)', `<p class="hint">${esc(cap)}</p><div class="grid2">` + r.histograms.map(hh => C.card(`${hh.point} · RWY ${hh.rwy} · limite ${hh.limit} kt`, C.stackedHist({ ...hh, xmin: hh.xmin, xmax: hh.xmax }, r.tol))).join('') +
      '</div><p class="hint">Inclui todas as passagens detectadas (não só violações). Verde = conforme · amarelo = abaixo do limite (com tolerância) · vermelho = acima do limite (com tolerância) · linha tracejada = limite publicado.</p>');
  }

  /* ================================================================ APP (por distância) */
  let adRwy = '02', adSel = new Set(), adComp = 'all', adBuf2 = null, adTop = 'all';
  const SCALE = Array.from({ length: 25 }, (_, i) => +(12 - i * .5).toFixed(1));
  const NAMED = { '02': { 11.5: 'PESEX', 8: 'NETVO', 4: 'OKNIB', 0: 'THR 02' }, '20': { 11.5: 'UPKAT', 8: 'TOPVI', 4: 'ROKOB', 0: 'THR 20' } };
  const SEGS = { '02': [['PESEX→NETVO', 11.5, 8, '#3b9cff'], ['NETVO→OKNIB', 7.5, 4, '#ff9b2f'], ['OKNIB→THR', 3.5, 0, '#ff5d5d']], '20': [['UPKAT→TOPVI', 11.5, 8, '#3b9cff'], ['TOPVI→ROKOB', 7.5, 4, '#ff9b2f'], ['ROKOB→THR', 3.5, 0, '#ff5d5d']] };
  function initScale() { if (!adSel.size) SCALE.forEach(n => adSel.add(n)); renderScale(); }
  function renderScale() {
    const rwys = FP.state.airport === 'LPPT' ? ['02', '20'] : [];
    $('adRwyBtns').innerHTML = rwys.map(x => `<button class="tog ${adRwy === x ? 'on' : ''}" data-v="${x}">PISTA: RWY ${x}</button>`).join('') || '<span class="hint">Escala da final disponível apenas para LPPT</span>';
    $('adRwyBtns').querySelectorAll('.tog').forEach(b => b.onclick = () => { adRwy = b.dataset.v; renderScale(); if (R.ad) runAppDist(true); });
    const named = NAMED[adRwy] || {};
    $('adScale').innerHTML = SCALE.map(n => `<button class="tog ${adSel.has(n) ? 'on' : ''} ${named[n] ? 'named' : ''}" data-n="${n}" title="${named[n] ? named[n] : n.toFixed(1) + ' NM da THR'}">${named[n] || n.toFixed(1)}</button>`).join('');
    $('adScale').querySelectorAll('.tog').forEach(b => b.onclick = () => { const n = +b.dataset.n; adSel.has(n) ? adSel.delete(n) : adSel.add(n); b.classList.toggle('on'); });
    $('adSegs').innerHTML = (SEGS[adRwy] || []).map(([lb, a, b, col], i) => `<button class="tog" data-i="${i}" style="border-color:${col};color:${col}">${lb} (${a}–${b})</button>`).join('');
    $('adSegs').querySelectorAll('.tog').forEach(b => b.onclick = () => { const [, a, lo] = SEGS[adRwy][+b.dataset.i]; const steps = SCALE.filter(n => n <= a && n >= lo); const allOn = steps.every(n => adSel.has(n)); steps.forEach(n => allOn ? adSel.delete(n) : adSel.add(n)); renderScale(); });
  }
  async function runAppDist(force) {
    const el = $('adBody');
    if (!hasFlights()) { empty(el, 'Sem dados carregados.'); return; }
    if (!adSel.size) { toast('Selecciona pelo menos um ponto na escala.', 'err'); return; }
    busy(el);
    try { R.ad = await call('run_app_dist', adRwy, parseInt($('adBuffer').value || '4'), [...adSel]); adBuf2 = R.ad.buffer; renderAppDist(); }
    catch (e) { empty(el, 'Erro: ' + e.message); toast(e.message, 'err'); }
  }
  function renderAppDist() {
    const d = R.ad, el = $('adBody'); if (!d) return;
    $('adCount').textContent = `${d.results.length} voo(s) com violações`;
    if (!d.results.length) { empty(el, `Sem violações encontradas · Pista: RWY${d.rwy} · Buffer: ±${d.buffer}kt · Voos ARR analisados: ${d.arrAnalysed} · Perfis construídos: ${d.profiles}`); return; }
    const comps = [...d.results.reduce((m, r) => m.set(r.comp, (m.get(r.comp) || 0) + 1), new Map())].sort((a, b) => b[1] - a[1]);
    let res = d.results.filter(r => adComp === 'all' || r.comp === adComp);
    if (adTop === 'top5above') res = res.filter(r => r.avgDev > 0).sort((a, b) => b.avgDev - a.avgDev).slice(0, 5);
    if (adTop === 'top5below') res = res.filter(r => r.avgDev < 0).sort((a, b) => a.avgDev - b.avgDev).slice(0, 5);
    const cols = d.columns.map(c => ({ label: c.named ? c.label : c.nm.toFixed(1), lim: c.profileLim, named: c.named, nm: c.nm }));
    const flights = res.map(r => { const vals = d.columns.map(c => r.dist[c.nm.toFixed(1)].ias); const mid = d.columns[Math.floor(d.columns.length / 2)]; const dd = r.dist[mid.nm.toFixed(1)];
      const viol = d.columns.some(c => { const x = r.dist[c.nm.toFixed(1)]; return x.dev != null && Math.abs(x.dev) > adBuf2; });
      return { csn: r.csn, vals, viol, color: !viol ? '#94a3b8' : (dd.dev > 0 ? '#ff5d5d' : '#3b9cff') }; });
    let h = `<div class="toolbar wrap" style="border:0;padding:0 0 8px"><label>Companhia <select id="adChartComp" class="inp tiny"><option value="all">Todas</option>${comps.map(([c, n]) => `<option value="${c}" ${adComp === c ? 'selected' : ''}>${c} (${n})</option>`).join('')}</select></label>
      <label>Buffer do gráfico <select id="adChartBuf" class="inp tiny">${[0, 2, 4, 6, 8, 10, 12].map(b => `<option ${adBuf2 === b ? 'selected' : ''}>${b}</option>`).join('')}</select> kt</label>
      <label>Filtro <select id="adTopF" class="inp tiny"><option value="all" ${adTop === 'all' ? 'selected' : ''}>Todos</option><option value="top5above" ${adTop === 'top5above' ? 'selected' : ''}>Top 5 ▲ acima</option><option value="top5below" ${adTop === 'top5below' ? 'selected' : ''}>Top 5 ▼ abaixo</option></select></label></div>`;
    h += C.card('📈 Perfil de velocidade ao longo da final', C.profile(cols, flights), 'Vermelho = acima do limite no ponto central · azul = abaixo · cinza = sem violação');
    const tcols = [{ k: 'csn', label: 'CALLSIGN', fmt: (v, r) => csnLink(v, r.flight_id) }, { k: 'actype', label: 'TIPO' }, { k: 'date', label: 'DATA' }, { k: 'tod', label: 'HORA' }, { k: 'rwy', label: 'PISTA', fmt: v => 'RWY ' + v }]
      .concat(d.columns.map(c => ({ k: 'd_' + c.nm.toFixed(1), label: c.named ? `${c.label} (${c.nm.toFixed(2)} NM)` : `${c.nm.toFixed(1)} NM`, fmt: (v, r) => { const x = r.dist[c.nm.toFixed(1)]; if (x.ias == null) return '—';
        return `<span class="${x.viol ? (x.dev > 0 ? 'dev-up' : 'dev-dn') : ''}" title="Lim: ${x.lim} kt Dev: ${x.dev >= 0 ? '+' : ''}${x.dev} kt">${x.ias}</span>`; } })))
      .concat([{ k: 'avgDev', label: 'MÉD DEV.', fmt: v => v == null ? '—' : `<span class="${v > 0 ? 'dev-up' : v < 0 ? 'dev-dn' : ''}">${v > 0 ? '+' : ''}${v}kt</span>` }]);
    const rows = res.map(r => { const o = { ...r }; d.columns.forEach(c => o['d_' + c.nm.toFixed(1)] = r.dist[c.nm.toFixed(1)].ias || 0); o.absDev = Math.abs(r.avgDev || 0); return o; });
    h += `<h3 class="mini">Violações por distância — ${res.length} voo(s) · buffer ±${d.buffer}kt · <span class="dev-dn">Azul</span> = abaixo do limite · <span class="dev-up">Vermelho</span> = acima</h3>` +
      C.table(tcols, rows, { id: 'adTable', sortKey: 'absDev', sortAsc: false, onRow: (r, tr, ev) => { if (ev.target.closest('a')) return;
        modal(`APP · ${r.csn} · RWY${r.rwy} · ${r.date}`, C.table([{ k: 'name', label: 'Ponto' }, { k: 'nm', label: 'Dist. (NM)', fmt: v => fmt(v, 2) }, { k: 'ias', label: 'IAS (kt)' }, { k: 'lim', label: 'Limite (kt)' },
          { k: 'dev', label: 'Desvio (kt)', fmt: v => v == null ? '—' : (v >= 0 ? '+' : '') + v }, { k: 'viol', label: 'Violação', fmt: (v, x) => v ? (x.dev > 0 ? '<span class="dev-up">⬆ ACIMA</span>' : '<span class="dev-dn">⬇ ABAIXO</span>') : '<span class="sep-g">✓ OK</span>' }],
          d.columns.map(c => ({ ...r.dist[c.nm.toFixed(1)], name: c.named ? c.label : c.nm.toFixed(1) + ' NM' })))); } });
    el.innerHTML = h; wireCsn(el);
    $('adChartComp').onchange = e => { adComp = e.target.value; renderAppDist(); }; $('adChartBuf').onchange = e => { adBuf2 = +e.target.value; renderAppDist(); }; $('adTopF').onchange = e => { adTop = e.target.value; renderAppDist(); };
  }

  /* ================================================================ FAST */
  let fastMode = 'all', fastInter = false, fastRwy = 'all', fastSelId = null;
  async function runFast() {
    const el = $('fastBody'); if (!hasFlights()) { empty(el, 'Sem dados. Aplica um filtro primeiro.'); return; }
    if (!R.final) { busy(el, 'A correr a Final…'); const f = await runFinal(false); if (!f) return; }
    try { R.fast = await call('fast', parseInt($('fastThr').value) || 160, fastMode, fastInter, fastRwy); renderFast(); }
    catch (e) { empty(el, 'Erro: ' + e.message); toast(e.message, 'err'); }
  }
  function renderFast() {
    const d = R.fast, el = $('fastBody'); if (!d) return;
    const thr = d.thr;
    $('fastCount').textContent = `${d.rows.length} par(es)${d.rows.length !== d.total ? ` (de ${d.total} total)` : ''}${fastInter ? ' · com DEP intercalar' : ''}${fastRwy !== 'all' ? ' · RWY ' + fastRwy : ''}`;
    if (!d.total) { empty(el, 'Sem pares — nenhuma aterragem consecutiva detectada na Final'); return; }
    if (!d.rows.length) { empty(el, 'Nenhum par encontrado com este filtro'); $('fastDetail').innerHTML = '<div class="empty">—</div>'; return; }
    el.innerHTML = C.table([{ k: 'i', label: '#', fmt: (v, r, i) => i + 1 }, { k: 'rwy', label: 'Pista', fmt: v => rwyBadge(v) }, { k: 'date', label: 'Data' }, { k: 'lead', label: 'Líder', fmt: (v, r) => csnLink(v, r.leadFlight) },
      { k: 'leadTod', label: 'Hora (THR)' }, { k: 'leadIas', label: 'IAS Líder', fmt: v => v == null ? '—' : fmt(v) + 'kt' }, { k: 'trail', label: 'Seguidor', fmt: (v, r) => csnLink(v, r.trailFlight) },
      { k: 'trailIas', label: 'IAS Seg.', fmt: v => v == null ? '—' : fmt(v) + 'kt' }, { k: 'sep', label: 'Sep. (s)', fmt: v => `<span class="${sepCls(v, thr)}">${fmt(v)}s</span>` }, { k: 'seq', label: 'Seq.', fmt: seqPill },
      { k: 'firstDep', label: 'DEP', fmt: v => v ? `<span class="badge dep">${esc(v)}</span>` : '—' }, { k: 'bNmAtDep', label: 'Seg. no DEP', fmt: v => v == null ? '—' : fmt(v, 1) + ' NM' }], d.rows,
      { id: 'fastTable', rowClass: r => r.id === fastSelId ? 'rowsel' : '', onRow: (r, tr, ev) => { if (ev.target.closest('a')) return; fastSelId = r.id; el.querySelectorAll('tr').forEach(x => x.classList.remove('rowsel')); tr.classList.add('rowsel'); fastDetail(r); } });
    wireCsn(el);
    const first = d.rows.find(r => r.id === fastSelId) || d.rows[0]; fastSelId = first.id; fastDetail(first);
  }
  function fastDetail(p) {
    const el = $('fastDetail'); const thr = R.fast.thr, W = 360, H = 500, topY = 18, thrY = H - 28, scale = (thrY - topY) / 12, ptY = nm => thrY - nm * scale;
    const wps = (p.rwy === '02' ? [['FAF/IF', 11.3], ['OKNIB', 7.0], ['NETVO', 4.5]] : [['UPKAT', 11.0], ['TOPVI', 8.0], ['ROKOB', 5.0]]);
    const trailNm = p.sep * 140 / 3600, col = p.sep < 120 ? C.RED : p.sep < 160 ? C.ORANGE : C.GREEN;
    let svg = `<svg viewBox="0 0 ${W} ${H}" class="chart-svg" style="max-height:420px"><line x1="${W / 2}" x2="${W / 2}" y1="${topY}" y2="${thrY}" stroke="#24314d" stroke-width="3"/>`;
    for (let n = 0; n <= 12; n += 2) svg += `<line x1="${W / 2 - 6}" x2="${W / 2 + 6}" y1="${ptY(n)}" y2="${ptY(n)}" stroke="#8a93a6"/><text x="${W / 2 + 10}" y="${ptY(n) + 3}" class="lbl">${n} NM</text>`;
    wps.forEach(([n, d]) => svg += `<circle cx="${W / 2}" cy="${ptY(d)}" r="4" fill="#ffd166"/><text x="${W / 2 - 10}" y="${ptY(d) + 3}" text-anchor="end" fill="#ffd166">${n}</text>`);
    svg += `<rect x="${W / 2 - 40}" y="${thrY - 3}" width="80" height="6" fill="#8a93a6"/><text x="${W / 2}" y="${thrY + 18}" text-anchor="middle" class="lbl">THR ${p.rwy}</text>`;
    svg += `<circle cx="${W / 2}" cy="${thrY - 8}" r="7" fill="#0b5cad"/><text x="${W / 2 + 14}" y="${thrY - 5}" fill="#7cc4ff">${esc(p.lead)} · THR ${p.leadTod}</text>`;
    svg += `<circle cx="${W / 2}" cy="${ptY(Math.min(trailNm, 12))}" r="7" fill="#7c3aed"/><text x="${W / 2 + 14}" y="${ptY(Math.min(trailNm, 12)) + 4}" fill="#c77dff">${esc(p.trail)} · ${fmt(p.sep)}s • ${trailNm.toFixed(1)} NM</text>`;
    svg += `<line x1="${W / 2 - 24}" x2="${W / 2 - 24}" y1="${ptY(Math.min(trailNm, 12))}" y2="${thrY - 8}" stroke="${col}" stroke-width="2" marker-end="url(#arr)"/>`;
    p.deps.forEach((d, i) => svg += `<rect x="${W / 2 + 60}" y="${ptY(1.5 + i * .5) - 8}" width="90" height="16" rx="3" fill="${C.ORANGE}"/><text x="${W / 2 + 105}" y="${ptY(1.5 + i * .5) + 4}" text-anchor="middle" fill="#061021" font-weight="700">DEP ${esc(d.csn)}</text>`);
    svg += '</svg>';
    const cardL = (title, csn, tod, ias, alt, extra) => `<div class="kcard" style="margin-bottom:8px"><span>${title}</span><b style="font-size:14px">${esc(csn)}</b><div class="s">Hora THR ${tod} · IAS ${ias == null ? '—' : fmt(ias) + ' kt'} · Alt THR ${fmt(alt)} ft${extra || ''}</div></div>`;
    el.innerHTML = `<div style="color:${col};font-weight:700;margin-bottom:6px">Separação ${fmt(p.sep)} s · ${seqPill(p.seq)} · RWY ${p.rwy} · ${p.date}</div>` +
      cardL('Líder (precedente)', p.lead, p.leadTod, p.leadIas, p.leadAlt) +
      p.deps.map(d => `<div class="kcard" style="margin-bottom:8px;border-color:${C.ORANGE}"><span>DEP intercalar</span><b style="font-size:14px">${esc(d.csn)}</b><div class="s">${d.tod} · descolou entre as duas aterragens</div></div>`).join('') +
      cardL('Seguidor', p.trail, p.trailTod, p.trailIas, p.trailAlt, `<br>${fmt(p.sep)}s atrás da soleira · distância aprox. quando o líder cruzou a THR: ${trailNm.toFixed(1)} NM`) +
      (p.depCnt ? `<div class="hint sep-o">⚠ ${p.depCnt} descolagem(ns) entre as duas aterragens${p.bNmAtDep != null ? ` · seguidor a ${fmt(p.bNmAtDep, 1)} NM da THR no 1.º DEP` : ''}</div>` : '') + svg;
  }

  /* ================================================================ ANÁLISE DE DADOS */
  const sdFilters = () => ({ limit: parseInt($('sdLimit').value), f_date: $('sdDate').value, f_hour: $('sdHour').value, f_rwy: $('sdRwy').value, f_tipo: $('sdTipo').value, f_seq: $('sdSeq').value, f_depnm: $('sdDepNm').value, f_crit: $('sdCrit').value });
  async function runDados() {
    const el = $('sdBody'); if (!hasFlights()) { empty(el, 'Sem dados. Aplica um filtro primeiro.'); return; }
    if (!R.final) { busy(el, 'A correr a Final…'); if (!(await runFinal(false))) return; }
    busy(el);
    try { R.dados = await call('data_analysis', sdFilters()); renderDados(); } catch (e) { empty(el, 'Erro: ' + e.message); toast(e.message, 'err'); }
  }
  function fillSel(id, vals, labelFn) { const s = $(id), cur = s.value; s.innerHTML = s.options[0].outerHTML + vals.map(v => `<option value="${esc(v)}">${esc(labelFn ? labelFn(v) : v)}</option>`).join(''); if ([...s.options].some(o => o.value === cur)) s.value = cur; }
  function renderDados() {
    const d = R.dados, el = $('sdBody'), k = d.kpis, limit = d.kpis && parseInt($('sdLimit').value), ch = d.charts;
    fillSel('sdDate', d.options.dates, v => `${v.slice(4, 6)}/${v.slice(2, 4)}/20${v.slice(0, 2)}`); fillSel('sdHour', d.options.hours, v => v + 'h'); fillSel('sdRwy', d.options.rwys, v => 'RWY ' + v); fillSel('sdSeq', d.options.seqs);
    const pk = p => p ? `${p.hour}h (${p.n})` : '—';
    const dr = d.rows || [], crit = dr.filter(x => x.sep < (parseInt($('sdLimit').value) || 165)), fl = FP.state.flights.filter(f => f.cls !== 'lvl');
    const hourRows = (d.tables && d.tables.hour) || [], byRwy = {}; dr.forEach(x => { byRwy[x.rwy] = (byRwy[x.rwy] || 0) + 1; });
    drillScope('dados', { 'Movimentos': { title: 'Movimentos (radar)', rows: fl }, 'Passagens THR detetadas': { title: 'Aterragens detetadas (Final)', rows: (R.final && R.final.results) || [] }, 'Pares globais': { title: 'Todos os pares de aterragens', rows: dr },
      'Pares analisados': { title: 'Pares analisados', rows: dr }, 'Abaixo do limite': { title: 'Pares abaixo do limite de separação', rows: crit }, 'Críticos com DEP': { title: 'Pares críticos com partida intercalada', rows: crit.filter(x => x.depCnt > 0) }, 'Críticos sem DEP': { title: 'Pares críticos sem partida intercalada', rows: crit.filter(x => !x.depCnt) },
      'Menor separação': { title: 'Pares por separação (crescente)', rows: dr.slice().sort((a, b) => a.sep - b.sep) }, 'Média': { title: 'Separações de todos os pares', rows: dr }, 'Mediana': { title: 'Separações de todos os pares', rows: dr.slice().sort((a, b) => a.sep - b.sep) },
      'Hora mais crítica': { title: 'Resumo por hora', rows: hourRows }, 'Hora mais movimentada': { title: 'Resumo por hora', rows: hourRows }, 'Pista mais usada': { title: 'Pares por pista', rows: Object.entries(byRwy).map(([r, n]) => ({ rwy: r, pairs: n })) },
      'DEP entre chegadas': { title: 'Pares com partidas intercaladas', rows: dr.filter(x => x.depCnt > 0) }, 'Movimentos ARR+DEP': { title: 'Chegadas e partidas (radar)', rows: fl },
      'Pico aterragens': { title: 'Resumo por hora', rows: hourRows }, 'Pico descolagens': { title: 'Resumo por hora', rows: hourRows }, 'Pico movimentos': { title: 'Resumo por hora', rows: hourRows } });
    let h = '<div class="kgrid">' + C.kcard('Ficheiros carregados', k.files) + C.kcard('Movimentos', k.movementRows) + C.kcard('Passagens THR detetadas', k.landings) + C.kcard('Pares globais', k.allPairs) + '</div>';
    h += `<div class="hint" style="margin-bottom:8px">${k.pairs} pares precedente/seguidor analisados · ${k.crit} abaixo de ${limit}s</div>`;
    h += '<div class="kgrid">' + C.kcard('Pares analisados', k.pairs) + C.kcard('Abaixo do limite', k.crit, '', k.crit ? 'bad' : 'ok') + C.kcard('Críticos com DEP', k.critDep) + C.kcard('Críticos sem DEP', k.critNoDep) +
      C.kcard('Menor separação', k.min == null ? '—' : fmt(Math.round(k.min)) + ' s') + C.kcard('Média', k.avg == null ? '—' : fmt(Math.round(k.avg)) + ' s') + C.kcard('Mediana', k.median == null ? '—' : fmt(Math.round(k.median)) + ' s') +
      C.kcard('Hora mais crítica', k.critHour) + C.kcard('Hora mais movimentada', k.busyHour) + C.kcard('Pista mais usada', k.mainRwy) + C.kcard('DEP entre chegadas', k.depTotal) + C.kcard('Movimentos ARR+DEP', k.movs) +
      C.kcard('Pico aterragens', pk(k.peakArr)) + C.kcard('Pico descolagens', pk(k.peakDep)) + C.kcard('Pico movimentos', pk(k.peakTotal)) + '</div>';
    h += '<div class="card narr"><h3>Síntese</h3>' + d.narrative.paragraphs.map(p => `<p>${esc(p)}</p>`).join('') + '<div class="insights">' + d.narrative.insights.map(i => `<span>${esc(i)}</span>`).join('') + '</div></div>';
    const hours = Object.keys(ch.byHour).sort();
    h += '<div class="grid2">' + C.card('Distribuição das separações', C.bars(ch.hist.total, ch.hist.labels, { red: ch.hist.red, tips: ch.hist.crit.map(c => c + ' críticos') }), `Vermelho = intervalos que intersectam o limite de ${limit}s`) +
      C.card('Resumo por hora', C.grouped([{ name: 'Total', values: hours.map(x => ch.byHour[x].total), color: C.BLUE }, { name: 'Críticos', values: hours.map(x => ch.byHour[x].crit), color: C.RED }], hours.map(x => x + 'h'))) +
      C.card('Análise por pista', C.grouped([{ name: 'Total', values: Object.values(ch.byRwy).map(v => v.total), color: C.BLUE }, { name: 'Críticos', values: Object.values(ch.byRwy).map(v => v.crit), color: C.RED }, { name: 'Com DEP', values: Object.values(ch.byRwy).map(v => v.dep), color: C.ORANGE }], Object.keys(ch.byRwy).map(r => 'RWY ' + r))) +
      C.card('Tipo de sequência', C.grouped([{ name: 'Total', values: Object.values(ch.bySeq).map(v => v.total), color: C.BLUE }, { name: 'Críticos', values: Object.values(ch.bySeq).map(v => v.crit), color: C.RED }], Object.keys(ch.bySeq))) +
      C.card('Movimentos por hora', C.bars(Object.values(ch.movHour).map(v => v.total), Object.keys(ch.movHour).map(x => x + 'h'))) +
      C.card('Movimentos por companhia (top 15)', C.hbars(ch.companies.map(c => ({ label: c.company, value: c.movements })))) +
      C.card('Top 10 companhias por taxa de ocorrências críticas', C.hbars(ch.topCritCompanies.map(c => ({ label: c.company, value: +(c.rate * 100).toFixed(1), text: fmt(c.rate * 100, 1) + '%', color: C.RED, title: `${c.critical} críticos em ${c.movements} movimentos` })))) +
      C.card('Posição do seguidor no momento do DEP', C.bars(ch.depDist.total, ch.depDist.labels.map(l => l + ' NM'), { red: [true, true, false, false, false], tips: ch.depDist.classes.map((c, i) => `${c} · ${ch.depDist.crit[i]} em pares críticos`) }), `${ch.depDist.n} descolagens intercaladas`) +
      C.card('IAS da aeronave seguidora', C.grouped([{ name: 'Total', values: ch.ias.total, color: C.BLUE }, { name: 'Críticos', values: ch.ias.crit, color: C.RED }], ch.ias.labels)) + '</div>';
    h += C.card('Separação vs distância do seguidor', C.scatter(ch.scatter.map(p => ({ x: p.sep, y: p.nm, color: p.dep ? C.ORANGE : C.BLUE, stroke: p.crit ? C.RED : null, title: `${p.lead} → ${p.trail} · ${fmt(p.sep)}s · ${p.nm} NM · IAS seg. ${p.ias == null ? '—' : fmt(p.ias)}` })),
      { vline: limit, ygrid: [3, 4, 5, 6], xlabel: 'separação (s)', ylabel: 'distância do seguidor à THR quando o precedente cruzou a soleira (NM, a 140 kt)' }), 'Laranja = com DEP · azul = sem DEP · contorno vermelho = par crítico');
    h += `<section class="card"><h3>Timeline operacional</h3><div class="toolbar wrap" style="border:0;padding:0 0 6px"><label>Zoom <select id="tlZoom" class="inp tiny"><option value="all">Dia completo</option><option value="4">4 h</option><option value="2" selected>2 h</option><option value="1">1 h</option></select></label>
      <label>Hora foco <select id="tlFocus" class="inp tiny"><option value="auto">auto</option>${hours.map(x => `<option value="${+x}">${x}h</option>`).join('')}</select></label><label>Etiquetas <select id="tlLbl" class="inp tiny"><option value="crit">só críticos</option><option value="all">todos</option><option value="none">nenhuma</option></select></label></div><div class="timeline" id="tlWrap"></div></section>`;
    h += '<div class="grid2">' + C.card('Top 10 situações mais críticas', C.table([{ k: 'rwy', label: 'Pista', fmt: v => 'RWY ' + v }, { k: 'date', label: 'Data' }, { k: 'leadTod', label: 'Hora A' }, { k: 'lead', label: 'Callsign A', fmt: (v, r) => csnLink(v, r.leadFlight) }, { k: 'trail', label: 'Callsign B', fmt: (v, r) => csnLink(v, r.trailFlight) },
      { k: 'seq', label: 'Seq.', fmt: seqPill }, { k: 'sep', label: 'Sep. s', fmt: v => `<span class="${sepCls(v, limit)}">${fmt(v)}</span>` }, { k: 'sepNm', label: 'Sep. NM' }, { k: 'firstDep', label: 'DEP', fmt: v => v ? `<span class="badge dep">${esc(v)}</span>` : 'Sem DEP' }, { k: 'firstDepTod', label: 'Hora DEP' }, { k: 'bSecAtDep', label: 'Seguidor no DEP (s)' }], d.tables.top10)) +
      C.card('Resumo por hora', C.table([{ k: 'hour', label: 'Hora', fmt: v => v + 'h' }, { k: 'arrivals', label: 'Chegadas' }, { k: 'pairs', label: 'Pares' }, { k: 'crit', label: '< limite', cls: r => r.crit ? 'sep-r' : '' }, { k: 'dep', label: 'Com DEP' }, { k: 'minSep', label: 'Menor sep.', fmt: v => v + ' s' }, { k: 'avgSep', label: 'Média sep.', fmt: v => fmt(v, 1) + ' s' }], d.tables.hour)) + '</div>';
    h += C.card('Resumo por companhia', C.table([{ k: 'company', label: 'Companhia' }, { k: 'movements', label: 'Movimentos' }, { k: 'arr', label: 'ARR' }, { k: 'dep', label: 'DEP' }, { k: 'critical', label: 'Ocorrências críticas' }, { k: 'rate', label: 'Taxa por movimento', fmt: v => fmt(v * 100, 1) + '%' }], d.tables.companies, { limit: 40 }));
    el.innerHTML = h; wireCsn(el);
    const drawTl = () => { const z = $('tlZoom').value, f = $('tlFocus').value; $('tlWrap').innerHTML = C.timeline(ch.timeline, { all: z === 'all', hours: +z || 2, pxPerHour: { 4: 1200, 2: 1500, 1: 2000 }[z] || 1500, focusHour: f === 'auto' ? null : +f, labels: $('tlLbl').value }); };
    ['tlZoom', 'tlFocus', 'tlLbl'].forEach(id => $(id).onchange = drawTl); drawTl();
  }

  /* ================================================================ ANÁLISE DIÁRIA */
  async function runDiaria() {
    const el = $('dyBody'); if (!hasFlights()) { empty(el, 'Sem dados. Aplica um filtro primeiro.'); return; }
    if (!R.final) { busy(el, 'A correr a Final…'); if (!(await runFinal(false))) return; }
    busy(el);
    try { R.diaria = await call('daily', parseInt($('sdLimit').value) || 165); renderDiaria(); } catch (e) { empty(el, 'Erro: ' + e.message); toast(e.message, 'err'); }
  }
  function renderDiaria() {
    const d = R.diaria, el = $('dyBody'), k = d.kpis, st = d.stats, pk = p => p ? `${p.hour}h (${p.n})` : '—';
    const flD = FP.state.flights.filter(f => f.cls !== 'lvl');
    drillScope('diaria', { 'Dias selecionados': { title: 'Estatísticas por dia', rows: st }, 'Movimentos ARR+DEP': { title: 'Chegadas e partidas (radar)', rows: flD }, 'Aterragens': { title: 'Aterragens (Final)', rows: (R.final && R.final.results) || [] }, 'Descolagens': { title: 'Partidas (radar)', rows: flD.filter(f => f.cls === 'dep') },
      'Pares': { title: 'Estatísticas por dia', rows: st }, [`Abaixo de ${d.limit}s`]: { title: 'Pares críticos por dia', rows: st }, 'Críticos com DEP': { title: 'Estatísticas por dia', rows: st }, 'Pico de aterragens': { title: 'Estatísticas por dia', rows: st }, 'Pico de descolagens': { title: 'Estatísticas por dia', rows: st },
      'Callsigns comuns aos dias': { title: 'Callsigns presentes em todos os dias', rows: (d.common || []).map(c => typeof c === 'string' ? { csn: c } : c) } });
    let h = '<div class="kgrid">' + C.kcard('Dias selecionados', k.days) + C.kcard('Movimentos ARR+DEP', k.movs) + C.kcard('Aterragens', k.arr) + C.kcard('Descolagens', k.dep) + C.kcard('Pares', k.pairs) + C.kcard(`Abaixo de ${d.limit}s`, k.crit, '', k.crit ? 'bad' : 'ok') +
      C.kcard('Críticos com DEP', k.critDep) + C.kcard('Pico de aterragens', pk(k.peakArr)) + C.kcard('Pico de descolagens', pk(k.peakDep)) + C.kcard('Callsigns comuns aos dias', k.common) + '</div>';
    h += '<div class="card narr"><h3>Síntese</h3>' + d.narrative.paragraphs.map(p => `<p>${esc(p)}</p>`).join('') + '<div class="insights">' + d.narrative.insights.map(i => `<span>${esc(i)}</span>`).join('') + '</div></div>';
    h += '<div class="grid2">' + C.card('Movimentos por dia', C.grouped([{ name: 'ARR', values: st.map(s => s.arr), color: C.BLUE }, { name: 'DEP', values: st.map(s => s.dep), color: C.RED }], st.map(s => s.label))) +
      C.card('Ocorrências críticas por dia', C.bars(st.map(s => s.crit), st.map(s => s.label), { color: C.RED })) +
      C.card('Pico horário por dia', C.bars(st.map(s => s.peakN), st.map(s => `${s.label} ${s.peakHour || ''}h`)), 'Hora com mais movimentos em cada dia selecionado') +
      C.card('Companhias por dia (top 10)', C.table([{ k: 'label', label: 'Dia' }, { k: 'companies', label: 'Companhias (movimentos)', fmt: v => v.map(([c, n]) => `${c} (${n})`).join(' · ') }], st), 'Companhia inferida pelo prefixo do callsign') + '</div>';
    if (d.weekday.length) {
      const wd = d.weekday;
      h += '<div class="grid2">' + C.card('Média de movimentos por dia da semana', C.bars(wd.map(e => e.avgMov), wd.map(e => e.name.slice(0, 3)), { dec: 1 }), 'Total de movimentos ÷ nº de dias desse dia da semana.') +
        C.card('Média de pares críticos por dia da semana', C.bars(wd.map(e => e.avgCrit), wd.map(e => e.name.slice(0, 3)), { color: C.RED, dec: 1 }), `Pares abaixo do limite (${d.limit}s) ÷ nº de dias.`) + '</div>';
      h += C.card('Padrões por dia da semana', C.table([{ k: 'name', label: 'Dia da semana' }, { k: 'days', label: 'Nº dias' }, { k: 'mov', label: 'Mov. totais' }, { k: 'avgMov', label: 'Méd mov/dia' }, { k: 'crit', label: 'Críticos totais' }, { k: 'avgCrit', label: 'Méd crít/dia' }, { k: 'rate', label: 'Taxa crít.', fmt: v => v + '%' }, { k: 'dates', label: 'Datas', fmt: v => v.join(', ') }], wd));
    }
    h += '<div class="grid2">' + C.card('Callsigns comuns entre dias', C.table([{ k: 'csn', label: 'Callsign' }, { k: 'count', label: 'Nº dias' }, { k: 'days', label: 'Dias', fmt: v => v.map(x => `${x.slice(4, 6)}/${x.slice(2, 4)}`).join(', ') }, { k: 'movements', label: 'Movimentos' }, { k: 'company', label: 'Companhia' }], d.common, { limit: 80 })) +
      C.card('Resumo por dia e hora', C.table([{ k: 'dateFmt', label: 'Data' }, { k: 'hour', label: 'Hora', fmt: v => v + 'h' }, { k: 'arr', label: 'ARR' }, { k: 'dep', label: 'DEP' }, { k: 'total', label: 'Movimentos' }, { k: 'pairs', label: 'Pares' }, { k: 'crit', label: 'Críticos', cls: r => r.crit ? 'sep-r' : '' }], d.hourTable, { limit: 200 })) + '</div>';
    el.innerHTML = h;
  }

  /* ================================================================ RRMS */
  async function runRrms(force) {
    const el = $('rrBody'); if (!hasFlights()) { empty(el, 'Sem dados. Aplica um filtro primeiro.'); return; }
    if (FP.state.airport !== 'LPPT') { empty(el, 'RRMS disponível apenas para LPPT (pontos TWY U6 / TWY P).'); return; }
    if (!R.rrms || force) { busy(el); try { R.rrms = await call('run_rrms'); } catch (e) { empty(el, 'Erro: ' + e.message); toast(e.message, 'err'); return; } }
    renderRrms();
  }
  const pct = (arr, p) => { if (!arr.length) return null; const s = [...arr].sort((a, b) => a - b), i = p / 100 * (s.length - 1), lo = Math.floor(i), hi = Math.ceil(i); return Math.round(s[lo] + (s[hi] - s[lo]) * (i - lo)); };
  const rrStats = rows => { const alts = rows.map(h => h.altFt).filter(v => v != null && v > 0), ias = rows.map(h => h.ias).filter(v => v); if (!alts.length) return null;
    return { n: rows.length, altMin: Math.min(...alts), altAvg: Math.round(alts.reduce((a, b) => a + b, 0) / alts.length), altMax: Math.max(...alts), iasMin: ias.length ? Math.min(...ias) : null, iasAvg: ias.length ? Math.round(ias.reduce((a, b) => a + b, 0) / ias.length) : null, iasMax: ias.length ? Math.max(...ias) : null }; };
  function renderRrms() {
    const d = R.rrms, el = $('rrBody'); if (!d) return;
    const cat = $('rrCat').value, grp = $('rrGrp').value, metric = $('rrMetric').value, rwyF = $('rrRwy').value;
    const shown = d.hits.filter(h => cat === 'all' || (cat === 'MH' ? 'MH'.includes(h.cat) : h.cat === cat));
    const s02 = shown.filter(h => h.rwy === '02'), s20 = shown.filter(h => h.rwy === '20'), filt = shown.filter(h => rwyF === 'all' || h.rwy === rwyF);
    $('rrCount').textContent = `${shown.length} passagens · analisados ${d.dbg.total}`;
    const st = rows => { const s = rrStats(rows); return s ? [`${s.altMin} / ${s.altAvg} / ${s.altMax} ft`, `${s.iasMin == null ? '—' : s.iasMin} / ${s.iasAvg == null ? '—' : s.iasAvg} / ${s.iasMax == null ? '—' : s.iasMax} kt`] : ['—', '—']; };
    const [a02, i02] = st(s02), [a20, i20] = st(s20);
    let h = `<div class="hint" style="margin-bottom:8px">RRMS — Reduced Runway Separation Minima · Pontos 2400m das THR deslocadas · ${d.points['02'].label} (${d.points['02'].dms}) · ${d.points['20'].label} (${d.points['20'].dms}) · aeronaves DEP e sobrevoos</div>`;
    drillScope('rrms', { 'RWY 02 — passagens': { title: 'Passagens no ponto 2400 m — RWY 02', rows: s02 }, 'RWY 20 — passagens': { title: 'Passagens no ponto 2400 m — RWY 20', rows: s20 },
      'Alt. mín/méd/máx RWY 02': { title: 'Passagens RWY 02 (altitude)', rows: s02.slice().sort((a, b) => a.altFt - b.altFt) }, 'Alt. mín/méd/máx RWY 20': { title: 'Passagens RWY 20 (altitude)', rows: s20.slice().sort((a, b) => a.altFt - b.altFt) },
      'IAS mín/méd/máx RWY 02': { title: 'Passagens RWY 02 (IAS)', rows: s02.slice().sort((a, b) => (a.ias || 0) - (b.ias || 0)) }, 'IAS mín/méd/máx RWY 20': { title: 'Passagens RWY 20 (IAS)', rows: s20.slice().sort((a, b) => (a.ias || 0) - (b.ias || 0)) } });
    h += '<div class="kgrid">' + C.kcard('RWY 02 — passagens', s02.length, `${s02.filter(x => x.airborne).length} no ar · ${s02.filter(x => !x.airborne).length} no solo`) + C.kcard('RWY 20 — passagens', s20.length, `${s20.filter(x => x.airborne).length} no ar · ${s20.filter(x => !x.airborne).length} no solo`) +
      C.kcard('Alt. mín/méd/máx RWY 02', a02) + C.kcard('Alt. mín/méd/máx RWY 20', a20) + C.kcard('IAS mín/méd/máx RWY 02', i02) + C.kcard('IAS mín/méd/máx RWY 20', i20) + '</div>';
    // estatísticas por grupo
    const groups = new Map(); const keyOf = x => ({ rwy: 'RWY ' + x.rwy, hour: x.hour + 'h', gnd: x.airborne ? '✈ No ar (alt ≥ 50ft)' : '⊙ No solo (alt < 50ft)', cat: { M: 'M (Medium)', H: 'H (Heavy)' }[x.cat] || '? (Desconhecido)', actype: x.acType || 'Desconhecido', top10csn: `${x.csn} (${x.acType}) [${x.cat}]`, comp: x.comp }[grp]);
    filt.forEach(x => { const k = keyOf(x); if (!groups.has(k)) groups.set(k, []); groups.get(k).push(x); });
    let grows = [...groups.entries()].map(([g, rows]) => ({ g, ...(rrStats(rows) || {}), n: rows.length })).filter(r => r.altMin != null);
    if (['actype', 'top10csn', 'comp'].includes(grp)) grows.sort((a, b) => b.n - a.n); else grows.sort((a, b) => String(a.g).localeCompare(String(b.g)));
    if (grp === 'top10csn') grows = grows.slice(0, 10); if (grp === 'comp') grows = grows.slice(0, 12);
    h += C.card('Estatísticas no ponto de referência (valores interpolados)', C.table([{ k: 'g', label: 'Grupo' }, { k: 'n', label: 'N' }, { k: 'altMin', label: 'Alt. mín (ft)' }, { k: 'altAvg', label: 'Alt. méd (ft)' }, { k: 'altMax', label: 'Alt. máx (ft)' }, { k: 'iasMin', label: 'IAS mín (kt)' }, { k: 'iasAvg', label: 'IAS méd (kt)' }, { k: 'iasMax', label: 'IAS máx (kt)' }], grows));
    // percentis por hora
    const src = { all: shown, '02': s02, '20': s20 }[rwyF] || shown;
    const byH = new Map(); src.forEach(x => { const v = metric === 'alt' ? x.altFt : x.ias; if (v != null && v > 0) { if (!byH.has(x.hour)) byH.set(x.hour, []); byH.get(x.hour).push(v); } });
    const buckets = [...byH.keys()].sort().map(hh => { const v = byH.get(hh); return { label: hh + 'h', n: v.length, p0: pct(v, 0), p25: pct(v, 25), p50: pct(v, 50), p75: pct(v, 75), p100: pct(v, 100) }; });
    h += C.card(`Evolução temporal no ponto (por hora) — ${metric === 'alt' ? 'altitude (ft)' : 'IAS (kt)'}`, C.percentiles(buckets, { unit: metric === 'alt' ? 'ft' : 'kt' }));
    const air = filt.filter(x => x.airborne).length, gnd = filt.length - air, pa = filt.length ? Math.round(air / filt.length * 100) : 0;
    const hrs = [...new Set(filt.map(x => x.hour))].sort();
    h += C.card('No ar vs Solo no ponto 2400m — por hora', `<div class="hint" style="margin-bottom:6px">Total: ${air} no ar (${pa}%) · ${gnd} no solo (${100 - pa}%) · ${gnd === 0 ? '✓ Todas as aeronaves já estavam no ar ao passar o ponto' : air === 0 ? '⚠ Nenhuma aeronave estava no ar ao passar o ponto' : `⚠ ${gnd} aeronave(s) passaram o ponto ainda no solo`}</div>` +
      C.grouped([{ name: 'No ar', values: hrs.map(x => filt.filter(y => y.hour === x && y.airborne).length), color: '#16a34a' }, { name: 'Solo', values: hrs.map(x => filt.filter(y => y.hour === x && !y.airborne).length), color: C.ORANGE }], hrs.map(x => x + 'h')));
    h += '<div class="grid2">' + ['02', '20'].map(r => { const rows = shown.filter(x => x.rwy === r); const hh = [...new Set(rows.map(x => x.hour))].sort(); return C.card(`RWY ${r} — distribuição horária (${rows.length} passagens)`, C.hbars(hh.map(x => ({ label: x + 'h', value: rows.filter(y => y.hour === x).length })))); }).join('') + '</div>';
    h += C.card(`Detalhe das passagens (${filt.length} registos)`, C.table([{ k: 'csn', label: 'Callsign', fmt: (v, x) => csnLink(v, x.flight_id) }, { k: 'cat', label: 'WTC' }, { k: 'acType', label: 'Tipo A/C' }, { k: 'rwy', label: 'RWY' }, { k: 'airborne', label: 'Status', fmt: v => v ? '▲ No ar' : '⚫ Solo' }, { k: 'date', label: 'Data' }, { k: 'tod', label: 'Hora' },
      { k: 'altFt', label: 'Alt. (ft)', fmt: v => `<span class="${v < 500 ? 'sep-r' : v < 1000 ? 'sep-o' : 'sep-g'}">${v}</span>` }, { k: 'ias', label: 'IAS (kt)', fmt: v => v == null ? '—' : v }, { k: 'distNM', label: 'Dist. (NM)' }], filt, { limit: 2000 }));
    h += `<div class="hint">RRMS · DEP independente do filtro ARR/DEP · Analisados: ${d.dbg.total} · Detectados: ${shown.length}</div>`;
    el.innerHTML = h; wireCsn(el);
  }

  /* ================================================================ ROT */
  async function runRot() {
    const el = $('rotBody'); if (!hasFlights()) { empty(el, 'Sem dados.'); return; }
    busy(el);
    try { R.rot = await call('run_rot'); renderRot(); } catch (e) { empty(el, 'Erro: ' + e.message); toast(e.message, 'err'); }
  }
  function renderRot() {
    const d = R.rot, el = $('rotBody'), rf = $('rotRwy').value, cf = $('rotCls').value; if (!d) return;
    const rws = [...new Set(d.results.map(r => r.rwy))].sort(); const sel = $('rotRwy'); sel.innerHTML = '<option value="all">Todas</option>' + rws.map(r => `<option value="${r}" ${rf === r ? 'selected' : ''}>RWY ${r}</option>`).join('');
    const rows = d.results.filter(r => (rf === 'all' || r.rwy === rf) && (cf === 'all' || (r.cls || 'arr') === cf));
    const nA = rows.filter(r => (r.cls || 'arr') === 'arr').length, nD = rows.length - nA;
    $('rotCount').textContent = `${rows.length} movimento(s) · ${nA} ARR · ${nD} DEP`;
    const stats = list => { const v = list.map(r => r.rotS).sort((a, b) => a - b), n = v.length; return { n, mean: n ? v.reduce((a, b) => a + b, 0) / n : null, p85: n ? v[Math.min(Math.floor(n * .85), n - 1)] : null, p95: n ? v[Math.min(Math.floor(n * .95), n - 1)] : null, max: n ? v[n - 1] : null }; };
    const S = stats(rows), SA = stats(rows.filter(r => (r.cls || 'arr') === 'arr')), SD = stats(rows.filter(r => r.cls === 'dep'));
    const rotSorted = rows.slice().sort((a, b) => b.rotS - a.rotS);
    const sv = v => v == null ? '—' : fmt(v) + ' s';
    drillScope('rot', { 'Saídas / entradas': { title: 'Movimentos por taxiway de saída / entrada', rows: rows.slice().sort((a, b) => String(a.twy || a.twyTower || '~').localeCompare(String(b.twy || b.twyTower || '~'))) }, 'N.º movimentos': { title: 'Movimentos com ROT', rows: rows }, 'ROT médio': { title: 'ROT por movimento', rows: rotSorted }, 'P85': { title: 'ROT por movimento (decrescente)', rows: rotSorted }, 'P95': { title: 'ROT por movimento (decrescente)', rows: rotSorted }, 'Máximo': { title: 'ROT por movimento (decrescente)', rows: rotSorted },
      'ROT chegada': { title: 'ROT das chegadas', rows: rotSorted.filter(r => (r.cls || 'arr') === 'arr') }, 'ROT partida': { title: 'ROT das partidas', rows: rotSorted.filter(r => r.cls === 'dep') } });
    const byTwy = {}; rows.forEach(r => { const k = (r.twy || r.twyTower) || '?'; byTwy[k] = (byTwy[k] || 0) + 1; }); const twyTxt = Object.entries(byTwy).sort((a, b) => b[1] - a[1]).slice(0, 4).map(([k, n]) => `${k} ${n}`).join(' · ');
    let h = '<div class="kgrid">' + C.kcard('N.º movimentos', S.n, `${nA} chegadas · ${nD} partidas`) + C.kcard('Saídas / entradas', Object.keys(byTwy).filter(k => k !== '?').length, twyTxt || '—') + C.kcard('ROT médio', sv(S.mean)) + C.kcard('P85', sv(S.p85)) + C.kcard('P95', sv(S.p95)) + C.kcard('Máximo', sv(S.max)) +
      (cf === 'all' ? C.kcard('ROT chegada', sv(SA.mean), `média · ${SA.n} · P85 ${sv(SA.p85)}`) + C.kcard('ROT partida', sv(SD.mean), `média · ${SD.n} · P85 ${sv(SD.p85)}`) : '') + '</div>';
    if (d.n_arr < d.processed * 0.3) h += '<div class="hint sep-o" style="margin-bottom:8px">⚠ A maioria das chegadas termina antes da pista (cobertura radar até ~250 ft / 1,5 NM da THR) — o ROT só é calculável quando existem plots na rolagem. Com ficheiro da torre, use a aba Solo → ROT e taxi (A-SMGCS), medido pelo A-SMGCS.</div>';
    if (d.tower) h += `<div class="hint" style="margin-bottom:8px">Com ficheiro da torre, o ROT de referência é o do A-SMGCS (chegada: ALDT → RWY_VAC; partida: RWY_ENT → ATOT) — ${d.n_tower} movimento(s); o radar fica ao lado para comparação (${d.n_radar_only} só com radar).</div>`;
    if (nD && !d.tower) h += '<div class="hint sep-o" style="margin-bottom:8px">⚠ Partidas: o radar só começa a ver a aeronave já em corrida (a primeira amostra está normalmente a 300–1 300 m da soleira), por isso o ROT de partida pelo radar é um valor mínimo — o valor real (entrada na pista → descolagem) está na aba Solo, medido pelo A-SMGCS.</div>';
    h += `<div class="hint" style="margin-bottom:8px">ARR processados: ${d.processed} · sem pontos: ${d.dbg.noPts || 0} · THR não detectada: ${d.dbg.noCross || 0} · sem saída de pista: ${d.dbg.noOnRwy || 0} · ROT inválido: ${d.dbg.tooShort || 0} · calculados: ${d.n_arr ?? d.n}
      &nbsp;|&nbsp; DEP processados: ${d.processed_dep ?? 0} · sem pontos: ${d.dbg.dep_noPts || 0} · sem amostras na pista: ${d.dbg.dep_noRwy || 0} · ROT inválido: ${d.dbg.dep_invalid || 0} · calculados: ${d.n_dep ?? 0}</div>`;
    h += C.table([{ k: 'i', label: 'N', fmt: (v, r, i) => i + 1 }, { k: 'cls', label: 'Mov.', fmt: v => `<span class="badge ${v || 'arr'}">${(v || 'arr').toUpperCase()}</span>` }, { k: 'rwy', label: 'Pista', fmt: v => rwyBadge(v) }, { k: 'date', label: 'Data' }, { k: 'csn', label: 'Voo', fmt: (v, r) => csnLink(v, r.flight_id) }, { k: 'actype', label: 'Tipo' },
      { k: 'tTHRstr', label: 'Hora', fmt: (v, r) => r.cls === 'dep' && r.tOffStr ? `${v} → ${r.tOffStr}` : v },
      { k: 'rotS', label: 'ROT (s)', fmt: (v, r) => `<span class="${v <= 45 ? 'sep-g' : v <= 60 ? 'sep-o' : 'sep-r'}"><b>${v}</b></span> <span class="muted" title="torre = ARR: ALDT → RWY_VAC; DEP: RWY_ENT → ATOT (A-SMGCS). radar = estimativa pelos plots">${r.src || 'radar'}</span>${r.rotTower != null && r.rotRadar != null ? `<div class="muted">radar ${r.rotRadar} s</div>` : ''}` },
      { k: 'twy', label: 'Saída / entrada (radar)', fmt: (v, r) => v ? `<b>${esc(v)}</b> <span class="muted">${r.tEventStr}</span>` : r.rotRadar == null ? '<span class="muted">—</span>' : r.cls === 'dep' ? '<span class="muted" title="O radar só vê a aeronave já em corrida: a entrada não é visível">— não visível</span>' : `<span class="muted" title="Sem junção conhecida perto da saída (${r.exitM} m da THR)">? ${r.exitM} m</span>` },
      ...(d.tower ? [{ k: 'twyTower', label: 'Saída / entrada (torre)', fmt: (v, r) => v || r.rotTower != null ? `<b>${esc(v || '?')}</b> <span class="muted">${r.cls === 'dep' ? `RWY_ENT ${r.tEventTowerStr || '?'} → ATOT ${r.tEventTower2Str || '?'}` : `ALDT ${r.tEventTower2Str || '?'} → RWY_VAC ${r.tEventTowerStr || '?'}`}</span>` : '<span class="muted">—</span>' }] : []),
      { k: 'exitM', label: 'Posição (m da THR)', fmt: (v, r) => v == null ? '<span class="muted">—</span>' : r.cls === 'dep' ? `<span title="1.ª amostra radar na pista → ponto de descolagem">${r.entryM} → ${v}</span>` : `<span title="Última amostra na pista">${v}</span>` }], rows, { id: 'rotTable' });
    el.innerHTML = h; wireCsn(el);
  }

  /* ================================================================ KPIs */
  async function runKpis() {
    const el = $('kpiBody'); if (!hasFlights()) { empty(el, 'Sem dados.'); return; }
    busy(el);
    try { if (!R.final) await runFinal(false); if (!R.star && FP.state.flights.length < 4000) await runStar(false); R.kpis = await call('kpis'); renderKpis(); } catch (e) { empty(el, 'Erro: ' + e.message); toast(e.message, 'err'); }
    try { R.pru = await call('pru_kpis'); registerPruDrills(R.pru); el.insertAdjacentHTML('afterbegin', renderPru(R.pru)); wirePru(); } catch (e) { toast('KPIs PRU: ' + e.message, 'err'); }
  }
  /* ---- drill-down: clicar num cartão mostra os dados de origem */
  const DRILL = {};           // key -> {title, cols:[{k,label,fmt?}], rows}
  function drillSet(key, title, cols, rows) { DRILL[key] = { title, cols, rows: rows || [] }; }
  // âmbito automático: cada função de render declara { 'Nome do cartão': linhas } e os cartões com esse nome ficam clicáveis
  let drillScopeMap = {}, drillPrefix = '';
  function drillScope(prefix, map) { drillPrefix = prefix; drillScopeMap = map || {}; }
  const COL_LABELS = { csn: 'Voo', date: 'Data', rwy: 'RWY', actype: 'Tipo', wtc: 'WTC', cls: 'Mov.', tod: 'Hora', tod_first: 'Início', tod_last: 'Fim', tFAFstr: 'Hora FAF', tTHRstr: 'Hora THR', durS: 'FAF→THR (s)',
    iasFAF: 'IAS FAF (kt)', ias4: 'IAS 4 NM (kt)', iasTHR: 'IAS THR (kt)', altFAF: 'Alt FAF (ft)', altTHR: 'Alt THR (ft)', crossFAF: 'Desvio eixo (NM)', trackNM: 'Distância (NM)', stab: 'Estab.', cdo: 'CDO', cdoLevelOffs: 'Patamares', cdoLevelSecs: 'Tempo nível (s)', sepTimeS: 'Sep. (s)',
    wp: 'Waypoint', ias: 'IAS (kt)', limit: 'Limite (kt)', excess: 'Excesso (kt)', dCpa: 'CPA (NM)', total: 'Passagens', compliant: 'Conformes', violations: 'Violações', pct: '%', op: 'Operador', flights: 'Voos', rate: 'Taxa',
    mode: 'Modo', detected: 'Pontos', violCount: 'Violações', maxAbsDeviation: 'Desvio máx (kt)', company: 'Operador',
    lead: 'Líder', leadTod: 'Hora líder', leadIas: 'IAS líder', leadAlt: 'Alt líder', trail: 'Seguidor', trailTod: 'Hora seguidor', trailIas: 'IAS seguidor', trailAlt: 'Alt seguidor', sep: 'Sep. (s)', sepNm: 'Sep. (NM)', seq: 'Seq.', depCnt: 'DEP', firstDep: '1º DEP', firstDepTod: 'Hora DEP', bSecAtDep: 'Seguidor no DEP (s)', bNmAtDep: 'Seguidor no DEP (NM)', hour: 'Hora',
    arrivals: 'Chegadas', pairs: 'Pares', crit: 'Críticos', dep: 'Partidas', arr: 'Chegadas', minSep: 'Sep. mín (s)', avgSep: 'Sep. média (s)', movements: 'Movimentos', critical: 'Críticos',
    cat: 'Cat.', acType: 'Tipo', airborne: 'No ar', distNM: 'Dist. (NM)', altFt: 'Alt (ft)', comp: 'Operador', rotS: 'ROT (s)', exitM: 'Saída (m)', alt_max: 'Alt máx', alt_min: 'Alt mín', n: 'N', label: 'Hora', value: 'Valor',
    day: 'Dia', weekday: 'Dia da semana', movs: 'Movimentos', peakHour: 'Hora de pico', peakN: 'Pico', common: 'Comuns', name: 'Nome', mt: 'Mov.', stand_d: 'Stand DEP', stand_a: 'Stand ARR', taxi_out: 'Taxi-out', taxi_in: 'Taxi-in', hp: 'HP', ep: 'Saída', aobt: 'AOBT', hp_time: 'HP', rwy_ent: 'RWY_ENT', atot: 'ATOT', aldt: 'ALDT', rwy_vac: 'RWY_VAC', aibt: 'AIBT', ctot: 'CTOT', spd_vac: 'Vel. saída (kt)', ga: 'GA', rto: 'RTO', atfm_delay: 'ATFM (min)', taxi_s: 'Taxi (s)', rot_s: 'ROT (s)', adep: 'ADEP', ades: 'ADES', reg: 'Matrícula', ao: 'Operador', sid: 'SID', star: 'STAR',
    src: 'Fontes', n_type: 'Tipo NMIR', t_type: 'Tipo torre', o_type: 'Tipo OPDI', t_reg: 'Matrícula', o_icao24: 'icao24', t_rwy: 'RWY', t_stand: 'Stand', t_rot: 'ROT torre', o_rot: 'ROT OPDI', t_taxi: 'Taxi', flags: 'Discrepâncias' };
  const HIDE_COLS = new Set(['flight_id', 'id', 'idx', '_dateRaw', 'dateRaw', 'points', 'deps', 'depDistances', 'latFAF', 'lonFAF', 'latTHR', 'lonTHR', 'epoch', 'epochTHR', 'epochFAF', 'tLead', 'tTrail', 'leadFlight', 'trailFlight', 'routable', 'corr', 'n_flags', 't_sort', 'gid', 't_ref', 'raw', 'leg']);
  const TIME_COLS = new Set(['aobt', 'hp_time', 'rwy_ent', 'atot', 'aldt', 'rwy_vac', 'aibt', 'ctot', 'etot', 'eta', 'ata', 't_first', 't_last', 't', 'r_t_first', 'r_t_last', 't_aobt', 't_rwy_ent', 't_atot', 't_aldt', 't_rwy_vac', 't_aibt', 'o_rwy_in', 'o_rwy_out', 'o_tod', 'o_toc', 't_tod', 't_toc']);
  const hms = t => t == null ? '—' : new Date(t * 1000).toISOString().slice(11, 19);
  function autoCols(rows) {
    const keys = []; for (const r of rows.slice(0, 50)) for (const k of Object.keys(r)) if (!keys.includes(k) && !HIDE_COLS.has(k)) keys.push(k);
    return keys.map(k => ({ k, label: COL_LABELS[k] || k, fmt: TIME_COLS.has(k) ? hms : k === 'date' ? (v => typeof v === 'string' && /^\d{6}$/.test(v) ? fd(v) : esc(String(v ?? '—'))) : k === 'csn' ? ((v, r) => r.flight_id ? csnLink(v, r.flight_id) : `<b>${esc(v ?? '')}</b>`)
      : (v => v == null ? '—' : typeof v === 'boolean' ? (v ? '✓' : '—') : Array.isArray(v) ? esc(v.join('; ')) : typeof v === 'number' ? fmt(v, Number.isInteger(v) ? 0 : 1) : esc(String(v))) }));
  }
  window.DrillAuto = label => {
    const d = drillScopeMap[label]; if (!d) return null;
    const rows = Array.isArray(d) ? d : d.rows, key = 'auto:' + drillPrefix + ':' + label;
    drillSet(key, (Array.isArray(d) ? label : d.title || label), (Array.isArray(d) || !d.cols) ? autoCols(rows || []) : d.cols, rows || []);
    return key;
  };
  function drillOpen(key) {
    const d = DRILL[key]; if (!d) { toast('Sem detalhe disponível para este valor.', 'err'); return; }
    const cols = d.cols.map(c => ({ ...c, fmt: c.fmt || (v => v == null ? '—' : typeof v === 'number' ? fmt(v, Number.isInteger(v) ? 0 : 1) : esc(String(v))) }));
    $('modalTitle').textContent = `${d.title} — ${d.rows.length} registo(s)`;
    $('modalBody').innerHTML = `<div class="row" style="gap:8px;margin-bottom:8px"><button class="btn sm" id="drExport">⬇ Excel</button><button class="btn sm" id="drPdf">📄 PDF</button><span class="hint">Dados que deram origem ao valor do cartão.</span></div>` +
      (d.rows.length ? C.table(cols, d.rows, { limit: 3000 }) : '<div class="empty">Sem registos.</div>');
    wireCsn($('modalBody'));
    const plain = () => d.rows.map(r => cols.map(c => { const v = r[c.k]; if (v == null) return ''; if (TIME_COLS.has(c.k)) return hms(v); if (c.k === 'date' && typeof v === 'string' && /^\d{6}$/.test(v)) return fd(v); if (Array.isArray(v)) return v.join('; '); if (typeof v === 'boolean') return v ? 'sim' : ''; return v; }));
    $('drExport').onclick = async () => { try { const p = await call('export_rows', d.title, cols.map(c => c.label), plain()); if (p) toast('Exportado para ' + p, 'ok'); } catch (e) { toast(e.message, 'err'); } };
    $('drPdf').onclick = async () => { try { await call('report_rows', d.title, cols.map(c => c.label), plain()); toast('Aberto no navegador — Imprimir → Guardar como PDF.', 'ok'); } catch (e) { toast(e.message, 'err'); } };
    $('modal').classList.remove('hidden');
  }
  document.addEventListener('click', ev => { const k = ev.target.closest('.kcard[data-drill]'); if (k && !(window.DrillSrv && window.DrillSrv[k.dataset.drill])) drillOpen(k.dataset.drill); });
  window.Drill = { set: drillSet, open: drillOpen, scope: (p, m) => drillScope(p, m) };
  const T = t => t == null ? '—' : new Date(t * 1000).toISOString().slice(11, 19);
  const fd = d => d ? `${d.slice(4, 6)}/${d.slice(2, 4)}/20${d.slice(0, 2)}` : '—';
  const csnCol = { k: 'csn', label: 'Voo', fmt: (v, r) => r.flight_id ? csnLink(v, r.flight_id) : `<b>${esc(v || '')}</b>` };
  function registerPruDrills(d) {
    const dd = d.details || {};
    const movCols = [{ k: 'date', label: 'Data', fmt: fd }, csnCol, { k: 'cls', label: 'Mov.' }, { k: 'actype', label: 'Tipo' }, { k: 'wtc', label: 'WTC' }, { k: 'rwy', label: 'RWY' }, { k: 't', label: 'Hora', fmt: T }, { k: 'stand', label: 'Stand' }];
    drillSet('pru.mov', 'Movimentos de pista', movCols, dd.mov);
    drillSet('pru.peak', 'Movimentos na hora de pico (60 min)', movCols, dd.peak);
    drillSet('pru.ga', 'Go-arounds — torre e radar', window.GA_COLS(fd, csnCol, T), dd.ga);
    const taxiCols = [{ k: 'date', label: 'Data', fmt: fd }, csnCol, { k: 'actype', label: 'Tipo' }, { k: 'stand', label: 'Stand' }, { k: 'rwy', label: 'RWY' }, { k: 'route', label: 'Taxi' }, { k: 'taxi_s', label: 'Taxi (s)' }, { k: 'ref_s', label: 'Referência (s)' }, { k: 'add_s', label: 'Adicional (s)' }];
    drillSet('pru.taxi_out', 'Taxi-out adicional por partida', taxiCols, dd.taxi_out);
    drillSet('pru.taxi_in', 'Taxi-in adicional por chegada', taxiCols, dd.taxi_in);
    drillSet('pru.asma', 'ASMA — tempo adicional por chegada', [{ k: 'date', label: 'Data', fmt: fd }, csnCol, { k: 'rwy', label: 'RWY' }, { k: 'sector', label: 'Setor' }, { k: 't', label: 'Trânsito (s)' }, { k: 'add', label: 'Adicional (s)' }], dd.asma);
    drillSet('pru.otp', 'Pontualidade à partida (NMIR)', [{ k: 'date', label: 'Data', fmt: fd }, csnCol, { k: 'actype', label: 'Tipo' }, { k: 'ades', label: 'ADES' }, { k: 'etot', label: 'ETOT', fmt: T }, { k: 'ctot', label: 'CTOT', fmt: T }, { k: 'atot', label: 'ATOT', fmt: T }, { k: 'dev_min', label: 'Desvio (min)' }, { k: 'ok', label: '≤ 15 min', fmt: v => v ? '✓' : '<span class="sep-r">✗</span>' }], dd.otp);
    drillSet('pru.atfm_nmir', 'Partidas com atraso ATFM (NMIR)', [{ k: 'date', label: 'Data', fmt: fd }, csnCol, { k: 'actype', label: 'Tipo' }, { k: 'ades', label: 'ADES' }, { k: 'etot', label: 'ETOT', fmt: T }, { k: 'ctot', label: 'CTOT', fmt: T }, { k: 'atfm_delay', label: 'Atraso (min)' }], dd.atfm_nmir);
    drillSet('pru.atfm_torre', 'Partidas com atraso ATFM (torre)', [{ k: 'date', label: 'Data', fmt: fd }, csnCol, { k: 'actype', label: 'Tipo' }, { k: 'ades', label: 'ADES' }, { k: 'ctot', label: 'CTOT', fmt: T }, { k: 'atot', label: 'ATOT', fmt: T }, { k: 'atfm_delay', label: 'Atraso (min)' }, { k: 'regulation', label: 'Regulação' }], dd.atfm_torre);
    drillSet('pru.cdo', 'Chegadas OPDI — patamares abaixo de FL100', [{ k: 'date', label: 'Data', fmt: fd }, csnCol, { k: 'typecode', label: 'Tipo' }, { k: 'adep', label: 'ADEP' }, { k: 't_tod', label: 'TOD', fmt: T }, { k: 'n_levels_low', label: 'Patamares < FL100' }, { k: 'cdo', label: 'CDO', fmt: v => v ? '✓' : '✗' }], dd.cdo);
  }
  /* ---- relatórios personalizados (botões) */
  let customReports = [];
  async function loadCustomReports() {
    try { customReports = await call('custom_reports') || []; } catch (e) { customReports = []; }
    $('kpiCustomBtns').innerHTML = customReports.map((r, i) => `<button class="btn" data-cr="${i}" title="${esc((r.sections || []).join(', '))}">📄 ${esc(r.name)}</button>`).join(' ');
    $('kpiCustomBtns').querySelectorAll('[data-cr]').forEach(b => b.onclick = () => { const r = customReports[+b.dataset.cr]; if (!hasFlights()) { toast('Aplica um filtro primeiro.', 'err'); return; } toast(`A gerar "${r.name}"…`, 'ok'); call('report', 'custom', { title: r.name, sections: r.sections }).catch(e => toast(e.message, 'err')); });
  }
  async function openReportBuilder() {
    const secs = await call('report_sections');
    $('modalTitle').textContent = 'Relatórios à medida';
    $('modalBody').innerHTML = `<p class="hint">Escolhe as secções e o título. "Gerar agora" abre o relatório no navegador; "Guardar como botão" cria um botão permanente na barra dos KPIs (fica na base de dados).</p>
      <label>Título <input id="rbTitle" class="inp" value="Relatório ${esc(FP.state.airport)}"></label>
      <div class="chips" style="margin:10px 0">${Object.entries(secs).map(([k, v]) => `<label class="chk" style="width:100%"><input type="checkbox" class="rbSec" value="${k}" ${['pru', 'painel', 'solo'].includes(k) ? 'checked' : ''}> <b>${k}</b> — ${esc(v)}</label>`).join('')}</div>
      <div class="row" style="gap:8px"><button class="btn primary" id="rbRun">📄 Gerar agora</button><button class="btn" id="rbSave">💾 Guardar como botão</button></div>
      ${customReports.length ? '<h3 class="mini" style="margin-top:14px">Botões guardados</h3>' + customReports.map((r, i) => `<div class="row" style="gap:8px;margin:4px 0"><b>${esc(r.name)}</b><span class="muted">${esc(r.sections.join(', '))}</span><button class="btn sm rbDel" data-i="${i}">✕ remover</button></div>`).join('') : ''}`;
    $('modal').classList.remove('hidden');
    const picked = () => [...document.querySelectorAll('.rbSec:checked')].map(x => x.value);
    $('rbRun').onclick = () => { if (!hasFlights()) { toast('Aplica um filtro primeiro.', 'err'); return; } toast('A gerar…', 'ok'); call('report', 'custom', { title: $('rbTitle').value, sections: picked() }).catch(e => toast(e.message, 'err')); };
    $('rbSave').onclick = async () => { const s = picked(); if (!s.length) { toast('Escolhe pelo menos uma secção.', 'err'); return; } customReports.push({ name: $('rbTitle').value || 'Relatório', sections: s }); await call('custom_reports_set', customReports); toast('Botão criado.', 'ok'); $('modal').classList.add('hidden'); loadCustomReports(); };
    document.querySelectorAll('.rbDel').forEach(b => b.onclick = async () => { customReports.splice(+b.dataset.i, 1); await call('custom_reports_set', customReports); loadCustomReports(); openReportBuilder(); });
  }
  /* ---- KPIs no estilo PRU / EUROCONTROL */
  const m1 = v => v == null ? '—' : fmt(v, 1), s0 = v => v == null ? '—' : Math.round(v) + ' s', pc = v => v == null ? '—' : fmt(v, 1) + '%';
  const tblKey = (list, keyLabel, cols) => C.table([{ k: 'key', label: keyLabel }, ...cols], list || []);
  function renderPru(d) {
    if (!d) return '';
    const t = d.throughput, a = d.asma, x = d.taxi, f = d.atfm, c = d.cdo;
    let h = `<div class="card pru"><h3>KPIs de aeroporto — estilo PRU / EUROCONTROL (${esc(d.airport)})${helpIcon('KPIs de aeroporto — estilo PRU / EUROCONTROL')}</h3>
      <p class="hint">Fontes: radar ${d.sources.radar} · torre ${d.sources.torre} · NMIR ${d.sources.nmir} · OPDI ${d.sources.opdi}. Definições em <i>ansperformance.eu</i>: tempo adicional = real − referência não-impedida (percentil 20 do grupo).</p>`;
    h += '<div class="kgrid">';
    if (t) h += C.kcard('Movimentos de pista', fmt(t.n), `${t.source} · ${fmt(t.per_day, 0)}/dia`, '', 'pru.mov') + C.kcard('Pico 60 min', `${t.peak_roll60} mov.`, t.peak_when ? `${new Date(t.peak_when[1] * 1000).toISOString().slice(11, 16)} UTC · hora cheia máx. ${t.peak_hour_mov}` : '', '', 'pru.peak') +
      C.kcard('Utilização no pico', pc(t.util_peak), `capacidade declarada ${t.capacity}/h · ${t.hours_over_capacity} h acima`, t.util_peak > 100 ? 'warn' : 'ok', 'pru.peak') +
      C.kcard('Go-arounds', t.ga, (t.ga_rate != null ? `${fmt(t.ga_rate, 1)} por 1 000 aterragens` : 'radar (sem ficheiro da torre)') + (t.ga_radar != null && t.ga_rate != null ? ` · ${t.ga_radar} confirmado(s) pelo radar${t.ga_only_radar ? ` · ${t.ga_only_radar} só radar` : ''}` : ''), t.ga ? 'warn' : '', 'pru.ga');
    if (x) h += C.kcard('Taxi-out adicional', x.taxi_out.n ? `${m1(x.taxi_out.mean_min)} min` : '—', `média por partida · n=${x.taxi_out.n}`, '', 'pru.taxi_out') + C.kcard('Taxi-in adicional', x.taxi_in.n ? `${m1(x.taxi_in.mean_min)} min` : '—', `média por chegada · n=${x.taxi_in.n}`, '', 'pru.taxi_in');
    if (a && a.n) h += C.kcard(`ASMA adicional (${a.ring_nm} NM)`, `${m1(a.mean_min)} min`, `média por chegada · n=${a.n} · trânsito mediano ${s0(a.transit.median)}`, '', 'pru.asma');
    else if (a) h += C.kcard('ASMA adicional', '—', a.note || '');
    if (f) h += C.kcard('Pontualidade partida (15 min)', pc(f.otp.pct), `NMIR · ATOT vs ETOT/CTOT · n=${f.otp.n}`, f.otp.pct != null && f.otp.pct < 80 ? 'warn' : '', 'pru.otp') +
      C.kcard('Atraso ATFM (NMIR)', f.atfm_nmir.n_dep ? `${m1(f.atfm_nmir.per_dep)} min/partida` : '—', `${fmt(f.atfm_nmir.minutes)} min · ${f.atfm_nmir.delayed} atrasados · ${f.atfm_nmir.regulated} regulados`, '', 'pru.atfm_nmir') +
      C.kcard('Atraso ATFM (torre)', f.atfm_torre.n_dep ? `${m1(f.atfm_torre.per_dep)} min/partida` : '—', `${fmt(f.atfm_torre.minutes)} min · ${f.atfm_torre.delayed} atrasados`, '', 'pru.atfm_torre');
    if (c && c.n) h += C.kcard('CDO (OPDI)', pc(c.pct), `${c.cdo}/${c.n} chegadas sem patamar < FL100 · média ${fmt(c.levels_mean, 1)} patamares`, '', 'pru.cdo');
    h += `<div class="kcard"><b><input id="pruCap" class="inp tiny" type="number" value="${d.capacity}" style="width:70px"> <button class="btn sm" id="pruCapSave">ok</button></b><span>capacidade declarada (mov./h)</span></div>`;
    h += '</div><div class="grid2">';
    if (t) h += C.card('Movimentos por hora (média diária, chegadas + partidas)', C.grouped ? C.bars(t.avg_by_hour.map(v => v[0] + v[1]), [...Array(24).keys()].map(i => String(i).padStart(2, '0')), { color: C.BLUE, dec: 0 }) : '');
    if (x) h += C.card('Taxi-out adicional por stand (média, s)', tblKey(x.taxi_out.by_stand, 'Stand', [{ k: 'n', label: 'N' }, { k: 'mean', label: 'Adicional médio (s)', fmt: v => Math.round(v) }])) +
      C.card('Taxi-in adicional por stand (média, s)', tblKey(x.taxi_in.by_stand, 'Stand', [{ k: 'n', label: 'N' }, { k: 'mean', label: 'Adicional médio (s)', fmt: v => Math.round(v) }]));
    if (a && a.n) h += C.card(`ASMA por setor de entrada (anel ${a.ring_nm} NM)`, tblKey(a.by_sector, 'Setor', [{ k: 'n', label: 'N' }, { k: 'mean', label: 'Adicional médio (s)', fmt: v => Math.round(v) }, { k: 'ref', label: 'Ref. não-impedida (s)', fmt: v => v == null ? '—' : Math.round(v) }])) +
      C.card('ASMA — chegadas com mais tempo adicional', C.table([{ k: 'csn', label: 'Voo', fmt: (v, r) => csnLink(v, r.flight_id) }, { k: 'rwy', label: 'RWY' }, { k: 't', label: 'Trânsito (s)', fmt: v => Math.round(v) }, { k: 'add', label: 'Adicional (s)', fmt: v => `<span class="sep-r">${Math.round(v)}</span>` }], a.worst));
    if (f && f.otp.n) h += C.card('Desvio ATOT − (CTOT ou ETOT), min', C.bars(f.otp.hist.counts, f.otp.hist.labels, { color: C.ORANGE }));
    if (f && f.atfm_torre.by_regulation.length) h += C.card('Atraso ATFM por regulação (torre)', tblKey(f.atfm_torre.by_regulation, 'Regulação', [{ k: 'n', label: 'Voos' }, { k: 'minutes', label: 'Minutos', fmt: v => Math.round(v) }]));
    if (c && c.n) h += C.card('Patamares abaixo de FL100 por chegada (OPDI)', C.bars(c.hist.counts, c.hist.labels, { color: C.GREEN }));
    return h + '</div></div>';
  }
  function wirePru() {
    const b = $('pruCapSave'); if (!b) return;
    b.onclick = async () => { try { await call('set_capacity', FP.state.airport, +$('pruCap').value); toast('Capacidade guardada.', 'ok'); R.pru = null; runKpis(); } catch (e) { toast(e.message, 'err'); } };
    wireCsn($('kpiBody'));
  }
  function renderKpis() {
    const k = R.kpis, el = $('kpiBody'); if (!k) return;
    const fl = FP.state.flights, fcols = [{ k: 'date', label: 'Data', fmt: fd }, csnCol, { k: 'cls', label: 'Mov.', fmt: v => v.toUpperCase() }, { k: 'actype', label: 'Tipo' }, { k: 'wtc', label: 'WTC' }, { k: 'tod_first', label: 'Início' }, { k: 'tod_last', label: 'Fim' }, { k: 'alt_max', label: 'Alt máx' }, { k: 'n', label: 'Plots' }];
    drillSet('kpi.all', 'Movimentos (radar)', fcols, fl); drillSet('kpi.arr', 'Chegadas (radar)', fcols, fl.filter(f => f.cls === 'arr')); drillSet('kpi.dep', 'Partidas (radar)', fcols, fl.filter(f => f.cls === 'dep')); drillSet('kpi.lvl', 'Sobrevoos (radar)', fcols, fl.filter(f => f.cls === 'lvl'));
    const p = v => k.total ? Math.round(v / k.total * 100) + '%' : '';
    $('kpiNote').textContent = [k.approach && `${k.approach.n} aproximações`, k.star && `${k.star.passes} passagens STAR`, k.star && `${k.star.viol} violações IAS`].filter(Boolean).join(' · ');
    const finRs = (R.final && R.final.results) || [], peakFl = fl.filter(f => Math.floor((f.t_first % 86400) / 3600) === k.peakHour);
    const lr = k.landingRate ? k.landingRate.labels.map((l, i) => ({ label: l + 'h', value: k.landingRate.series[i] })) : [];
    const sv = (R.star && R.star.violations) || [], sw = (R.star && R.star.perWp) || [];
    drillScope('kpi', { 'Dias de dados': { title: 'Movimentos por dia', rows: (k.byDay || []).map(d => Array.isArray(d) ? { date: d[0], n: d[1] } : d) }, 'Total': { title: 'Passagens por waypoint', rows: sw }, 'Hora de pico': { title: `Movimentos na hora de pico (${String(k.peakHour).padStart(2, '0')}:00)`, rows: peakFl }, 'Período (UTC)': { title: 'Movimentos', rows: fl }, 'Amostras (radar)': { title: 'Movimentos (plots por movimento)', rows: fl },
      'Aterragens': { title: 'Aterragens (Final)', rows: finRs }, 'Estabilizadas': { title: 'Aproximações estabilizadas / não', rows: finRs.slice().sort((a, b) => (a.stab ? 1 : 0) - (b.stab ? 1 : 0)) }, 'IAS@FAF méd.': { title: 'IAS no FAF por aterragem', rows: finRs }, 'Tempo FAF→THR méd.': { title: 'Tempo FAF→THR por aterragem', rows: finRs },
      'Sep. temporal méd.': { title: 'Separações entre aterragens', rows: finRs.filter(x => x.sepTimeS != null) }, 'Sep. temporal mín./máx.': { title: 'Separações (crescente)', rows: finRs.filter(x => x.sepTimeS != null).sort((a, b) => a.sepTimeS - b.sepTimeS) },
      ...Object.fromEntries(Object.keys((k.approach && k.approach.byRwy) || {}).map(r => ['RWY ' + r, { title: 'Aterragens RWY ' + r, rows: finRs.filter(x => x.rwy === r) }])),
      'Pico 60 min': { title: 'Aterragens por janela de 60 min (passos de 5 min)', rows: lr }, 'Média período': { title: 'Aterragens por janela de 60 min', rows: lr },
      'Média': { title: 'Separações entre aterragens', rows: finRs.filter(x => x.sepTimeS != null) }, 'Mediana': { title: 'Separações (crescente)', rows: finRs.filter(x => x.sepTimeS != null).sort((a, b) => a.sepTimeS - b.sepTimeS) }, 'Mínimo': { title: 'Separações (crescente)', rows: finRs.filter(x => x.sepTimeS != null).sort((a, b) => a.sepTimeS - b.sepTimeS) }, 'Máximo': { title: 'Separações (decrescente)', rows: finRs.filter(x => x.sepTimeS != null).sort((a, b) => b.sepTimeS - a.sepTimeS) }, 'Bunching': { title: 'Pares com menos de 90 s', rows: finRs.filter(x => x.sepTimeS != null && x.sepTimeS < 90) },
      'Taxa CDO': { title: 'Aproximações (CDO)', rows: finRs.slice().sort((a, b) => (a.cdo ? 1 : 0) - (b.cdo ? 1 : 0)) }, 'Level-offs méd./aprox.': { title: 'Patamares por aproximação', rows: finRs.slice().sort((a, b) => (b.cdoLevelOffs || 0) - (a.cdoLevelOffs || 0)) }, 'Tempo nível méd.': { title: 'Tempo em nível por aproximação', rows: finRs.slice().sort((a, b) => (b.cdoLevelSecs || 0) - (a.cdoLevelSecs || 0)) },
      'Passagens analisadas': { title: 'Passagens por waypoint', rows: sw }, 'Conformes': { title: 'Conformidade por waypoint', rows: sw }, 'Violações': { title: 'Violações de IAS (STAR)', rows: sv }, 'Taxa de cumprimento': { title: 'Cumprimento por waypoint', rows: sw } });
    let h = C.card('Resumo Operacional', '<div class="kgrid">' + C.kcard('Movimentos', fmt(k.total), '', '', 'kpi.all') + C.kcard('Chegadas (ARR)', k.arr, p(k.arr), '', 'kpi.arr') + C.kcard('Partidas (DEP)', k.dep, p(k.dep), '', 'kpi.dep') + C.kcard('Sobrevoos (LVL)', k.lvl, p(k.lvl), '', 'kpi.lvl') + C.kcard('Dias de dados', k.days) +
      C.kcard('Hora de pico', `${String(k.peakHour).padStart(2, '0')}:00`, `${k.peakN} mov.`) + C.kcard('Período (UTC)', k.period) + C.kcard('Amostras (radar)', fmt(k.pts)) + '</div>' + (k.days > 1 ? `<p class="hint">Contagem por (callsign, dia): ${k.total} movimentos em ${k.callsigns} callsigns distintos ao longo de ${k.days} dias.</p>` : ''));
    if (k.approach) { const a = k.approach; h += C.card(`Análise de Aproximações (${FP.state.airport})`, '<div class="kgrid">' + C.kcard('Aterragens', a.n, a.rate ? fmt(a.rate, 1) + ' aterr./h' : '') + Object.entries(a.byRwy).map(([r, n]) => C.kcard('RWY ' + r, n)).join('') +
      C.kcard('Estabilizadas', `${a.stab}/${a.n}`, Math.round(a.stab / a.n * 100) + '%') + C.kcard('IAS@FAF méd.', fmt(a.iasFAF) + ' kt') + C.kcard('Tempo FAF→THR méd.', fmt(a.durS) + ' s') + C.kcard('Sep. temporal méd.', sec(a.sepMean) + ' s') + C.kcard('Sep. temporal mín./máx.', `${sec(a.sepMin)} / ${sec(a.sepMax)} s`) + '</div>'); }
    if (k.landingRate) { const l = k.landingRate; h += C.card('Taxa de aterragem (rolling 60 min)', '<div class="kgrid">' + C.kcard('Pico 60 min', l.peak + ' aterr./h', `${fmt(l.pct)}% da capacidade LPPT (38)`) + C.kcard('Média período', l.avg + ' aterr./h', 'média inteira (arred. por defeito)') + C.kcard('Total', k.approach.n + ' aterragens') + '</div>' + C.bars(l.series, l.labels, { color: C.RED, h: 110 }), 'Cada ponto: aterragens na hora anterior. Referência: capacidade declarada LPPT ≈ 38 mov/h.'); }
    if (k.sepHist) { const s = k.sepHist; h += C.card('Separação temporal entre aterragens consecutivas', '<div class="kgrid">' + C.kcard('Média', fmt(Math.round(s.mean)) + ' s', 'sensível a extremos') + C.kcard('Mediana', fmt(Math.round(s.median)) + ' s', 'valor central (50%)') + C.kcard('Mínimo', fmt(Math.round(s.min)) + ' s') + C.kcard('Máximo', fmt(Math.round(s.max)) + ' s') + C.kcard('Bunching', `${s.bunching} <90s`, 'aproximações muito comprimidas', s.bunching ? 'warn' : '') + '</div>' + C.bars(s.counts, s.labels, { color: C.RED })); }
    if (k.cdo) { const c = k.cdo; h += C.card('CDO — Continuous Descent Operations (< FL100)', '<div class="kgrid">' + C.kcard('Taxa CDO', fmt(c.pct) + '%', `${c.count}/${c.n} aprox.`, c.pct >= 70 ? 'ok' : c.pct < 40 ? 'bad' : '') + C.kcard('Level-offs méd./aprox.', fmt(c.levelOffs, 1)) + C.kcard('Tempo nível méd.', fmt(c.levelSecs) + ' s') + '</div>'); }
    if (k.star) { const s = k.star; h += C.card('Cumprimento de IAS em waypoints STAR (ARR)', '<div class="kgrid">' + C.kcard('Passagens analisadas', s.passes, `${s.flights} voos ARR`) + C.kcard('Conformes', s.comp, `Raio ${s.radius} NM · Tol +${s.tol} kt`) + C.kcard('Violações', s.viol, '', s.viol ? 'bad' : 'ok') + C.kcard('Taxa de cumprimento', s.pct == null ? '—' : fmt(s.pct, 1) + '%', '', s.pct >= 95 ? 'ok' : s.pct < 85 ? 'bad' : '') + '</div>' +
      (s.top5.length ? '<h3 class="mini">Top 5 waypoints com mais violações</h3>' + C.hbars(s.top5.map(w => ({ label: w.wp, value: w.violations, text: `${w.violations} (${fmt(w.violations / w.total * 100, 1)}% de ${w.total}) · lim ${w.limit} kt`, color: C.RED }))) : '') +
      (s.operators.length ? '<h3 class="mini" style="margin-top:10px">Cumprimento IAS por operador (top 10 pior)</h3>' + C.table([{ k: 'op', label: 'Operador' }, { k: 'arrFlights', label: 'Voos ARR' }, { k: 'violations', label: 'Violações' }, { k: 'rate', label: 'Inc./voo', fmt: v => fmt(v * 100, 1) + '%' }], s.operators) : '')); }
    h += C.card('Movimentos por hora (UTC)', C.grouped([{ name: 'ARR', values: k.byArr, color: '#f87171' }, { name: 'DEP', values: k.byDep, color: '#22d3a0' }], Array.from({ length: 24 }, (_, i) => String(i).padStart(2, '0'))));
    if (k.byDay.length > 1) h += C.card(`Movimentos por dia (${k.byDay.length} dias)`, C.grouped([{ name: 'ARR', values: k.byDay.map(d => d.arr), color: '#22d3a0' }, { name: 'DEP', values: k.byDay.map(d => d.dep), color: C.ORANGE }, { name: 'LVL', values: k.byDay.map(d => d.lvl), color: '#6366f1' }], k.byDay.map(d => d.label.slice(0, 5))));
    h += C.card('Top 10 operadores (prefixo callsign)', C.hbars(k.topOps.map(([o, n]) => ({ label: o, value: n }))));
    el.innerHTML = h;
  }

  /* ================================================================ PONTOS / SEQUÊNCIA */
  let ptCircle = null, pts = [];
  async function loadPoints() {
    pts = await call('points_list');
    const opts = pts.slice().sort((a, b) => a.name.localeCompare(b.name)).map(p => `<option value="${esc(p.name)}">${esc(p.name)} · ${esc(p.desc || '')}${p.type === 'user' ? ' (manual)' : ''}</option>`).join('');
    ['ptSel', 'seqSel'].forEach(id => { const s = $(id), cur = s.value; s.innerHTML = opts; if (cur && [...s.options].some(o => o.value === cur)) s.value = cur; else if ([...s.options].some(o => o.value === 'PESEX')) s.value = 'PESEX'; });
    $('upBody').innerHTML = C.table([{ k: 'name', label: 'Nome' }, { k: 'lat', label: 'Lat', fmt: v => v.toFixed(6) }, { k: 'lon', label: 'Lon', fmt: v => v.toFixed(6) }, { k: 'desc', label: 'Descrição' }, { k: 'type', label: 'Origem', fmt: v => v === 'user' ? '<span class="badge dep">Manual</span>' : '<span class="badge lvl">AIP</span>' },
      { k: 'x', label: '', fmt: (v, p) => p.type === 'user' ? `<button class="btn ghost up-x" data-n="${esc(p.name)}">✖</button>` : '' }], pts, { id: 'upTable', sortKey: 'name' });
    setTimeout(() => $('upBody').querySelectorAll('.up-x').forEach(b => b.onclick = async () => { if (confirm(`Remover ${b.dataset.n}?`)) { await call('user_point_remove', b.dataset.n); loadPoints(); } }), 10);
  }
  const drawCircle = (name, radius, color) => { const p = pts.find(x => x.name === name); if (!p) return; if (ptCircle) FP.overlay.removeLayer(ptCircle); ptCircle = L.circle([p.lat, p.lon], { radius: radius * 1852, color, weight: 2, fillOpacity: .08 }).addTo(FP.overlay); };
  const iasLabel = () => { const op = $('ptOp').value, v1 = $('ptV1').value, v2 = $('ptV2').value, tol = $('ptTol').value; return { any: '', lt: `< ${v1} kt`, le: `≤ ${v1} kt`, eq: `= ${v1} ± ${tol} kt`, ge: `≥ ${v1} kt`, gt: `> ${v1} kt`, between: `${v1}–${v2} kt` }[op]; };
  async function runPt() {
    const el = $('ptBody'); if (!hasFlights()) { empty(el, 'Sem dados.'); return; }
    busy(el);
    try {
      const r = await call('point_query', $('ptSel').value, +$('ptRadius').value || 1, $('ptOp').value, $('ptV1').value || null, $('ptV2').value || null, +$('ptTol').value || 2);
      R.pt = r; drawCircle($('ptSel').value, +$('ptRadius').value || 1, C.ORANGE);
      $('ptCount').textContent = `${r.total} passagem(ns) no raio de ${$('ptRadius').value} NM` + (iasLabel() ? ` · ${r.rows.length} com IAS ${iasLabel()}` : '');
      if (!r.rows.length) { empty(el, r.total ? `Nenhuma passagem com IAS ${iasLabel()}` : 'Nenhum voo encontrado neste raio'); return; }
      el.innerHTML = C.table([{ k: 'tod', label: 'Hora' }, { k: 'date', label: 'Data' }, { k: 'block', label: 'Bloco' }, { k: 'csn', label: 'Voo', fmt: (v, x) => csnLink(v, x.flight_id) }, { k: 'actype', label: 'Tipo' }, { k: 'cls', label: 'Tipo mov.', fmt: v => `<span class="badge ${v}">${v.toUpperCase()}</span>` },
        { k: 'd', label: 'Dist (NM)' }, { k: 'alt', label: 'Alt (ft)' }, { k: 'ias', label: 'IAS', fmt: v => v == null ? '—' : fmt(v) }, { k: 'roc', label: 'ROC', fmt: v => v == null ? '—' : `<span class="${v > 0 ? 'sep-g' : v < 0 ? 'sep-r' : ''}">${fmt(v)}</span>` }, { k: 'lat', label: 'Lat' }, { k: 'lon', label: 'Lon' }], r.rows, { id: 'ptTable', limit: 3000 });
      wireCsn(el);
    } catch (e) { empty(el, 'Erro: ' + e.message); toast(e.message, 'err'); }
  }
  async function runSeq() {
    const el = $('seqBody'); if (!hasFlights()) { empty(el, 'Sem dados.'); return; }
    busy(el);
    try {
      const r = await call('sequence', $('seqSel').value, +$('seqRadius').value || 1); R.seq = r; drawCircle($('seqSel').value, +$('seqRadius').value || 1, C.GREEN);
      $('seqCount').textContent = `${r.length} aeronave(s) ≤ ${$('seqRadius').value} NM · ${$('seqSel').value}`;
      if (!r.length) { empty(el, 'Nenhuma aeronave neste raio'); return; }
      const nb = v => v == null ? '—' : v > 20 ? '>20' : fmt(v, 1);
      el.innerHTML = C.table([{ k: 'i', label: '#', fmt: (v, x, i) => i + 1 }, { k: 'tod', label: 'Hora' }, { k: 'date', label: 'Data' }, { k: 'block', label: 'Bloco' }, { k: 'csn', label: 'Voo', fmt: (v, x) => csnLink(v, x.flight_id) }, { k: 'actype', label: 'Tipo' }, { k: 'd', label: 'Dist CPA (NM)' },
        { k: 'antD', label: 'AC à frente (NM)', fmt: nb }, { k: 'segD', label: 'AC atrás (NM)', fmt: nb }, { k: 'alt', label: 'Alt (ft)' }, { k: 'ias', label: 'IAS', fmt: v => v == null ? '—' : fmt(v) }], r, { id: 'seqTable' });
      wireCsn(el);
    } catch (e) { empty(el, 'Erro: ' + e.message); toast(e.message, 'err'); }
  }

  /* ================================================================ IA */
  let iaCfg = null;
  async function loadIa() {
    iaCfg = await call('ia_settings');
    const pv = iaCfg.providers[iaCfg.provider];
    $('iaStatus').innerHTML = iaCfg.hasKey ? `${esc(pv.name)}` : '<span class="sep-o">Sem chave — configura em ⚙ Preferências</span>';
    $('iaModel').innerHTML = pv.models.map(([id, lb]) => `<option value="${id}" ${id === iaCfg.model ? 'selected' : ''}>${esc(lb)}</option>`).join('');
    $('prProv').innerHTML = Object.entries(iaCfg.providers).map(([k, v]) => `<option value="${k}" ${k === iaCfg.provider ? 'selected' : ''}>${esc(v.name)}</option>`).join('');
    $('prModel').innerHTML = $('iaModel').innerHTML; $('prAzure').value = iaCfg.azure_endpoint || ''; $('prAzureWrap').classList.toggle('hidden', iaCfg.provider !== 'azure'); $('prKey').placeholder = iaCfg.hasKey ? '(mantém a chave guardada)' : 'Chave API';
    renderIaHistory();
  }
  function renderIaHistory() {
    const el = $('iaBody'); if (!iaCfg.history.length) { empty(el, 'Faz uma pergunta sobre os dados filtrados. O modelo recebe o resumo das análises (Final, FAST, STAR, APP, ROT, Pontos).'); return; }
    el.innerHTML = iaCfg.history.map(m => m.role === 'user' ? `<div class="msg u">◈ TU\n${esc(m.text)}</div>` : `<div class="msg a">${esc(m.text)}${m.grafico && m.grafico.dados ? '<div class="chart" style="margin-top:8px">' + iaChart(m.grafico) + '</div>' : ''}</div>`).join('');
    el.scrollTop = el.scrollHeight;
  }
  function iaChart(g) {
    const vals = g.dados.map(d => +d.valor || 0), labels = g.dados.map(d => String(d.nome));
    const tipo = String(g.tipo || 'bar').toLowerCase();
    if (/pie|pizza|circular|doughnut|rosca|anel/.test(tipo)) { const tot = vals.reduce((a, b) => a + b, 0) || 1; let a0 = -Math.PI / 2, s = `<svg viewBox="0 0 460 200" class="chart-svg"><text x="230" y="14" text-anchor="middle" class="lbl">${esc(g.titulo || '')}</text>`;
      const cols = ['#4cc9f0', '#f72585', '#b5e48c', '#ffd166', '#c77dff', '#06d6a0', '#ff8fab', '#90e0ef', '#f9c74f', '#a0c4ff'];
      vals.forEach((v, i) => { const a1 = a0 + v / tot * 2 * Math.PI, x0 = 110 + 70 * Math.cos(a0), y0 = 110 + 70 * Math.sin(a0), x1 = 110 + 70 * Math.cos(a1), y1 = 110 + 70 * Math.sin(a1);
        s += `<path d="M110,110 L${x0},${y0} A70,70 0 ${a1 - a0 > Math.PI ? 1 : 0} 1 ${x1},${y1} Z" fill="${cols[i % 10]}"><title>${esc(labels[i])}: ${v}</title></path><rect x="200" y="${30 + i * 16}" width="10" height="10" fill="${cols[i % 10]}"/><text x="215" y="${39 + i * 16}" class="lbl">${esc(labels[i])} (${v})</text>`; a0 = a1; });
      return s + '</svg>'; }
    return `<div class="hint">${esc(g.titulo || '')}</div>` + C.bars(vals, labels, { dec: Number.isInteger(vals[0]) ? 0 : 1 });
  }
  async function iaSend() {
    const q = $('iaQ').value.trim(); if (!q) return;
    if (!hasFlights()) { toast('Aplica um filtro primeiro — a IA analisa os dados seleccionados.', 'err'); return; }
    if (!iaCfg.hasKey) { toast('Configura a chave API em ⚙ Preferências.', 'err'); FP.showTab('pref'); return; }
    $('iaQ').value = ''; iaCfg.history.push({ role: 'user', text: q }); renderIaHistory();
    $('iaBody').insertAdjacentHTML('beforeend', '<div class="msg a" id="iaWait">⏳ A analisar...</div>'); $('iaBody').scrollTop = 1e9;
    try { await call('ia_settings_set', null, null, $('iaModel').value, null); const r = await call('ia_ask', q); iaCfg.history.push({ role: 'ai', text: r.texto, grafico: r.grafico }); renderIaHistory(); }
    catch (e) { const w = $('iaWait'); if (w) { w.className = 'msg e'; w.textContent = '⚠ Erro: ' + e.message; } }
  }

  /* ================================================================ orquestração */
  /* Pré-cálculo em segundo plano: depois de um filtro, as análises principais são calculadas uma a uma
     (Final → FAST → STAR → APP → KPIs → Dados → Diária) para que as abas abram já com resultados. */
  const P = {};            // pedidos em curso, por análise
  let prefetchGen = 0;
  function prefetch() {
    const gen = ++prefetchGen;
    const steps = [['final', () => runFinal(false)], ['fast', runFast], ['star', () => runStar(false)], ['app', () => runApp(false)],
                   ['kpis', runKpis], ['dados', runDados], ['diaria', runDiaria]];
    setTimeout(async () => {
      for (const [k, fn] of steps) {
        if (gen !== prefetchGen || !hasFlights()) return;
        if (R[k] || P[k]) continue;
        FP.status($('sTxt').textContent, 'busy', `a preparar ${k} em segundo plano…`);
        P[k] = fn().catch(() => null).finally(() => { P[k] = null; });
        await P[k];
      }
      if (gen === prefetchGen) FP.status($('sTxt').textContent, 'on', 'análises prontas');
    }, 1500);
  }
  function onFilter() {
    Object.keys(R).forEach(k => R[k] = null); Object.keys(P).forEach(k => P[k] = null); FP.overlay.clearLayers(); ptCircle = null;
    [['finBody', 'Filtro alterado. Clica Analisar para actualizar resultados'], ['starBody', 'Filtro alterado. Clica Analisar'], ['appBody', 'Filtro alterado. Clica Analisar'], ['adBody', 'Filtro alterado. Clica Analisar'],
     ['fastBody', 'Filtro alterado. Abre a sub-aba para recalcular'], ['sdBody', 'Filtro alterado. Clica Atualizar análise'], ['dyBody', 'Filtro alterado. Clica Actualizar'], ['rrBody', 'Filtro alterado. Clica Analisar'], ['rotBody', 'Filtro alterado. Clica Analisar'], ['kpiBody', 'Filtro alterado. Clica Actualizar'], ['ptBody', 'Filtro alterado. Clica Pesquisar'], ['seqBody', 'Filtro alterado. Clica Pesquisar']].forEach(([id, m]) => empty($(id), m));
    ['finCount', 'starCount', 'appCount', 'adCount', 'fastCount', 'rrCount', 'rotCount', 'ptCount', 'seqCount', 'kpiNote'].forEach(id => $(id).textContent = '');
    renderScale();
    if (window.Ground) { Ground.onFilter(); Ground.onFilterCross(); }
    const active = document.querySelector('.tab.active'); if (active) onTab(active.dataset.tab);
    prefetch();
  }
  function onTab(name) {
    if (name === 'panel' && window.Ground) { Ground.onTabPanel(); return; }
    if (!hasFlights()) return;
    if (name === 'final' && !R.final && !P.final) runFinal(false);
    if (name === 'star' && !R.star && !P.star) runStar(false);
    if (name === 'app' && !R.app && !P.app) runApp(false);
    if (name === 'ana') onSub(document.querySelector('#tab-ana .subtab.active').dataset.sub);
    if (name === 'kpi' && !R.kpis && !P.kpis) runKpis();
    if (name === 'solo' && window.Ground) Ground.onTab();
    if (name === 'cross' && window.Ground) Ground.onTabCross();
    if (name === 'pts' && !R.pt && $('ptSel').value) { runPt(); }
    if (name === 'ia') loadIa();
    if (name === 'pref') { loadIa(); call('get_state').then(s => { $('prLan').innerHTML = s.lan && s.lan.on ? `Ativo — no iPad abre <b>${esc(s.lan.url)}</b>` : 'Inativo (a app só responde neste PC).'; }); call('get_state').then(s => $('prDb').textContent = `${s.db_path} · ${(s.db_bytes / 1048576).toFixed(0)} MB · ${s.files} ficheiros · ${fmt(s.rows)} plots · ${s.nmir} registos NMIR`); }
  }
  function onSub(sub) {
    if (!hasFlights()) return;
    if (sub === 'fast' && !R.fast && !P.fast) runFast();
    if (sub === 'dados' && !R.dados && !P.dados) runDados();
    if (sub === 'diaria' && !R.diaria && !P.diaria) runDiaria();
    if (sub === 'rrms' && !R.rrms) runRrms(false);
    if (sub === 'rot' && !R.rot) runRot();
    if (sub === 'seq' && !R.seq && $('seqSel').value) runSeq();
    if (sub === 'ptman') loadPoints();
  }
  const exportBtn = (id, kind, extraFn, name) => $(id).onclick = async () => { try { const p = await call('export', kind, extraFn ? extraFn() : {}, name ? name() : null); if (p) toast('Exportado para ' + p, 'ok'); } catch (e) { toast(e.message, 'err'); } };
  const reportBtn = (id, kind, extraFn) => $(id).onclick = () => call('report', kind, extraFn ? extraFn() : {}).then(() => toast('Relatório aberto no navegador — usa Imprimir / Guardar como PDF.', 'ok')).catch(e => toast(e.message, 'err'));

  document.addEventListener('DOMContentLoaded', () => {
    $('modalClose').onclick = closeModal; $('modal').onclick = e => { if (e.target === $('modal')) closeModal(); };
    // Final
    $('finRun').onclick = () => runFinal(true); $('finOverlay').onchange = drawFinalOverlay; exportBtn('finExport', 'final');
    // STAR
    $('starRun').onclick = () => runStar(true); $('starManage').onclick = manageLimits; exportBtn('starExport', 'star');
    // APP
    $('appRun').onclick = () => runApp(true); $('appCharts').onclick = appCharts; exportBtn('appExport', 'app');
    $('appPptx').onclick = async () => { try { await runApp(false); const p = await call('export_pptx'); if (p) toast('PowerPoint guardado em ' + p, 'ok'); } catch (e) { toast(e.message, 'err'); } };
    $('adRun').onclick = () => runAppDist(true); exportBtn('adExport', 'appdist'); initScale();
    // FAST
    $('fastThr').oninput = () => { if (R.final) runFast(); };
    $('fastMode').querySelectorAll('.tog').forEach(b => b.onclick = () => { fastMode = b.dataset.v; $('fastMode').querySelectorAll('.tog').forEach(x => x.classList.toggle('on', x === b)); runFast(); });
    $('fastInter').onclick = () => { fastInter = !fastInter; $('fastInter').classList.toggle('on', fastInter); runFast(); };
    $('fastRwy').querySelectorAll('.tog').forEach(b => b.onclick = () => { fastRwy = fastRwy === b.dataset.v ? 'all' : b.dataset.v; $('fastRwy').querySelectorAll('.tog').forEach(x => x.classList.toggle('on', x.dataset.v === fastRwy)); runFast(); });
    exportBtn('fastExport', 'operacional', () => ({ thr: parseInt($('fastThr').value) || 160, mode: fastMode, intercal: fastInter, rwy: fastRwy }), () => `export_operacional_${new Date().toISOString().slice(0, 10)}.xlsx`);
    // Dados / Diária
    $('sdRun').onclick = runDados; exportBtn('sdExport', 'dados', sdFilters, () => 'analise_separacao_thr.xlsx'); reportBtn('sdPdf', 'dados', sdFilters);
    $('dyRun').onclick = runDiaria; exportBtn('dyExport', 'diaria', () => ({ limit: parseInt($('sdLimit').value) || 165 }), () => 'analise_diaria.xlsx'); reportBtn('dyPdf', 'diaria', () => ({ limit: parseInt($('sdLimit').value) || 165 }));
    // RRMS / ROT
    $('rrRun').onclick = () => runRrms(true); ['rrCat', 'rrGrp', 'rrMetric', 'rrRwy'].forEach(id => $(id).onchange = () => R.rrms && renderRrms());
    exportBtn('rrExport', 'rrms', null, () => 'RRMS_passagens.xlsx'); reportBtn('rrPdf', 'rrms', () => ({ cat: $('rrCat').value, rwy: $('rrRwy').value }));
    $('rotRun').onclick = runRot; $('rotRwy').onchange = () => R.rot && renderRot(); $('rotCls').onchange = () => R.rot && renderRot(); exportBtn('rotExport', 'rot');
    // KPIs
    $('kpiRun').onclick = runKpis; exportBtn('kpiExport', 'kpis'); exportBtn('kpiExportPru', 'pru'); reportBtn('kpiReport', 'kpis');
    $('kpiMonthly').onclick = () => { if (!hasFlights()) { toast('Aplica um filtro (idealmente um mês inteiro) primeiro.', 'err'); return; } toast('A gerar o relatório mensal… abre no navegador quando estiver pronto.', 'ok'); call('report', 'mensal', {}).catch(e => toast(e.message, 'err')); };
    $('kpiCustom').onclick = openReportBuilder; loadCustomReports();
    // Pontos
    $('ptRun').onclick = runPt; $('seqRun').onclick = runSeq; exportBtn('ptExport', 'pontos', () => ({ rows: R.pt ? R.pt.rows : [] })); exportBtn('seqExport', 'sequencia');
    $('ptOp').onchange = () => { const op = $('ptOp').value; $('ptV1').classList.toggle('hidden', op === 'any'); $('ptV2').classList.toggle('hidden', op !== 'between'); $('ptTol').classList.toggle('hidden', op !== 'eq'); };
    $('upAdd').onclick = async () => { const n = $('upName').value.trim().toUpperCase(), la = parseFloat($('upLat').value), lo = parseFloat($('upLon').value); if (!n || Number.isNaN(la) || Number.isNaN(lo) || Math.abs(la) > 90 || Math.abs(lo) > 180) { toast('Nome e coordenadas decimais válidas são obrigatórios.', 'err'); return; }
      try { await call('user_point_add', n, la, lo, $('upDesc').value || 'Ponto manual'); ['upName', 'upLat', 'upLon', 'upDesc'].forEach(id => $(id).value = ''); toast('Ponto adicionado.', 'ok'); loadPoints(); } catch (e) { toast(e.message, 'err'); } };
    $('upImport').onclick = async () => { try { const r = await call('points_import'); if (r) { toast(`${r.imported} ponto(s) importado(s).`, 'ok'); loadPoints(); } } catch (e) { toast(e.message, 'err'); } };
    $('upExport').onclick = async () => { try { const p = await call('points_export'); if (p) toast('Guardado em ' + p, 'ok'); } catch (e) { toast(e.message, 'err'); } };
    // IA
    $('iaSend').onclick = iaSend; $('iaQ').onkeydown = e => { if (e.key === 'Enter') iaSend(); };
    $('iaClear').onclick = async () => { await call('ia_clear'); loadIa(); };
    $('iaCtx').onclick = async () => { try { const c = await call('ia_context'); modal('Contexto enviado ao modelo', `<pre style="white-space:pre-wrap;font-size:11px">${esc(c)}</pre>`); } catch (e) { toast(e.message, 'err'); } };
    reportBtn('iaExportHtml', 'ia'); exportBtn('iaExportXls', 'ia', null, () => 'IA_analise.xlsx');
    $('iaModel').onchange = () => call('ia_settings_set', null, null, $('iaModel').value, null);
    // Preferências
    $('prProv').onchange = () => { const pv = iaCfg.providers[$('prProv').value]; $('prModel').innerHTML = pv.models.map(([id, lb]) => `<option value="${id}">${esc(lb)}</option>`).join(''); $('prAzureWrap').classList.toggle('hidden', $('prProv').value !== 'azure'); };
    $('prSave').onclick = async () => { try { await call('ia_settings_set', $('prProv').value, $('prKey').value || null, $('prModel').value, $('prAzure').value); $('prKey').value = ''; toast('Definições guardadas.', 'ok'); loadIa(); } catch (e) { toast(e.message, 'err'); } };
    // ---- histórico de versões / e-mail de novidades
    let newsVersion = null;
    async function loadChangelog() {
      try {
        const r = await call('changelog');
        $('prChangelog').innerHTML = r.versions.map(v => `<div class="ver-row"><div class="ver-head"><span class="ver-tag">v${esc(v.version)}</span><span class="ver-title">${esc(v.title)}</span><span class="ver-date">${esc(v.date || '')}</span>
          <button class="btn sm" data-news="${esc(v.version)}">✉ Email de novidades</button></div><div class="ver-sum">${esc(v.summary || '')}</div>
          ${(v.sections || []).map(s => `<div class="ver-sec"><b>${esc(s.title)}</b><ul>${s.items.map(i => `<li>${esc(i)}</li>`).join('')}</ul></div>`).join('')}</div>`).join('');
        $('prChangelog').querySelectorAll('[data-news]').forEach(b => b.onclick = () => openNews(b.dataset.news));
      } catch (e) { $('prChangelog').innerHTML = `<p class="mini">${esc(e.message)}</p>`; }
    }
    async function openNews(v) {
      try {
        const r = await call('news_preview', v); newsVersion = v;
        $('newsVer').textContent = 'v' + v; $('newsFrame').srcdoc = r.html; $('newsModal').classList.remove('hidden');
      } catch (e) { toast(e.message, 'err'); }
    }
    const closeNews = () => $('newsModal').classList.add('hidden');
    $('newsClose').onclick = closeNews; $('newsModal').onclick = e => { if (e.target === $('newsModal')) closeNews(); };
    $('newsOpen').onclick = async () => { try { const p = await call('news_email', newsVersion); toast('Rascunho aberto no cliente de e-mail (' + p + ').', 'ok'); } catch (e) { toast(e.message, 'err'); } };
    $('newsCopy').onclick = async () => {
      try {
        const r = await call('news_preview', newsVersion);
        // só o corpo do email (sem <html>/<head>), em HTML + texto simples; o Outlook na web cola o HTML formatado
        const doc = new DOMParser().parseFromString(r.html, 'text/html'); const bodyHtml = doc.body.innerHTML; const text = r.subject + '\n\n' + doc.body.innerText;
        if (navigator.clipboard && window.ClipboardItem) {
          await navigator.clipboard.write([new ClipboardItem({ 'text/html': new Blob([bodyHtml], { type: 'text/html' }), 'text/plain': new Blob([text], { type: 'text/plain' }) })]);
        } else {   // fallback: seleção + execCommand
          const div = document.createElement('div'); div.innerHTML = bodyHtml; div.style.position = 'fixed'; div.style.left = '-9999px'; document.body.appendChild(div);
          const range = document.createRange(); range.selectNodeContents(div); const sel = getSelection(); sel.removeAllRanges(); sel.addRange(range); document.execCommand('copy'); sel.removeAllRanges(); div.remove();
        }
        toast('Copiado. No Outlook: Nova mensagem → cola no corpo (Ctrl+V). Assunto: ' + r.subject, 'ok');
        $('newsSubject').value = r.subject; $('newsSubjectWrap').classList.remove('hidden'); $('newsSubject').select();
      } catch (e) { toast('Não foi possível copiar: ' + e.message, 'err'); }
    };
    $('newsSubjectCopy').onclick = async () => { try { await navigator.clipboard.writeText($('newsSubject').value); toast('Assunto copiado.', 'ok'); } catch (e) { $('newsSubject').select(); document.execCommand('copy'); toast('Assunto copiado.', 'ok'); } };
    $('newsSave').onclick = async () => { try { const p = await call('news_save_html', newsVersion); if (p) toast('Guardado em ' + p, 'ok'); } catch (e) { toast(e.message, 'err'); } };
    $('prAbout').onclick = e => { e.preventDefault(); $('btnAbout').click(); };
    loadChangelog();
    $('prRemoveMissing').onclick = async () => { try { const n = await call('remove_missing'); toast(`${n} ficheiro(s) removidos da base.`, 'ok'); } catch (e) { toast(e.message, 'err'); } };
    setTimeout(() => { loadPoints().catch(() => {}); loadIa().catch(() => {}); }, 800);
  });
  return { onFilter, onTab, onSub, runFinal, R };
})();
window.Analyses = Analyses;
