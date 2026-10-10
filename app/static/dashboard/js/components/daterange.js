// Date-range filter: preset dropdown + custom from/to dates.
import { h, select } from '../ui.js';

const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

export const PRESETS = {
  today: { label: 'Today', range: () => { const t = new Date(); return [iso(t), iso(t)]; } },
  '7': { label: 'Last 7 days', range: () => back(6) },
  '30': { label: 'Last 30 days', range: () => back(29) },
  '90': { label: 'Last 90 days', range: () => back(89) },
  month: { label: 'This month', range: () => { const t = new Date(); return [iso(new Date(t.getFullYear(), t.getMonth(), 1)), iso(t)]; } },
  last_month: { label: 'Last month', range: () => {
    const t = new Date();
    return [iso(new Date(t.getFullYear(), t.getMonth() - 1, 1)), iso(new Date(t.getFullYear(), t.getMonth(), 0))];
  } },
  year: { label: 'This year', range: () => { const t = new Date(); return [iso(new Date(t.getFullYear(), 0, 1)), iso(t)]; } },
};
function back(days) { const t = new Date(); const f = new Date(t); f.setDate(t.getDate() - days); return [iso(f), iso(t)]; }

/**
 * dateRange({ preset, from, to, onChange, allowAll, label })
 * onChange({ from, to, preset }) - from/to are 'YYYY-MM-DD' or ''.
 */
export function dateRange({ preset = '', from = '', to = '', onChange, allowAll = true, label = 'Date range' }) {
  const state = { preset, from, to };
  if (preset && PRESETS[preset]) [state.from, state.to] = PRESETS[preset].range();
  const fromInput = h('input', { type: 'date', value: state.from, 'aria-label': `${label}: from`, onchange: () => custom() });
  const toInput = h('input', { type: 'date', value: state.to, 'aria-label': `${label}: to`, onchange: () => custom() });
  const customBox = h('span', { class: 'daterange', hidden: state.preset !== 'custom' }, fromInput, h('span', { class: 'sep' }, '→'), toInput);
  const options = [
    ...(allowAll ? [{ value: '', label: `Any ${label.toLowerCase()}` }] : []),
    ...Object.entries(PRESETS).map(([value, p]) => ({ value, label: p.label })),
    { value: 'custom', label: 'Custom range…' },
  ];
  const presetSel = select(options, state.preset, { 'aria-label': label, onchange: (e) => {
    state.preset = e.target.value;
    customBox.hidden = state.preset !== 'custom';
    if (state.preset === 'custom') {
      if (!fromInput.value) [fromInput.value, toInput.value] = PRESETS['30'].range();
      custom();
      return;
    }
    [state.from, state.to] = state.preset ? PRESETS[state.preset].range() : ['', ''];
    emit();
  } });
  function custom() {
    state.from = fromInput.value;
    state.to = toInput.value;
    if (state.from && state.to && state.from > state.to) [state.from, state.to] = [state.to, state.from];
    emit();
  }
  function emit() { onChange?.({ ...state }); }
  const el = h('span', { class: 'daterange' }, presetSel, customBox);
  return {
    el,
    get: () => ({ ...state }),
    reset() { state.preset = ''; state.from = ''; state.to = ''; presetSel.value = ''; customBox.hidden = true; },
    describe() {
      if (!state.from && !state.to) return '';
      if (state.preset && PRESETS[state.preset]) return PRESETS[state.preset].label;
      return `${state.from || '…'} → ${state.to || '…'}`;
    },
  };
}
