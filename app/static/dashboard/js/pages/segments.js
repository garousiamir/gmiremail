import { api, errorMessage } from '../api.js';
import {
  busy, clear, confirmDialog, debounce, field, fmtNum, h, icon, loading, navigate, pageHead, pager, relTime,
  select, table, toast, toastError,
} from '../ui.js';
import { parseValue } from './subscribers.js';

const STATUSES = ['active', 'inactive', 'bounced', 'unsubscribed'];

const OPS = {
  equals: 'is', not_equals: 'is not', contains: 'contains', not_contains: 'does not contain',
  starts_with: 'starts with', ends_with: 'ends with', in: 'is one of', not_in: 'is not one of',
  greater_than: 'is greater than', less_than: 'is less than', greater_or_equal: 'is at least',
  less_or_equal: 'is at most', is_set: 'is set', is_not_set: 'is empty',
  within_last_days: 'is within the last … days', before: 'is before', after: 'is after',
};
const TYPE_OPS = {
  text: ['equals', 'not_equals', 'contains', 'not_contains', 'starts_with', 'ends_with', 'in', 'not_in', 'is_set', 'is_not_set'],
  status: ['equals', 'not_equals', 'in', 'not_in'],
  number: ['equals', 'not_equals', 'greater_than', 'less_than', 'greater_or_equal', 'less_or_equal'],
  date: ['within_last_days', 'before', 'after', 'is_set', 'is_not_set'],
  tags: ['contains', 'not_contains', 'is_set', 'is_not_set'],
  campaign: ['equals', 'not_equals'],
  custom: ['equals', 'not_equals', 'contains', 'not_contains', 'in', 'not_in', 'greater_than', 'less_than', 'is_set', 'is_not_set'],
};
const CAMPAIGN_OPS = { equals: 'did', not_equals: 'did not' };

const STANDARD_FIELDS = [
  { value: 'email', label: 'Email', type: 'text' },
  { value: 'first_name', label: 'First name', type: 'text' },
  { value: 'last_name', label: 'Last name', type: 'text' },
  { value: 'status', label: 'Status', type: 'status' },
  { value: 'tags', label: 'Tags', type: 'tags' },
  { value: 'engagement_score', label: 'Engagement score (0-100)', type: 'number' },
  { value: 'total_opens', label: 'Total opens', type: 'number' },
  { value: 'total_clicks', label: 'Total clicks', type: 'number' },
  { value: 'bounce_count', label: 'Bounce count', type: 'number' },
  { value: 'subscribed_at', label: 'Subscribed date', type: 'date' },
  { value: 'created_at', label: 'Added date', type: 'date' },
  { value: 'last_opened_at', label: 'Last opened', type: 'date' },
  { value: 'last_clicked_at', label: 'Last clicked', type: 'date' },
  { value: 'campaign_received', label: 'Received campaign', type: 'campaign' },
  { value: 'campaign_opened', label: 'Opened campaign', type: 'campaign' },
  { value: 'campaign_clicked', label: 'Clicked campaign', type: 'campaign' },
];

export async function renderList(main) {
  let page = 1;
  const host = h('div', {}, loading());
  clear(main, pageHead('Segments', 'Groups of subscribers defined by rules; membership updates automatically', [
    h('button', { class: 'primary', onclick: () => navigate('segments/new') }, icon('plus'), 'New segment'),
  ]), h('div', { class: 'card' }, host));

  async function load() {
    const data = await api.get('/api/segments', { page, per_page: 25 });
    clear(host, table([
      { label: 'Name', render: (s) => h('a', { href: `#/segments/${s.id}` }, s.name) },
      { label: 'Description', render: (s) => s.description || h('span', { class: 'muted' }, '—') },
      { label: 'Rules', class: 'num', render: (s) => (s.filter_rules?.rules || []).length },
      { label: 'Subscribers', class: 'num', render: (s) => fmtNum(s.subscriber_count) },
      { label: 'Counted', render: (s) => relTime(s.count_updated_at) },
    ], data.items, {
      onRowClick: (s) => navigate(`segments/${s.id}`),
      empty: h('div', {}, 'No segments yet. A segment lets you target a campaign at part of your list.', h('br'),
        h('button', { class: 'primary', onclick: () => navigate('segments/new') }, 'Create a segment')),
    }), pager(data, (p) => { page = p; load(); }));
  }
  await load();
}

function isFlat(rules) {
  return !(rules?.rules || []).some((r) => r && 'rules' in r);
}

