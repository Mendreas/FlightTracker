/* FlightTracker 4 — abas de análise (Final, Velocidades, Análise Op., KPIs, Pontos, IA, Preferências) */
'use strict';
const Analyses = (() => {
  const { esc, fmt } = C;
  const $ = id => document.getElementById(id);
  const call = (...a) => FP.call(...a);
  const toast = (m, k) => FP.toast(m, k);
  const busy = (el, msg = 'A calcular…') => { if (el) el.innerHTML = `<div class="empty">⏳ ${esc(msg)}</div>`; };
  const empty = (el, msg) => { if (el) el.innerHTML = `<div class="empty">${esc(msg)}</div>`; };
  const R = { final: null, star: null, app: null, ad: null, fast: null, dados: null, diaria: null, rrms: null, rot: null, kpis: null, pt: null, seq: null };
  const hasFlights = () => FP.state.flights.length > 0;
  const sec = v => v == null ? '—' : fmt(Math.round(v));
  const rwyBadge = r => `<span class="badge" style="background:${r === '02' || r === '17' || r === '10' || r === '05' ? '#3b9cff' : '#c77dff'}">RWY ${esc(r)}</span>`;
  const csnLink = (csn, fid) => `<a href="#" class="csn-link" data-fid="${fid}"><b>${esc(csn)}</b></a>`;
  const wireCsn = root => root.querySelectorAll('.csn-link').forEach(a => a.onclick = ev => { ev.preventDefault(); FP.showTab('map'); FP.selectFlight(+a.dataset.fid, true); });
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
    let h = '<div class="kgrid">' + C.kcard('Ficheiros carregados', k.files) + C.kcard('Movimentos', k.movementRows) + C.kcard('Passagens THR detetadas', k.landings) + C.kcard('Pares globais', k.allPairs) + '</div>';
    h += `<div class="hint" style="margin-bottom:8px">${k.pairs} pares precedente/seguidor analisados · ${k.crit} abaixo de ${limit}s</div>`;
    h += '<div class="kgrid">' + C.kcard('Pares analisados', k.pairs) + C.kcard('Abaixo do limite', k.crit, '', k.crit ? 'bad' : 'ok') + C.kcard('Críticos com DEP', k.critDep) + C.kcard('Críticos sem DEP', k.critNoDep) +
      C.kcard('Menor separação', k.min == null ? '—' : fmt(k.min, 1) + ' s') + C.kcard('Média', k.avg == null ? '—' : fmt(k.avg, 1) + ' s') + C.kcard('Mediana', k.median == null ? '—' : fmt(k.median, 1) + ' s') +
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
    const d = R.rot, el = $('rotBody'), rf = $('rotRwy').value; if (!d) return;
    const rws = [...new Set(d.results.map(r => r.rwy))].sort(); const sel = $('rotRwy'); sel.innerHTML = '<option value="all">Todas</option>' + rws.map(r => `<option value="${r}" ${rf === r ? 'selected' : ''}>RWY ${r}</option>`).join('');
    const rows = d.results.filter(r => rf === 'all' || r.rwy === rf);
    $('rotCount').textContent = `${rows.length} aterragem(ns)`;
    const vals = rows.map(r => r.rotS).sort((a, b) => a - b), n = vals.length;
    let h = '<div class="kgrid">' + C.kcard('N.º aterragens', n) + C.kcard('ROT médio', n ? fmt(vals.reduce((a, b) => a + b, 0) / n) + ' s' : '—') + C.kcard('P85', n ? vals[Math.min(Math.floor(n * .85), n - 1)] + ' s' : '—') + C.kcard('P95', n ? vals[Math.min(Math.floor(n * .95), n - 1)] + ' s' : '—') + C.kcard('Máximo', n ? vals[n - 1] + ' s' : '—') + '</div>';
    if (d.n < d.processed * 0.3) h += '<div class="hint sep-o" style="margin-bottom:8px">⚠ A maioria das chegadas termina antes da pista (cobertura radar até ~250 ft / 1,5 NM da THR) — o ROT só é calculável quando existem plots na rolagem.</div>';
    h += `<div class="hint" style="margin-bottom:8px">ARR processados: ${d.processed} · sem pontos: ${d.dbg.noPts || 0} · THR não detectada: ${d.dbg.noCross || 0} · sem saída de pista: ${d.dbg.noOnRwy || 0} · ROT inválido: ${d.dbg.tooShort || 0} · calculados: ${d.n}</div>`;
    h += C.table([{ k: 'i', label: 'N', fmt: (v, r, i) => i + 1 }, { k: 'rwy', label: 'Pista', fmt: v => rwyBadge(v) }, { k: 'date', label: 'Data' }, { k: 'csn', label: 'Voo', fmt: (v, r) => csnLink(v, r.flight_id) }, { k: 'actype', label: 'Tipo' }, { k: 'tTHRstr', label: 'Hora THR' },
      { k: 'rotS', label: 'ROT (s)', fmt: v => `<span class="${v <= 45 ? 'sep-g' : v <= 60 ? 'sep-o' : 'sep-r'}">${v}</span>` }, { k: 'exitM', label: 'Dist. saída (m)' }], rows, { id: 'rotTable' });
    el.innerHTML = h; wireCsn(el);
  }

  /* ================================================================ KPIs */
  async function runKpis() {
    const el = $('kpiBody'); if (!hasFlights()) { empty(el, 'Sem dados.'); return; }
    busy(el);
    try { if (!R.final) await runFinal(false); if (!R.star && FP.state.flights.length < 4000) await runStar(false); R.kpis = await call('kpis'); renderKpis(); } catch (e) { empty(el, 'Erro: ' + e.message); toast(e.message, 'err'); }
  }
  function renderKpis() {
    const k = R.kpis, el = $('kpiBody'); if (!k) return;
    const p = v => k.total ? Math.round(v / k.total * 100) + '%' : '';
    $('kpiNote').textContent = [k.approach && `${k.approach.n} aproximações`, k.star && `${k.star.passes} passagens STAR`, k.star && `${k.star.viol} violações IAS`].filter(Boolean).join(' · ');
    let h = C.card('Resumo Operacional', '<div class="kgrid">' + C.kcard('Movimentos', fmt(k.total)) + C.kcard('Chegadas (ARR)', k.arr, p(k.arr)) + C.kcard('Partidas (DEP)', k.dep, p(k.dep)) + C.kcard('Sobrevoos (LVL)', k.lvl, p(k.lvl)) + C.kcard('Dias de dados', k.days) +
      C.kcard('Hora de pico', `${String(k.peakHour).padStart(2, '0')}:00`, `${k.peakN} mov.`) + C.kcard('Período (UTC)', k.period) + C.kcard('Amostras (radar)', fmt(k.pts)) + '</div>' + (k.days > 1 ? `<p class="hint">Contagem por (callsign, dia): ${k.total} movimentos em ${k.callsigns} callsigns distintos ao longo de ${k.days} dias.</p>` : ''));
    if (k.approach) { const a = k.approach; h += C.card(`Análise de Aproximações (${FP.state.airport})`, '<div class="kgrid">' + C.kcard('Aterragens', a.n, a.rate ? fmt(a.rate, 1) + ' aterr./h' : '') + Object.entries(a.byRwy).map(([r, n]) => C.kcard('RWY ' + r, n)).join('') +
      C.kcard('Estabilizadas', `${a.stab}/${a.n}`, Math.round(a.stab / a.n * 100) + '%') + C.kcard('IAS@FAF méd.', fmt(a.iasFAF) + ' kt') + C.kcard('Tempo FAF→THR méd.', fmt(a.durS) + ' s') + C.kcard('Sep. temporal méd.', sec(a.sepMean) + ' s') + C.kcard('Sep. temporal mín./máx.', `${sec(a.sepMin)} / ${sec(a.sepMax)} s`) + '</div>'); }
    if (k.landingRate) { const l = k.landingRate; h += C.card('Taxa de aterragem (rolling 60 min)', '<div class="kgrid">' + C.kcard('Pico 60 min', l.peak + ' aterr./h', `${fmt(l.pct)}% da capacidade LPPT (38)`) + C.kcard('Média período', l.avg + ' aterr./h', 'média inteira (arred. por defeito)') + C.kcard('Total', k.approach.n + ' aterragens') + '</div>' + C.bars(l.series, l.labels, { color: C.RED, h: 110 }), 'Cada ponto: aterragens na hora anterior. Referência: capacidade declarada LPPT ≈ 38 mov/h.'); }
    if (k.sepHist) { const s = k.sepHist; h += C.card('Separação temporal entre aterragens consecutivas', '<div class="kgrid">' + C.kcard('Média', fmt(s.mean) + ' s', 'sensível a extremos') + C.kcard('Mediana', s.median + ' s', 'valor central (50%)') + C.kcard('Mínimo', s.min + ' s') + C.kcard('Máximo', s.max + ' s') + C.kcard('Bunching', `${s.bunching} <90s`, 'aproximações muito comprimidas', s.bunching ? 'warn' : '') + '</div>' + C.bars(s.counts, s.labels, { color: C.RED })); }
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
  function onFilter() {
    Object.keys(R).forEach(k => R[k] = null); FP.overlay.clearLayers(); ptCircle = null;
    [['finBody', 'Filtro alterado. Clica Analisar para actualizar resultados'], ['starBody', 'Filtro alterado. Clica Analisar'], ['appBody', 'Filtro alterado. Clica Analisar'], ['adBody', 'Filtro alterado. Clica Analisar'],
     ['fastBody', 'Filtro alterado. Abre a sub-aba para recalcular'], ['sdBody', 'Filtro alterado. Clica Atualizar análise'], ['dyBody', 'Filtro alterado. Clica Actualizar'], ['rrBody', 'Filtro alterado. Clica Analisar'], ['rotBody', 'Filtro alterado. Clica Analisar'], ['kpiBody', 'Filtro alterado. Clica Actualizar'], ['ptBody', 'Filtro alterado. Clica Pesquisar'], ['seqBody', 'Filtro alterado. Clica Pesquisar']].forEach(([id, m]) => empty($(id), m));
    ['finCount', 'starCount', 'appCount', 'adCount', 'fastCount', 'rrCount', 'rotCount', 'ptCount', 'seqCount', 'kpiNote'].forEach(id => $(id).textContent = '');
    renderScale();
    const active = document.querySelector('.tab.active'); if (active) onTab(active.dataset.tab);
  }
  function onTab(name) {
    if (!hasFlights()) return;
    if (name === 'final' && !R.final) runFinal(false);
    if (name === 'star' && !R.star) runStar(false);
    if (name === 'app' && !R.app) runApp(false);
    if (name === 'ana') onSub(document.querySelector('#tab-ana .subtab.active').dataset.sub);
    if (name === 'kpi' && !R.kpis) runKpis();
    if (name === 'pts' && !R.pt && $('ptSel').value) { runPt(); }
    if (name === 'ia') loadIa();
    if (name === 'pref') { loadIa(); call('get_state').then(s => $('prDb').textContent = `${s.db_path} · ${(s.db_bytes / 1048576).toFixed(0)} MB · ${s.files} ficheiros · ${fmt(s.rows)} plots · ${s.nmir} registos NMIR`); }
  }
  function onSub(sub) {
    if (!hasFlights()) return;
    if (sub === 'fast' && !R.fast) runFast();
    if (sub === 'dados' && !R.dados) runDados();
    if (sub === 'diaria' && !R.diaria) runDiaria();
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
    $('rotRun').onclick = runRot; $('rotRwy').onchange = () => R.rot && renderRot(); exportBtn('rotExport', 'rot');
    // KPIs
    $('kpiRun').onclick = runKpis; exportBtn('kpiExport', 'kpis'); reportBtn('kpiReport', 'kpis');
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
    $('prRemoveMissing').onclick = async () => { try { const n = await call('remove_missing'); toast(`${n} ficheiro(s) removidos da base.`, 'ok'); } catch (e) { toast(e.message, 'err'); } };
    setTimeout(() => { loadPoints().catch(() => {}); loadIa().catch(() => {}); }, 800);
  });
  return { onFilter, onTab, onSub, runFinal, R };
})();
window.Analyses = Analyses;
