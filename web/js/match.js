import { $, h, getJSON, dur, themeToggle } from './common.js';
import { sparkline, dotPlot, groupedBars, scatter, probChart } from './charts.js';

themeToggle($('#theme'));

const RES = { '1-0': '1–0', '0-1': '0–1', '1/2-1/2': '½–½', '*': 'live' };
const cap = (t) => t.charAt(0).toUpperCase() + t.slice(1);
const fmtPts = (p) => (Number.isInteger(p) ? String(p) : `${Math.floor(p) || ''}½`);
const roundOf = (g) => parseInt(g.round, 10);

async function main() {
  const match = await getJSON('data/match.json');
  $('#match-name').textContent = match.short_name;
  $('#gen').textContent = `Updated ${new Date(match.generated_at).toLocaleString()}.`;
  const P = match.patterns.players;
  const names = match.players;
  const prof = (n) => P[n] || { name: n, short: match.display[n]?.short || n, slot: match.display[n]?.slot || 1, points: 0, games: 0 };
  const color = (n) => `var(--p${prof(n).slot})`;
  const nm = (n) => prof(n).short;
  const byShort = (s) => names.find((n) => nm(n) === s);
  const ctx = { match, P, names, prof, color, nm, byShort };
  const app = $('#app');
  app.innerHTML = '';

  app.append(hero(ctx), gamesSection(ctx));
  const strip = newStrip(ctx);
  if (strip) app.append(strip);
  const story = storyCard(ctx);
  if (story) app.append(story);
  if (match.games.length) app.append(deepDive(ctx));
}

// ---------------------------------------------------------------- hero

function nextRound(match) {
  const r = match.schedule.find((x) => !x.finished && x.startsAt);
  if (!r) return null;
  const d = new Date(r.startsAt);
  const ng = match.win_probability?.next_game;
  return {
    name: r.name,
    when: `${d.toLocaleDateString('en-GB', { weekday: 'long', month: 'short', day: 'numeric', timeZone: 'UTC' })}`,
    time: `${d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'UTC' })} UTC`,
    white: ng && `${ng.round}` === r.name.split(' ').pop() ? ng.white : null,
  };
}

function hero({ match, names, prof, color, nm }) {
  const played = match.games.length;
  const [a, b] = names.map(prof);
  const nx = nextRound(match);
  const headline = match.story?.headline || 'Where the games were decided, and where the clock went';
  return h('section', { class: 'hero home-hero' },
    h('div', {},
      h('div', { class: 'eyebrow' }, `${match.name} · after ${played} of ${match.schedule.length || played} games`),
      h('div', { class: 'score' },
        h('div', { class: 'pl' }, h('span', { class: 'dot', style: `background:${color(a.name)};width:14px;height:14px` }), a.short),
        h('div', { class: 'pts' }, `${fmtPts(a.points)} – ${fmtPts(b.points)}`),
        h('div', { class: 'pl' }, b.short, h('span', { class: 'dot', style: `background:${color(b.name)};width:14px;height:14px` }))),
      h('h1', {}, headline)),
    nx ? h('div', { class: 'next-box' },
      h('div', { class: 'eyebrow' }, 'Next'),
      h('div', { class: 'v' }, `${nx.name} · ${nx.when}`),
      h('div', { class: 's' }, `${nx.white ? `${nm(nx.white)} has White. ` : ''}Starts ${nx.time}.`)) : null);
}

// ---------------------------------------------------------------- games

function gamesSection({ match, nm, byShort, color }) {
  const byRound = new Map(match.games.map((g) => [roundOf(g), g]));
  const latest = Math.max(0, ...byRound.keys());
  const sched = match.schedule.length ? match.schedule : match.games.map((g) => ({ name: `Game ${roundOf(g)}` }));
  const cards = [];
  const upcoming = [];
  sched.forEach((r, i) => {
    const g = byRound.get(i + 1);
    if (!g) { upcoming.push(r); return; }
    const pl = (p) => h('span', { class: 'pl' }, h('span', { class: 'dot', style: `background:var(--p${p.slot})` }), p.short || p.name);
    const who = byShort(g.tag.split(' ')[0]);
    cards.push(h('a', { class: `card gcard${roundOf(g) === latest ? ' latest' : ''}`, href: `game.html?id=${g.id}` },
      h('div', { class: 'gtop' }, h('b', {}, `${r.name || `Game ${i + 1}`}${roundOf(g) === latest ? ' · latest' : ''}`), h('span', { class: 'muted' }, fmtDate(g.date))),
      h('div', { class: 'gplayers' }, pl(g.white), h('span', { class: 'muted' }, '–'), pl(g.black), h('b', { class: 'gres' }, RES[g.result] || g.result)),
      sparkline(g.sparkline, { w: 220, hgt: 30 }),
      h('div', { class: 'ghead' }, g.headline || g.opening_name || ''),
      h('span', { class: 'gtag', style: who ? `--c:${color(who)}` : '' }, g.tag)));
  });
  if (upcoming.length) {
    const fmt = (r) => (r.startsAt ? new Date(r.startsAt).toLocaleDateString('en-GB', { weekday: 'short', month: 'short', day: 'numeric', timeZone: 'UTC' }) : '');
    cards.push(h('div', { class: 'gcard coming' },
      h('b', {}, 'Coming up'),
      ...upcoming.slice(0, 3).map((r) => h('div', {}, `${r.name} · ${fmt(r)}`)),
      upcoming.length > 3 ? h('div', { class: 'muted' }, `+ ${upcoming.length - 3} more`) : null));
  }
  return h('section', { id: 'games' },
    h('div', { class: 'section-h' }, h('h2', {}, 'Games'), h('span', { class: 'muted' }, 'Open a game for the board and its key moments')),
    h('div', { class: 'game-cards' }, ...cards));
}

