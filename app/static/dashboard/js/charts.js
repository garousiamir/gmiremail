// Small dependency-free SVG charts: multi-series line and single-series
// column, each with a hover tooltip, legend (2+ series) and a table view.
import { clear, fmtNum, h, s } from './ui.js';

const PAD = { top: 10, right: 12, bottom: 26, left: 44 };

// Axis scale for counts: a 1/2/5 x 10^k step (never below 1) and a max that
// is a whole number of steps, so ticks are clean integers.
function scale(dataMax, target = 4) {
  const raw = Math.max(dataMax, 1) / target;
  const exp = 10 ** Math.floor(Math.log10(raw));
  const step = Math.max(1, [1, 2, 5, 10].map((m) => m * exp).find((v) => v >= raw));
  const max = Math.max(step, Math.ceil(dataMax / step) * step);
  return { max, ticks: Array.from({ length: Math.round(max / step) + 1 }, (_, i) => i * step) };
}

function tickLabel(v) {
  return v >= 1000 ? new Intl.NumberFormat(undefined, { notation: 'compact' }).format(v) : fmtNum(Math.round(v * 10) / 10);
}

function legend(series) {
  if (series.length < 2) return null;
  return h('div', { class: 'legend' }, series.map((sr) => h('span', { class: 'key' },
    h('span', { class: 'swatch', style: { background: `var(${sr.color})` } }), sr.label)));
}

function tableView(data, columns) {
  const wrap = h('div', { class: 'chart-table', hidden: true }, h('table', {},
    h('thead', {}, h('tr', {}, columns.map((c) => h('th', { class: c.num ? 'num' : '' }, c.label)))),
    h('tbody', {}, data.map((row) => h('tr', {}, columns.map((c) => h('td', { class: c.num ? 'num' : '' },
      c.format ? c.format(row[c.key]) : row[c.key])))))));
  const toggle = h('button', {
    class: 'link-btn', type: 'button',
    onclick: () => { wrap.hidden = !wrap.hidden; toggle.textContent = wrap.hidden ? 'Show as table' : 'Hide table'; },
  }, 'Show as table');
  return [h('div', { class: 'row', style: { marginTop: '6px' } }, toggle), wrap];
}

function responsive(container, draw) {
  let width = 0;
  let attached = false;
  const render = () => {
    if (container.isConnected) attached = true;
    else if (attached) { ro.disconnect(); return; } // page navigated away
    const w = Math.max(container.clientWidth, 280);
    if (w === width) return;
    width = w;
    draw(w);
  };
  const ro = new ResizeObserver(render);
  ro.observe(container);
  render();
}

function positionTooltip(tip, chartEl, x, y) {
  const box = chartEl.getBoundingClientRect();
  tip.hidden = false;
  const tw = tip.offsetWidth;
  let left = x + 14;
  if (left + tw > box.width) left = x - tw - 14;
  tip.style.left = `${Math.max(left, 0)}px`;
  tip.style.top = `${Math.max(y - 10, 0)}px`;
}

/**
 * lineChart({ data, x, series: [{ key, label, color: '--series-1' }], formatX, height, ariaLabel })
 */
