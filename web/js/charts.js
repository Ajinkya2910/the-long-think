// Dependency-free SVG charts. Every timeline chart shares the same x margins so
// plies line up vertically across the eval / time / clock charts.
import { h, dur, evalText, css } from './common.js';

const NS = 'http://www.w3.org/2000/svg';
const s = (tag, attrs = {}, ...kids) => {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v != null) e.setAttribute(k, v);
  for (const k of kids) if (k != null) e.append(k.nodeType ? k : document.createTextNode(k));
  return e;
};
export const M = { l: 46, r: 14 };

const squash = (cp) => 2 / (1 + Math.exp(-0.00368208 * cp)) - 1; // Lichess winning-chances curve
const evY = (ev) => (ev.mate != null ? (ev.mate > 0 || (ev.mate === 0 && ev.cp > 0) ? 1 : -1) : squash(Math.max(-1000, Math.min(1000, ev.cp))));

/** Coordinates a set of timeline charts: shared hover + cursor + click-to-select. */
export class Timeline {
  constructor(n, { onSelect, tooltip }) {
    this.n = n; this.onSelect = onSelect; this.tooltip = tooltip; this.charts = []; this.cursor = 0;
  }
  x(i, w) { return M.l + (i * (w - M.l - M.r)) / this.n; }
  idxAt(px, w) { return Math.max(0, Math.min(this.n, Math.round(((px - M.l) * this.n) / (w - M.l - M.r)))); }
  add(el, draw, describe) {
    const chart = { el, draw, describe };
    this.charts.push(chart);
    const tip = h('div', { class: 'tooltip' });
    el.append(tip);
    chart.tip = tip;
    const pick = (ev) => {
      const r = el.getBoundingClientRect();
      return this.idxAt(ev.clientX - r.left, r.width);
    };
    el.addEventListener('pointermove', (ev) => this.hover(pick(ev)));
    el.addEventListener('pointerleave', () => this.hover(null));
    el.addEventListener('click', (ev) => { if (!ev.target.closest('[data-ply]')) this.onSelect(pick(ev)); });
    return chart;
  }
  render() {
    for (const c of this.charts) {
      const w = c.el.clientWidth || 600;
      c.el.querySelector('svg')?.remove();
      const svg = c.draw(w, (i) => this.x(i, w));
      c.el.prepend(svg);
      c.svg = svg; c.w = w;
    }
    this.setCursor(this.cursor);
  }
  setCursor(i) {
    this.cursor = i;
    for (const c of this.charts) {
      if (!c.svg) continue;
      let line = c.svg.querySelector('.cursor');
      const H = +c.svg.getAttribute('height');
      if (!line) { line = s('line', { class: 'cursor', y1: 4, y2: H - 18 }); c.svg.append(line); }
      const x = this.x(i, c.w);
      line.setAttribute('x1', x); line.setAttribute('x2', x);
    }
  }
  hover(i) {
    for (const c of this.charts) {
      if (!c.svg) continue;
      let line = c.svg.querySelector('.hover');
      const H = +c.svg.getAttribute('height');
      if (i == null) { line?.remove(); c.tip.style.display = 'none'; continue; }
      if (!line) { line = s('line', { class: 'hover', y1: 4, y2: H - 18 }); c.svg.append(line); }
      const x = this.x(i, c.w);
      line.setAttribute('x1', x); line.setAttribute('x2', x);
      const html = c.describe(i);
      if (html) {
        c.tip.innerHTML = html; c.tip.style.display = 'block';
        const tw = c.tip.offsetWidth;
        c.tip.style.left = `${Math.max(tw / 2, Math.min(c.w - tw / 2, x))}px`;
        c.tip.style.top = '14px';
      } else c.tip.style.display = 'none';
    }
  }
}

function yAxis(svg, w, ticks) {
  const g = s('g', { class: 'grid' });
  for (const t of ticks) {
    g.append(s('line', { x1: M.l, x2: w - M.r, y1: t.y, y2: t.y, class: t.zero ? 'zero' : null }));
    g.append(s('text', { x: M.l - 8, y: t.y + 3.5, 'text-anchor': 'end' }, t.label));
  }
  svg.append(g);
}
function xAxis(svg, n, x, H) {
  const g = s('g');
  const step = n > 120 ? 20 : 10;
  for (let mv = step; mv * 2 <= n; mv += step) g.append(s('text', { x: x(mv * 2), y: H - 4, 'text-anchor': 'middle' }, `${mv}`));
  g.append(s('text', { x: M.l, y: H - 4, 'text-anchor': 'start' }, 'move'));
  svg.append(g);
}