function fmtDate(d) {
  if (!d) return '';
  const [y, m, day] = d.split('.').map(Number);
  return new Date(Date.UTC(y, m - 1, day)).toLocaleDateString('en-GB', { month: 'short', day: 'numeric', timeZone: 'UTC' });
}

// ---------------------------------------------------------------- what's new

function rankAlert(a) { return a.kind === 'record' ? (a.tile ? 0 : 1) : a.kind === 'first' ? 2 : 3; }

function alertLine(a, nm) {
  if (a.tile) return [h('b', {}, `${nm(a.player)}: ${a.tile.badge} ${a.tile.label}`), ` ${a.tile.value} (was ${a.tile.was})`];
  if (a.short) return [h('b', {}, `${nm(a.player)}: `), a.short];
  return [cap(a.text.replace(/^Game \d+: /, ''))];
}

function newStrip({ match, nm, color }) {
  const last = (match.alerts || []).at(-1);
  if (!last?.alerts.length) return null;
  // best alerts first, alternating between players so one player doesn't fill the strip
  const queues = new Map();
  for (const a of last.alerts.slice().sort((x, y) => rankAlert(x) - rankAlert(y))) {
    const k = a.player || '';
    if (!queues.has(k)) queues.set(k, []);
    queues.get(k).push(a);
  }
  const top = [];
  while (top.length < 3 && [...queues.values()].some((q) => q.length)) for (const q of queues.values()) if (q.length && top.length < 3) top.push(q.shift());
  return h('section', { class: 'card new-strip' },
    h('div', { class: 'eyebrow' }, `New after ${last.game}`),
    h('ul', {}, ...top.map((a) => h('li', {}, a.player ? h('span', { class: 'dot', style: `background:${color(a.player)}` }) : h('span', { class: 'dot', style: 'background:var(--muted)' }), h('span', {}, ...alertLine(a, nm))))),
    h('a', { class: 'more', href: '#alerts' }, `All ${last.alerts.length} insight alerts →`));
}

// ---------------------------------------------------------------- story

function storyCard({ match }) {
  const st = match.story;
  if (!st?.sections?.length) return null;
  const played = match.games.length;
  return h('section', { id: 'story', class: 'card story' },
    h('div', { class: 'story-main' },
      h('div', { class: 'eyebrow' }, `The story so far · after ${played} ${played === 1 ? 'game' : 'games'}`),
      h('p', { class: 'story-lede' }, st.summary),
      h('details', { class: 'story-more' },
        h('summary', {}, 'Read the full story'),
        h('h2', {}, st.headline),
        h('div', { class: 'gist-sections' }, ...st.sections.map((x) => h('div', {}, h('h3', {}, x.title), h('p', {}, x.text)))),
        h('details', { class: 'facts' },
          h('summary', {}, st.source === 'claude' ? `Written by ${st.model} from these facts; every move it names is checked against them · show facts` : 'Written from a template using these facts · show facts'),
          h('pre', {}, JSON.stringify(st.facts, null, 2))))),
    st.takeaways?.length ? h('div', { class: 'story-side' },
      h('div', { class: 'eyebrow' }, 'Patterns to watch'),
      h('ul', {}, ...st.takeaways.map((t) => h('li', {}, t.point)))) : null);
}

// ---------------------------------------------------------------- deep dive

const TABS = [
  ['odds', 'Who’s the favourite?'],
  ['prep', 'Preparation'],
  ['clock', 'Clock & thinking'],
  ['alerts', 'Insight alerts'],
  ['explore', 'Explore moves'],
  ['fans', 'What fans say'],
];
const LEGACY = { openings: 'prep', patterns: 'clock', explorer: 'explore', crowd: 'fans' };