export function lineChart({ data, x, series, formatX = (v) => v, height = 220, ariaLabel = 'Line chart' }) {
  const plot = h('div', { class: 'chart' });
  const tip = h('div', { class: 'tooltip', hidden: true });
  const root = h('div', {}, legend(series), plot,
    tableView(data, [{ key: x, label: 'Date', format: formatX },
      ...series.map((sr) => ({ key: sr.key, label: sr.label, num: true, format: fmtNum }))]));

  responsive(plot, (width) => {
    const innerW = width - PAD.left - PAD.right;
    const innerH = height - PAD.top - PAD.bottom;
    const { max, ticks } = scale(Math.max(0, ...data.flatMap((d) => series.map((sr) => d[sr.key] || 0))));
    const n = data.length;
    const px = (i) => PAD.left + (n <= 1 ? innerW / 2 : (innerW * i) / (n - 1));
    const py = (v) => PAD.top + innerH - (innerH * (v || 0)) / max;

    const grid = ticks.map((t) => [
      s('line', { class: t === 0 ? 'baseline' : 'grid-line', x1: PAD.left, x2: width - PAD.right, y1: py(t), y2: py(t) }),
      s('text', { class: 'tick', x: PAD.left - 8, y: py(t) + 4, 'text-anchor': 'end' }, tickLabel(t)),
    ]);
    const labelEvery = Math.max(1, Math.ceil(n / Math.max(2, Math.floor(innerW / 80))));
    const xLabels = data.map((d, i) => (i % labelEvery === 0 || i === n - 1) && !(i !== n - 1 && n - 1 - i < labelEvery / 2)
      ? s('text', { class: 'tick', x: px(i), y: height - 6, 'text-anchor': i === 0 ? 'start' : i === n - 1 ? 'end' : 'middle' }, formatX(d[x]))
      : null);
    const lines = series.map((sr) => s('path', {
      class: 'line', stroke: `var(${sr.color})`,
      d: data.map((d, i) => `${i ? 'L' : 'M'}${px(i).toFixed(1)},${py(d[sr.key]).toFixed(1)}`).join(''),
    }));
    // End dots on the latest point
    const ends = n ? series.map((sr) => s('circle', { class: 'dot', r: 4, cx: px(n - 1), cy: py(data[n - 1][sr.key]), fill: `var(${sr.color})` })) : [];

    const cross = s('line', { class: 'crosshair', y1: PAD.top, y2: PAD.top + innerH, visibility: 'hidden' });
    const hoverDots = series.map((sr) => s('circle', { class: 'dot', r: 4, fill: `var(${sr.color})`, visibility: 'hidden' }));
    const hide = () => { cross.setAttribute('visibility', 'hidden'); hoverDots.forEach((d) => d.setAttribute('visibility', 'hidden')); tip.hidden = true; };
    const overlay = s('rect', {
      x: PAD.left, y: PAD.top, width: innerW, height: innerH, fill: 'transparent',
      onmousemove: (e) => {
        if (!n) return;
        const rect = svg.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const i = Math.min(n - 1, Math.max(0, Math.round(((mx - PAD.left) / innerW) * (n - 1))));
        const d = data[i];
        cross.setAttribute('x1', px(i)); cross.setAttribute('x2', px(i)); cross.setAttribute('visibility', 'visible');
        hoverDots.forEach((dot, k) => { dot.setAttribute('cx', px(i)); dot.setAttribute('cy', py(d[series[k].key])); dot.setAttribute('visibility', 'visible'); });
        clear(tip, h('div', { class: 't-title' }, formatX(d[x])), series.map((sr) => h('div', { class: 't-row' },
          h('span', {}, h('span', { class: 'swatch', style: { background: `var(${sr.color})` } }), sr.label),
          h('strong', { class: 'num' }, fmtNum(d[sr.key] || 0)))));
        positionTooltip(tip, plot, px(i), e.clientY - rect.top);
      },
      onmouseleave: hide,
    });
    const svg = s('svg', { viewBox: `0 0 ${width} ${height}`, height, role: 'img', 'aria-label': ariaLabel },
      grid, xLabels, lines, ends, cross, hoverDots, overlay);
    clear(plot, svg, tip);
  });
  return root;
}

function columnPath(x, y, w, base) {
  const r = Math.min(4, w / 2, Math.max(base - y, 0));
  if (base - y <= 0) return '';
  return `M${x},${base}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${base}Z`;
}

/**
 * columnChart({ data, x, y, label, color, formatX, height, ariaLabel })
 */
export function columnChart({ data, x, y, label, color = '--series-1', formatX = (v) => v, height = 200, ariaLabel = 'Column chart' }) {
  const plot = h('div', { class: 'chart' });
  const tip = h('div', { class: 'tooltip', hidden: true });
  const root = h('div', {}, plot,
    tableView(data, [{ key: x, label: 'Bucket', format: formatX }, { key: y, label, num: true, format: fmtNum }]));

  responsive(plot, (width) => {
    const innerW = width - PAD.left - PAD.right;
    const innerH = height - PAD.top - PAD.bottom;
    const { max, ticks } = scale(Math.max(0, ...data.map((d) => d[y] || 0)));
    const n = data.length || 1;
    const band = innerW / n;
    const barW = Math.min(24, Math.max(band - 2, 2) * 0.7);
    const base = PAD.top + innerH;
    const py = (v) => base - (innerH * (v || 0)) / max;

    const grid = ticks.map((t) => [
      s('line', { class: t === 0 ? 'baseline' : 'grid-line', x1: PAD.left, x2: width - PAD.right, y1: py(t), y2: py(t) }),
      s('text', { class: 'tick', x: PAD.left - 8, y: py(t) + 4, 'text-anchor': 'end' }, tickLabel(t)),
    ]);
    const labelEvery = Math.max(1, Math.ceil(n / Math.max(2, Math.floor(innerW / 44))));
    const bars = data.map((d, i) => {
      const cx = PAD.left + band * i + band / 2;
      const bar = s('path', { class: 'bar', fill: `var(${color})`, d: columnPath(cx - barW / 2, py(d[y]), barW, base) });
      const hit = s('rect', {
        x: PAD.left + band * i, y: PAD.top, width: band, height: innerH, fill: 'transparent',
        onmousemove: (e) => {
          bar.classList.add('hover');
          clear(tip, h('div', { class: 't-title' }, formatX(d[x])),
            h('div', { class: 't-row' }, h('span', {}, h('span', { class: 'swatch', style: { background: `var(${color})` } }), label),
              h('strong', { class: 'num' }, fmtNum(d[y] || 0))));
          positionTooltip(tip, plot, cx, e.clientY - svg.getBoundingClientRect().top);
        },
        onmouseleave: () => { bar.classList.remove('hover'); tip.hidden = true; },
      });
      const lbl = i % labelEvery === 0
        ? s('text', { class: 'tick', x: cx, y: height - 6, 'text-anchor': 'middle' }, formatX(d[x])) : null;
      return [bar, lbl, hit];
    });
    const svg = s('svg', { viewBox: `0 0 ${width} ${height}`, height, role: 'img', 'aria-label': ariaLabel }, grid, bars);
    clear(plot, svg, tip);
  });
  return root;
}
