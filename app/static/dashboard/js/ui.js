// DOM helpers. All user data goes in as text nodes / attributes, never HTML.
import { errorMessage } from './api.js';

export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === 'class') el.className = value;
    else if (key === 'style' && typeof value === 'object') Object.assign(el.style, value);
    else if (key.startsWith('on') && typeof value === 'function') el.addEventListener(key.slice(2).toLowerCase(), value);
    else if (key === 'value') el.value = value;
    else if (['checked', 'selected', 'disabled', 'open', 'hidden', 'multiple', 'required', 'readonly'].includes(key)) {
      if (value) el.setAttribute(key, '');
      if (key in el) el[key] = Boolean(value);
    } else el.setAttribute(key, value === true ? '' : value);
  }
  append(el, children);
  return el;
}

function append(el, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
}

export function clear(el, ...children) {
  el.replaceChildren();
  append(el, children);
  return el;
}

const SVG_NS = 'http://www.w3.org/2000/svg';
export function s(tag, attrs = {}, ...children) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === undefined || value === null) continue;
    if (key.startsWith('on') && typeof value === 'function') el.addEventListener(key.slice(2).toLowerCase(), value);
    else el.setAttribute(key, value);
  }
  append(el, children);
  return el;
}

// Feather-style line icons
const ICONS = {
  overview: 'M3 12h4l3 8 4-16 3 8h4',
  users: 'M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75',
  filter: 'M22 3H2l8 9.46V19l4 2v-8.54L22 3z',
  template: 'M4 4h16v16H4zM4 9h16M9 9v11',
  send: 'M22 2 11 13M22 2l-7 20-4-9-9-4 20-7z',
  zap: 'M13 2 3 14h9l-1 8 10-12h-9l1-8z',
  list: 'M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01',
  settings: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.6 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z',
  plus: 'M12 5v14M5 12h14',
  upload: 'M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12',
  download: 'M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3',
  sheet: 'M3 3h18v18H3zM3 9h18M3 15h18M9 3v18',
  trash: 'M3 6h18M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6M10 11v6M14 11v6M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2',
  x: 'M18 6 6 18M6 6l12 12',
  up: 'M18 15l-6-6-6 6',
  down: 'M6 9l6 6 6-6',
  logout: 'M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9',
  sun: 'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41',
  moon: 'M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9z',
  monitor: 'M3 4h18v12H3zM8 20h8M12 16v4',
  mail: 'M4 4h16v16H4zM4 6l8 7 8-7',
  copy: 'M9 9h11v11H9zM5 15H4V4h11v1',
  refresh: 'M23 4v6h-6M1 20v-6h6M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15',
  pause: 'M6 4h4v16H6zM14 4h4v16h-4z',
  play: 'M5 3l14 9-14 9V3z',
  clock: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 6v6l4 2',
  back: 'M19 12H5M12 19l-7-7 7-7',
  check: 'M20 6 9 17l-5-5',
  alert: 'M12 9v4M12 17h.01M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z',
  info: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 16v-4M12 8h.01',
  tag: 'M20.59 13.41 13.42 20.58a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82zM7 7h.01',
  sliders: 'M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6',
  calendar: 'M3 4h18v18H3zM16 2v4M8 2v4M3 10h18',
  eye: 'M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z',
  target: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 18a6 6 0 1 0 0-12 6 6 0 0 0 0 12zM12 14a2 2 0 1 0 0-4 2 2 0 0 0 0 4z',
  click: 'M9 9l5 12 1.8-5.2L21 14 9 9zM7.2 2.2 8 5.1M5.1 8 2.2 7.2M14 4.1 12 6.2M6.2 12l-2.1 2',
  inbox: 'M22 12h-6l-2 3h-4l-2-3H2M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z',
  bounce: 'M3 12h4l3-9 4 18 3-9h4',
  userx: 'M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2M8.5 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8M18 8l5 5M23 8l-5 5',
  gauge: 'M12 14l4-4M3.34 19a10 10 0 1 1 17.32 0',
  sparkles: 'M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3zM19 15l.9 2.1L22 18l-2.1.9L19 21l-.9-2.1L16 18l2.1-.9L19 15z',
  shield: 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z',
};