/** Evaluation chart. evals[i] = White-POV eval of position i (0..n). */
export function evalChart(game, evals, opts) {
  const H = 210, top = 10, bot = H - 24;
  const mid = (top + bot) / 2, half = (bot - top) / 2;
  return (w, x) => {
    const svg = s('svg', { viewBox: `0 0 ${w} ${H}`, width: w, height: H, role: 'img', 'aria-label': 'Engine evaluation over the game' });
    const yv = (v) => mid - v * half;
    // opening book band
    const nov = game.opening?.novelty_ply;
    if (nov != null) {
      svg.append(s('rect', { x: x(0), y: top, width: x(nov) - x(0), height: bot - top, fill: 'var(--book)' }));
      svg.append(s('text', { x: x(nov) - 6, y: top + 28, 'text-anchor': 'end', class: 'lbl' }, 'Book'));
    }
    yAxis(svg, w, [
      { y: yv(squash(300)), label: '+3' }, { y: yv(squash(100)), label: '+1' }, { y: mid, label: '0', zero: true },
      { y: yv(squash(-100)), label: '−1' }, { y: yv(squash(-300)), label: '−3' },
    ]);
    svg.append(s('text', { x: M.l + 4, y: top + 9, class: 'lbl', 'font-size': 10.5 }, 'White better'));
    svg.append(s('text', { x: M.l + 4, y: bot - 4, class: 'lbl', 'font-size': 10.5 }, 'Black better'));
    const pts = evals.map((ev, i) => [x(i), yv(evY(ev))]);
    const line = pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join('');
    svg.append(s('path', { d: `${line}L${pts.at(-1)[0]},${mid}L${pts[0][0]},${mid}Z`, fill: 'var(--eval-fill)' }));
    svg.append(s('path', { d: line, fill: 'none', stroke: 'var(--ink)', 'stroke-width': 2, 'stroke-linejoin': 'round' }));
    if (nov != null) {
      svg.append(s('line', { x1: x(nov), x2: x(nov), y1: top, y2: bot, stroke: 'var(--ink-2)', 'stroke-width': 1 }));
    }
    // classified mistakes
    game.moves.forEach((m) => {
      if (!m.classification) return;
      const [cx, cy] = pts[m.ply + 1];
      svg.append(s('circle', { cx, cy, r: 4, fill: m.classification === 'inaccuracy' ? 'var(--warn)' : 'var(--critical)', stroke: 'var(--surface)', 'stroke-width': 2 }));
    });
    // critical moments
    game.critical_moments.forEach((c, k) => {
      const [cx, cy] = pts[c.ply + 1];
      const g = s('g', { 'data-ply': c.ply, style: 'cursor:pointer' });
      g.append(s('circle', { cx, cy, r: 10, fill: 'var(--ink)', stroke: 'var(--surface)', 'stroke-width': 2 }));
      g.append(s('text', { x: cx, y: cy + 3.8, 'text-anchor': 'middle', style: 'fill:var(--bg);font-weight:700;font-size:11px' }, `${k + 1}`));
      g.addEventListener('click', () => opts.onCritical(c.ply));
      svg.append(g);
    });
    xAxis(svg, evals.length - 1, x, H);
    return svg;
  };
}