function deepDive(ctx) {
  const builders = { odds: oddsTab, prep: prepTab, clock: clockTab, alerts: alertsTab, explore: exploreTab, fans: fansTab };
  const panels = {};
  const redraw = {};
  const list = h('div', { class: 'tabs', role: 'tablist', 'aria-label': 'Deep dive' });
  const box = h('div', {});
  const btns = {};
  for (const [id, label] of TABS) {
    btns[id] = h('button', { class: 'tab', role: 'tab', id: `tab-${id}`, 'aria-controls': `panel-${id}`, 'aria-selected': 'false', tabindex: '-1', onclick: () => show(id, true) }, label);
    panels[id] = h('div', { class: 'tabpanel', role: 'tabpanel', id: `panel-${id}`, 'aria-labelledby': `tab-${id}`, hidden: true });
    list.append(btns[id]);
    box.append(panels[id]);
  }
  list.addEventListener('keydown', (e) => {
    const ids = TABS.map((t) => t[0]);
    const i = ids.indexOf(document.activeElement?.id?.replace('tab-', ''));
    if (i < 0) return;
    const j = e.key === 'ArrowRight' ? (i + 1) % ids.length : e.key === 'ArrowLeft' ? (i - 1 + ids.length) % ids.length : null;
    if (j != null) { show(ids[j], true); btns[ids[j]].focus(); e.preventDefault(); }
  });
  let active = null;
  function show(id, push) {
    if (!builders[id]) return;
    active = id;
    for (const [k] of TABS) {
      const on = k === id;
      btns[k].setAttribute('aria-selected', String(on));
      btns[k].tabIndex = on ? 0 : -1;
      panels[k].hidden = !on;
    }
    if (!redraw[id]) {
      const r = builders[id](ctx, panels[id], (tab) => { show(tab, true); section.scrollIntoView({ behavior: 'smooth' }); });
      redraw[id] = typeof r === 'function' ? r : () => {};
    } else redraw[id]();
    if (push) history.replaceState(null, '', `#${id}`);
  }
  const section = h('section', { id: 'deep', class: 'deep' }, h('div', { class: 'section-h' }, h('h2', {}, 'Deep dive'), h('span', { class: 'muted' }, 'One topic at a time')), list, box);
  const fromHash = () => {
    const k = location.hash.slice(1);
    const id = LEGACY[k] || k;
    if (builders[id]) { show(id, false); section.scrollIntoView(); return true; }
    return false;
  };
  addEventListener('hashchange', fromHash);
  queueMicrotask(() => { if (!fromHash()) show('odds', false); });
  let rt;
  addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(() => active && redraw[active]?.(), 120); });
  return section;
}

const kindTag = (k) => h('span', { class: `kind kind-${k}` }, k === 'model' ? 'MODEL' : 'OPINION');

