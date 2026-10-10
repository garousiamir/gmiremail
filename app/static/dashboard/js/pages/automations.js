import { api } from '../api.js';
import {
  badge, busy, clear, confirmDialog, emptyState, field, fmtDate, h, icon, loading, navigate, pageHead, pager, relTime,
  select, table, toast, toastError,
} from '../ui.js';
import { parseValue } from '../components/rules.js';

const TRIGGERS = [
  { value: 'new_subscriber', label: 'A subscriber joins' },
  { value: 'email_opened', label: 'A subscriber opens an email' },
  { value: 'email_clicked', label: 'A subscriber clicks a link' },
  { value: 'custom_event', label: 'A custom event is sent via the API' },
  { value: 'time_based', label: 'A number of days after subscribing' },
];
const STEP_TYPES = [
  { value: 'send_email', label: 'Send email' },
  { value: 'wait', label: 'Wait' },
  { value: 'condition', label: 'If / else' },
  { value: 'add_tag', label: 'Add tag' },
  { value: 'remove_tag', label: 'Remove tag' },
  { value: 'update_field', label: 'Set custom field' },
  { value: 'unsubscribe', label: 'Unsubscribe' },
];
const CONDITIONS = [
  { value: 'email_opened', label: 'Opened the previous email' },
  { value: 'email_not_opened', label: 'Did not open the previous email' },
  { value: 'email_clicked', label: 'Clicked in the previous email' },
  { value: 'email_not_clicked', label: 'Did not click in the previous email' },
  { value: 'segment_rules', label: 'Matches segment rules (JSON)' },
];
const typeLabel = (t) => STEP_TYPES.find((s) => s.value === t)?.label || t;

function describeTrigger(a, campaigns = []) {
  const base = TRIGGERS.find((t) => t.value === a.trigger_type)?.label || a.trigger_type;
  if (a.trigger_type === 'custom_event') return `Event "${a.trigger_value}"`;
  if (a.trigger_type === 'time_based') return `${(a.trigger_value || '').split(':')[1]} days after subscribing`;
  if (['email_opened', 'email_clicked'].includes(a.trigger_type) && a.trigger_value) {
    const c = campaigns.find((x) => x.id === a.trigger_value);
    return `${base} from "${c ? c.name : 'a campaign'}"`;
  }
  return base;
}

export async function renderList(main) {
  const state = { page: 1, status: '', trigger_type: '' };
  const host = h('div', {}, loading());
  const reload = () => { state.page = 1; load(); };
  const toolbar = h('div', { class: 'toolbar' },
    select([{ value: '', label: 'Any status' }, { value: 'active', label: 'Active' }, { value: 'inactive', label: 'Off' }, { value: 'paused', label: 'Paused' }],
      '', { 'aria-label': 'Status', onchange: (e) => { state.status = e.target.value; reload(); } }),
    select([{ value: '', label: 'Any trigger' }, ...TRIGGERS], '', { 'aria-label': 'Trigger', onchange: (e) => { state.trigger_type = e.target.value; reload(); } }));
  clear(main, pageHead('Automations', 'Workflows that run by themselves when something happens', [
    h('button', { class: 'primary', onclick: () => navigate('automations/new') }, icon('plus'), 'New automation'),
  ]), h('div', { class: 'card' }, toolbar, host));

  async function load() {
    const data = await api.get('/api/automations', { page: state.page, per_page: 25, status: state.status, trigger_type: state.trigger_type });
    clear(host, table([
      { label: 'Automation', render: (a) => h('div', {}, h('a', { class: 'cell-main', href: `#/automations/${a.id}` }, a.name),
        h('div', { class: 'cell-sub' }, describeTrigger(a))) },
      { label: 'Steps', class: 'num', render: (a) => a.workflow.steps.length },
      { label: 'Status', render: (a) => badge(a.status) },
      { label: 'Updated', render: (a) => h('span', { class: 'muted' }, relTime(a.updated_at)) },
      { label: '', render: (a) => {
        const on = a.status === 'active';
        const b = h('button', { class: on ? 'sm' : 'primary sm', onclick: () => busy(b, async () => {
          await api.post(`/api/automations/${a.id}/${on ? 'deactivate' : 'activate'}`);
          toast(on ? 'Automation turned off' : 'Automation turned on');
          load();
        }) }, on ? 'Turn off' : 'Turn on');
        return b;
      } },
    ], data.items, {
      onRowClick: (a) => navigate(`automations/${a.id}`),
      empty: state.status || state.trigger_type ? 'No automations match these filters.' : emptyState('zap', 'No automations yet',
        'A welcome series is a great first one: it greets every new subscriber automatically.',
        h('button', { class: 'primary', onclick: () => navigate('automations/new') }, icon('plus'), 'Create an automation')),
    }), pager(data, (p) => { state.page = p; load(); }));
  }
  await load();
}