/** Time spent per move, mirrored: White's moves above the axis, Black's below. */
export function timeChart(game, opts) {
  const H = 220, top = 12, bot = H - 24, mid = (top + bot) / 2;
  const spent = game.moves.map((m) => m.clock.spent ?? 0);
  const max = Math.max(60, ...spent);
  const niceMax = [300, 600, 900, 1200, 1800, 2400, 3600, 5400].find((v) => v >= max) || max;
  return (w, x) => {
    const svg = s('svg', { viewBox: `0 0 ${w} ${H}`, width: w, height: H, role: 'img', 'aria-label': 'Time spent per move' });
    const half = mid - top;
    const yh = (sec) => (sec / niceMax) * half;
    const ticks = [{ y: mid, label: '0', zero: true }];
    const stepT = niceMax / 2;
    for (const t of [stepT, niceMax]) {
      ticks.push({ y: mid - yh(t), label: `${Math.round(t / 60)}m` });
      ticks.push({ y: mid + yh(t), label: `${Math.round(t / 60)}m` });
    }
    yAxis(svg, w, ticks);
    const bw = Math.max(2, Math.min(12, ((w - M.l - M.r) / game.moves.length) * 1.5));
    const best = {};
    game.moves.forEach((m) => {
      const v = m.clock.spent ?? 0;
      if (!best[m.side] || v > (best[m.side].clock.spent ?? 0)) best[m.side] = m;
    });
    game.moves.forEach((m) => {
      const v = m.clock.spent ?? 0;
      const cx = x(m.ply + 1);
      const hgt = Math.max(v > 0 ? 1.5 : 0, yh(v));
      const up = m.side === 'white';
      const slot = game.players[m.side].slot;
      // 4px rounded data-end, anchored to the baseline
      const r = Math.min(4, bw / 2, hgt);
      const x0 = cx - bw / 2, x1 = cx + bw / 2;
      const y0 = mid, y1 = up ? mid - hgt : mid + hgt;
      const d = up
        ? `M${x0},${y0}V${y1 + r}Q${x0},${y1} ${x0 + r},${y1}H${x1 - r}Q${x1},${y1} ${x1},${y1 + r}V${y0}Z`
        : `M${x0},${y0}V${y1 - r}Q${x0},${y1} ${x0 + r},${y1}H${x1 - r}Q${x1},${y1} ${x1},${y1 - r}V${y0}Z`;
      svg.append(s('path', { d, fill: `var(--p${slot})`, opacity: m.clock.long_think ? 1 : 0.55 }));
      if (m.clock.adjustment) {
        svg.append(s('text', { x: cx, y: up ? mid - 6 : mid + 14, 'text-anchor': 'middle', class: 'lbl' }, `+${dur(m.clock.adjustment)}`));
      }
    });
    for (const side of ['white', 'black']) {
      const m = best[side];
      if (!m || !m.clock.spent) continue;
      const up = side === 'white';
      const y = up ? mid - yh(m.clock.spent) - 6 : mid + yh(m.clock.spent) + 14;
      const cx = x(m.ply + 1);
      const anchor = cx > w * 0.75 ? 'end' : 'start';
      svg.append(s('text', { x: cx + (anchor === 'start' ? -4 : 4), y, 'text-anchor': anchor, class: 'lbl' }, `${dur(m.clock.spent)} · ${m.label}`));
    }
    svg.append(s('text', { x: w - M.r, y: top + 9, 'text-anchor': 'end', class: 'lbl' }, `${opts.whiteName} (White) ↑`));
    svg.append(s('text', { x: w - M.r, y: bot - 2, 'text-anchor': 'end', class: 'lbl' }, `${opts.blackName} (Black) ↓`));
    xAxis(svg, game.moves.length, x, H);
    return svg;
  };
}

/** Remaining clock for both players. */
export function clockChart(game, opts) {
  const H = 180, top = 10, bot = H - 24;
  const base = game.time_control.periods[0].seconds;
  const all = game.moves.map((m) => m.clock.remaining ?? 0);
  const max = Math.max(base, ...all);
  return (w, x) => {
    const svg = s('svg', { viewBox: `0 0 ${w} ${H}`, width: w, height: H, role: 'img', 'aria-label': 'Clock time remaining' });
    const y = (sec) => bot - (sec / max) * (bot - top);
    const ticks = [];
    for (let t = 0; t <= max; t += 1800) ticks.push({ y: y(t), label: t ? `${t / 3600}h`.replace('0.5h', '30m').replace('1.5h', '1h30') : '0', zero: t === 0 });
    yAxis(svg, w, ticks);
    for (const side of ['white', 'black']) {
      const slot = game.players[side].slot;
      const pts = [[x(0), y(base)]];
      game.moves.forEach((m) => { if (m.side === side && m.clock.remaining != null) pts.push([x(m.ply + 1), y(m.clock.remaining)]); });
      svg.append(s('path', { d: pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(''), fill: 'none', stroke: `var(--p${slot})`, 'stroke-width': 2, 'stroke-linejoin': 'round' }));
      const last = pts.at(-1);
      svg.append(s('circle', { cx: last[0], cy: last[1], r: 4, fill: `var(--p${slot})`, stroke: 'var(--surface)', 'stroke-width': 2 }));
      const name = side === 'white' ? opts.whiteName : opts.blackName;
      svg.append(s('text', { x: last[0] - 8, y: last[1] + (side === 'white' ? -8 : 15), 'text-anchor': 'end', class: 'lbl' }, name));
    }
    xAxis(svg, game.moves.length, x, H);
    return svg;
  };
}

