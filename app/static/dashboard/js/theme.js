import { h, icon } from './ui.js';

const KEY = 'emk.theme';
const MODES = ['system', 'light', 'dark'];
const LABELS = { system: 'System theme', light: 'Light mode', dark: 'Dark mode' };
const ICONS = { system: 'monitor', light: 'sun', dark: 'moon' };

export function currentTheme() {
  try {
    const saved = localStorage.getItem(KEY);
    return MODES.includes(saved) ? saved : 'system';
  } catch { return 'system'; }
}

export function setTheme(mode) {
  const root = document.documentElement;
  if (mode === 'system') delete root.dataset.theme; else root.dataset.theme = mode;
  try {
    if (mode === 'system') localStorage.removeItem(KEY); else localStorage.setItem(KEY, mode);
  } catch { /* not remembered, still applied */ }
}

/** Button that cycles System -> Light -> Dark. */
export function themeButton(extraClass = '') {
  const btn = h('button', { type: 'button', class: `icon theme-toggle ${extraClass}`.trim(), onclick: () => {
    const mode = MODES[(MODES.indexOf(currentTheme()) + 1) % MODES.length];
    setTheme(mode);
    draw();
  } });
  function draw() {
    const mode = currentTheme();
    const next = MODES[(MODES.indexOf(mode) + 1) % MODES.length];
    btn.replaceChildren(icon(ICONS[mode]));
    btn.title = `${LABELS[mode]} (click for ${LABELS[next].toLowerCase()})`;
    btn.setAttribute('aria-label', `${LABELS[mode]}. Switch to ${LABELS[next].toLowerCase()}`);
  }
  draw();
  return btn;
}
