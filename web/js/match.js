import { $, h, getJSON, dur, themeToggle } from './common.js';
import { sparkline, dotPlot, groupedBars, scatter } from './charts.js';

themeToggle($('#theme'));

async function main() {
  const match = await getJSON('data/match.json');
  $('#match-name').textContent = match.short_name;
  $('#gen').textContent = `Updated ${new Date(match.generated_at).toLocaleString()}.`;
  const P = match.patterns.players;
  const names = match.players;
  const prof = (n) => P[n] || { name: n, short: match.display[n]?.short || n, slot: match.display[n]?.slot || 1, points: 0, games: 0 };
  const color = (n) => `var(--p${prof(n).slot})`;
  const played = match.games.length;
  const app = $('#app');
  app.innerHTML = '';

  // ---------- hero + score ----------
  const [a, b] = names.map(prof);
  app.append(h('section', { class: 'hero' },
    h('div', { class: 'eyebrow' }, `${match.name} · ${played} of ${match.schedule.length || played} games analysed`),
    h('h1', {}, 'Where the games were decided, and where the clock went'),
    h('p', {}, 'Each game shown move by move: the engine’s evaluation, how long each player thought, where opening preparation ran out, and the positions that mattered most. Every claim on the site comes from an engine, a clock or a database.'),
    h('div', { class: 'score' },
      h('div', { class: 'pl' }, h('span', { class: 'dot', style: `background:${color(a.name)};width:14px;height:14px` }), a.short),
      h('div', { class: 'pts' }, fmtPts(a.points)), h('div', { class: 'sep' }, '–'), h('div', { class: 'pts' }, fmtPts(b.points)),
      h('div', { class: 'pl' }, b.short, h('span', { class: 'dot', style: `background:${color(b.name)};width:14px;height:14px` })),
    ),
  ));

  // ---------- games table ----------
  const byRound = new Map(match.games.map((g) => [parseInt(g.round, 10), g]));
  const rows = (match.schedule.length ? match.schedule : match.games.map((g) => ({ name: `Game ${parseInt(g.round, 10)}` }))).map((r, i) => {
    const g = byRound.get(i + 1);
    if (!g) {
      return h('tr', { class: 'future' }, h('td', {}, r.name), h('td', { colspan: 7 }, r.startsAt ? `Scheduled ${new Date(r.startsAt).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}` : 'Not played yet'));
    }
    const res = { '1-0': '1–0', '0-1': '0–1', '1/2-1/2': '½–½', '*': 'live' }[g.result] || g.result;
    const pl = (p) => h('span', {}, h('span', { class: 'dot', style: `background:var(--p${p.slot})` }), ' ', p.short || p.name);
    return h('tr', { class: 'played', onclick: () => (location.href = `game.html?id=${g.id}`) },
      h('td', {}, h('a', { href: `game.html?id=${g.id}`, style: 'font-weight:600;text-decoration:none' }, r.name || `Game ${i + 1}`)),
      h('td', {}, pl(g.white), h('span', { class: 'muted' }, ' – '), pl(g.black)),
      h('td', { class: 'res' }, res),
      h('td', {}, h('div', {}, g.eco || ''), h('div', { class: 'muted', style: 'font-size:12.5px;max-width:260px' }, g.opening_name || '')),
      h('td', {}, g.novelty ? g.novelty.label : '—'),
      h('td', {}, g.longest_think ? h('span', {}, dur(g.longest_think.seconds), h('div', { class: 'muted', style: 'font-size:12.5px' }, g.longest_think.label)) : '—'),
      h('td', {}, String(g.critical_count)),
      h('td', {}, sparkline(g.sparkline)),
    );
  });
  app.append(h('div', { class: 'section-h' }, h('h2', {}, 'Games'), h('span', { class: 'muted' }, 'Sparkline: White’s winning chances, move by move')),
    h('div', { class: 'card table-scroll' }, h('table', { class: 'games' },
      h('thead', {}, h('tr', {}, ...['Game', 'Players (White – Black)', 'Result', 'Opening', 'Prep ended', 'Longest think', 'Critical', 'Eval'].map((t) => h('th', {}, t)))),
      h('tbody', {}, ...rows))));

  if (!played) return;

  // ---------- insights ----------
  const ins = match.patterns.insights;
  app.append(h('div', { class: 'section-h', id: 'patterns' }, h('h2', {}, 'Patterns so far'), h('span', { class: 'muted' }, played < 4 ? `Based on ${played} game${played > 1 ? 's' : ''}. These become meaningful as the match goes on.` : `Across ${played} games`)),
    h('div', { class: 'insights' }, ...ins.map((i) => h('div', { class: 'card insight' }, h('span', { class: 'dot', style: `background:${color(i.player)}` }), h('span', {}, i.text)))));

  // ---------- profile charts ----------
  const series = names.filter((n) => P[n]).map((n) => ({ key: n, label: P[n].short, color: color(n) }));
  const legend = h('div', { class: 'legend' }, ...series.map((se) => h('span', {}, h('span', { class: 'dot', style: `background:${se.color}` }), ' ', se.label)));
  const card = (title, sub, el, note) => h('div', { class: 'card chart-card' }, h('div', { class: 'chart-head' }, h('h2', {}, title), legend.cloneNode(true)), h('p', { class: 'note', style: 'margin:0 0 8px' }, sub), el, note ? h('p', { class: 'note' }, note) : null);
  const phaseEl = h('div', { class: 'chart' }), clockEl = h('div', { class: 'chart' }), thinkEl = h('div', { class: 'chart' }), hardEl = h('div', { class: 'chart' });
  app.append(h('div', { class: 'patterns', style: 'margin-top:14px' },
    card('Time budget by phase', 'Share of each player’s thinking time', phaseEl),
    card('Accuracy under time pressure', 'Average move accuracy, grouped by clock time left before the move', clockEl, 'Hover a dot to see how many moves it is based on.'),
    card('Does a long think pay off?', 'Average move accuracy, grouped by how long the move took', thinkEl),
    card('Hard positions', 'Accuracy where few good moves existed (difficulty ≥ 0.5) vs everywhere else', hardEl),
  ));
  const draws = [];
  const phases = ['opening', 'middlegame', 'endgame'];
  draws.push(groupedBars(phaseEl, {
    rows: phases.map((p) => ({ label: p, values: Object.fromEntries(series.map((se) => [se.key, P[se.key].time_share_by_phase[p]])), extra: Object.fromEntries(series.map((se) => [se.key, dur(P[se.key].time_by_phase[p])])) })),
    series, max: 100, format: (v) => v.toFixed(0), unit: '%',
  }));
  const accRows = (field) => P[series[0].key][field].map((bk, i) => ({ label: bk.bucket, values: Object.fromEntries(series.map((se) => { const d = P[se.key][field][i]; return [se.key, { value: d.accuracy, n: d.moves }]; })) }));
  const allAcc = series.flatMap((se) => [...P[se.key].accuracy_by_clock, ...P[se.key].accuracy_by_think].map((d) => d.accuracy)).filter((v) => v != null);
  const lo = Math.max(0, 100 - 4 * Math.ceil((100 - Math.min(...allAcc) + 2) / 4)); // 4 even steps
  draws.push(dotPlot(clockEl, { rows: accRows('accuracy_by_clock'), series, domain: [lo, 100], unit: '%' }));
  draws.push(dotPlot(thinkEl, { rows: accRows('accuracy_by_think'), series, domain: [lo, 100], unit: '%' }));
  draws.push(dotPlot(hardEl, {
    rows: [
      { label: 'hard', values: Object.fromEntries(series.map((se) => [se.key, { value: P[se.key].accuracy_hard.accuracy, n: P[se.key].accuracy_hard.moves }])) },
      { label: 'other', values: Object.fromEntries(series.map((se) => [se.key, { value: P[se.key].accuracy_easy.accuracy, n: P[se.key].accuracy_easy.moves }])) },
    ], series, domain: [lo, 100], unit: '%',
  }));

  // ---------- moves map (explorer) ----------
  const cols = match.patterns.move_columns;
  const moves = match.patterns.moves.map((r) => Object.fromEntries(cols.map((c, i) => [c, r[i]])));
  const AX = {
    spent: { label: 'time spent', get: (m) => m.spent, scale: 'sqrt' },
    clock_before: { label: 'clock left before move', get: (m) => m.clock_before, scale: 'sqrt' },
    move: { label: 'move number', get: (m) => Math.floor(m.ply / 2) + 1, scale: 'linear' },
  };
  const AY = {
    wp_loss: { label: 'win chance lost (pts)', get: (m) => m.wp_loss },
    difficulty: { label: 'position difficulty', get: (m) => m.difficulty, max: 1 },
    spent_min: { label: 'minutes spent', get: (m) => (m.spent ?? 0) / 60 },
  };
  const sel = (id, opts, val) => h('select', { id }, ...opts.map(([v, t]) => { const o = h('option', { value: v }, t); if (v === val) o.selected = true; return o; }));
  const fx = sel('fx', Object.entries(AX).map(([k, v]) => [k, v.label]), 'spent');
  const fy = sel('fy', Object.entries(AY).map(([k, v]) => [k, v.label]), 'difficulty');
  const fp = sel('fp', [['all', 'both players'], ...series.map((se) => [se.key, se.label])], 'all');
  const fph = sel('fph', [['all', 'all phases'], ...phases.map((p) => [p, p])], 'all');
  const fg = sel('fg', [['all', 'all games'], ...match.games.map((g) => [g.id, `Game ${parseInt(g.round, 10)}`])], 'all');
  const fb = sel('fb', [['no', 'hide book moves'], ['yes', 'include book moves']], 'no');
  const mapEl = h('div', { class: 'chart' });
  const count = h('span', { class: 'muted', style: 'font-size:12.5px' });
  app.append(h('div', { class: 'section-h', id: 'explorer' }, h('h2', {}, 'Moves map'), h('span', { class: 'muted' }, 'Every move of the match as a dot. Pick the axes and look for clusters. Click a dot to open that position.')),
    h('div', { class: 'card chart-card' },
      h('div', { class: 'filters' }, 'x', fx, 'y', fy, fp, fph, fg, fb, count),
      h('div', { class: 'legend', style: 'margin-bottom:6px' }, ...series.map((se) => h('span', {}, h('span', { class: 'dot', style: `background:${se.color}` }), ' ', se.label))),
      mapEl));
  let drawMap = () => {};
  const update = () => {
    const ax = AX[fx.value], ay = AY[fy.value];
    const pts = moves.filter((m) => (fp.value === 'all' || m.player === fp.value) && (fph.value === 'all' || m.phase === fph.value) && (fg.value === 'all' || m.game === fg.value) && (fb.value === 'yes' || !m.in_book) && ax.get(m) != null)
      .map((m) => ({
        x: ax.get(m), y: ay.get(m) ?? 0, color: color(m.player),
        html: `<b>${m.label}</b> · ${P[m.player]?.short || m.player}<br>${dur(m.spent)} spent · ${dur(m.clock_before)} left<br>win chance lost ${m.wp_loss.toFixed(1)} · difficulty ${m.difficulty.toFixed(2)}${m.classification ? `<br>${m.classification}` : ''}`,
        onClick: () => (location.href = `game.html?id=${m.game}&ply=${m.ply + 1}`),
      }));
    count.textContent = `${pts.length} moves`;
    drawMap = scatter(mapEl, { points: pts, xLabel: ax.label, yLabel: ay.label, xScale: ax.scale, yMax: ay.max });
  };
  [fx, fy, fp, fph, fg, fb].forEach((e) => e.addEventListener('change', update));
  update();
  let rt;
  addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(() => { draws.forEach((d) => d()); drawMap(); }, 120); });
}

const fmtPts = (p) => (Number.isInteger(p) ? String(p) : `${Math.floor(p) || ''}½`);

main().catch((e) => { $('#app').innerHTML = `<div class="loading">Could not load match data: ${e.message}</div>`; console.error(e); });
