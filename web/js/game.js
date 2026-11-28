import { Chessground } from '../vendor/chessground/chessground.min.js';
import { $, h, getJSON, dur, clock, evalText, shortName, themeToggle, SYM } from './common.js';
import { Timeline, evalChart, timeChart, clockChart } from './charts.js';

themeToggle($('#theme'));
const params = new URLSearchParams(location.search);
const id = params.get('id') || 'game-01';

const BRUSHES = {
  best: { key: 'best', color: '#1baf7a', opacity: 0.85, lineWidth: 10 },
  played: { key: 'played', color: '#2a78d6', opacity: 0.8, lineWidth: 10 },
  green: { key: 'g', color: '#15781B', opacity: 1, lineWidth: 10 },
  red: { key: 'r', color: '#882020', opacity: 1, lineWidth: 10 },
  blue: { key: 'b', color: '#003088', opacity: 1, lineWidth: 10 },
  yellow: { key: 'y', color: '#e68f00', opacity: 1, lineWidth: 10 },
  paleBlue: { key: 'pb', color: '#003088', opacity: 0.4, lineWidth: 15 },
  paleGreen: { key: 'pg', color: '#15781B', opacity: 0.4, lineWidth: 15 },
  paleRed: { key: 'pr', color: '#882020', opacity: 0.4, lineWidth: 15 },
  paleGrey: { key: 'pgr', color: '#4a4a4a', opacity: 0.35, lineWidth: 15 },
};
const arrow = (uci, brush) => ({ orig: uci.slice(0, 2), dest: uci.slice(2, 4), brush });
const lastMove = (uci) => [uci.slice(0, 2), uci.slice(2, 4)];

async function main() {
  const [game, match] = await Promise.all([getJSON(`data/games/${id}.json`), getJSON('data/match.json').catch(() => null)]);
  if (match) $('#match-name').textContent = match.short_name;
  $('#engine-note').textContent = `${game.engine.name}, depth ${game.engine.depth}, ${game.engine.multipv} lines per position`;
  render(game);
}