// --- odds
function oddsTab({ match, names, color, nm }, el) {
  const wp = match.win_probability;
  if (!wp) { el.append(h('p', { class: 'muted' }, 'Ratings not available yet.')); return; }
  const now = wp.series.at(-1);
  const fav = names.slice().sort((x, y) => now.win[y] - now.win[x])[0];
  const dog = names.find((n) => n !== fav);
  const ng = wp.next_game;
  const chartEl = h('div', { class: 'chart' });
  const tableWrap = h('div', { class: 'scroll-x', hidden: true },
    h('table', { class: 'data-table' },
      h('thead', {}, h('tr', {}, ...['', `${nm(names[0])} wins match`, `${nm(names[1])} wins match`, 'Tiebreak needed', 'Score'].map((t) => h('th', {}, t)))),
      h('tbody', {}, ...wp.series.map((sr) => h('tr', {}, h('td', {}, sr.label), h('td', {}, `${sr.win[names[0]]}%`), h('td', {}, `${sr.win[names[1]]}%`), h('td', {}, `${sr.tiebreak}%`), h('td', {}, `${fmtPts(sr.score[names[0]])}–${fmtPts(sr.score[names[1]])}`))))));
  const tableBtn = h('button', { class: 'table-toggle', onclick: () => { tableWrap.hidden = !tableWrap.hidden; tableBtn.textContent = tableWrap.hidden ? 'Show data table' : 'Hide data table'; } }, 'Show data table');
  const nextBar = ng ? h('div', { class: 'card pad' },
    h('div', { class: 'muted small' }, `Game ${ng.round} · ${nm(ng.white)} has White`),
    h('div', { class: 'stack big' },
      h('div', { style: `flex:${ng.white_win};background:${color(ng.white)}` }, `${ng.white_win.toFixed(0)}%`),
      h('div', { style: `flex:${ng.draw};background:var(--muted)` }, `Draw ${ng.draw.toFixed(0)}%`),
      h('div', { style: `flex:${ng.black_win};background:${color(ng.black)}` }, `${ng.black_win.toFixed(0)}%`)),
    h('div', { class: 'split muted small' }, h('span', {}, `${nm(ng.white)} wins`), h('span', {}, `${nm(ng.black)} wins`))) : null;
  el.append(
    h('div', { class: 'odds-grid' },
      h('div', { class: 'odds-side' },
        kindTag('model'),
        h('div', { class: 'card pad' },
          h('div', { class: 'muted small' }, 'Chance to win the match'),
          h('div', { class: 'big-pair' },
            h('span', {}, h('b', { style: `color:${color(fav)}` }, `${now.win[fav].toFixed(0)}%`), ` ${nm(fav)}`),
            h('span', {}, h('b', { style: `color:${color(dog)}` }, `${now.win[dog].toFixed(0)}%`), ` ${nm(dog)}`)),
          h('div', { class: 'small ink2' }, `${now.tiebreak.toFixed(0)}% chance it goes to tiebreaks.`)),
        nextBar),
      h('div', { class: 'card chart-card' },
        h('div', { class: 'chart-head' }, h('h3', {}, 'How the odds moved, game by game'), h('div', { class: 'legend' }, ...names.map((n) => h('span', {}, h('span', { class: 'dot', style: `background:${color(n)}` }), ' ', nm(n))), h('span', {}, h('span', { style: 'display:inline-block;width:14px;height:10px;background:var(--rule);vertical-align:-1px' }), ' draw-rate range'))),
        chartEl,
        h('p', { class: 'note' }, wp.assumptions.text, ' It says nothing about how well anyone played.'),
        tableBtn, tableWrap)));
  const draw = () => probChart(chartEl, {
    series: wp.series, games: wp.games,
    players: names.map((n) => ({ name: n, short: nm(n), color: color(n) })),
    onHover: (sr) => `<b>${sr.label}</b>${sr.result ? ` (${RES[sr.result]})` : ''}<br>${names.map((n) => `${nm(n)} ${sr.win[n].toFixed(1)}%`).join(' · ')}<br>tiebreak ${sr.tiebreak.toFixed(1)}%`,
  });
  draw();
  return draw;
}