export function icon(name) {
  return s('svg', { viewBox: '0 0 24 24', width: 16, height: 16, fill: 'none', stroke: 'currentColor', 'stroke-width': 2,
    'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true' },
  s('path', { d: ICONS[name] || '' }));
}

// ---------- feedback ----------
const TOAST_ICON = { success: 'check', error: 'alert', warning: 'alert', info: 'info' };
const TOAST_TITLE = { success: 'Done', error: 'Something went wrong', warning: 'Heads up', info: 'Note' };

/**
 * toast(message, type?)  type: success (default) | error | warning | info
 * toast({ title, message, type, duration })
 */
export function toast(message, type = 'success') {
  const opts = typeof message === 'object' && message !== null && !(message instanceof Node)
    ? message : { message, type };
  const kind = opts.type || 'success';
  const duration = opts.duration ?? (kind === 'error' ? 7000 : 4000);
  const host = document.getElementById('toasts');
  const dismiss = () => {
    if (el.classList.contains('leaving')) return;
    el.classList.add('leaving');
    setTimeout(() => el.remove(), 260);
  };
  const bar = h('div', { class: 'toast-bar', style: { animationDuration: `${duration}ms` } });
  const el = h('div', { class: `toast ${kind}`, role: kind === 'error' ? 'alert' : 'status' },
    h('div', { class: 'toast-icon' }, icon(TOAST_ICON[kind] || 'info')),
    h('div', {}, h('div', { class: 'toast-title' }, opts.title || TOAST_TITLE[kind]),
      opts.message ? h('div', { class: 'toast-msg' }, opts.message) : null),
    h('button', { class: 'toast-close', 'aria-label': 'Dismiss', onclick: dismiss }, icon('x')),
    bar);
  bar.addEventListener('animationend', dismiss);
  host.append(el);
  while (host.children.length > 4) host.firstElementChild.remove();
  return dismiss;
}

export function toastError(err) { toast(errorMessage(err), 'error'); }

export function spinner(large = false) { return h('span', { class: `spinner${large ? ' lg' : ''}`, 'aria-hidden': 'true' }); }

/** Run an async action with a busy button (spinner inside); shows errors as toasts. */
export async function busy(button, fn) {
  let spin;
  if (button) {
    button.disabled = true;
    button.classList.add('is-loading');
    spin = spinner();
    button.append(spin);
  }
  try {
    return await fn();
  } catch (err) {
    toastError(err);
    return undefined;
  } finally {
    if (button) {
      button.disabled = false;
      button.classList.remove('is-loading');
      spin?.remove();
    }
  }
}

// ---------- modal ----------
export function modal({ title, body, actions = [], wide = false, onClose }) {
  const previous = document.activeElement;
  const close = () => {
    backdrop.remove();
    document.removeEventListener('keydown', onKey);
    previous?.focus?.();
    onClose?.();
  };
  const onKey = (e) => { if (e.key === 'Escape') close(); };
  const foot = actions.length ? h('div', { class: 'modal-foot' }, actions) : null;
  const dialog = h('div', { class: `modal${wide ? ' wide' : ''}`, role: 'dialog', 'aria-modal': 'true', 'aria-label': title },
    h('div', { class: 'modal-head' }, h('h2', {}, title),
      h('button', { class: 'ghost icon', 'aria-label': 'Close', onclick: close }, icon('x'))),
    h('div', { class: 'modal-body' }, body),
    foot);
  const backdrop = h('div', { class: 'modal-backdrop', onmousedown: (e) => { if (e.target === backdrop) close(); } }, dialog);
  document.body.append(backdrop);
  document.addEventListener('keydown', onKey);
  setTimeout(() => (dialog.querySelector('input, select, textarea') || dialog.querySelector('button'))?.focus(), 0);
  return { close, dialog };
}

