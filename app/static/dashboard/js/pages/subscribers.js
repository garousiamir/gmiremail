import { api } from '../api.js';
import {
  badge, busy, clear, confirmDialog, debounce, emptyState, field, filterChip, fmtDate, fmtNum, fmtPct, h, icon, loading,
  modal, navigate, pageHead, pager, relTime, select, table, toast, toastError,
} from '../ui.js';
import { dateRange } from '../components/daterange.js';
import { loadRuleContext, parseValue, ruleBuilder, STATUSES } from '../components/rules.js';

export { parseValue };

export async function render(main) {
  const state = { page: 1, search: '', status: '', tag: '', segment_id: '', subscribed: { from: '', to: '' },
    engagement_min: '', engagement_max: '', rules: null };
  const selected = new Map(); // id -> email
  let allMatching = false;
  let lastData = null;

  const [segments, context] = await Promise.all([
    api.get('/api/segments', { per_page: 100 }).then((d) => d.items),
    loadRuleContext(),
  ]);

  const listHost = h('div', {}, loading());
  const chipsHost = h('div', { class: 'filter-chips' });
  const bannerHost = h('div');
  const bulkHost = h('div');

  const search = h('input', { type: 'search', placeholder: 'Search email or name', 'aria-label': 'Search subscribers',
    oninput: debounce(() => { state.search = search.value.trim(); reset(); }) });
  const statusSel = select([{ value: '', label: 'Any status' }, ...STATUSES], '', {
    'aria-label': 'Status', onchange: (e) => { state.status = e.target.value; reset(); } });
  const tagSel = select([{ value: '', label: 'Any tag' }, ...context.tags], '', {
    'aria-label': 'Tag', onchange: (e) => { state.tag = e.target.value; reset(); } });
  const segSel = select([{ value: '', label: 'Any segment' }, ...segments.map((sg) => ({ value: sg.id, label: sg.name }))], '', {
    'aria-label': 'Segment', onchange: (e) => { state.segment_id = e.target.value; reset(); } });
  const subscribedRange = dateRange({ label: 'Subscribed date', onChange: (r) => { state.subscribed = r; reset(); } });

  // Advanced filter panel
  const engMin = h('input', { type: 'number', min: 0, max: 100, placeholder: 'min', 'aria-label': 'Engagement from', style: { width: '90px' } });
  const engMax = h('input', { type: 'number', min: 0, max: 100, placeholder: 'max', 'aria-label': 'Engagement to', style: { width: '90px' } });
  const builder = ruleBuilder({ rules: null, context, intro: 'Also require', allowJson: false, onChange: () => {} });
  const panel = h('div', { class: 'filter-panel', hidden: true },
    h('div', { class: 'row', style: { marginBottom: '14px' } }, h('strong', {}, 'Engagement score'), engMin, h('span', { class: 'muted' }, 'to'), engMax),
    builder.el,
    h('div', { class: 'row', style: { marginTop: '14px', justifyContent: 'flex-end' } },
      h('button', { type: 'button', class: 'ghost sm', onclick: () => { engMin.value = ''; engMax.value = ''; builder.set(null); applyAdvanced(); } }, 'Clear'),
      h('button', { type: 'button', class: 'primary sm', onclick: () => applyAdvanced() }, 'Apply filters')));
  const moreBtn = h('button', { onclick: () => { panel.hidden = !panel.hidden; } }, icon('sliders'), 'More filters');
  function applyAdvanced() {
    state.engagement_min = engMin.value;
    state.engagement_max = engMax.value;
    state.rules = builder.isEmpty() ? null : builder.get();
    reset();
  }

  const exportBtn = h('button', { onclick: () => busy(exportBtn, () => api.download('/api/subscribers/export',
    filterBody(), `subscribers-${new Date().toISOString().slice(0, 10)}.csv`)) }, icon('download'), 'Export');

  clear(main,
    pageHead('Subscribers', 'Everyone on your list. Filter, select and act on groups of people.', [
      h('button', { onclick: () => importDialog(load) }, icon('upload'), 'Import CSV'),
      exportBtn,
      h('button', { class: 'primary', onclick: () => editDialog(null, load) }, icon('plus'), 'Add subscriber'),
    ]),
    h('div', { class: 'card' },
      h('div', { class: 'toolbar' }, search, statusSel, context.tags.length ? tagSel : null, segments.length ? segSel : null,
        subscribedRange.el, moreBtn, h('span', { class: 'grow' }),
        h('button', { class: 'ghost sm', title: 'Save these filters as a segment', onclick: saveAsSegment }, icon('filter'), 'Save as segment')),
      panel, chipsHost, bannerHost, listHost),
    bulkHost);

  function filterBody() {
    const body = {};
    for (const key of ['search', 'status', 'tag', 'segment_id', 'engagement_min', 'engagement_max']) if (state[key] !== '') body[key] = state[key];
    if (state.subscribed.from) body.subscribed_from = state.subscribed.from;
    if (state.subscribed.to) body.subscribed_to = state.subscribed.to;
    if (state.rules) body.rules = state.rules;
    return body;
  }

  function activeFilters() {
    const out = [];
    if (state.search) out.push([`Search: ${state.search}`, () => { search.value = ''; state.search = ''; }]);
    if (state.status) out.push([`Status: ${state.status}`, () => { statusSel.value = ''; state.status = ''; }]);
    if (state.tag) out.push([`Tag: ${state.tag}`, () => { tagSel.value = ''; state.tag = ''; }]);
    if (state.segment_id) out.push([`Segment: ${segments.find((x) => x.id === state.segment_id)?.name}`, () => { segSel.value = ''; state.segment_id = ''; }]);
    if (state.subscribed.from || state.subscribed.to) {
      out.push([`Subscribed: ${subscribedRange.describe()}`, () => { subscribedRange.reset(); state.subscribed = { from: '', to: '' }; }]);
    }
    if (state.engagement_min !== '' || state.engagement_max !== '') {
      out.push([`Engagement ${state.engagement_min || 0}–${state.engagement_max || 100}`, () => { engMin.value = engMax.value = ''; state.engagement_min = state.engagement_max = ''; }]);
    }
    if (state.rules) out.push([`${state.rules.rules.length} custom rule${state.rules.rules.length > 1 ? 's' : ''}`, () => { builder.set(null); state.rules = null; }]);
    return out;
  }

  function drawChips() {
    const filters = activeFilters();
    clear(chipsHost, filters.map(([label, remove]) => filterChip(label, () => { remove(); reset(); })),
      filters.length > 1 ? h('button', { class: 'link-btn', onclick: () => { filters.forEach(([, remove]) => remove()); reset(); } }, 'Clear all') : null);
  }

  function reset() { state.page = 1; selected.clear(); allMatching = false; load(); }

  function selectionCount() { return allMatching ? (lastData?.total || 0) : selected.size; }

  function drawBulk() {
    const n = selectionCount();
    if (!n) { clear(bulkHost); return; }
    const target = () => (allMatching ? { filters: filterBody() } : { ids: [...selected.keys()] });
    const run = async (btn, action, value, verb) => busy(btn, async () => {
      const r = await api.post('/api/subscribers/bulk-action', { action, value, ...target() });
      toast({ title: verb, message: `${fmtNum(r.affected)} subscriber${r.affected === 1 ? '' : 's'} updated.` });
      selected.clear(); allMatching = false; load();
    });
    const tagBtn = (action, label) => {
      const b = h('button', { onclick: async () => {
        const tag = prompt(action === 'add_tag' ? 'Tag to add' : 'Tag to remove');
        if (tag && tag.trim()) run(b, action, tag.trim(), action === 'add_tag' ? 'Tag added' : 'Tag removed');
      } }, icon('tag'), label);
      return b;
    };
    const statusBtn = h('button', { onclick: () => {
      const m = modal({ title: `Change status of ${fmtNum(n)} subscriber${n === 1 ? '' : 's'}`,
        body: h('div', { class: 'tag-cloud' }, STATUSES.map((st) => h('button', { class: 'tag-toggle', onclick: () => {
          m.close(); run(statusBtn, 'set_status', st, `Status set to ${st}`);
        } }, st))) });
    } }, 'Change status');
    const deleteBtn = h('button', { class: 'danger', onclick: async () => {
      if (!await confirmDialog(`Delete ${fmtNum(n)} subscriber${n === 1 ? '' : 's'}?`, 'They and their email history are removed permanently.',
        { confirmLabel: 'Delete', danger: true })) return;
      run(deleteBtn, 'delete', null, 'Deleted');
    } }, icon('trash'), 'Delete');
    const campaignBtn = h('button', { onclick: async () => {
      const { campaignDialog } = await import('./campaigns.js');
      const audience = allMatching ? audienceFromFilters() : { subscriber_ids: [...selected.keys()] };
      campaignDialog(null, null, { audience, picked: Object.fromEntries(selected) });
    } }, icon('send'), 'Create campaign');
    clear(bulkHost, h('div', { class: 'bulk-bar', role: 'toolbar', 'aria-label': 'Bulk actions' },
      h('strong', {}, `${fmtNum(n)} selected`),
      campaignBtn, tagBtn('add_tag', 'Add tag'), tagBtn('remove_tag', 'Remove tag'), statusBtn, deleteBtn,
      h('button', { class: 'icon', 'aria-label': 'Clear selection', onclick: () => { selected.clear(); allMatching = false; draw(); } }, icon('x'))));
  }

  /** Current filters as segment rules (for "Save as segment" / campaign audience). */
  function filterRules() {
    const rules = [];
    if (state.status) rules.push({ field: 'status', operator: 'equals', value: state.status });
    if (state.tag) rules.push({ field: 'tags', operator: 'contains', value: state.tag });
    if (state.search) rules.push({ field: 'email', operator: 'contains', value: state.search });
    if (state.subscribed.from || state.subscribed.to) rules.push({ field: 'subscribed_at', operator: 'between', value: [state.subscribed.from, state.subscribed.to] });
    if (state.engagement_min !== '' || state.engagement_max !== '') rules.push({ field: 'engagement_score', operator: 'between', value: [state.engagement_min, state.engagement_max] });
    if (state.rules) rules.push(...(state.rules.logic === 'OR' && state.rules.rules.length > 1 ? [state.rules] : state.rules.rules));
    return { logic: 'AND', rules };
  }
  function audienceFromFilters() {
    const out = {};
    const rules = filterRules();
    if (rules.rules.length) out.rules = rules;
    if (state.segment_id) out.segment_ids = [state.segment_id];
    if (!rules.rules.length && !state.segment_id) return null;
    if (rules.rules.length && state.segment_id) {
      // Both: people in the segment who also match the filters
      out.rules = { logic: 'AND', rules: [...rules.rules, ...(segments.find((x) => x.id === state.segment_id)?.filter_rules?.rules || [])] };
      delete out.segment_ids;
    }
    return out;
  }

  async function saveAsSegment() {
    const rules = filterRules();
    if (state.segment_id) rules.rules.push(...(segments.find((x) => x.id === state.segment_id)?.filter_rules?.rules || []));
    if (!rules.rules.length) { toast({ type: 'info', title: 'Add a filter first', message: 'Filter the list, then save it as a segment.' }); return; }
    const name = prompt('Name for the new segment');
    if (!name || !name.trim()) return;
    try {
      const seg = await api.post('/api/segments', { name: name.trim(), filter_rules: rules });
      toast({ title: 'Segment saved', message: `"${seg.name}" has ${fmtNum(seg.subscriber_count)} subscribers.` });
      navigate(`segments/${seg.id}`);
    } catch (err) { toastError(err); }
  }

  function draw() {
    const data = lastData;
    drawChips();
    const pageIds = data.items.map((x) => x.id);
    const allOnPage = pageIds.length && pageIds.every((id) => selected.has(id));
    const headCheck = h('input', { type: 'checkbox', 'aria-label': 'Select all on this page', checked: allOnPage || allMatching,
      onchange: (e) => {
        allMatching = false;
        data.items.forEach((x) => (e.target.checked ? selected.set(x.id, x.email) : selected.delete(x.id)));
        draw();
      } });
    clear(bannerHost, (allOnPage || allMatching) && data.total > pageIds.length ? h('div', { class: 'select-banner' },
      allMatching
        ? [`All ${fmtNum(data.total)} matching subscribers are selected. `, h('button', { onclick: () => { allMatching = false; selected.clear(); draw(); } }, 'Clear selection')]
        : [`${fmtNum(selected.size)} on this page selected. `, h('button', { onclick: () => { allMatching = true; draw(); } }, `Select all ${fmtNum(data.total)} matching`)]) : null);
    const filtered = activeFilters().length > 0;
    clear(listHost,
      table([
        { label: headCheck, class: 'check', render: (x) => h('input', { type: 'checkbox', 'aria-label': `Select ${x.email}`,
          checked: allMatching || selected.has(x.id), onchange: (e) => {
            if (allMatching) { allMatching = false; data.items.forEach((y) => selected.set(y.id, y.email)); }
            if (e.target.checked) selected.set(x.id, x.email); else selected.delete(x.id);
            draw();
          } }) },
        { label: 'Subscriber', render: (x) => h('div', {}, h('div', { class: 'cell-main' }, x.email),
          h('div', { class: 'cell-sub' }, [x.first_name, x.last_name].filter(Boolean).join(' ') || '—')) },
        { label: 'Status', render: (x) => badge(x.status) },
        { label: 'Tags', render: (x) => (x.tags.length ? x.tags.map((t) => h('span', { class: 'chip' }, t)) : h('span', { class: 'muted' }, '—')) },
        { label: 'Engagement', class: 'num', render: (x) => h('span', { title: `${fmtPct(x.engagement_score)} engagement score` }, Math.round(x.engagement_score)) },
        { label: 'Subscribed', render: (x) => h('span', { class: 'nowrap', title: fmtDate(x.subscribed_at) }, relTime(x.subscribed_at)) },
      ], data.items, {
        onRowClick: (x) => editDialog(x, load),
        rowClass: (x) => (allMatching || selected.has(x.id) ? 'selected' : ''),
        empty: filtered ? emptyState('filter', 'No matches', 'No subscribers match these filters.')
          : emptyState('users', 'No subscribers yet', 'Add people one by one or import a CSV.',
            h('button', { class: 'primary', onclick: () => importDialog(load) }, icon('upload'), 'Import CSV')),
      }),
      pager(data, (p) => { state.page = p; load(); }));
    drawBulk();
  }

  async function load() {
    lastData = await api.post('/api/subscribers/query', { ...filterBody(), page: state.page, per_page: 25 });
    draw();
  }

  await load();
  return () => clear(bulkHost);
}