// --- preparation
function prepTab({ match, color, byShort, nm }, el) {
  const pr = match.prep;
  if (pr) {
    const max = Math.max(1, ...Object.values(pr.players).flat().filter((v) => v != null));
    const rows = pr.games.map((g, i) => h('div', { class: 'prep-row' },
      h('b', {}, `Game ${g}`),
      h('div', {}, ...Object.entries(pr.players).map(([who, vals]) => h('div', { class: 'prep-bar' },
        h('span', { class: 'bar', style: `width:${vals[i] == null ? 0 : Math.max(1.5, (70 * vals[i]) / max)}%;background:${color(byShort(who))}` }),
        h('span', { class: 'small' }, `${who} ${pr.text[who][i]}`))))));
    el.append(h('div', { class: 'card pad prep-card' },
      h('div', {},
        h('div', { class: 'eyebrow' }, 'Time spent before leaving known theory'),
        h('h3', { class: 'chart-title' }, pr.headline)),
      h('div', { class: 'prep-rows' }, ...rows)));
  }
  // branches: one card per root line, one row per game in it
  const byId = new Map(match.games.map((g) => [g.id, g]));
  const collect = (seg) => [...seg.games, ...seg.children.flatMap(collect)];
  const branches = (match.opening_tree?.segments || []).map((seg) => {
    const ids = [...new Set(collect(seg))];
    const gs = ids.map((id) => byId.get(id)).filter(Boolean).sort((x, y) => roundOf(x) - roundOf(y));
    const fams = [...new Set(gs.map((g) => (g.opening_name || '').split(',')[0]).filter(Boolean))];
    const first = seg.moves.slice(0, 10).map((m, i) => `${m.ply % 2 === 0 ? `${Math.floor(m.ply / 2) + 1}.` : i === 0 ? `${Math.floor(m.ply / 2) + 1}...` : ''}${m.san}`).join(' ');
    const whites = [...new Set(gs.map((g) => g.white.short))];
    return h('div', { class: 'branch' },
      h('div', { class: 'branch-root' },
        h('b', {}, fams.join(' / ') || 'Opening'),
        h('div', { class: 'small ink2' }, first + (seg.moves.length > 10 ? ' …' : '')),
        h('div', { class: 'small muted' }, `${gs.length} game${gs.length === 1 ? '' : 's'} · ${whites.length === 1 ? `${whites[0]} had White${gs.length > 1 ? ' each time' : ''}` : 'both players had White'}`)),
      h('div', { class: 'branch-games' }, ...gs.map((g) => {
        const nv = g.novelty;
        const who = nv ? nm(nv.player) : null;
        const prepI = pr ? pr.games.indexOf(roundOf(g)) : -1;
        const used = who && pr && prepI >= 0 ? pr.text[who]?.[prepI] : null;
        return h('div', { class: 'branch-game' },
          h('a', { href: `game.html?id=${g.id}`, class: 'bg-title' }, `Game ${roundOf(g)} · ${RES[g.result] || g.result}`),
          h('div', { class: 'small ink2' }, (g.opening_name || '').split(':').slice(1).join(':').trim() || g.eco || ''),
          nv ? h('div', {}, h('span', { class: 'dot', style: `background:${color(nv.player)}` }), ` ${who} left theory with `,
            h('a', { class: 'mv', href: `game.html?id=${g.id}&ply=${nv.ply + 1}` }, nv.label), used ? h('span', { class: 'muted small' }, ` · after using ${used}`) : null)
            : h('div', { class: 'muted small' }, 'Stayed in the database to the end'));
      })));
  });
  el.append(h('div', { class: 'card pad' },
    h('div', { class: 'chart-head' }, h('h3', { class: 'chart-title' }, 'Opening tree'), h('span', { class: 'muted small' }, 'Where each game left the masters database, and who left it')),
    ...branches,
    match.opening_tree?.segments?.length ? h('details', { class: 'tree-full' }, h('summary', {}, 'Show every move of the tree'), h('div', { class: 'tree' }, treeList(match.opening_tree.segments, match, color))) : null));
  const last = (match.alerts || []).at(-1);
  const prepAlerts = (last?.alerts || []).filter((a) => ['prep_time', 'novelty_ply', 'reaction_to_novelty'].includes(a.metric));
  if (prepAlerts.length) {
    el.append(h('div', { class: 'eyebrow', style: 'margin:18px 0 8px' }, `Preparation records after ${last.game}`),
      h('div', { class: 'mini-cards' }, ...prepAlerts.map((a) => h('div', { class: 'card pad small-text' }, ...alertLine(a, nm)))));
  }
}

function treeList(segments, match, color) {
  const byId = new Map(match.games.map((g) => [g.id, g]));
  return h('ul', {}, ...segments.map((seg) => {
    const line = h('div', { class: 'line' });
    seg.moves.forEach((m, i) => {
      const white = m.ply % 2 === 0;
      if (white || i === 0) line.append(h('span', { class: 'no' }, `${Math.floor(m.ply / 2) + 1}${white ? '.' : '...'}`));
      line.append(h('span', { class: 'm', title: m.master_games != null ? `${m.master_games.toLocaleString()} master games` : null }, m.san));
    });
    line.append(h('span', { class: 'count' }, `${seg.games.length} game${seg.games.length === 1 ? '' : 's'}`));
    const leaves = [
      ...seg.novelties.map((n) => {
        const g = byId.get(n.game_id);
        const mv = seg.moves.find((x) => x.ply === n.ply);
        return h('div', { class: 'leaf' },
          h('span', {}, h('span', { class: 'dot', style: `background:${color(n.player)}` }), ` ${match.display[n.player]?.short || n.player} left theory`),
          h('a', { href: `game.html?id=${n.game_id}&ply=${n.ply + 1}` }, `${Math.floor(n.ply / 2) + 1}${n.ply % 2 ? '...' : '.'}${mv?.san ?? ''}`),
          h('span', { class: 'muted' }, `Game ${parseInt(n.round, 10)} · ${RES[n.result] || n.result}${g ? ` · ${g.white.short} (W) – ${g.black.short} (B)` : ''}`));
      }),
      ...(seg.ends || []).map((e) => h('div', { class: 'leaf muted' }, `Game ${parseInt(e.round, 10)} · ${RES[e.result] || e.result} · ${e.reason}`)),
    ];
    return h('li', {}, line, ...leaves, seg.children.length ? treeList(seg.children, match, color) : null);
  }));
}