export async function renderEditor(main, id) {
  const isNew = id === 'new';
  const [automation, templates, campaigns] = await Promise.all([
    isNew ? Promise.resolve(null) : api.get(`/api/automations/${id}`),
    api.get('/api/templates', { per_page: 100 }).then((d) => d.items),
    api.get('/api/campaigns', { per_page: 100 }).then((d) => d.items),
  ]);

  const model = automation ? structuredClone(automation) : {
    name: '', trigger_type: 'new_subscriber', trigger_value: null, status: 'active',
    workflow: { steps: templates.length
      ? [{ id: 1, type: 'send_email', template_id: templates[0].id, delay_days: 0 }]
      : [{ id: 1, type: 'wait', days: 1 }] },
  };
  let steps = model.workflow.steps.map((st, i) => ({ id: i + 1, ...st }));
  const nextId = () => Math.max(0, ...steps.map((st) => Number(st.id) || 0)) + 1;

  const name = h('input', { value: model.name, required: true, placeholder: 'Welcome series' });
  const triggerHost = h('div');
  const stepsHost = h('div', { class: 'steps' });
  const triggerSel = select(TRIGGERS, model.trigger_type, { onchange: (e) => { model.trigger_type = e.target.value; model.trigger_value = null; drawTrigger(); } });

  function drawTrigger() {
    const t = model.trigger_type;
    let extra = null;
    if (t === 'email_opened' || t === 'email_clicked') {
      extra = field('From which emails', select([{ value: '', label: 'Any campaign' }, ...campaigns.map((c) => ({ value: c.id, label: c.name }))],
        model.trigger_value || '', { onchange: (e) => { model.trigger_value = e.target.value || null; } }),
      'Emails sent by this automation never re-trigger it');
    } else if (t === 'custom_event') {
      const input = h('input', { value: model.trigger_value || '', placeholder: 'purchase_completed',
        oninput: (e) => { model.trigger_value = e.target.value.trim(); } });
      extra = field('Event name', input, h('span', {}, 'Send it with ', h('code', {}, 'POST /api/automations/events {"event": "…", "email": "…"}')));
    } else if (t === 'time_based') {
      const days = Number((model.trigger_value || 'days_after_subscribe:7').split(':')[1]) || 7;
      model.trigger_value = `days_after_subscribe:${days}`;
      extra = field('Days after subscribing', h('input', { type: 'number', min: 0, value: days,
        oninput: (e) => { model.trigger_value = `days_after_subscribe:${Number(e.target.value) || 0}`; } }),
      'Only subscribers whose anniversary falls after this automation was created are enrolled');
    } else {
      extra = h('p', { class: 'small muted' }, 'Runs once for each new active subscriber (added one by one, or imported with automations enabled).');
    }
    clear(triggerHost, h('div', { class: 'form-row' }, field('When', triggerSel), extra));
  }

  function targetSelect(value, onChange) {
    const options = [{ value: '', label: 'Continue to the next step' },
      ...steps.map((st, i) => ({ value: String(st.id), label: `Go to step ${i + 1}: ${typeLabel(st.type)}` })),
      { value: 'end', label: 'End the workflow' }];
    return select(options, value === null || value === undefined ? '' : String(value), {
      onchange: (e) => {
        const v = e.target.value;
        onChange(v === '' ? null : v === 'end' ? 'end' : (Number.isNaN(Number(v)) ? v : Number(v)));
      } });
  }

  function num(stepObj, key, label) {
    return field(label, h('input', { type: 'number', min: 0, step: 'any', value: stepObj[key] ?? '',
      oninput: (e) => { if (e.target.value === '') delete stepObj[key]; else stepObj[key] = Number(e.target.value); } }));
  }

  function stepBody(st) {
    switch (st.type) {
      case 'send_email':
        return h('div', { class: 'form' },
          templates.length
            ? field('Template', select(templates.map((t) => ({ value: t.id, label: t.name })), st.template_id,
              { onchange: (e) => { st.template_id = e.target.value; } }))
            : h('p', { class: 'error-text' }, 'Create a template first.'),
          h('div', { class: 'form-row' }, num(st, 'delay_days', 'Delay (days)'), num(st, 'delay_hours', 'Delay (hours)'),
            field('Subject override', h('input', { value: st.subject || '', placeholder: 'Optional',
              oninput: (e) => { if (e.target.value) st.subject = e.target.value; else delete st.subject; } }))));
      case 'wait':
        return h('div', { class: 'form-row' }, num(st, 'days', 'Days'), num(st, 'hours', 'Hours'), num(st, 'minutes', 'Minutes'));
      case 'condition': {
        const rules = h('textarea', { class: 'code', style: { minHeight: '120px' },
          value: JSON.stringify(st.rules || { logic: 'AND', rules: [{ field: 'tags', operator: 'contains', value: 'vip' }] }, null, 2),
          oninput: (e) => { try { st.rules = JSON.parse(e.target.value); rules.style.borderColor = ''; } catch { rules.style.borderColor = 'var(--danger)'; } } });
        if (st.condition === 'segment_rules' && !st.rules) st.rules = JSON.parse(rules.value);
        return h('div', { class: 'form' },
          field('If the subscriber', select(CONDITIONS, st.condition, { onchange: (e) => { st.condition = e.target.value; drawSteps(); } })),
          st.condition === 'segment_rules' ? field('Rules', rules, 'Same format as segment rules') : null,
          h('div', { class: 'form-row' },
            field('Then', targetSelect(st.if_true, (v) => { st.if_true = v; })),
            field('Otherwise', targetSelect(st.if_false, (v) => { st.if_false = v; }))));
      }
      case 'add_tag':
      case 'remove_tag':
        return field('Tag', h('input', { value: st.tag || '', oninput: (e) => { st.tag = e.target.value; } }));
      case 'update_field':
        return h('div', { class: 'form-row' },
          field('Field', h('input', { value: (st.field || '').replace(/^custom_fields\./, ''), placeholder: 'plan',
            oninput: (e) => { st.field = e.target.value.trim(); } }), 'A custom field, or first_name / last_name'),
          field('Value', h('input', { value: st.value ?? '', oninput: (e) => { st.value = parseValue(e.target.value); } }),
            'Leave empty to remove the field'));
      case 'unsubscribe':
        return h('p', { class: 'small muted', style: { margin: 0 } }, 'Unsubscribes the person and stops all their automations.');
      default:
        return null;
    }
  }

  function defaults(type) {
    if (type === 'send_email') return { template_id: templates[0]?.id, delay_days: 0 };
    if (type === 'wait') return { days: 1 };
    if (type === 'condition') return { condition: 'email_opened', if_true: null, if_false: 'end' };
    if (type === 'add_tag' || type === 'remove_tag') return { tag: '' };
    if (type === 'update_field') return { field: '', value: '' };
    return {};
  }

  function drawSteps() {
    clear(stepsHost, steps.map((st, i) => {
      const typeSel = select(STEP_TYPES, st.type, { 'aria-label': 'Step type', style: { width: 'auto' }, onchange: (e) => {
        steps[i] = { id: st.id, type: e.target.value, ...defaults(e.target.value) };
        drawSteps();
      } });
      const move = (dir) => { const j = i + dir; [steps[i], steps[j]] = [steps[j], steps[i]]; drawSteps(); };
      const jump = st.type !== 'condition'
        ? h('details', { class: 'more', open: st.next !== undefined && st.next !== null, style: { marginTop: '8px' } },
          h('summary', { class: 'small' }, 'Afterwards…'), targetSelect(st.next, (v) => { if (v === null) delete st.next; else st.next = v; }))
        : null;
      return [i ? h('div', { class: 'connector', 'aria-hidden': 'true' }) : null,
        h('div', { class: `step t-${st.type}` },
          h('div', { class: 'step-head' }, h('span', { class: 'step-num' }, `Step ${i + 1}`), typeSel, h('span', { class: 'grow' }),
            h('button', { class: 'ghost icon', 'aria-label': 'Move up', disabled: i === 0, onclick: () => move(-1) }, icon('up')),
            h('button', { class: 'ghost icon', 'aria-label': 'Move down', disabled: i === steps.length - 1, onclick: () => move(1) }, icon('down')),
            h('button', { class: 'ghost icon', 'aria-label': 'Remove step', disabled: steps.length === 1,
              onclick: () => { steps.splice(i, 1); drawSteps(); } }, icon('trash'))),
          stepBody(st), jump)];
    }), h('div', { class: 'row', style: { marginTop: '6px' } },
      select([{ value: '', label: 'Add a step…' }, ...STEP_TYPES], '', { style: { width: 'auto' }, 'aria-label': 'Add step', onchange: (e) => {
        if (!e.target.value) return;
        steps.push({ id: nextId(), type: e.target.value, ...defaults(e.target.value) });
        drawSteps();
      } })));
  }

  const status = h('label', { class: 'check' }, h('input', { type: 'checkbox', checked: model.status === 'active',
    onchange: (e) => { model.status = e.target.checked ? 'active' : 'inactive'; } }), 'Active');
  const saveBtn = h('button', { class: 'primary', onclick: save }, isNew ? 'Create automation' : 'Save');
  const actions = [h('button', { onclick: () => navigate('automations') }, 'Cancel'), saveBtn];
  if (!isNew) actions.unshift(h('button', { class: 'danger', onclick: remove }, icon('trash'), 'Delete'));

  const runsHost = h('div');
  clear(main,
    pageHead(isNew ? 'New automation' : model.name, isNew ? null : describeTrigger(model, campaigns), actions,
      h('a', { href: '#/automations' }, '← Automations')),
    h('div', { class: 'stack' },
      h('div', { class: 'card form' }, h('div', { class: 'form-row' }, field('Name', name), h('div', { style: { alignSelf: 'end', paddingBottom: '8px' } }, status))),
      h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Trigger')), triggerHost),
      h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Steps'),
        h('span', { class: 'sub' }, 'Run top to bottom unless a step says otherwise')), stepsHost),
      isNew ? null : h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Runs'),
        automation.instances ? h('span', { class: 'sub' },
          `${automation.instances.active} running · ${automation.instances.completed} completed · ${automation.instances.failed} failed`) : null), runsHost)));
  drawTrigger();
  drawSteps();
  if (!isNew) loadRuns(1);

  async function loadRuns(page) {
    const data = await api.get(`/api/automations/${id}/instances`, { page, per_page: 20 });
    clear(runsHost, table([
      { label: 'Subscriber', render: (r) => r.subscriber_email || r.subscriber_id },
      { label: 'Status', render: (r) => badge(r.status) },
      { label: 'Position', render: (r) => (r.status === 'active' ? `Step ${r.current_step + 1}` : '—') },
      { label: 'Next run', render: (r) => (r.status === 'active' ? fmtDate(r.next_run_at) : '—') },
      { label: 'Started', render: (r) => relTime(r.started_at) },
      { label: 'Note', render: (r) => r.error_message || '' },
    ], data.items, { empty: 'Nobody has entered this automation yet.' }), pager(data, loadRuns));
  }

  async function save() {
    if (!name.value.trim()) { toast('Give the automation a name', 'error'); name.focus(); return; }
    const body = {
      name: name.value.trim(), trigger_type: model.trigger_type, trigger_value: model.trigger_value || null,
      status: model.status,
      workflow: { steps: steps.map((st) => {
        const clean = { ...st };
        if (clean.type === 'update_field' && clean.value === '') clean.value = null;
        return clean;
      }) },
    };
    await busy(saveBtn, async () => {
      const saved = isNew ? await api.post('/api/automations', body) : await api.put(`/api/automations/${id}`, body);
      toast(isNew ? 'Automation created' : 'Automation saved');
      if (isNew) navigate(`automations/${saved.id}`);
    });
  }

  async function remove() {
    if (!await confirmDialog('Delete automation?', 'Running workflows stop immediately. Emails already sent are kept in the logs.',
      { confirmLabel: 'Delete', danger: true })) return;
    try {
      await api.del(`/api/automations/${id}`);
      toast('Automation deleted');
      navigate('automations');
    } catch (err) { toastError(err); }
  }
}