function customFieldRows(initial) {
  const host = h('div');
  const addRow = (key = '', value = '') => {
    const row = h('div', { class: 'kv' },
      h('input', { placeholder: 'Field', value: key, 'data-role': 'key', 'aria-label': 'Field name' }),
      h('input', { placeholder: 'Value', value: typeof value === 'object' ? JSON.stringify(value) : value, 'data-role': 'value', 'aria-label': 'Field value' }),
      h('button', { type: 'button', class: 'ghost icon', 'aria-label': 'Remove field', onclick: () => row.remove() }, icon('x')));
    host.append(row);
  };
  Object.entries(initial || {}).forEach(([k, v]) => addRow(k, v));
  const collect = () => {
    const out = {};
    for (const row of host.querySelectorAll('.kv')) {
      const key = row.querySelector('[data-role=key]').value.trim();
      const raw = row.querySelector('[data-role=value]').value;
      if (!key) continue;
      out[key] = parseValue(raw);
    }
    return out;
  };
  return { el: h('div', {}, host, h('button', { type: 'button', class: 'sm', onclick: () => addRow() }, icon('plus'), 'Add field')), collect };
}

async function editDialog(subscriber, reload) {
  const isNew = !subscriber;
  const custom = customFieldRows(subscriber?.custom_fields);
  const form = h('form', { class: 'form', onsubmit: (e) => { e.preventDefault(); save(); } },
    field('Email', h('input', { name: 'email', type: 'email', required: true, value: subscriber?.email })),
    h('div', { class: 'form-row' },
      field('First name', h('input', { name: 'first_name', value: subscriber?.first_name })),
      field('Last name', h('input', { name: 'last_name', value: subscriber?.last_name }))),
    h('div', { class: 'form-row' },
      field('Status', select(STATUSES, subscriber?.status || 'active', { name: 'status' })),
      field('Tags', h('input', { name: 'tags', value: (subscriber?.tags || []).join(', '), placeholder: 'vip, customer' }), 'Comma separated')),
    field('Custom fields', custom.el));

  const activity = h('div');
  const saveBtn = h('button', { class: 'primary', onclick: () => save() }, isNew ? 'Add subscriber' : 'Save changes');
  const actions = [h('button', { onclick: () => m.close() }, 'Cancel'), saveBtn];
  if (!isNew) {
    actions.unshift(h('button', { class: 'danger', style: { marginRight: 'auto' }, onclick: remove }, icon('trash'), 'Delete'));
  }
  const m = modal({ title: isNew ? 'Add subscriber' : subscriber.email, body: h('div', {}, form, activity), actions, wide: !isNew });

  if (!isNew) {
    api.get(`/api/subscribers/${subscriber.id}/activity`).then((a) => {
      clear(activity, h('h3', { style: { margin: '20px 0 8px' } }, 'Activity'),
        h('div', { class: 'tiles' },
          h('div', { class: 'tile' }, h('div', { class: 'label' }, 'Emails received'), h('div', { class: 'value' }, fmtNum(a.stats.emails_received))),
          h('div', { class: 'tile' }, h('div', { class: 'label' }, 'Open rate'), h('div', { class: 'value' }, fmtPct(a.stats.open_rate))),
          h('div', { class: 'tile' }, h('div', { class: 'label' }, 'Click rate'), h('div', { class: 'value' }, fmtPct(a.stats.click_rate))),
          h('div', { class: 'tile' }, h('div', { class: 'label' }, 'Engagement score'), h('div', { class: 'value' }, Math.round(a.subscriber.engagement_score)))),
        table([
          { label: 'Subject', key: 'subject_line' },
          { label: 'Status', render: (l) => badge(l.status) },
          { label: 'Sent', render: (l) => fmtDate(l.sent_at) },
        ], a.recent_emails.slice(0, 10), { empty: 'No emails sent to this subscriber yet.' }));
    }).catch(toastError);
  }

  async function save() {
    if (!form.reportValidity()) return;
    const data = Object.fromEntries(new FormData(form));
    const body = {
      email: data.email, first_name: data.first_name || null, last_name: data.last_name || null,
      status: data.status, tags: data.tags.split(',').map((t) => t.trim()).filter(Boolean),
      custom_fields: custom.collect(),
    };
    await busy(saveBtn, async () => {
      if (isNew) {
        await api.post('/api/subscribers', body);
        toast('Subscriber added');
      } else {
        // Removed custom fields are sent as null so the API deletes them
        for (const key of Object.keys(subscriber.custom_fields || {})) {
          if (!(key in body.custom_fields)) body.custom_fields[key] = null;
        }
        await api.put(`/api/subscribers/${subscriber.id}`, body);
        toast('Subscriber saved');
      }
      m.close();
      reload();
    });
  }

  async function remove() {
    if (!await confirmDialog('Delete subscriber?', `${subscriber.email} and their email history will be removed permanently.`,
      { confirmLabel: 'Delete', danger: true })) return;
    try {
      await api.del(`/api/subscribers/${subscriber.id}`);
      toast('Subscriber deleted');
      m.close();
      reload();
    } catch (err) { toastError(err); }
  }
}