// --- clock & thinking
function clockTab({ match, P, names, color }, el) {
  const series = names.filter((n) => P[n]).map((n) => ({ key: n, label: P[n].short, color: color(n) }));
  const H = match.headlines || {};
  const legend = () => h('div', { class: 'legend' }, ...series.map((se) => h('span', {}, h('span', { class: 'dot', style: `background:${se.color}` }), ' ', se.label)));
  const small = (field) => series.flatMap((se) => (P[se.key][field] || []).filter((d) => d.moves > 0 && d.moves < 10).map((d) => `${se.label} ${d.bucket} (${d.moves})`));
  const smallNote = (list) => (list.length ? h('p', { class: 'note warn' }, `Few moves behind: ${list.join(', ')}. Read these lightly.`) : null);
  const card = (eyebrow, headline, sub, chartEl, extra) => h('div', { class: 'card chart-card' },
    h('div', { class: 'eyebrow' }, eyebrow),
    h('div', { class: 'chart-head' }, h('h3', { class: 'chart-title' }, headline || eyebrow), legend()),
    h('p', { class: 'note', style: 'margin:0 0 8px' }, sub), chartEl, extra);
  const phaseEl = h('div', { class: 'chart' }), clockEl = h('div', { class: 'chart' }), thinkEl = h('div', { class: 'chart' }), hardEl = h('div', { class: 'chart' });
  const hardSmall = series.filter((se) => P[se.key].accuracy_hard?.moves < 10).map((se) => `${se.label} hard (${P[se.key].accuracy_hard.moves})`);
  el.append(
    h('p', { class: 'ink2', style: 'margin:0 0 12px' }, `How each player spends the clock, and whether time turns into better moves. All ${match.games.length} games, book moves left out.`),
    h('div', { class: 'patterns' },
      card('Time budget by phase', H.phase, 'Share of each player’s own thinking time', phaseEl),
      card('Accuracy under time pressure', H.pressure, 'Average move accuracy, grouped by clock time left before the move. Hover a dot for the number of moves.', clockEl, smallNote(small('accuracy_by_clock'))),
      card('Does a long think pay off?', H.think, 'Average move accuracy, grouped by how long the move took. Long thinks usually happen in harder positions, so this is not cause and effect.', thinkEl, smallNote(small('accuracy_by_think'))),
      card('Hard positions', H.hard, 'Accuracy where the engine found few good moves (difficulty 0.5 or more) vs everywhere else', hardEl, smallNote(hardSmall))));
  const phases = ['opening', 'middlegame', 'endgame'];
  const accRows = (field) => P[series[0].key][field].map((bk, i) => ({ label: bk.bucket, values: Object.fromEntries(series.map((se) => { const d = P[se.key][field][i]; return [se.key, { value: d.accuracy, n: d.moves }]; })) }));
  const allAcc = series.flatMap((se) => [...P[se.key].accuracy_by_clock, ...P[se.key].accuracy_by_think].map((d) => d.accuracy)).filter((v) => v != null);
  const lo = Math.max(0, 100 - 4 * Math.ceil((100 - Math.min(...allAcc) + 2) / 4));
  const draws = [
    groupedBars(phaseEl, {
      rows: phases.map((p) => ({ label: p, values: Object.fromEntries(series.map((se) => [se.key, P[se.key].time_share_by_phase[p]])), extra: Object.fromEntries(series.map((se) => [se.key, dur(P[se.key].time_by_phase[p])])) })),
      series, max: 100, format: (v) => v.toFixed(0), unit: '%',
    }),
    dotPlot(clockEl, { rows: accRows('accuracy_by_clock'), series, domain: [lo, 100], unit: '%' }),
    dotPlot(thinkEl, { rows: accRows('accuracy_by_think'), series, domain: [lo, 100], unit: '%' }),
    dotPlot(hardEl, {
      rows: [
        { label: 'hard', values: Object.fromEntries(series.map((se) => [se.key, { value: P[se.key].accuracy_hard.accuracy, n: P[se.key].accuracy_hard.moves }])) },
        { label: 'everything else', values: Object.fromEntries(series.map((se) => [se.key, { value: P[se.key].accuracy_easy.accuracy, n: P[se.key].accuracy_easy.moves }])) },
      ], series, domain: [lo, 100], unit: '%',
    }),
  ];
  return () => draws.forEach((d) => d());
}

