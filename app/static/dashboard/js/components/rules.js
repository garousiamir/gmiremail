// Reusable filter-rule builder (segment rule format). Used by Segments,
// the Subscribers advanced filter and the campaign audience.
import { api } from '../api.js';
import { clear, h, icon, select, toast } from '../ui.js';

export const STATUSES = ['active', 'inactive', 'bounced', 'unsubscribed'];

const OPS = {
  equals: 'is', not_equals: 'is not', contains: 'contains', not_contains: 'does not contain',
  starts_with: 'starts with', ends_with: 'ends with', in: 'is one of', not_in: 'is not one of',
  greater_than: 'is greater than', less_than: 'is less than', greater_or_equal: 'is at least',
  less_or_equal: 'is at most', is_set: 'is set', is_not_set: 'is empty', between: 'is between',
  within_last_days: 'is in the last … days', not_within_last_days: 'is more than … days ago',
  before: 'is before', after: 'is after',
};
const TYPE_OPS = {
  text: ['equals', 'not_equals', 'contains', 'not_contains', 'starts_with', 'ends_with', 'in', 'not_in', 'is_set', 'is_not_set'],
  status: ['equals', 'not_equals', 'in', 'not_in'],
  number: ['equals', 'not_equals', 'greater_than', 'less_than', 'greater_or_equal', 'less_or_equal', 'between'],
  date: ['within_last_days', 'not_within_last_days', 'between', 'before', 'after', 'is_set', 'is_not_set'],
  tags: ['contains', 'not_contains', 'is_set', 'is_not_set'],
  campaign: ['equals', 'not_equals'],
  custom: ['equals', 'not_equals', 'contains', 'not_contains', 'in', 'not_in', 'greater_than', 'less_than', 'between', 'is_set', 'is_not_set'],
};
const CAMPAIGN_OPS = { equals: 'did', not_equals: 'did not' };

export const STANDARD_FIELDS = [
  { value: 'email', label: 'Email', type: 'text' },
  { value: 'first_name', label: 'First name', type: 'text' },
  { value: 'last_name', label: 'Last name', type: 'text' },
  { value: 'status', label: 'Status', type: 'status' },
  { value: 'tags', label: 'Tags', type: 'tags' },
  { value: 'subscribed_at', label: 'Subscribed date', type: 'date' },
  { value: 'created_at', label: 'Added date', type: 'date' },
  { value: 'last_opened_at', label: 'Last opened', type: 'date' },
  { value: 'last_clicked_at', label: 'Last clicked', type: 'date' },
  { value: 'engagement_score', label: 'Engagement score (0-100)', type: 'number' },
  { value: 'total_opens', label: 'Total opens', type: 'number' },
  { value: 'total_clicks', label: 'Total clicks', type: 'number' },
  { value: 'bounce_count', label: 'Bounce count', type: 'number' },
  { value: 'campaign_received', label: 'Received campaign', type: 'campaign' },
  { value: 'campaign_opened', label: 'Opened campaign', type: 'campaign' },
  { value: 'campaign_clicked', label: 'Clicked campaign', type: 'campaign' },
];

/** "12" -> 12, "true" -> true, otherwise the string. */
export function parseValue(raw) {
  const v = String(raw).trim();
  if (v === 'true') return true;
  if (v === 'false') return false;
  if (v !== '' && !Number.isNaN(Number(v))) return Number(v);
  return raw;
}

export function isFlat(rules) {
  return !(rules?.rules || []).some((r) => r && 'rules' in r);
}

/** Field list (incl. custom fields), tags in use and sent campaigns. */
export async function loadRuleContext() {
  const [fields, campaigns] = await Promise.all([
    api.get('/api/subscribers/fields'),
    api.get('/api/campaigns', { per_page: 100 }).then((d) => d.items.filter((c) => c.send_time)),
  ]);
  return {
    tags: fields.tags,
    campaigns,
    fieldDefs: [
      ...STANDARD_FIELDS,
      ...fields.custom_fields.map((key) => ({ value: `custom_fields.${key}`, label: `Custom: ${key}`, type: 'custom' })),
    ],
  };
}

const today = () => new Date().toISOString().slice(0, 10);

/**
 * ruleBuilder({ rules, context, onChange, intro, allowJson })
 * -> { el, get(): rules|null (null = invalid JSON), set(rules), isEmpty() }
 */