export function confirmDialog(title, message, { confirmLabel = 'Confirm', danger = false } = {}) {
  return new Promise((resolve) => {
    let answered = false;
    const done = (value) => { answered = true; m.close(); resolve(value); };
    const m = modal({
      title,
      body: h('p', { class: 'secondary' }, message),
      actions: [
        h('button', { onclick: () => done(false) }, 'Cancel'),
        h('button', { class: danger ? 'danger' : 'primary', onclick: () => done(true) }, confirmLabel),
      ],
      onClose: () => { if (!answered) resolve(false); },
    });
  });
}

// ---------- form helpers ----------
export function field(label, input, hint) {
  return h('label', { class: 'field' }, label, input, hint ? h('span', { class: 'hint' }, hint) : null);
}

export function select(options, value, attrs = {}) {
  return h('select', attrs, options.map((o) => {
    const opt = typeof o === 'string' ? { value: o, label: o } : o;
    return h('option', { value: opt.value, selected: String(opt.value) === String(value ?? '') }, opt.label);
  }));
}

export function formData(form) {
  const data = {};
  for (const el of form.querySelectorAll('[name]')) {
    if (el.type === 'checkbox') data[el.name] = el.checked;
    else if (el.type === 'number') data[el.name] = el.value === '' ? null : Number(el.value);
    else data[el.name] = el.value;
  }
  return data;
}

export function debounce(fn, ms = 350) {
  let timer;
  return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), ms); };
}

// ---------- formatting ----------
const nf = new Intl.NumberFormat();
export const fmtNum = (n) => (n === null || n === undefined ? '—' : nf.format(n));
export const fmtPct = (n) => (n === null || n === undefined ? '—' : `${Number(n).toFixed(1)}%`);
export function compact(n) {
  if (n === null || n === undefined) return '—';
  return new Intl.NumberFormat(undefined, { notation: n >= 10000 ? 'compact' : 'standard', maximumFractionDigits: 1 }).format(n);
}
/** API timestamps are naive UTC ISO strings. */
export function parseUtc(value) {
  if (!value) return null;
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(value) ? value : `${value}Z`);
}
export function fmtDate(value, withTime = true) {
  const d = parseUtc(value);
  if (!d) return '—';
  return d.toLocaleString(undefined, withTime
    ? { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }
    : { year: 'numeric', month: 'short', day: 'numeric' });
}
export function relTime(value) {
  const d = parseUtc(value);
  if (!d) return '—';
  const diff = (Date.now() - d.getTime()) / 1000;
  const abs = Math.abs(diff);
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' });
  const units = [[60, 'second', 1], [3600, 'minute', 60], [86400, 'hour', 3600], [2592000, 'day', 86400],
    [31536000, 'month', 2592000], [Infinity, 'year', 31536000]];
  for (const [limit, unit, size] of units) {
    if (abs < limit) return rtf.format(-Math.round(diff / size), unit);
  }
  return fmtDate(value);
}

export function initials(name) {
  return (name || '?').split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join('') || '?';
}

const STATUS_TONE = {
  active: 'good', sent: 'good', completed: 'good', opened: 'good', clicked: 'good', delivered: 'good',
  sending: 'info', scheduled: 'info', pending: 'info',
  paused: 'warn', draft: '', inactive: '',
  bounced: 'bad', unsubscribed: 'bad', failed: 'bad',
};
export function badge(status) {
  return h('span', { class: `badge ${STATUS_TONE[status] ?? ''}` }, status);
}

// ---------- tables ----------
/**
 * columns: [{ label, render(row) | key, class }]
 */
/** Friendly empty state: emptyState('users', 'No subscribers yet', 'Add one or import a CSV.', button) */
export function emptyState(iconName, title, text, action) {
  return h('div', { class: 'empty' },
    h('div', { class: 'empty-icon' }, icon(iconName || 'inbox')),
    title ? h('strong', {}, title) : null,
    text ? h('div', {}, text) : null,
    action || null);
}