// --- insight alerts
function alertsTab({ match, names, color, nm }, el) {
  const hist = (match.alerts || []);
  if (!hist.length) return;
  let cur = hist.length - 1;
  const pills = h('div', { class: 'pills', role: 'group', 'aria-label': 'Pick a game' });
  const body = h('div', {});
  const head = h('h3', { class: 'chart-title' });
  el.append(h('div', { class: 'chart-head' }, head, pills), body);
  const paint = () => {
    const g = hist[cur];
    head.textContent = `What changed after ${g.game}`;
    pills.replaceChildren(...hist.map((x, i) => h('button', { class: 'pill', 'aria-pressed': String(i === cur), onclick: () => { cur = i; paint(); } }, x.game)));
    if (!g.alerts.length) {
      body.replaceChildren(h('p', { class: 'ink2' }, `Nothing new: no records, streaks or firsts.${roundOf({ round: g.game.split(' ')[1] }) < (match.alerts_min_games || 3) ? ` Records (“highest so far”) start after Game ${match.alerts_min_games || 3}, and streaks need three games in a row.` : ''}`));
      return;
    }
    const cols = names.map((n) => {
      const mine = g.alerts.filter((a) => a.player === n);
      if (!mine.length) return null;
      const tiles = mine.filter((a) => a.tile);
      const lines = mine.filter((a) => !a.tile);
      return h('div', { class: 'card pad alert-col', style: `--c:${color(n)}` },
        h('div', { class: 'alert-name' }, nm(n)),
        tiles.length ? h('div', { class: 'tiles' }, ...tiles.map((a) => h('div', { class: 'tile' },
          h('div', { class: 'tb' }, a.tile.badge), h('div', { class: 'tv' }, a.tile.value), h('div', { class: 'tl' }, `${a.tile.label} (was ${a.tile.was})`)))) : null,
        lines.length ? h('ul', { class: 'alert-lines' }, ...lines.map((a) => h('li', {}, h('span', { class: `kb kb-${a.kind}` }, a.kind === 'streak' ? 'trend' : a.kind), a.short || cap(a.text.replace(/^Game \d+: /, ''))))) : null);
    }).filter(Boolean);
    const matchLevel = g.alerts.filter((a) => !a.player);
    body.replaceChildren(
      cols.length ? h('div', { class: 'alert-cols' }, ...cols) : '',
      ...matchLevel.map((a) => h('div', { class: 'card pad match-alert' }, h('span', { class: 'kb' }, 'match'), a.text)));
  };
  paint();
}

// --- explore moves
function exploreTab({ match, P, names, color }, el) {
  const series = names.filter((n) => P[n]).map((n) => ({ key: n, label: P[n].short, color: color(n) }));
  const cols = match.patterns.move_columns;
  const moves = match.patterns.moves.map((r) => Object.fromEntries(cols.map((c, i) => [c, r[i]])));
  const AX = {
    spent: { label: 'time spent on the move', get: (m) => m.spent, scale: 'sqrt' },
    clock_before: { label: 'clock left before the move', get: (m) => m.clock_before, scale: 'sqrt' },
    move: { label: 'move number', get: (m) => Math.floor(m.ply / 2) + 1, scale: 'linear' },
  };
  const AY = {
    wp_loss: { label: 'winning chances lost', get: (m) => m.wp_loss },
    difficulty: { label: 'how hard (few good moves)', get: (m) => m.difficulty, max: 1 },
    spent_min: { label: 'minutes spent', get: (m) => (m.spent ?? 0) / 60 },
  };
  const QUESTIONS = [
    ['Do long thinks happen in hard positions?', 'spent', 'difficulty'],
    ['Does a low clock cost winning chances?', 'clock_before', 'wp_loss'],
    ['When in the game do they think longest?', 'move', 'spent_min'],
  ];
  const sel = (label, opts, val) => {
    const s = h('select', { 'aria-label': label }, ...opts.map(([v, t]) => { const o = h('option', { value: v }, t); if (v === val) o.selected = true; return o; }));
    return s;
  };
  const fx = sel('x axis', Object.entries(AX).map(([k, v]) => [k, v.label]), 'spent');
  const fy = sel('y axis', Object.entries(AY).map(([k, v]) => [k, v.label]), 'difficulty');
  const fp = sel('player', [['all', 'both players'], ...series.map((se) => [se.key, se.label])], 'all');
  const fph = sel('phase', [['all', 'all phases'], ...['opening', 'middlegame', 'endgame'].map((p) => [p, p])], 'all');
  const fg = sel('game', [['all', 'all games'], ...match.games.map((g) => [g.id, `Game ${roundOf(g)}`])], 'all');
  const fb = sel('book moves', [['no', 'hide book moves'], ['yes', 'include book moves']], 'no');
  const qBtns = QUESTIONS.map(([q, x, y]) => h('button', { class: 'pill', 'aria-pressed': 'false', onclick: () => { fx.value = x; fy.value = y; update(); } }, q));
  const mapEl = h('div', { class: 'chart' });
  const count = h('span', { class: 'muted small' });
  el.append(
    h('p', { class: 'ink2', style: 'margin:0 0 10px' }, 'Every move of the match as a dot. Start from a question, or set your own axes. Click a dot to open that position.'),
    h('div', { class: 'pills', style: 'margin-bottom:12px' }, ...qBtns),
    h('div', { class: 'card chart-card' },
      h('div', { class: 'filters' }, fp, fph, fg, fb, count),
      h('details', { class: 'axes' }, h('summary', {}, 'Custom axes'), h('div', { class: 'filters' }, 'x', fx, 'y', fy)),
      h('div', { class: 'legend', style: 'margin:6px 0' }, ...series.map((se) => h('span', {}, h('span', { class: 'dot', style: `background:${se.color}` }), ' ', se.label))),
      mapEl));
  let drawMap = () => {};
  function update() {
    const ax = AX[fx.value], ay = AY[fy.value];
    qBtns.forEach((b, i) => b.setAttribute('aria-pressed', String(QUESTIONS[i][1] === fx.value && QUESTIONS[i][2] === fy.value)));
    const pts = moves.filter((m) => (fp.value === 'all' || m.player === fp.value) && (fph.value === 'all' || m.phase === fph.value) && (fg.value === 'all' || m.game === fg.value) && (fb.value === 'yes' || !m.in_book) && ax.get(m) != null)
      .map((m) => ({
        x: ax.get(m), y: ay.get(m) ?? 0, color: color(m.player),
        html: `<b>${m.label}</b> · ${P[m.player]?.short || m.player}<br>${dur(m.spent)} spent · ${dur(m.clock_before)} left<br>winning chances lost ${m.wp_loss.toFixed(1)} · difficulty ${m.difficulty.toFixed(2)}${m.classification ? `<br>${m.classification}` : ''}`,
        onClick: () => (location.href = `game.html?id=${m.game}&ply=${m.ply + 1}`),
      }));
    count.textContent = `${pts.length} moves`;
    drawMap = scatter(mapEl, { points: pts, xLabel: ax.label, yLabel: ay.label, xScale: ax.scale, yMax: ay.max });
  }
  [fx, fy, fp, fph, fg, fb].forEach((e) => e.addEventListener('change', update));
  update();
  return () => drawMap();
}

