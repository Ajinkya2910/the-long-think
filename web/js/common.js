// Shared helpers for every page.
export const $ = (sel, el = document) => el.querySelector(sel);
export const h = (tag, attrs = {}, ...kids) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k === 'html') e.innerHTML = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? '' : v);
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) e.append(kid.nodeType ? kid : document.createTextNode(kid));
  return e;
};

export async function getJSON(url) {
  const r = await fetch(url, { cache: 'no-cache' });
  if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
  return r.json();
}

export function dur(sec) {
  if (sec == null) return '—';
  sec = Math.round(sec);
  const hh = Math.floor(sec / 3600), mm = Math.floor((sec % 3600) / 60), ss = sec % 60;
  if (hh) return `${hh}h ${String(mm).padStart(2, '0')}m`;
  if (mm) return `${mm}m ${String(ss).padStart(2, '0')}s`;
  return `${ss}s`;
}
export function clock(sec) {
  if (sec == null) return '—';
  const hh = Math.floor(sec / 3600), mm = Math.floor((sec % 3600) / 60), ss = Math.round(sec % 60);
  return `${hh}:${String(mm).padStart(2, '0')}:${String(ss).padStart(2, '0')}`;
}
export function evalText(ev) {
  if (!ev) return '—';
  if (ev.mate != null) return ev.mate === 0 ? 'mate' : `#${ev.mate > 0 ? '' : '-'}${Math.abs(ev.mate)}`;
  const p = ev.cp / 100;
  return (p > 0 ? '+' : '') + p.toFixed(2);
}
export const shortName = (p) => p.short || (p.name || '').split(',')[0];
export const slotVar = (slot) => `var(--p${slot})`;
export const SYM = { inaccuracy: '?!', mistake: '?', blunder: '??' };

export function themeToggle(btn) {
  const root = document.documentElement;
  const saved = (() => { try { return localStorage.getItem('lt-theme'); } catch { return null; } })();
  if (saved) root.dataset.theme = saved;
  const isDark = () => root.dataset.theme ? root.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
  const paint = () => { btn.textContent = isDark() ? '☀' : '☾'; btn.title = isDark() ? 'Light mode' : 'Dark mode'; };
  btn.addEventListener('click', () => {
    root.dataset.theme = isDark() ? 'light' : 'dark';
    try { localStorage.setItem('lt-theme', root.dataset.theme); } catch {}
    paint();
    window.dispatchEvent(new Event('themechange'));
  });
  paint();
}

export function css(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