export function table(columns, rows, { onRowClick, empty = 'Nothing here yet.', rowClass } = {}) {
  if (!rows.length) return typeof empty === 'string' ? emptyState('inbox', null, empty) : h('div', { class: 'empty' }, empty);
  return h('div', { class: 'table-wrap' }, h('table', {},
    h('thead', {}, h('tr', {}, columns.map((c) => h('th', { class: c.class }, c.label)))),
    h('tbody', {}, rows.map((row) => h('tr', {
      class: [onRowClick ? 'clickable' : '', rowClass ? rowClass(row) : ''].join(' ').trim() || null,
      onclick: onRowClick ? (e) => { if (!e.target.closest('button, a, input, select')) onRowClick(row); } : null,
    }, columns.map((c) => h('td', { class: c.class }, c.render ? c.render(row) : (row[c.key] ?? '—'))))))));
}

export function pager(data, onPage) {
  if (!data || data.pages <= 1) {
    return data && data.total ? h('div', { class: 'pager' }, h('span', {}, `${fmtNum(data.total)} total`)) : null;
  }
  return h('div', { class: 'pager' },
    h('span', {}, `Page ${data.page} of ${data.pages} · ${fmtNum(data.total)} total`),
    h('div', { class: 'row' },
      h('button', { class: 'sm', disabled: data.page <= 1, onclick: () => onPage(data.page - 1) }, 'Previous'),
      h('button', { class: 'sm', disabled: data.page >= data.pages, onclick: () => onPage(data.page + 1) }, 'Next')));
}

export function tile(label, value, hint, meter, iconName) {
  return h('div', { class: 'tile' },
    h('div', { class: 'tile-top' }, h('div', { class: 'label' }, label),
      iconName ? h('div', { class: 'tile-icon' }, icon(iconName)) : null),
    h('div', { class: 'value' }, value),
    hint ? h('div', { class: 'hint' }, hint) : null,
    meter !== undefined ? h('div', { class: 'meter', role: 'meter', 'aria-valuenow': Math.round(meter), 'aria-valuemin': 0, 'aria-valuemax': 100 },
      h('div', { style: { width: `${Math.min(Math.max(meter, 0), 100)}%` } })) : null);
}

export function pageHead(title, sub, actions = [], crumbs) {
  return h('div', { class: 'page-head' },
    h('div', {}, crumbs ? h('div', { class: 'crumbs' }, crumbs) : null, h('h1', {}, title),
      sub ? h('div', { class: 'sub' }, sub) : null),
    h('div', { class: 'row' }, actions));
}

/** Shimmering placeholder rows while data loads. */
export function loading(rows = 6) {
  const widths = ['70%', '55%', '40%', '30%'];
  return h('div', { class: 'skeleton-rows', 'aria-busy': 'true', 'aria-label': 'Loading' },
    Array.from({ length: rows }, (_, r) => h('div', { class: 'skeleton-row' },
      widths.map((w, i) => h('div', { class: 'skeleton', style: { width: i === 0 ? `${60 + ((r * 13) % 35)}%` : w } })))));
}

export function loadingTiles(n = 6) {
  return h('div', { class: 'skeleton-tiles' }, Array.from({ length: n }, () => h('div', { class: 'skeleton' })));
}

/** Removable chip for an active filter. */
export function filterChip(label, onRemove) {
  return h('span', { class: 'filter-chip' }, label,
    h('button', { type: 'button', 'aria-label': `Remove filter ${label}`, onclick: onRemove }, icon('x')));
}

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    toast('Copied to clipboard');
  } catch {
    toast('Copy failed: select the text and copy it manually', 'error');
  }
}

/** Local datetime-local input value -> ISO string with timezone. */
export function localInputToIso(value) {
  return value ? new Date(value).toISOString() : null;
}

export function navigate(path) { location.hash = `#/${path}`; }