// --- fans
function fansTab({ match, names, color, nm }, el) {
  const SRC = { youtube: ['YouTube', 'comments'], bluesky: ['Bluesky', 'posts'] };
  const crowdOf = (g) => (g.crowd?.favours ? { youtube: g.crowd } : g.crowd || {});
  const crowdGames = match.games.filter((g) => Object.keys(crowdOf(g)).length);
  if (!crowdGames.length) { el.append(kindTag('opinion'), h('p', { class: 'muted' }, 'No fan comments collected yet.')); return; }
  const bar = (c, unit) => {
    const picks = Object.entries(c.favours.keys).map(([k, name]) => ({ label: nm(name), v: c.favours.counts[k], bg: color(name) }));
    const total = picks.reduce((t, x) => t + x.v, 0);
    return [total ? h('div', { class: 'stack', style: `margin:0${total < 10 ? ';opacity:.45' : ''}`, title: total < 10 ? 'Fewer than 10 pick a side: too few to read much into' : null }, ...picks.filter((x) => x.v).map((x) => h('div', { style: `flex:${x.v};background:${x.bg}`, title: `${x.label}: ${x.v} of ${total} (${Math.round((100 * x.v) / total)}%)` }, `${Math.round((100 * x.v) / total)}%`)))
      : h('span', { class: 'muted' }, 'nobody picked a side'),
    h('span', { class: 'muted', style: 'font-size:12.5px' }, `${total} of ${c.comments} ${unit} pick a side`)];
  };
  el.append(kindTag('opinion'), h('div', { class: 'card crowd opinion', style: 'margin-top:10px' },
    h('h3', {}, 'Who fans back, game by game'),
    h('div', { class: 'crowd-rows' }, ...crowdGames.flatMap((g) => Object.entries(SRC).filter(([k]) => crowdOf(g)[k]).map(([k, [label, unit]], i) =>
      h('div', { class: 'crowd-row' },
        i === 0 ? h('a', { href: `game.html?id=${g.id}#crowd`, style: 'font-weight:600;text-decoration:none' }, `Game ${roundOf(g)}`) : h('span'),
        h('span', { class: 'muted', style: 'font-size:12.5px' }, label),
        ...bar(crowdOf(g)[k], unit))))),
    h('div', { class: 'stack-legend', style: 'margin-top:6px' }, ...names.map((n) => h('span', {}, h('span', { class: 'dot', style: `background:${color(n)}` }), ` backs ${nm(n)}`))),
    h('p', { class: 'note' }, 'Among YouTube comments and Bluesky posts that say who will or should win the match. Most don’t pick a side, and each audience leans its own way, so read this as mood, not a forecast. Faded bars rest on fewer than 10 opinions.')));
}

main().catch((e) => { $('#app').innerHTML = `<div class="loading">Could not load match data: ${e.message}</div>`; console.error(e); });