function importDialog(reload) {
  const file = h('input', { type: 'file', accept: '.csv,text/csv', required: true });
  const updateExisting = h('input', { type: 'checkbox' });
  const triggerAutomations = h('input', { type: 'checkbox' });
  const result = h('div');
  const importBtn = h('button', { class: 'primary', onclick: run }, icon('upload'), 'Import');
  const m = modal({
    title: 'Import subscribers',
    body: h('div', { class: 'form' },
      h('p', { class: 'secondary' }, 'Upload a CSV with a header row. It needs an ', h('code', {}, 'email'), ' column; ',
        h('code', {}, 'first_name'), ', ', h('code', {}, 'last_name'), ', ', h('code', {}, 'status'), ' and ',
        h('code', {}, 'tags'), ' (comma separated) are optional. Any other column becomes a custom field.'),
      field('CSV file', file),
      h('label', { class: 'check' }, updateExisting, 'Update subscribers that already exist'),
      h('label', { class: 'check' }, triggerAutomations, 'Start "new subscriber" automations for imported people'),
      result),
    actions: [h('button', { onclick: () => m.close() }, 'Close'), importBtn],
  });

  async function run() {
    if (!file.files.length) { toast('Choose a CSV file first', 'error'); return; }
    const form = new FormData();
    form.append('file', file.files[0]);
    form.append('update_existing', updateExisting.checked);
    form.append('trigger_automations', triggerAutomations.checked);
    await busy(importBtn, async () => {
      const r = await api.upload('/api/subscribers/bulk', form);
      clear(result, h('div', { class: 'card', style: { padding: '14px' } },
        h('div', { class: 'row' },
          h('span', { class: 'badge good' }, `${r.created} added`),
          h('span', { class: 'badge info' }, `${r.updated} updated`),
          h('span', { class: 'badge' }, `${r.skipped} skipped`),
          r.failed ? h('span', { class: 'badge bad' }, `${r.failed} invalid`) : null),
        r.errors.length ? h('ul', { class: 'small secondary', style: { margin: '10px 0 0', paddingLeft: '18px' } },
          r.errors.slice(0, 10).map((e) => h('li', {}, `Row ${e.row}${e.email ? ` (${e.email})` : ''}: ${e.error}`))) : null));
      reload();
    });
  }
}