/** Horizontal dot plot: rows = buckets, one dot per player. For accuracy (no zero baseline needed). */
export function dotPlot(el, { rows, series, domain, format = (v) => v.toFixed(0), unit = '' }) {
  el.innerHTML = '';
  const tip = h('div', { class: 'tooltip' });
  el.append(tip);
  const rowH = 34, top = 8, H = top + rows.length * rowH + 22, L = 92, R = 18;
  const draw = () => {
    const w = el.clientWidth || 400;
    el.querySelector('svg')?.remove();
    const svg = s('svg', { viewBox: `0 0 ${w} ${H}`, width: w, height: H });
    const xs = (v) => L + ((v - domain[0]) / (domain[1] - domain[0])) * (w - L - R);
    const g = s('g', { class: 'grid' });
    const step = (domain[1] - domain[0]) / 4;
    for (let v = domain[0]; v <= domain[1] + 1e-9; v += step) {
      g.append(s('line', { x1: xs(v), x2: xs(v), y1: top, y2: H - 20 }));
      g.append(s('text', { x: xs(v), y: H - 4, 'text-anchor': 'middle' }, format(v) + unit));
    }
    svg.append(g);
    rows.forEach((row, i) => {
      const cy = top + i * rowH + rowH / 2;
      svg.append(s('text', { x: L - 10, y: cy + 4, 'text-anchor': 'end', class: 'lbl' }, row.label));
      const vals = series.map((se) => ({ se, d: row.values[se.key] })).filter((o) => o.d && o.d.value != null);
      if (vals.length === 2) svg.append(s('line', { x1: xs(vals[0].d.value), x2: xs(vals[1].d.value), y1: cy, y2: cy, stroke: 'var(--rule)', 'stroke-width': 2 }));
      if (!vals.length) svg.append(s('text', { x: L + 4, y: cy + 4 }, 'no moves'));
      vals.forEach(({ se, d }) => {
        const c = s('circle', { cx: xs(d.value), cy, r: 6, fill: se.color, stroke: 'var(--surface)', 'stroke-width': 2 });
        const hit = s('circle', { cx: xs(d.value), cy, r: 14, fill: 'transparent' });
        hit.addEventListener('pointerenter', () => {
          tip.innerHTML = `<b>${se.label}</b> · ${row.label}<br>${format(d.value)}${unit} over ${d.n} move${d.n === 1 ? '' : 's'}`;
          tip.style.display = 'block'; tip.style.left = `${xs(d.value)}px`; tip.style.top = `${cy - 6}px`;
        });
        hit.addEventListener('pointerleave', () => { tip.style.display = 'none'; });
        svg.append(c, hit);
      });
    });
    el.prepend(svg);
  };
  draw();
  return draw;
}

/** Grouped horizontal bars: rows = categories, a thin bar per series, zero baseline. */
export function groupedBars(el, { rows, series, max, format, unit = '' }) {
  el.innerHTML = '';
  const tip = h('div', { class: 'tooltip' });
  el.append(tip);
  const barH = 9, gap = 2, groupGap = 16, L = 92, R = 54;
  const groupH = series.length * (barH + gap) - gap;
  const H = rows.length * (groupH + groupGap) + 4;
  const draw = () => {
    const w = el.clientWidth || 400;
    el.querySelector('svg')?.remove();
    const svg = s('svg', { viewBox: `0 0 ${w} ${H}`, width: w, height: H });
    const xs = (v) => (v / max) * (w - L - R);
    svg.append(s('line', { x1: L, x2: L, y1: 0, y2: H - groupGap + 4, class: 'zero', stroke: 'var(--rule)' }));
    rows.forEach((row, i) => {
      const y0 = i * (groupH + groupGap) + 2;
      svg.append(s('text', { x: L - 10, y: y0 + groupH / 2 + 4, 'text-anchor': 'end', class: 'lbl' }, row.label));
      series.forEach((se, j) => {
        const v = row.values[se.key] ?? 0;
        const y = y0 + j * (barH + gap);
        const bw = Math.max(v > 0 ? 2 : 0, xs(v));
        const r = Math.min(4, bw);
        const d = `M${L},${y}H${L + bw - r}Q${L + bw},${y} ${L + bw},${y + r}V${y + barH - r}Q${L + bw},${y + barH} ${L + bw - r},${y + barH}H${L}Z`;
        const p = s('path', { d, fill: se.color });
        p.addEventListener('pointerenter', () => {
          tip.innerHTML = `<b>${se.label}</b> · ${row.label}<br>${format(v)}${unit}${row.extra?.[se.key] ? ` · ${row.extra[se.key]}` : ''}`;
          tip.style.display = 'block'; tip.style.left = `${L + bw / 2}px`; tip.style.top = `${y}px`;
        });
        p.addEventListener('pointerleave', () => { tip.style.display = 'none'; });
        svg.append(p, s('text', { x: L + bw + 6, y: y + barH - 1 }, format(v) + unit));
      });
    });
    el.prepend(svg);
  };
  draw();
  return draw;
}