function render(game) {
  const N = game.moves.length;
  const W = game.players.white, B = game.players.black;
  const wn = shortName(W), bn = shortName(B);
  const base = game.time_control.periods[0].seconds;
  const evals = [game.moves[0].eval_before, ...game.moves.map((m) => m.eval_after)];
  const summ = game.summary;
  const roundNo = game.round?.split('.')[0];
  document.title = `${wn} vs ${bn}, Game ${roundNo} · The Long Think`;
  const resultText = { '1-0': `${wn} won`, '0-1': `${bn} won`, '1/2-1/2': 'Draw', '*': 'In progress' }[game.result] || game.result;
  const resShort = { '1-0': '1–0', '0-1': '0–1', '1/2-1/2': '½–½', '*': 'live' }[game.result] || game.result;
  const moves = Math.ceil(N / 2);
  const name = (side) => shortName(game.players[side]);
  const dotEl = (side, extra = '') => h('span', { class: 'dot', style: `background:var(--p${game.players[side].slot});${extra}` });

  // lowest clock before the move-40 time bonus
  let low = null;
  for (const m of game.moves) if (m.move_number <= 39 && m.clock.remaining != null && (!low || m.clock.remaining < low.clock.remaining)) low = m;

  // ---------- header ----------
  const nov = summ.novelty;
  const app = $('#app');
  app.innerHTML = '';
  app.append(
    h('section', { class: 'hero game-hero' },
      h('div', {},
        h('div', { class: 'eyebrow' }, `Game ${roundNo} · ${fmtDate(game.date)} · ${(game.opening_name || game.eco || '').replace(/^Ruy Lopez: /, '')}`),
        h('h1', {}, game.gist?.headline || `${wn} vs ${bn}`),
        h('p', { class: 'who' }, dotEl('white'), ` ${wn} (White) `, h('span', { class: 'muted' }, 'vs'), ' ', dotEl('black'), ` ${bn} (Black) · ${resultText} in ${moves} moves`),
        h('p', {}, game.gist?.source === 'claude' ? game.gist.summary : storyLine(game, wn, bn))),
      h('div', { class: 'mini-stats' },
        stat('Result', resShort, `in ${moves} moves`),
        stat('Prep ended', nov ? nov.label : '—', nov ? `by ${name(nov.side)}` : 'book data unavailable'),
        stat('Lowest clock', low ? dur(low.clock.remaining) : '—', low ? `${name(low.side)}, move ${low.move_number}` : '', low && low.clock.remaining < 300 ? 'warn' : ''),
        stat('Accuracy', `${summ.players.white.accuracy ?? '—'} · ${summ.players.black.accuracy ?? '—'}`, `${wn} · ${bn}`)),
    ),
  );

  // ---------- story mode: board + key moments ----------
  const boardEl = h('div', { class: 'board-wrap' });
  const topLine = h('div', { class: 'players-line' });
  const botLine = h('div', { class: 'players-line bottom' });
  const moveLine = h('div', { class: 'move-line' });
  const movesEl = h('div', { class: 'moves' });
  let orientation = 'white';
  let showEngine = true;
  const engineBtn = h('button', { class: 'btn', 'aria-pressed': 'true', title: 'Show the engine’s top move from this position' }, 'Engine arrow');
  const controls = h('div', { class: 'controls' },
    h('button', { class: 'btn icon-btn', title: 'Start (Home)', 'aria-label': 'Start', onclick: () => go(0) }, '⏮'),
    h('button', { class: 'btn icon-btn', title: 'Previous move (←)', 'aria-label': 'Previous move', onclick: () => go(cur - 1) }, '◀'),
    h('button', { class: 'btn icon-btn', title: 'Next move (→)', 'aria-label': 'Next move', onclick: () => go(cur + 1) }, '▶'),
    h('button', { class: 'btn icon-btn', title: 'End (End)', 'aria-label': 'End', onclick: () => go(N) }, '⏭'),
    h('button', { class: 'btn', title: 'Flip board (f)', onclick: () => { orientation = orientation === 'white' ? 'black' : 'white'; cg.set({ orientation }); paintClocks(); } }, 'Flip'),
    engineBtn,
  );
  engineBtn.addEventListener('click', () => { showEngine = !showEngine; engineBtn.setAttribute('aria-pressed', String(showEngine)); go(cur); });

  const panel = h('div', { class: 'moment-panel', 'aria-live': 'polite' });
  const momentNav = h('div', { class: 'moment-nav' });
  const movesBox = h('details', { class: 'fold moves-fold' }, h('summary', {}, 'Move list'), movesEl);
  if (innerWidth > 960) movesBox.open = true;

  app.append(h('section', { class: 'card story-mode' },
    h('div', { class: 'story-board' }, topLine, boardEl, botLine, controls, moveLine),
    h('div', { class: 'story-text' }, panel, momentNav, movesBox)));

  // ---------- whole game timeline ----------
  const evalEl = h('div', { class: 'chart' });
  const timeEl = h('div', { class: 'chart' });
  const clockEl = h('div', { class: 'chart', hidden: true });
  const legendP = (side) => h('span', {}, dotEl(side), ` ${name(side)}`);
  const viewBtns = [['time', 'Time per move'], ['clock', 'Clocks']].map(([k, t]) => h('button', { class: 'pill', 'aria-pressed': String(k === 'time'), onclick: () => {
    timeEl.hidden = k !== 'time'; clockEl.hidden = k !== 'clock';
    viewBtns.forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.k === k)));
    tl.render();
  } }, t));
  viewBtns.forEach((b, i) => { b.dataset.k = i ? 'clock' : 'time'; });
  app.append(h('section', { class: 'card chart-card whole-game' },
    h('div', { class: 'chart-head' }, h('h2', {}, 'The whole game'),
      h('div', { class: 'legend' },
        h('span', {}, h('span', { class: 'num', style: 'width:18px;height:18px;font-size:11px;margin-right:4px' }, '1'), 'key moment'),
        h('span', {}, h('span', { class: 'dot', style: 'background:var(--critical)' }), ' mistake'),
        h('span', {}, h('span', { style: 'display:inline-block;width:14px;height:10px;background:var(--book);border:1px solid var(--rule);vertical-align:-1px' }), ' known theory'))),
    h('div', { class: 'sub-head' }, 'Who was better'),
    evalEl,
    h('div', { class: 'sub-head row' }, h('span', {}, 'Thinking'), h('div', { class: 'pills' }, ...viewBtns), h('div', { class: 'legend' }, legendP('white'), legendP('black'))),
    timeEl, clockEl,
    h('p', { class: 'note' }, `Top: the engine’s view on a winning-chances scale. Bottom: minutes spent per move (solid bars are long thinks), or each clock. Click anywhere to jump the board there. Time control: ${game.time_control.description}.`)));

  // ---------- folded sections ----------
  const tableWrap = h('div', { class: 'scroll-x' });
  app.append(h('section', { class: 'folds' },
    game.gist?.sections?.length ? h('details', { class: 'fold' }, h('summary', {}, 'Read the full game summary'), h('div', { id: 'gist' })) : null,
    h('details', { class: 'fold' }, h('summary', {}, 'Patterns: reactions to surprises, prep payoff, missed chances'), h('div', { class: 'events', id: 'events' })),
    h('details', { class: 'fold opinion', id: 'crowd-fold' }, h('summary', {}, 'What fans said ', h('span', { class: 'kind kind-opinion' }, 'OPINION')), h('div', { id: 'crowd' })),
    h('details', { class: 'fold' }, h('summary', {}, 'Every move with clocks and engine numbers'), tableWrap)));

  // ---------- board ----------
  const cg = Chessground(boardEl, {
    fen: game.moves[0].fen_before, orientation, viewOnly: true, coordinates: true,
    animation: { enabled: true, duration: 160 },
    drawable: { enabled: false, visible: true, brushes: BRUSHES },
  });

  // ---------- timeline ----------
  let cur = 0;
  let momentIdx = null;
  const tl = new Timeline(N, { onSelect: (i) => go(i) });
  const mv = (i) => (i > 0 ? game.moves[i - 1] : null);
  tl.add(evalEl, evalChart(game, evals, { onCritical: (ply) => showMoment(game.critical_moments.findIndex((c) => c.ply === ply)) }), (i) => {
    const m = mv(i);
    return m ? `<b>${m.label}</b> · ${evalText(m.eval_after)}${m.classification ? ` · ${m.classification}` : ''}` : `Start · ${evalText(evals[0])}`;
  });
  tl.add(timeEl, timeChart(game, { whiteName: wn, blackName: bn }), (i) => {
    const m = mv(i);
    return m ? `<b>${m.label}</b> · ${name(m.side)} thought ${dur(m.clock.spent)}${m.clock.adjustment ? ` · clock +${dur(m.clock.adjustment)}` : ''}` : null;
  });
  tl.add(clockEl, clockChart(game, { whiteName: wn, blackName: bn }), (i) => {
    const c = clocksAt(i);
    return `<b>${i ? mv(i).label : 'Start'}</b> · ${wn} ${clock(c.white)} · ${bn} ${clock(c.black)}`;
  });
  tl.render();
  let rt;
  addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(() => tl.render(), 120); });

  function clocksAt(i) {
    const c = { white: base, black: base };
    for (let k = 0; k < i; k++) { const m = game.moves[k]; if (m.clock.remaining != null) c[m.side] = m.clock.remaining; }
    return c;
  }
  function paintClocks() {
    const c = clocksAt(cur);
    const toMove = cur % 2 === 0 ? 'white' : 'black';
    const line = (side) => [
      h('span', {}, dotEl(side), ` ${name(side)}`, h('span', { class: 'muted' }, ` ${game.players[side].elo || ''}`)),
      h('span', { class: 'clock', style: toMove === side && cur < N ? 'outline:1.5px solid var(--ink)' : '' }, clock(c[side])),
    ];
    const topSide = orientation === 'white' ? 'black' : 'white';
    topLine.replaceChildren(...line(topSide));
    botLine.replaceChildren(...line(topSide === 'white' ? 'black' : 'white'));
  }

  // ---------- move list ----------
  const btns = [];
  for (let n = 0; n < Math.ceil(N / 2); n++) {
    movesEl.append(h('span', { class: 'n' }, `${n + 1}.`));
    for (const k of [2 * n, 2 * n + 1]) {
      const m = game.moves[k];
      if (!m) { movesEl.append(h('span')); continue; }
      const b = h('button', { class: [m.in_book ? 'book' : '', m.tags.includes('critical') ? 'crit' : ''].join(' '), title: m.in_book ? 'Known theory (masters database)' : '', onclick: () => go(k + 1) },
        h('span', {}, m.san, m.classification ? h('span', { class: `sym ${m.classification}` }, SYM[m.classification]) : null),
        h('span', { class: 't' }, m.clock.spent != null ? dur(m.clock.spent).replace(/ 00s$/, '') : '±'));
      btns[k + 1] = b;
      movesEl.append(b);
    }
  }

  // ---------- current move (one line under the board) ----------
  function paintMoveLine() {
    const m = mv(cur);
    if (!m) { put(moveLine, h('span', { class: 'muted' }, 'Start position · use ← → or the charts to step through')); return; }
    const best = m.top_lines[0];
    put(moveLine, 
      h('b', {}, m.label), h('span', { class: 'muted' }, ` · ${name(m.side)} · thought ${m.clock.spent != null ? dur(m.clock.spent) : '?'} · ${evalText(m.eval_before)} → ${evalText(m.eval_after)}`),
      best && m.played_rank !== 1 ? h('span', { class: 'muted' }, ` · engine preferred ${best.san}`) : null,
      m.classification ? h('span', { class: `tag ${m.classification}`, style: 'margin-left:6px' }, m.classification) : null);
  }

  // ---------- key moments ----------
  const CM = game.critical_moments;
  function showMoment(k) {
    if (k == null || k < 0 || !CM.length) return;
    momentIdx = ((k % CM.length) + CM.length) % CM.length;
    const c = CM[momentIdx];
    go(c.ply, momentIdx);
  }
  function paintPanel() {
    if (!CM.length) { put(panel, h('p', { class: 'muted' }, 'No key moments detected in this game.')); put(momentNav, ); return; }
    const k = momentIdx ?? 0;
    const c = CM[k], m = game.moves[c.ply], n = c.narrative;
    const sentences = (n.text || '').split(/(?<=[.!?])\s+(?=[A-Z])/);
    const shortText = sentences.slice(0, 2).join(' ').trim();
    const rest = sentences.slice(2).join(' ').trim();
    const spent = m.clock.spent ?? 0;
    const viewing = momentIdx != null && cur === c.ply;
    put(panel, 
      h('div', { class: 'moment-head' },
        h('span', { class: 'eyebrow' }, `Key moment ${k + 1} of ${CM.length} · ${name(m.side)}`),
        h('div', { class: 'dots' }, ...CM.map((_, j) => h('button', { class: 'mdot', 'aria-label': `Key moment ${j + 1}`, 'aria-pressed': String(j === k && viewing), onclick: () => showMoment(j) }, `${j + 1}`)))),
      h('h2', {}, n.headline),
      h('p', { class: 'lede' }, ...withMoves(shortText, game, (ply) => go(ply + 1))),
      h('div', { class: 'chips' },
        chip('Thought', dur(m.clock.spent)), chip('Clock left', dur(m.clock.remaining)),
        chip('Engine', `${evalText(m.eval_before)} → ${evalText(m.eval_after)}`),
        chip('Good moves', `${m.difficulty.good_moves}${m.difficulty.only_move ? ' (only move)' : ''}`)),
      (rest || n.likely_reasons?.length) ? h('details', { class: 'why' },
        h('summary', {}, spent >= 120 ? `Why it took ${dur(spent)}` : 'Why it was so quick'),
        rest ? h('p', {}, ...withMoves(rest, game, (ply) => go(ply + 1))) : null,
        n.likely_reasons?.length ? h('ul', {}, ...n.likely_reasons.map((r) => h('li', {}, r.reason))) : null) : null,
      viewing ? h('div', { class: 'legend-arrows' }, h('span', {}, h('i', { style: 'background:#2a78d6' }), `played: ${m.san}`),
        m.top_lines[0] && m.top_lines[0].uci !== m.uci ? h('span', {}, h('i', { style: 'background:#1baf7a' }), `engine’s choice: ${m.top_lines[0].san}`) : h('span', {}, 'the engine agreed'))
        : h('button', { class: 'link-btn', onclick: () => showMoment(k) }, 'Show this moment on the board'),
      h('details', { class: 'facts' },
        h('summary', {}, n.source === 'claude' ? `Written by ${n.model} from these facts · show facts` : 'Written from a template using these facts · show facts'),
        h('pre', {}, JSON.stringify({ facts: c.facts, score: c.score }, null, 2))));
    put(momentNav, 
      h('button', { class: 'btn big-btn', onclick: () => showMoment((momentIdx ?? 0) - 1) }, '◀ Previous'),
      h('button', { class: 'btn big-btn primary', onclick: () => showMoment(momentIdx == null ? 0 : momentIdx + 1) }, momentIdx == null ? 'Start the key moments ▶' : 'Next moment ▶'));
  }

  function go(i, moment = null) {
    cur = Math.max(0, Math.min(N, i));
    const m = mv(cur);
    const next = game.moves[cur];
    cg.set({
      fen: m ? m.fen_after : game.moves[0].fen_before,
      lastMove: m ? lastMove(m.uci) : undefined,
      check: m ? /[+#]$/.test(m.san) : false,
      turnColor: cur % 2 === 0 ? 'white' : 'black',
    });
    if (moment != null) {
      // key moment: position before the move, with the move played and the engine's choice
      const shapes = [arrow(next.uci, 'played')];
      if (next.top_lines[0] && next.top_lines[0].uci !== next.uci) shapes.push(arrow(next.top_lines[0].uci, 'best'));
      cg.setAutoShapes(shapes);
    } else {
      cg.setAutoShapes(showEngine && next?.top_lines?.[0] ? [arrow(next.top_lines[0].uci, 'best')] : []);
    }
    btns.forEach((b) => b && b.classList.remove('on'));
    if (btns[cur]) { btns[cur].classList.add('on'); if (movesBox.open) btns[cur].scrollIntoView({ block: 'nearest' }); }
    tl.setCursor(cur);
    paintClocks();
    paintMoveLine();
    paintPanel();
    const u = new URL(location); u.searchParams.set('ply', cur); history.replaceState(null, '', u);
  }

  addEventListener('keydown', (e) => {
    if (e.target.closest('input,select,textarea')) return;
    if (e.key === 'ArrowRight') { go(cur + 1); e.preventDefault(); }
    if (e.key === 'ArrowLeft') { go(cur - 1); e.preventDefault(); }
    if (e.key === 'Home') go(0);
    if (e.key === 'End') go(N);
    if (e.key === 'f') { orientation = orientation === 'white' ? 'black' : 'white'; cg.set({ orientation }); paintClocks(); }
  });

  // ---------- data table ----------
  tableWrap.append(h('table', { class: 'data-table' },
    h('thead', {}, h('tr', {}, ...['Move', 'Player', 'Spent', 'Clock', 'Eval', 'Engine best', 'Win% lost'].map((t) => h('th', {}, t)))),
    h('tbody', {}, ...game.moves.map((m) => h('tr', {},
      h('td', {}, m.label), h('td', {}, name(m.side)), h('td', {}, dur(m.clock.spent)), h('td', {}, clock(m.clock.remaining)),
      h('td', {}, evalText(m.eval_after)), h('td', {}, m.top_lines[0]?.san || '—'), h('td', {}, m.wp_loss.toFixed(1))))),
  ));

  const toBoard = (ply) => { go(ply + 1); $('.story-mode')?.scrollIntoView({ behavior: 'smooth', block: 'start' }); };
  renderEvents(game, $('#events'), toBoard);
  if ($('#gist')) renderGist(game, $('#gist'), toBoard);
  renderCrowd(game, $('#crowd'), toBoard);
  if (!$('#crowd').childElementCount) $('#crowd-fold').remove();
  if (location.hash === '#crowd' && $('#crowd-fold')) { $('#crowd-fold').open = true; $('#crowd-fold').scrollIntoView(); }

  const startPly = parseInt(params.get('ply') ?? '', 10);
  if (Number.isFinite(startPly)) go(startPly);
  else if (CM.length) showMoment(0);
  else go(0);
}