export async function renderEditor(main, id) {
  const isNew = id === 'new';
  const [segment, fields, campaigns] = await Promise.all([
    isNew ? Promise.resolve({ name: '', description: '', filter_rules: { logic: 'AND', rules: [] } }) : api.get(`/api/segments/${id}`),
    api.get('/api/subscribers/fields'),
    api.get('/api/campaigns', { per_page: 100 }).then((d) => d.items.filter((c) => c.send_time)),
  ]);

  const fieldDefs = [
    ...STANDARD_FIELDS,
    ...fields.custom_fields.map((key) => ({ value: `custom_fields.${key}`, label: `Custom: ${key}`, type: 'custom' })),
  ];
  const fieldType = (name) => fieldDefs.find((f) => f.value === name)?.type || 'custom';

  let rules = structuredClone(segment.filter_rules || { logic: 'AND', rules: [] });
  let jsonMode = !isFlat(rules);

  const name = h('input', { value: segment.name, required: true, 'aria-label': 'Segment name' });
  const description = h('input', { value: segment.description || '', placeholder: 'Optional' });
  const rulesHost = h('div');
  const previewHost = h('div', {}, h('span', { class: 'muted' }, 'Add a rule to see who matches.'));

  const refreshPreview = debounce(async () => {
    const current = collect();
    if (current === null) return;
    try {
      const result = await api.post('/api/segments/preview', { filter_rules: current });
      clear(previewHost,
        h('div', { class: 'tile', style: { marginBottom: '12px' } }, h('div', { class: 'label' }, 'Matching subscribers'),
          h('div', { class: 'value' }, fmtNum(result.subscriber_count))),
        result.sample.length ? h('div', {}, h('div', { class: 'small muted', style: { marginBottom: '6px' } }, 'Most recent matches'),
          h('ul', { style: { margin: 0, paddingLeft: '18px' } }, result.sample.map((s) => h('li', {}, s.email, ' ',
            h('span', { class: 'muted small' }, s.status))))) : null);
    } catch (err) {
      clear(previewHost, h('div', { class: 'error-text' }, errorMessage(err)));
    }
  }, 400);

  function ruleRow(rule, index) {
    const type = fieldType(rule.field);
    const fieldOptions = fieldDefs.some((f) => f.value === rule.field) || !rule.field
      ? fieldDefs : [...fieldDefs, { value: rule.field, label: `Custom: ${rule.field.replace(/^custom_fields\./, '')}` }];
    const fieldSel = select([...fieldOptions.map((f) => ({ value: f.value, label: f.label })), { value: '__other', label: 'Other custom field…' }],
      rule.field, { 'aria-label': 'Field', onchange: (e) => {
        let value = e.target.value;
        if (value === '__other') {
          const key = prompt('Custom field name');
          if (!key) { drawRules(); return; }
          value = `custom_fields.${key.trim()}`;
        }
        const t = fieldType(value);
        rules.rules[index] = { field: value, operator: TYPE_OPS[t][0], value: defaultValue(t) };
        drawRules();
      } });
    const opLabels = type === 'campaign' ? CAMPAIGN_OPS : OPS;
    const opSel = select(TYPE_OPS[type].map((op) => ({ value: op, label: opLabels[op] })), rule.operator, {
      'aria-label': 'Condition', onchange: (e) => {
        rule.operator = e.target.value;
        if (['is_set', 'is_not_set'].includes(rule.operator)) delete rule.value;
        else if (rule.operator === 'within_last_days') rule.value = 30;
        else if (['in', 'not_in'].includes(rule.operator) && !Array.isArray(rule.value)) rule.value = rule.value ? [rule.value] : [];
        else if (Array.isArray(rule.value)) rule.value = rule.value[0] ?? '';
        drawRules();
      } });
    return h('div', { class: 'rule', style: { marginBottom: '8px' } }, fieldSel, opSel, valueInput(rule, type),
      h('button', { class: 'ghost icon', 'aria-label': 'Remove rule', onclick: () => { rules.rules.splice(index, 1); drawRules(); } }, icon('x')));
  }

  function defaultValue(type) {
    if (type === 'status') return 'active';
    if (type === 'number') return 0;
    if (type === 'date') return 30;
    if (type === 'campaign') return campaigns[0]?.id || '';
    return '';
  }

  function valueInput(rule, type) {
    const op = rule.operator;
    const changed = () => refreshPreview();
    if (['is_set', 'is_not_set'].includes(op)) return h('span');
    if (['in', 'not_in'].includes(op)) {
      return h('input', { value: (rule.value || []).join(', '), placeholder: 'a, b, c', 'aria-label': 'Values',
        oninput: (e) => { rule.value = e.target.value.split(',').map((v) => v.trim()).filter(Boolean).map((v) => (type === 'custom' ? parseValue(v) : v)); changed(); } });
    }
    if (type === 'status') {
      return select(STATUSES, rule.value, { 'aria-label': 'Value', onchange: (e) => { rule.value = e.target.value; changed(); } });
    }
    if (type === 'campaign') {
      if (!campaigns.length) return h('span', { class: 'muted small' }, 'No sent campaigns yet');
      return select(campaigns.map((c) => ({ value: c.id, label: c.name })), rule.value,
        { 'aria-label': 'Campaign', onchange: (e) => { rule.value = e.target.value; changed(); } });
    }
    if (op === 'within_last_days') {
      return h('input', { type: 'number', min: 1, value: rule.value, 'aria-label': 'Days', oninput: (e) => { rule.value = Number(e.target.value); changed(); } });
    }
    if (type === 'date') {
      return h('input', { type: 'date', value: (rule.value || '').slice(0, 10), 'aria-label': 'Date',
        oninput: (e) => { rule.value = e.target.value ? new Date(`${e.target.value}T00:00:00`).toISOString() : ''; changed(); } });
    }
    if (type === 'number') {
      return h('input', { type: 'number', value: rule.value, 'aria-label': 'Value', oninput: (e) => { rule.value = Number(e.target.value); changed(); } });
    }
    if (type === 'tags' && fields.tags.length) {
      const list = `tags-${Math.random().toString(36).slice(2)}`;
      return h('div', {}, h('input', { value: rule.value || '', list, 'aria-label': 'Tag', oninput: (e) => { rule.value = e.target.value; changed(); } }),
        h('datalist', { id: list }, fields.tags.map((t) => h('option', { value: t }))));
    }
    return h('input', { value: rule.value ?? '', 'aria-label': 'Value',
      oninput: (e) => { rule.value = type === 'custom' ? parseValue(e.target.value) : e.target.value; changed(); } });
  }

  const jsonArea = h('textarea', { class: 'code', style: { minHeight: '260px' }, 'aria-label': 'Rules JSON', oninput: () => refreshPreview() });

  function drawRules() {
    if (jsonMode) {
      jsonArea.value = JSON.stringify(rules, null, 2);
      clear(rulesHost, h('p', { class: 'small muted' }, 'Advanced mode: edit the rules as JSON (supports nested groups).'), jsonArea,
        isFlat(rules) ? h('button', { class: 'sm', style: { marginTop: '8px' }, onclick: () => {
          const parsed = collect();
          if (parsed && isFlat(parsed)) { rules = parsed; jsonMode = false; drawRules(); }
          else toast('Nested groups can only be edited as JSON', 'error');
        } }, 'Back to visual editor') : null);
    } else {
      const logic = select([{ value: 'AND', label: 'all' }, { value: 'OR', label: 'any' }], rules.logic || 'AND', {
        style: { width: 'auto', display: 'inline-block', margin: '0 6px' }, 'aria-label': 'Match',
        onchange: (e) => { rules.logic = e.target.value; refreshPreview(); } });
      clear(rulesHost,
        h('div', { class: 'row', style: { marginBottom: '12px' } }, 'Subscribers matching', logic, 'of these rules:'),
        rules.rules.length ? rules.rules.map(ruleRow) : h('p', { class: 'muted' }, 'No rules: everyone on your list matches.'),
        h('div', { class: 'row', style: { marginTop: '8px' } },
          h('button', { class: 'sm', onclick: () => { rules.rules.push({ field: 'status', operator: 'equals', value: 'active' }); drawRules(); } },
            icon('plus'), 'Add rule'),
          h('button', { class: 'ghost sm', onclick: () => { jsonMode = true; drawRules(); } }, 'Edit as JSON')));
    }
    refreshPreview();
  }

  function collect() {
    if (!jsonMode) return rules;
    try {
      const parsed = JSON.parse(jsonArea.value);
      rules = parsed;
      return parsed;
    } catch {
      clear(previewHost, h('div', { class: 'error-text' }, 'Invalid JSON'));
      return null;
    }
  }

  const saveBtn = h('button', { class: 'primary', onclick: save }, isNew ? 'Create segment' : 'Save');
  const actions = [h('button', { onclick: () => navigate('segments') }, 'Cancel'), saveBtn];
  if (!isNew) actions.unshift(h('button', { class: 'danger', onclick: remove }, icon('trash'), 'Delete'));

  clear(main,
    pageHead(isNew ? 'New segment' : segment.name, null, actions, h('a', { href: '#/segments' }, '← Segments')),
    h('div', { class: 'editor' },
      h('div', { class: 'stack' },
        h('div', { class: 'card form' }, h('div', { class: 'form-row' }, field('Name', name), field('Description', description))),
        h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Rules')), rulesHost)),
      h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Preview')), previewHost)));
  drawRules();

  async function save() {
    const filterRules = collect();
    if (!filterRules) return;
    if (!name.value.trim()) { toast('Give the segment a name', 'error'); name.focus(); return; }
    await busy(saveBtn, async () => {
      const body = { name: name.value.trim(), description: description.value.trim() || null, filter_rules: filterRules };
      const saved = isNew ? await api.post('/api/segments', body) : await api.put(`/api/segments/${id}`, body);
      toast(isNew ? 'Segment created' : 'Segment saved');
      if (isNew) navigate(`segments/${saved.id}`);
    });
  }

  async function remove() {
    if (!await confirmDialog('Delete segment?', 'Campaigns already sent keep their history.', { confirmLabel: 'Delete', danger: true })) return;
    try {
      await api.del(`/api/segments/${id}`);
      toast('Segment deleted');
      navigate('segments');
    } catch (err) { toastError(err); }
  }
}
