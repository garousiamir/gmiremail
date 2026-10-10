// Campaign audience builder: everyone, or any mix of segments, tags,
// hand-picked people and a custom filter, minus exclusions. Live count.
import { api, errorMessage } from '../api.js';
import { clear, debounce, fmtNum, h, icon, spinner } from '../ui.js';
import { ruleBuilder } from './rules.js';

export function audienceBuilder({ audience, segments, context, picked = {} }) {
  const a = {
    segment_ids: [...(audience?.segment_ids || [])],
    tags: [...(audience?.tags || [])],
    subscriber_ids: [...(audience?.subscriber_ids || [])],
    exclude_segment_ids: [...(audience?.exclude_segment_ids || [])],
    exclude_tags: [...(audience?.exclude_tags || [])],
  };
  const labels = new Map(Object.entries(picked)); // subscriber id -> email (for chips)
  const hasIncludes = () => a.segment_ids.length || a.tags.length || a.subscriber_ids.length || (rules && !rules.isEmpty());
  let mode = audience && (audience.segment_ids?.length || audience.tags?.length || audience.subscriber_ids?.length || audience.rules)
    ? 'groups' : 'everyone';
  let rules = null;
  const rulesWrap = h('div');
  const summary = h('div', { class: 'aud-summary' });
  const includeHost = h('div', { class: 'audience' });
  const excludeHost = h('div');

  const refresh = debounce(async () => {
    clear(summary, spinner(), h('span', { class: 'muted' }, 'Counting recipients…'));
    try {
      const r = await api.post('/api/campaigns/audience/preview', { audience: get() });
      clear(summary,
        h('div', { class: 'big' }, fmtNum(r.recipients)),
        h('div', {}, h('strong', {}, r.recipients === 1 ? 'recipient' : 'recipients'),
          h('div', { class: 'small muted' }, r.sample.length
            ? `${r.sample.slice(0, 3).map((s) => s.email).join(', ')}${r.recipients > 3 ? ` and ${fmtNum(r.recipients - 3)} more` : ''}`
            : 'Nobody matches yet. Only active subscribers are counted.')));
    } catch (err) {
      clear(summary, h('span', { class: 'error-text' }, errorMessage(err)));
    }
  }, 350);

  function toggle(list, value) {
    const i = list.indexOf(value);
    if (i === -1) list.push(value); else list.splice(i, 1);
    refresh();
  }

  function segmentList(list) {
    if (!segments.length) return h('p', { class: 'muted small', style: { margin: 0 } }, 'No segments yet. Create them under Segments.');
    return h('div', { class: 'check-list' }, segments.map((s) => h('label', {},
      h('input', { type: 'checkbox', checked: list.includes(s.id), onchange: () => toggle(list, s.id) }),
      s.name, h('span', { class: 'meta' }, fmtNum(s.subscriber_count)))));
  }

  function tagCloud(list) {
    if (!context.tags.length) return h('p', { class: 'muted small', style: { margin: 0 } }, 'No tags in use yet.');
    return h('div', { class: 'tag-cloud' }, context.tags.map((t) => {
      const b = h('button', { type: 'button', class: `tag-toggle${list.includes(t) ? ' on' : ''}`, onclick: () => {
        toggle(list, t);
        b.classList.toggle('on', list.includes(t));
      } }, t);
      return b;
    }));
  }

  function peoplePicker() {
    const results = h('div', { class: 'picker-results', hidden: true });
    const chips = h('div', { class: 'picked' });
    const drawChips = () => clear(chips, a.subscriber_ids.length > 30
      ? h('span', { class: 'chip' }, `${fmtNum(a.subscriber_ids.length)} people selected`)
      : a.subscriber_ids.map((id) => h('span', { class: 'filter-chip' }, labels.get(id) || 'Selected person',
        h('button', { type: 'button', 'aria-label': 'Remove', onclick: () => { toggle(a.subscriber_ids, id); drawChips(); } }, icon('x')))),
    a.subscriber_ids.length ? h('button', { type: 'button', class: 'link-btn', onclick: () => { a.subscriber_ids.length = 0; drawChips(); refresh(); } }, 'Clear') : null);
    const input = h('input', { type: 'search', placeholder: 'Search by email or name to add people…', 'aria-label': 'Add people',
      oninput: debounce(async () => {
        const q = input.value.trim();
        if (q.length < 2) { results.hidden = true; return; }
        const r = await api.get('/api/subscribers', { search: q, status: 'active', per_page: 8 });
        clear(results, r.items.length ? r.items.map((s) => h('button', { type: 'button', onclick: () => {
          labels.set(s.id, s.email);
          if (!a.subscriber_ids.includes(s.id)) { a.subscriber_ids.push(s.id); refresh(); }
          drawChips(); input.value = ''; results.hidden = true; input.focus();
        } }, a.subscriber_ids.includes(s.id) ? icon('check') : icon('plus'), s.email,
        s.first_name ? h('span', { class: 'muted' }, ` · ${s.first_name}`) : null))
          : h('div', { class: 'muted small', style: { padding: '10px' } }, 'No active subscribers match.'));
        results.hidden = false;
      }, 250),
      onblur: () => setTimeout(() => { results.hidden = true; }, 200) });
    drawChips();
    return h('div', {}, h('div', { class: 'picker' }, input, results), chips);
  }

  function section(title, iconName, content, hint) {
    return h('div', { class: 'aud-section' }, h('h3', {}, icon(iconName), title, hint ? h('span', { class: 'count' }, hint) : null), content);
  }

  function draw() {
    if (mode === 'groups') {
      if (!rules) {
        rules = ruleBuilder({ rules: audience?.rules, context, onChange: refresh, intro: 'People matching' });
        clear(rulesWrap, rules.el);
      }
      clear(includeHost,
        section('Segments', 'filter', segmentList(a.segment_ids)),
        section('Tags', 'tag', tagCloud(a.tags), 'anyone with a selected tag'),
        section('Specific people', 'users', peoplePicker()),
        section('Custom filter', 'sliders', rulesWrap, 'e.g. subscribed between two dates'));
      includeHost.hidden = false;
    } else {
      includeHost.hidden = true;
    }
    refresh();
  }

  const modeBtns = h('div', { class: 'aud-mode' });
  function drawMode() {
    clear(modeBtns,
      h('button', { type: 'button', class: `aud-option${mode === 'everyone' ? ' on' : ''}`, onclick: () => { mode = 'everyone'; drawMode(); draw(); } },
        h('strong', {}, 'Everyone'), h('span', {}, 'All active subscribers')),
      h('button', { type: 'button', class: `aud-option${mode === 'groups' ? ' on' : ''}`, onclick: () => { mode = 'groups'; drawMode(); draw(); } },
        h('strong', {}, 'Choose who'), h('span', {}, 'Segments, tags, specific people or a custom filter')));
  }

  const excludeDetails = h('details', { class: 'more', open: a.exclude_segment_ids.length || a.exclude_tags.length },
    h('summary', {}, 'Exclude people'),
    h('div', { class: 'audience' },
      section('Exclude segments', 'filter', segmentList(a.exclude_segment_ids)),
      section('Exclude tags', 'tag', tagCloud(a.exclude_tags))));
  clear(excludeHost, excludeDetails);

  function get() {
    const out = { exclude_segment_ids: a.exclude_segment_ids, exclude_tags: a.exclude_tags };
    if (mode === 'groups') {
      Object.assign(out, { segment_ids: a.segment_ids, tags: a.tags, subscriber_ids: a.subscriber_ids });
      const r = rules?.get();
      if (r && (r.rules || []).length) out.rules = r;
    }
    const any = Object.values(out).some((v) => (Array.isArray(v) ? v.length : v));
    return any ? out : null;
  }

  drawMode();
  draw();
  return {
    el: h('div', { class: 'audience' }, modeBtns, includeHost, excludeHost, summary),
    get,
    isValid: () => mode === 'everyone' || hasIncludes(),
  };
}
