import { api } from '../api.js';
import {
  badge, busy, clear, confirmDialog, debounce, field, fmtDate, fmtNum, fmtPct, h, icon, loading, modal,
  pageHead, pager, relTime, select, table, toast, toastError,
} from '../ui.js';

const STATUSES = ['active', 'inactive', 'bounced', 'unsubscribed'];

export async function render(main) {
  const state = { page: 1, search: '', status: '', tag: '', segment_id: '' };
  const listHost = h('div', {}, loading());
  const segments = (await api.get('/api/segments', { per_page: 100 })).items;
  const fields = await api.get('/api/subscribers/fields');

  const search = h('input', { type: 'search', placeholder: 'Search email or name', 'aria-label': 'Search subscribers',
    oninput: debounce((e) => { state.search = e.target.value.trim(); state.page = 1; load(); }) });
  const statusFilter = select([{ value: '', label: 'Any status' }, ...STATUSES], '', {
    'aria-label': 'Status', onchange: (e) => { state.status = e.target.value; state.page = 1; load(); } });
  const tagFilter = fields.tags.length ? select([{ value: '', label: 'Any tag' }, ...fields.tags], '', {
    'aria-label': 'Tag', onchange: (e) => { state.tag = e.target.value; state.page = 1; load(); } }) : null;
  const segmentFilter = segments.length ? select([{ value: '', label: 'Any segment' },
    ...segments.map((s) => ({ value: s.id, label: s.name }))], '', {
    'aria-label': 'Segment', onchange: (e) => { state.segment_id = e.target.value; state.page = 1; load(); } }) : null;

  const exportBtn = h('button', { onclick: () => busy(exportBtn, () => api.download('/api/subscribers/export',
    { status: state.status, search: state.search, tag: state.tag, segment_id: state.segment_id },
    `subscribers-${new Date().toISOString().slice(0, 10)}.csv`)) }, icon('download'), 'Export CSV');

  clear(main,
    pageHead('Subscribers', 'Everyone on your list', [
      h('button', { onclick: () => importDialog(load) }, icon('upload'), 'Import CSV'),
      exportBtn,
      h('button', { class: 'primary', onclick: () => editDialog(null, load) }, icon('plus'), 'Add subscriber'),
    ]),
    h('div', { class: 'card' }, h('div', { class: 'toolbar' }, search, statusFilter, tagFilter, segmentFilter), listHost));

  async function load() {
    const data = await api.get('/api/subscribers', { ...state, per_page: 25 });
    clear(listHost,
      table([
        { label: 'Email', render: (s) => h('strong', {}, s.email) },
        { label: 'Name', render: (s) => [s.first_name, s.last_name].filter(Boolean).join(' ') || h('span', { class: 'muted' }, '—') },
        { label: 'Status', render: (s) => badge(s.status) },
        { label: 'Tags', render: (s) => s.tags.length ? s.tags.map((t) => h('span', { class: 'chip' }, t)) : h('span', { class: 'muted' }, '—') },
        { label: 'Engagement', class: 'num', render: (s) => Math.round(s.engagement_score) },
        { label: 'Added', render: (s) => h('span', { class: 'nowrap', title: fmtDate(s.created_at) }, relTime(s.created_at)) },
      ], data.items, {
        onRowClick: (s) => editDialog(s, load),
        empty: state.search || state.status || state.tag || state.segment_id
          ? 'No subscribers match these filters.'
          : h('div', {}, 'No subscribers yet. Add one or import a CSV.'),
      }),
      pager(data, (page) => { state.page = page; load(); }));
  }

  await load();
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

/** "12" -> 12, "true" -> true, otherwise the string. */
export function parseValue(raw) {
  const v = raw.trim();
  if (v === 'true') return true;
  if (v === 'false') return false;
  if (v !== '' && !Number.isNaN(Number(v))) return Number(v);
  return raw;
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
