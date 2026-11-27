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
  document.title = `${wn} vs ${bn}, ${game.id.replace('game-0', 'Game ').replace('game-', 'Game ')} · The Long Think`;
  const resultText = { '1-0': `${wn} won`, '0-1': `${bn} won`, '1/2-1/2': 'Draw', '*': 'In progress' }[game.result] || game.result;

  // ---------- header ----------
  const nov = summ.novelty;
  const lt = summ.longest_think;
  const ltMove = lt ? game.moves[lt.ply] : null;
  const app = $('#app');
  app.innerHTML = '';
  app.append(
    h('section', { class: 'hero' },
      h('div', { class: 'eyebrow' }, `Round ${game.round?.split('.')[0]} · ${game.date?.replaceAll('.', '-')} · ${game.eco || ''} ${game.opening_name || ''}`),
      h('h1', {}, h('span', { class: 'dot', style: `background:var(--p${W.slot});width:14px;height:14px;margin-right:10px` }), `${wn} `, h('span', { class: 'muted' }, 'vs'), ` ${bn}`,
        h('span', { class: 'dot', style: `background:var(--p${B.slot});width:14px;height:14px;margin-left:10px` })),
      h('p', {}, `${resultText} in ${Math.ceil(N / 2)} moves. ${wn} had White. ${game.gist?.source === 'claude' ? game.gist.summary : storyLine(game, wn, bn)}`),
    ),
    h('section', { class: 'stats' },
      stat('Prep ended', nov ? nov.label : '—', nov ? `${shortName(game.players[nov.side])} left the masters database` : 'book data unavailable'),
      stat('Longest think', lt ? dur(lt.seconds) : '—', lt ? `${shortName(game.players[ltMove.side])} on ${lt.label}` : ''),
      stat('Critical moments', String(game.critical_moments.length), 'ranked by eval swing, time and difficulty'),
      stat('Accuracy', `${summ.players.white.accuracy ?? '—'} · ${summ.players.black.accuracy ?? '—'}`, `${wn} · ${bn} (non-book moves)`),
    ),
    h('section', { id: 'gist' }),
  );

  // ---------- layout ----------
  const boardEl = h('div', { class: 'board-wrap' });
  const topLine = h('div', { class: 'players-line' });
  const botLine = h('div', { class: 'players-line bottom' });
  const info = h('div', { class: 'card move-info' });
  const movesEl = h('div', { class: 'moves' });
  let orientation = 'white';
  let showEngine = true;
  const engineBtn = h('button', { class: 'btn', 'aria-pressed': 'true', title: 'Show the engine’s top move from this position' }, 'Engine arrow');
  const controls = h('div', { class: 'controls' },
    h('button', { class: 'btn icon-btn', title: 'Start (Home)', onclick: () => go(0) }, '⏮'),
    h('button', { class: 'btn icon-btn', title: 'Back (←)', onclick: () => go(cur - 1) }, '◀'),
    h('button', { class: 'btn icon-btn', title: 'Forward (→)', onclick: () => go(cur + 1) }, '▶'),
    h('button', { class: 'btn icon-btn', title: 'End (End)', onclick: () => go(N) }, '⏭'),
    h('button', { class: 'btn', title: 'Flip board', onclick: () => { orientation = orientation === 'white' ? 'black' : 'white'; cg.set({ orientation }); paintClocks(); } }, 'Flip'),
    engineBtn,
  );
  engineBtn.addEventListener('click', () => { showEngine = !showEngine; engineBtn.setAttribute('aria-pressed', String(showEngine)); go(cur); });

  const evalEl = h('div', { class: 'chart' });
  const timeEl = h('div', { class: 'chart' });
  const clockEl = h('div', { class: 'chart' });
  const tableWrap = h('div', { class: 'scroll-x', hidden: true });
  const tableBtn = h('button', { class: 'table-toggle', onclick: () => { tableWrap.hidden = !tableWrap.hidden; tableBtn.textContent = tableWrap.hidden ? 'Show data table' : 'Hide data table'; } }, 'Show data table');
  const legendP = (side) => h('span', {}, h('span', { class: 'dot', style: `background:var(--p${game.players[side].slot})` }), ` ${shortName(game.players[side])} (${side})`);

  app.append(h('div', { class: 'game-grid' },
    h('div', { class: 'board-col' },
      h('div', { class: 'card board-card' }, topLine, boardEl, botLine, controls),
      info,
      h('div', { class: 'card' }, movesEl),
    ),
    h('div', {},
      h('div', { class: 'card chart-card' },
        h('div', { class: 'chart-head' }, h('h2', {}, 'Who was better'), h('div', { class: 'legend' },
          h('span', {}, h('span', { class: 'num', style: 'width:18px;height:18px;font-size:11px;margin-right:4px' }, '1'), 'critical moment'),
          h('span', {}, h('span', { class: 'dot', style: 'background:var(--critical)' }), ' mistake'),
          h('span', {}, h('span', { style: 'display:inline-block;width:14px;height:10px;background:var(--book);border:1px solid var(--rule);vertical-align:-1px' }), ' known theory'))),
        evalEl,
        h('p', { class: 'note' }, 'Engine evaluation in pawns, drawn on a winning-chances scale so small edges stay visible. Click anywhere to jump the board there.')),
      h('div', { class: 'card chart-card' },
        h('div', { class: 'chart-head' }, h('h2', {}, 'Where the time went'), h('div', { class: 'legend' }, legendP('white'), legendP('black'))),
        timeEl,
        h('p', { class: 'note' }, `Minutes spent on each move. Solid bars are long thinks (over ${15} min, or among a player’s 5 longest). Time control: ${game.time_control.description}.`)),
      h('div', { class: 'card chart-card' },
        h('div', { class: 'chart-head' }, h('h2', {}, 'Clock'), h('div', { class: 'legend' }, legendP('white'), legendP('black'))),
        clockEl, tableBtn, tableWrap),
      h('div', { class: 'section-h' }, h('h2', {}, 'Patterns in this game'), h('span', { class: 'muted' }, 'Click a move to load it on the board')),
      h('div', { class: 'events', id: 'events' }),
      h('div', { id: 'crowd' }),
      h('div', { class: 'section-h' }, h('h2', {}, 'Critical moments'), h('span', { class: 'muted' }, 'Click a card to load it on the board')),
      h('div', { class: 'moments', id: 'moments' }),
    ),
  ));

  // ---------- board ----------
  const cg = Chessground(boardEl, {
    fen: game.moves[0].fen_before, orientation, viewOnly: true, coordinates: true,
    animation: { enabled: true, duration: 160 },
    drawable: { enabled: false, visible: true, brushes: BRUSHES },
  });

  // ---------- timeline ----------
  let cur = 0;
  const tl = new Timeline(N, { onSelect: (i) => go(i) });
  const mv = (i) => (i > 0 ? game.moves[i - 1] : null);
  tl.add(evalEl, evalChart(game, evals, { onCritical: (ply) => go(ply + 1) }), (i) => {
    const m = mv(i);
    return m ? `<b>${m.label}</b> · ${evalText(m.eval_after)}${m.classification ? ` · ${m.classification}` : ''}` : `Start · ${evalText(evals[0])}`;
  });
  tl.add(timeEl, timeChart(game, { whiteName: wn, blackName: bn }), (i) => {
    const m = mv(i);
    return m ? `<b>${m.label}</b> · ${shortName(game.players[m.side])} thought ${dur(m.clock.spent)}${m.clock.adjustment ? ` · clock +${dur(m.clock.adjustment)}` : ''}` : null;
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
      h('span', {}, h('span', { class: 'dot', style: `background:var(--p${game.players[side].slot})` }), ` ${shortName(game.players[side])}`, h('span', { class: 'muted' }, ` ${game.players[side].elo || ''}`)),
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

  // ---------- move info ----------
  function paintInfo() {
    const m = mv(cur);
    if (!m) {
      info.replaceChildren(h('div', { class: 'eyebrow' }, 'Start'), h('h3', {}, 'Initial position'),
        h('p', { class: 'ink2', style: 'margin:8px 0 0' }, 'Use ← → or click any chart to step through the game.'));
      return;
    }
    const best = m.top_lines[0];
    const tags = m.tags.filter((t) => t !== 'critical').map((t) => h('span', { class: `tag ${t}` }, t.replaceAll('_', ' ')));
    info.replaceChildren(
      h('div', { class: 'eyebrow' }, `${shortName(game.players[m.side])} · ${m.phase}${m.in_book ? ' · book' : ''}`),
      h('h3', {}, m.label, ...tags),
      h('dl', { class: 'kv' },
        h('dt', {}, 'Time spent'), h('dd', {}, m.clock.spent != null ? dur(m.clock.spent) : `unknown (clock +${dur(m.clock.adjustment)} outside the increments)`),
        h('dt', {}, 'Clock after'), h('dd', {}, clock(m.clock.remaining)),
        h('dt', {}, 'Evaluation'), h('dd', {}, `${evalText(m.eval_before)} → ${evalText(m.eval_after)}`),
        h('dt', {}, 'Engine’s choice'), h('dd', {}, best ? (m.played_rank === 1 ? `${best.san} (played)` : `${best.san} (${evalText(best)}) · played move ranked ${m.played_rank ?? `outside top ${game.engine.multipv}`}`) : '—'),
        h('dt', {}, 'Win chance lost'), h('dd', {}, `${m.wp_loss.toFixed(1)} pts · accuracy ${m.accuracy}%`),
        h('dt', {}, 'Difficulty'), h('dd', {}, `${m.difficulty.score.toFixed(2)} · ${m.difficulty.good_moves} good move${m.difficulty.good_moves === 1 ? '' : 's'}${m.difficulty.only_move ? ' · only move' : ''}${m.difficulty.obvious ? ' · obvious (recapture/check)' : ''}`),
      ),
      h('div', { class: 'legend-arrows' },
        h('span', {}, h('i', { style: 'background:#1baf7a' }), 'engine’s next move'),
        h('span', {}, h('i', { style: 'background:var(--surface-2);outline:1px solid var(--rule)' }), 'last move played')),
    );
  }

  function go(i) {
    cur = Math.max(0, Math.min(N, i));
    const m = mv(cur);
    const next = game.moves[cur];
    cg.set({
      fen: m ? m.fen_after : game.moves[0].fen_before,
      lastMove: m ? lastMove(m.uci) : undefined,
      check: m ? /[+#]$/.test(m.san) : false,
      turnColor: cur % 2 === 0 ? 'white' : 'black',
    });
    cg.setAutoShapes(showEngine && next?.top_lines?.[0] ? [arrow(next.top_lines[0].uci, 'best')] : []);
    btns.forEach((b) => b && b.classList.remove('on'));
    if (btns[cur]) { btns[cur].classList.add('on'); btns[cur].scrollIntoView({ block: 'nearest' }); }
    tl.setCursor(cur);
    paintClocks();
    paintInfo();
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
      h('td', {}, m.label), h('td', {}, shortName(game.players[m.side])), h('td', {}, dur(m.clock.spent)), h('td', {}, clock(m.clock.remaining)),
      h('td', {}, evalText(m.eval_after)), h('td', {}, m.top_lines[0]?.san || '—'), h('td', {}, m.wp_loss.toFixed(1))))),
  ));

  // ---------- patterns in this game ----------
  renderEvents(game, $('#events'), (ply) => { go(ply + 1); scrollTo({ top: 0, behavior: 'smooth' }); });

  // ---------- game gist ----------
  renderGist(game, $('#gist'), (ply) => { go(ply + 1); $('.board-wrap')?.scrollIntoView({ behavior: 'smooth', block: 'center' }); });

  // ---------- crowd mood ----------
  renderCrowd(game, $('#crowd'), (ply) => { go(ply + 1); scrollTo({ top: 0, behavior: 'smooth' }); });

  // ---------- critical moment cards ----------
  const mom = $('#moments');
  if (!game.critical_moments.length) mom.append(h('p', { class: 'muted' }, 'No critical moments detected.'));
  game.critical_moments.forEach((c, k) => {
    const m = game.moves[c.ply];
    const f = c.facts, n = c.narrative;
    const mini = h('div', { class: 'mini' });
    const best = m.top_lines[0];
    const card = h('article', { class: 'card moment', onclick: (e) => { if (!e.target.closest('details')) { go(c.ply + 1); scrollTo({ top: 0, behavior: 'smooth' }); } } },
      h('div', {}, mini,
        h('div', { class: 'legend-arrows' },
          h('span', {}, h('i', { style: 'background:#2a78d6' }), 'played'),
          best && best.uci !== m.uci ? h('span', {}, h('i', { style: 'background:#1baf7a' }), 'engine best') : h('span', {}, 'played = engine best'))),
      h('div', {},
        h('div', { class: 'eyebrow' }, `${shortName(game.players[m.side])} · ${m.phase}`),
        h('h3', {}, h('span', { class: 'num' }, `${k + 1}`), n.headline),
        h('p', {}, n.text),
        n.likely_reasons?.length ? h('div', { class: 'reasons' },
          h('div', { class: 'eyebrow' }, `What might have been on ${shortName(game.players[m.side])}’s mind`),
          h('ul', {}, ...n.likely_reasons.map((r) => h('li', {}, r.reason)))) : null,
        h('div', { class: 'chips' },
          chip('Thought', dur(m.clock.spent)),
          chip('Clock left', dur(m.clock.remaining)),
          chip('Eval', `${evalText(m.eval_before)} → ${evalText(m.eval_after)}`),
          chip('Good moves', `${m.difficulty.good_moves}${m.difficulty.only_move ? ' (only move)' : ''}`),
          chip('Score', `${c.score.total.toFixed(2)}`)),
        h('details', {},
          h('summary', {}, n.source === 'claude' ? `Written by ${n.model} from these facts · show facts` : 'Written from a template using these facts · show facts'),
          h('pre', {}, JSON.stringify({ facts: f, score: c.score }, null, 2))),
      ),
    );
    mom.append(card);
    const shapes = [arrow(m.uci, 'played')];
    if (best && best.uci !== m.uci) shapes.push(arrow(best.uci, 'best'));
    const mcg = Chessground(mini, { fen: m.fen_before, orientation: m.side, viewOnly: true, coordinates: false, drawable: { enabled: false, visible: true, brushes: BRUSHES } });
    mcg.setAutoShapes(shapes);
  });

  const startPly = parseInt(params.get('ply') ?? '', 10);
  go(Number.isFinite(startPly) ? startPly : (game.critical_moments[0] ? 0 : 0));
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
  el.append(h('div', { class: 'card gist' },
    h('div', { class: 'eyebrow' }, 'How the game went'),
    h('h2', {}, g.headline),
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
  el.append(h('div', { class: 'section-h' }, h('h2', {}, 'What viewers said'), h('span', { class: 'muted' }, 'Opinion, not fact')));
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

function stat(label, value, sub) {
  return h('div', { class: 'card stat' }, h('div', { class: 'eyebrow' }, label), h('div', { class: 'v' }, value), h('div', { class: 's' }, sub));
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