/** Scatter explorer. points: [{x, y, color, key, html, onClick}] */
export function scatter(el, { points, xLabel, yLabel, xScale = 'linear', yMax, xMax }) {
  el.innerHTML = '';
  const tip = h('div', { class: 'tooltip' });
  el.append(tip);
  const H = 350, top = 28, bot = H - 40, L = 52, R = 16;
  const draw = () => {
    const w = el.clientWidth || 600;
    el.querySelector('svg')?.remove();
    const svg = s('svg', { viewBox: `0 0 ${w} ${H}`, width: w, height: H, role: 'img', 'aria-label': `${yLabel} by ${xLabel}` });
    const xm = xMax ?? Math.max(1, ...points.map((p) => p.x));
    const ym = yMax ?? Math.max(1, ...points.map((p) => p.y));
    const tx = xScale === 'sqrt' ? Math.sqrt : (v) => v;
    const xs = (v) => L + (tx(Math.max(0, v)) / tx(xm)) * (w - L - R);
    const ys = (v) => bot - (v / ym) * (bot - top);
    const g = s('g', { class: 'grid' });
    for (let k = 0; k <= 4; k++) {
      const v = (ym * k) / 4;
      g.append(s('line', { x1: L, x2: w - R, y1: ys(v), y2: ys(v), class: k === 0 ? 'zero' : null }));
      g.append(s('text', { x: L - 8, y: ys(v) + 3.5, 'text-anchor': 'end' }, fmtTick(v)));
    }
    const xt = xScale === 'sqrt' ? [0, 60, 300, 900, 1800, 3600].filter((v) => v <= xm * 1.01) : [0, 0.25, 0.5, 0.75, 1].map((f) => xm * f);
    for (const v of xt) g.append(s('text', { x: xs(v), y: bot + 16, 'text-anchor': 'middle' }, xScale === 'sqrt' ? (v ? dur(v).replace(' 00s', '') : '0') : fmtTick(v)));
    svg.append(g);
    svg.append(s('text', { x: w - R, y: H - 4, 'text-anchor': 'end', class: 'lbl' }, `${xLabel} →`));
    svg.append(s('text', { x: L - 8, y: 10, class: 'lbl' }, `↑ ${yLabel}`));
    for (const p of points) {
      const c = s('circle', { cx: xs(p.x), cy: ys(p.y), r: 4.5, fill: p.color, stroke: 'var(--surface)', 'stroke-width': 2, 'fill-opacity': 0.85, style: 'cursor:pointer' });
      c.addEventListener('pointerenter', () => {
        tip.innerHTML = p.html; tip.style.display = 'block'; tip.style.left = `${xs(p.x)}px`; tip.style.top = `${ys(p.y) - 4}px`;
        c.setAttribute('r', 7);
      });
      c.addEventListener('pointerleave', () => { tip.style.display = 'none'; c.setAttribute('r', 4.5); });
      c.addEventListener('click', p.onClick);
      svg.append(c);
    }
    el.prepend(svg);
  };
  draw();
  return draw;
}
const fmtTick = (v) => (Math.abs(v) >= 10 ? Math.round(v) : +v.toFixed(2)).toString();

/** Tiny eval sparkline: White win% (0..100) per position. */
export function sparkline(wps, { w = 160, hgt = 34 } = {}) {
  const svg = s('svg', { viewBox: `0 0 ${w} ${hgt}`, width: w, height: hgt, 'aria-label': 'Evaluation sparkline' });
  const x = (i) => 1 + (i * (w - 2)) / Math.max(1, wps.length - 1);
  const y = (v) => hgt - 2 - (v / 100) * (hgt - 4);
  svg.append(s('line', { x1: 0, x2: w, y1: y(50), y2: y(50), stroke: 'var(--rule)' }));
  const d = wps.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join('');
  svg.append(s('path', { d: `${d}L${x(wps.length - 1)},${y(50)}L${x(0)},${y(50)}Z`, fill: 'var(--eval-fill)' }));
  svg.append(s('path', { d, fill: 'none', stroke: 'var(--ink)', 'stroke-width': 1.5 }));
  return svg;
}
export { evalText };