// replaceChildren() turns null into the text "null"; drop empty parts first
function put(el, ...kids) { el.replaceChildren(...kids.filter((k) => k != null && k !== false)); }

function fmtDate(d) {
  if (!d) return '';
  const [y, m, day] = d.split('.').map(Number);
  return new Date(Date.UTC(y, m - 1, day)).toLocaleDateString('en-GB', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' });
}

function renderEvents(game, el, jump) {
  const ev = game.summary.events;
  if (!ev) return;
  const name = (side) => shortName(game.players[side]);
  const mv = (ply, label) => h('button', { class: 'mv', onclick: () => jump(ply) }, label);
  const gap = (g) => `${dur(Math.abs(g))} ${g >= 0 ? 'ahead' : 'behind'}`;
  const pawns = (v) => (v == null ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(2)}`);

  // 1. reactions
  const rx = h('div', { class: 'card event-card' }, h('div', { class: 'eyebrow' }, 'Reaction time'), h('h3', {}, 'Answering a surprise'));
  if (!ev.reactions.length) rx.append(h('p', { class: 'lead' }, 'No novelty or classified error to react to in this game.'));
  else rx.append(h('ul', {}, ...ev.reactions.map((r) => {
    const kind = r.trigger_kinds.includes('novelty') ? `${name(r.trigger_side)}’s novelty` : `${name(r.trigger_side)}’s ${r.trigger_kinds[0]}`;
    return h('li', {},
      h('div', { class: 'big' }, r.spent != null ? dur(r.spent) : '—', r.ratio != null ? h('span', { class: 'muted', style: 'font-size:14px;font-family:var(--sans)' }, `  ${r.ratio}× usual`) : null),
      h('div', {}, 'After ', mv(r.trigger_ply, r.trigger_label), ` (${kind}), ${name(r.response_side)} answered with `, mv(r.response_ply, r.response_label),
        `. Usual think in this game: ${dur(r.usual)}.`));
  })));

  // 2. prep payoff
  const pp = ev.prep_payoff;
  const pc = h('div', { class: 'card event-card' }, h('div', { class: 'eyebrow' }, 'Opening preparation'), h('h3', {}, 'Did the prep pay off?'));
  if (!pp) pc.append(h('p', { class: 'lead' }, 'The game never left the masters database (or book data is unavailable).'));
  else {
    const me = pp.player_side, other = me === 'white' ? 'black' : 'white';
    const ch = pp.win_chance_change;
    const verdict = Math.abs(ch) < 3 ? 'The position barely moved' : ch > 0 ? `${name(me)}’s winning chances rose ${ch.toFixed(0)} pts` : `${name(me)}’s winning chances fell ${Math.abs(ch).toFixed(0)} pts`;
    const clockMove = pp.clock_gap_after - pp.clock_gap_before;
    pc.append(
      h('p', { class: 'lead' }, `${name(me)} left theory with `, mv(pp.novelty_ply, pp.novelty_label), `. Compared with `, mv(pp.end_ply, pp.end_label),
        `, ${pp.moves_measured} moves later${pp.truncated ? ' (the game ended)' : ''}, from ${name(me)}’s side:`),
      h('table', { class: 'cmp' },
        h('thead', {}, h('tr', {}, h('th', {}, ''), h('th', {}, 'At novelty'), h('th', {}, `+${pp.moves_measured} moves`))),
        h('tbody', {},
          h('tr', {}, h('td', {}, 'Engine eval'), h('td', {}, pawns(pp.eval_before)), h('td', {}, pawns(pp.eval_after))),
          h('tr', {}, h('td', {}, 'Winning chances'), h('td', {}, `${pp.win_chance_before}%`), h('td', {}, `${pp.win_chance_after}%`)),
          h('tr', {}, h('td', {}, `${name(me)} clock`), h('td', {}, clock(pp.clock_before[me])), h('td', {}, clock(pp.clock_after[me]))),
          h('tr', {}, h('td', {}, `${name(other)} clock`), h('td', {}, clock(pp.clock_before[other])), h('td', {}, clock(pp.clock_after[other]))),
          h('tr', {}, h('td', {}, 'Clock gap'), h('td', {}, gap(pp.clock_gap_before)), h('td', {}, gap(pp.clock_gap_after))))),
      h('p', { class: 'lead' }, `${verdict}. On the clock, ${name(me)} ${clockMove >= 0 ? 'gained' : 'lost'} ${dur(Math.abs(clockMove))} relative to ${name(other)}.`));
  }

  // 3. missed chances
  const mc = h('div', { class: 'card event-card' }, h('div', { class: 'eyebrow' }, 'Missed chances'), h('h3', {}, 'Errors that went unpunished'));
  const th = ev.params || {};
  if (!ev.missed_chances.length) mc.append(h('p', { class: 'lead' }, `None. No error handed over ${th.missed_chance_min_gift ?? 10}+ winning-chance points and then got ${Math.round((th.missed_chance_give_back ?? 0.5) * 100)}% of it straight back.`));
  else mc.append(h('ul', {}, ...ev.missed_chances.map((m) => h('li', {},
    h('div', { class: 'big' }, `${m.gift.toFixed(0)} → ${m.given_back.toFixed(0)} pts`),
    h('div', {}, mv(m.error_ply, m.error_label), ` (${name(m.error_side)}) handed over ${m.gift.toFixed(0)} winning-chance points; `, mv(m.reply_ply, m.reply_label),
      ` gave back ${m.given_back.toFixed(0)}. The engine’s reply was ${m.best_reply ?? '—'}${m.best_reply_eval != null ? ` (${pawns(m.best_reply_eval)})` : ''}.`)))));

  el.append(rx, pc, mc);
}

// Turn move labels in text ("21.c3", "29...gxf4") into buttons that load the move on the board.
function withMoves(text, game, jump) {
  const plyOf = new Map(game.moves.map((m) => [m.label.replace(/[+#]$/, ''), m.ply]));
  const out = [];
  let last = 0;
  for (const mt of text.matchAll(/\b\d+\.(?:\.\.)?[KQRBNa-hO][\w=+#-]*/g)) {
    const lbl = mt[0].replace(/[+#]$/, '');
    if (!plyOf.has(lbl)) continue;
    out.push(text.slice(last, mt.index), h('button', { class: 'mv', onclick: () => jump(plyOf.get(lbl)) }, mt[0]));
    last = mt.index + mt[0].length;
  }
  out.push(text.slice(last));
  return out;
}

function renderGist(game, el, jump) {
  const g = game.gist;
  if (!g || !g.sections?.length) return;
  el.append(h('div', { class: 'gist' },
    h('div', { class: 'gist-sections' }, ...g.sections.map((x) => h('div', {}, h('h3', {}, x.title), h('p', {}, ...withMoves(x.text, game, jump))))),
    g.takeaways?.length ? h('div', { class: 'reasons' }, h('div', { class: 'eyebrow' }, 'Worth remembering'),
      h('ul', {}, ...g.takeaways.map((t) => h('li', {}, ...withMoves(t.point, game, jump))))) : null,
    h('details', {},
      h('summary', {}, g.source === 'claude' ? `Written by ${g.model} from these facts; every move it names is checked against them · show facts` : 'Written from a template using these facts · show facts'),
      h('pre', {}, JSON.stringify(g.facts, null, 2)))));
}

const SOURCES = {
  youtube: { name: 'YouTube', unit: 'comments', q: 'Who do commenters think will win the match?' },
  bluesky: { name: 'Bluesky', unit: 'posts', q: 'Who do Bluesky posters think will win the match?' },
};

function crowdSources(crowd) {
  if (!crowd) return [];
  const bySrc = crowd.source ? { [crowd.source]: crowd } : crowd;          // older files: one YouTube object
  return Object.keys(SOURCES).filter((k) => bySrc[k]?.comments_labelled).map((k) => [k, bySrc[k]]);
}

function renderCrowd(game, el, jump) {
  const list = crowdSources(game.crowd);
  if (!list.length) return;
  for (const [src, c] of list) el.append(crowdCard(game, src, c, jump));
}

function fmtWindow(w) {
  const o = { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'UTC' };
  return `${new Date(w[0]).toLocaleString('en-GB', o)} – ${new Date(w[1]).toLocaleString('en-GB', o)} UTC`;
}

function crowdCard(game, src, c, jump) {
  const S = SOURCES[src];
  const keys = c.favours.keys;               // {gukesh: 'Gukesh D', ...}
  const slotOf = (name) => (game.players.white.name === name ? game.players.white.slot : game.players.black.slot);
  const shortOf = (name) => shortName(game.players.white.name === name ? game.players.white : game.players.black);
  const n = c.comments_labelled;
  const pct = (x) => Math.round((100 * x) / n);
  const picks = Object.entries(keys).map(([k, name]) => ({ label: shortOf(name), v: c.favours.counts[k], bg: `var(--p${slotOf(name)})` }));
  const total = picks.reduce((t, x) => t + x.v, 0);
  const share = (v) => (total ? Math.round((100 * v) / total) : 0);
  const stack = total
    ? h('div', { class: 'stack', role: 'img', 'aria-label': picks.map((x) => `${x.label} ${share(x.v)}%`).join(', ') },
      ...picks.filter((x) => x.v).map((x) => h('div', { style: `flex:${x.v};background:${x.bg}`, title: `${x.label}: ${x.v} of ${total} ${S.unit}` }, share(x.v) >= 8 ? `${share(x.v)}%` : '')))
    : h('p', { class: 'ink2' }, 'No comment picked a side.');
  const legend = h('div', { class: 'stack-legend' }, ...picks.map((x) => h('span', {}, h('span', { class: 'dot', style: `background:${x.bg}` }), ` backs ${x.label}: ${x.v}`)),
    h('span', {}, `${total} of ${n} ${S.unit} (${pct(total)}%) pick a side`));
  const tone = h('div', {}, h('div', { class: 'sub' }, 'Tone toward each player'),
    ...Object.entries(keys).map(([k, name]) => h('div', { style: 'font-size:14px;margin:4px 0' },
      h('span', { class: 'dot', style: `background:var(--p${slotOf(name)})` }), ` ${shortOf(name)}: `,
      h('b', {}, `${c.tone[k].positive}`), ' positive · ', h('b', {}, `${c.tone[k].negative}`), ' negative')),
    h('div', { style: 'font-size:14px;margin-top:8px' }, 'The game felt ', h('b', {}, 'exciting'), ` to ${c.game_feel.exciting}, `, h('b', {}, 'boring'), ` to ${c.game_feel.boring}`));
  const movesBox = h('div', { style: 'grid-column:1 / -1' }, h('div', { class: 'sub' }, 'Moves people talked about · engine vs crowd'));
  if (!c.moves.length) movesBox.append(h('p', { class: 'ink2', style: 'margin:0;font-size:14px' }, `No move got ${c.min_mentions}+ opinions.`));
  else movesBox.append(h('table', { class: 'cmp', style: 'max-width:none' },
    h('thead', {}, h('tr', {}, ...['Move', 'Praise · criticism', 'Crowd says', 'Engine says', 'Agree?'].map((t) => h('th', {}, t)))),
    h('tbody', {}, ...c.moves.slice(0, 8).map((m) => h('tr', {},
      h('td', {}, h('button', { class: 'mv', onclick: () => jump(m.ply) }, m.label), m.ambiguous ? h('span', { class: 'muted', title: 'This move was played more than once; matched to the first time' }, ' *') : null),
      h('td', {}, `${m.praise} · ${m.criticism}`), h('td', {}, m.crowd), h('td', {}, m.engine),
      h('td', {}, m.agrees == null ? '–' : h('span', { class: m.agrees ? 'agree-yes' : 'agree-no' }, m.agrees ? 'yes' : 'no')))))));
  const where = src === 'youtube'
    ? h('div', {}, h('div', { class: 'sub' }, `Videos read (${c.videos.length})`),
      h('ul', { class: 'videos' }, ...c.videos.map((v) => h('li', {}, h('a', { href: v.url, target: '_blank', rel: 'noopener' }, v.title), h('span', { class: 'muted' }, ` · ${v.channel} · ${v.comments_read} comments`)))))
    : h('div', {}, h('div', { class: 'sub' }, 'Posts read'),
      h('div', { style: 'font-size:14px;line-height:1.5' },
        'Every public post containing ', h('b', {}, c.query.split(' OR ').join(' or ')), ', written ', fmtWindow(c.window), ' (this game’s start until the next game). ',
        `${c.posts_found} found; ${n} kept after dropping repeats and posts under three words.`,
        c.window_closed ? '' : ' The window is still open, so more posts will be added.',
        c.truncated ? ' Some very busy minutes hit the search limit, so a few posts may be missing.' : ''));
  const note = src === 'youtube'
    ? `${n} public comments from the videos above, labelled by ${c.model || 'Claude'}. Only counts are published; usernames and comment text are not stored on this site. Fetched ${new Date(c.fetched_at).toLocaleDateString()}.`
    : `${n} public Bluesky posts, labelled by ${c.model || 'Claude'}. Posts in this window can also be about the match in general or earlier games. Only counts are published; handles and post text are not stored on this site. Fetched ${new Date(c.fetched_at).toLocaleDateString()}.`;
  return h('div', { class: 'card crowd', style: 'margin-bottom:14px' },
    h('div', { class: 'eyebrow' }, `Crowd mood · ${S.name}`),
    h('h3', {}, S.q),
    stack, legend,
    h('div', { class: 'crowd-grid' }, tone, where, movesBox),
    h('p', { class: 'note' }, note));
}

function stat(label, value, sub, cls = '') {
  return h('div', { class: `card stat ${cls}` }, h('div', { class: 'eyebrow' }, label), h('div', { class: 'v' }, value), h('div', { class: 's' }, sub));
}
function chip(k, v) { return h('span', { class: 'chip' }, k, ' ', h('b', {}, v)); }

function storyLine(game, wn, bn) {
  const s = game.summary;
  const bits = [];
  if (s.novelty) {
    const who = shortName(game.players[s.novelty.side]);
    const used = s.players[s.novelty.side].time_before_novelty;
    const other = s.novelty.side === 'white' ? 'black' : 'white';
    bits.push(`Theory ran out at ${s.novelty.label}, played by ${who} after using ${dur(used)} (${shortName(game.players[other])} had used ${dur(s.players[other].time_before_novelty)}).`);
  }
  const tt = ['white', 'black'].filter((x) => s.players[x].time_trouble_moves > 0);
  for (const x of tt) bits.push(`${shortName(game.players[x])} played ${s.players[x].time_trouble_moves} ${s.players[x].time_trouble_moves === 1 ? 'move' : 'moves'} before move 40 with under 5 minutes left.`);
  return bits.join(' ');
}

main().catch((e) => { $('#app').innerHTML = `<div class="loading">Could not load this game: ${e.message}</div>`; console.error(e); });