export function ruleBuilder({ rules: initial, context, onChange = () => {}, intro = 'Subscribers matching', allowJson = true }) {
  const { fieldDefs, tags, campaigns } = context;
  let rules = structuredClone(initial || { logic: 'AND', rules: [] });
  if (!Array.isArray(rules.rules)) rules.rules = [];
  let jsonMode = !isFlat(rules);
  const host = h('div', { class: 'rule-builder' });
  const jsonArea = h('textarea', { class: 'code', style: { minHeight: '220px' }, 'aria-label': 'Rules JSON', oninput: () => onChange() });
  const fieldType = (name) => fieldDefs.find((f) => f.value === name)?.type || 'custom';

  function defaultValue(type, op) {
    if (op === 'between') return type === 'date' ? ['', today()] : ['', ''];
    if (type === 'status') return 'active';
    if (type === 'number') return 0;
    if (type === 'date') return 30;
    if (type === 'campaign') return campaigns[0]?.id || '';
    return '';
  }

  function valueInput(rule, type) {
    const op = rule.operator;
    const changed = () => onChange();
    if (['is_set', 'is_not_set'].includes(op)) return h('span');
    if (op === 'between') {
      const pair = Array.isArray(rule.value) ? rule.value : ['', ''];
      rule.value = pair;
      const asDate = type === 'date' || (type === 'custom' && /^\d{4}-/.test(String(pair[0] || pair[1] || '')));
      const mk = (i, label) => h('input', {
        type: asDate ? 'date' : (type === 'number' ? 'number' : 'text'), value: String(pair[i] ?? '').slice(0, asDate ? 10 : undefined),
        'aria-label': label, placeholder: asDate ? '' : (i ? 'to' : 'from'),
        oninput: (e) => { pair[i] = type === 'number' && e.target.value !== '' ? Number(e.target.value) : e.target.value; changed(); },
      });
      return h('div', { class: 'rule-value-pair' }, mk(0, 'From'), h('span', { class: 'sep' }, 'and'), mk(1, 'To'));
    }
    if (['in', 'not_in'].includes(op)) {
      return h('input', { value: (rule.value || []).join(', '), placeholder: 'a, b, c', 'aria-label': 'Values',
        oninput: (e) => { rule.value = e.target.value.split(',').map((v) => v.trim()).filter(Boolean).map((v) => (type === 'custom' ? parseValue(v) : v)); changed(); } });
    }
    if (type === 'status') return select(STATUSES, rule.value, { 'aria-label': 'Value', onchange: (e) => { rule.value = e.target.value; changed(); } });
    if (type === 'campaign') {
      if (!campaigns.length) return h('span', { class: 'muted small' }, 'No sent campaigns yet');
      return select(campaigns.map((c) => ({ value: c.id, label: c.name })), rule.value,
        { 'aria-label': 'Campaign', onchange: (e) => { rule.value = e.target.value; changed(); } });
    }
    if (['within_last_days', 'not_within_last_days'].includes(op)) {
      return h('div', { class: 'row', style: { flexWrap: 'nowrap' } },
        h('input', { type: 'number', min: 1, value: rule.value, 'aria-label': 'Days', oninput: (e) => { rule.value = Number(e.target.value); changed(); } }),
        h('span', { class: 'muted small' }, 'days'));
    }
    if (type === 'date') {
      return h('input', { type: 'date', value: String(rule.value || '').slice(0, 10), 'aria-label': 'Date',
        oninput: (e) => { rule.value = e.target.value || ''; changed(); } });
    }
    if (type === 'number') {
      return h('input', { type: 'number', value: rule.value, 'aria-label': 'Value', oninput: (e) => { rule.value = Number(e.target.value); changed(); } });
    }
    if (type === 'tags' && tags.length) {
      const list = `tags-${Math.random().toString(36).slice(2)}`;
      return h('div', {}, h('input', { value: rule.value || '', list, 'aria-label': 'Tag', placeholder: 'Tag', oninput: (e) => { rule.value = e.target.value; changed(); } }),
        h('datalist', { id: list }, tags.map((t) => h('option', { value: t }))));
    }
    return h('input', { value: rule.value ?? '', 'aria-label': 'Value',
      oninput: (e) => { rule.value = type === 'custom' ? parseValue(e.target.value) : e.target.value; changed(); } });
  }

  function ruleRow(rule, index) {
    const type = fieldType(rule.field);
    const options = fieldDefs.some((f) => f.value === rule.field) || !rule.field
      ? fieldDefs : [...fieldDefs, { value: rule.field, label: `Custom: ${rule.field.replace(/^custom_fields\./, '')}` }];
    const fieldSel = select([...options.map((f) => ({ value: f.value, label: f.label })), { value: '__other', label: 'Other custom field…' }],
      rule.field, { 'aria-label': 'Field', onchange: (e) => {
        let value = e.target.value;
        if (value === '__other') {
          const key = prompt('Custom field name');
          if (!key) { draw(); return; }
          value = `custom_fields.${key.trim()}`;
        }
        const t = fieldType(value);
        rules.rules[index] = { field: value, operator: TYPE_OPS[t][0], value: defaultValue(t, TYPE_OPS[t][0]) };
        draw();
      } });
    const labels = type === 'campaign' ? CAMPAIGN_OPS : OPS;
    const ops = TYPE_OPS[type].includes(rule.operator) ? TYPE_OPS[type] : [...TYPE_OPS[type], rule.operator];
    const opSel = select(ops.map((op) => ({ value: op, label: labels[op] || op })), rule.operator, {
      'aria-label': 'Condition', onchange: (e) => {
        const op = e.target.value;
        rule.operator = op;
        if (['is_set', 'is_not_set'].includes(op)) delete rule.value;
        else if (op === 'between') rule.value = defaultValue(type, op);
        else if (['within_last_days', 'not_within_last_days'].includes(op)) rule.value = 30;
        else if (['in', 'not_in'].includes(op)) rule.value = Array.isArray(rule.value) ? rule.value : (rule.value ? [rule.value] : []);
        else if (Array.isArray(rule.value) || typeof rule.value === 'number' && type === 'date') rule.value = type === 'date' ? today() : '';
        draw();
      } });
    return h('div', { class: 'rule', style: { marginBottom: '8px' } }, fieldSel, opSel, valueInput(rule, type),
      h('button', { type: 'button', class: 'ghost icon', 'aria-label': 'Remove rule', onclick: () => { rules.rules.splice(index, 1); draw(); } }, icon('x')));
  }

  function draw() {
    if (jsonMode) {
      jsonArea.value = JSON.stringify(rules, null, 2);
      clear(host, h('p', { class: 'small muted' }, 'Advanced mode: edit the rules as JSON (supports nested groups).'), jsonArea,
        isFlat(rules) ? h('button', { type: 'button', class: 'sm', style: { marginTop: '8px' }, onclick: () => {
          const parsed = get();
          if (parsed && isFlat(parsed)) { rules = parsed; jsonMode = false; draw(); } else toast('Nested groups can only be edited as JSON', 'error');
        } }, 'Back to visual editor') : null);
    } else {
      const logic = select([{ value: 'AND', label: 'all' }, { value: 'OR', label: 'any' }], rules.logic || 'AND', {
        style: { width: 'auto', display: 'inline-block', margin: '0 6px' }, 'aria-label': 'Match',
        onchange: (e) => { rules.logic = e.target.value; onChange(); } });
      clear(host,
        h('div', { class: 'row', style: { marginBottom: '12px' } }, intro, logic, 'of these rules:'),
        rules.rules.length ? rules.rules.map(ruleRow) : h('p', { class: 'muted small' }, 'No rules yet.'),
        h('div', { class: 'row', style: { marginTop: '8px' } },
          h('button', { type: 'button', class: 'sm', onclick: () => {
            rules.rules.push({ field: 'subscribed_at', operator: 'within_last_days', value: 30 });
            draw();
          } }, icon('plus'), 'Add rule'),
          allowJson ? h('button', { type: 'button', class: 'ghost sm', onclick: () => { jsonMode = true; draw(); } }, 'Edit as JSON') : null));
    }
    onChange();
  }

  function get() {
    if (!jsonMode) return rules;
    try {
      rules = JSON.parse(jsonArea.value);
      return rules;
    } catch {
      return null;
    }
  }

  draw();
  return {
    el: host,
    get,
    set(next) { rules = structuredClone(next || { logic: 'AND', rules: [] }); jsonMode = !isFlat(rules); draw(); },
    isEmpty() { const r = get(); return !r || !(r.rules || []).length; },
  };
}
