import { api } from '../api.js';
import { badge, clear, debounce, emptyState, fmtDate, h, loading, pageHead, pager, select, table } from '../ui.js';
import { dateRange } from '../components/daterange.js';

const STATUSES = ['pending', 'sending', 'sent', 'opened', 'clicked', 'bounced', 'failed'];

export async function render(main, params) {
  const state = { page: 1, status: params?.get('status') || '', campaign_id: params?.get('campaign_id') || '',
    email: '', subject: '', range: { from: '', to: '' } };
  const campaigns = (await api.get('/api/campaigns', { per_page: 100 })).items;
  const host = h('div', {}, loading(8));
  const reload = () => { state.page = 1; load(); };

  const toolbar = h('div', { class: 'toolbar' },
    h('input', { type: 'search', placeholder: 'Recipient email', 'aria-label': 'Recipient email',
      oninput: debounce((e) => { state.email = e.target.value.trim(); reload(); }) }),
    h('input', { type: 'search', placeholder: 'Subject', 'aria-label': 'Subject',
      oninput: debounce((e) => { state.subject = e.target.value.trim(); reload(); }) }),
    select([{ value: '', label: 'Any status' }, ...STATUSES], state.status, { 'aria-label': 'Status',
      onchange: (e) => { state.status = e.target.value; reload(); } }),
    select([{ value: '', label: 'Any campaign' }, ...campaigns.map((c) => ({ value: c.id, label: c.name }))], state.campaign_id,
      { 'aria-label': 'Campaign', onchange: (e) => { state.campaign_id = e.target.value; reload(); } }),
    dateRange({ label: 'Date', onChange: (r) => { state.range = r; reload(); } }).el);

  clear(main, pageHead('Email logs', 'Every email the platform has queued or sent, with its delivery status'),
    h('div', { class: 'card' }, toolbar, host));

  async function load() {
    const data = await api.get('/api/analytics/email-logs', {
      page: state.page, per_page: 50, status: state.status, campaign_id: state.campaign_id, email: state.email,
      subject: state.subject, date_from: state.range.from, date_to: state.range.to });
    const campaignName = (cid) => campaigns.find((c) => c.id === cid)?.name;
    clear(host, table([
      { label: 'Recipient', render: (l) => h('span', { class: 'cell-main' }, l.recipient_email) },
      { label: 'Subject', render: (l) => h('div', {}, l.subject_line || '—',
        h('div', { class: 'cell-sub' }, l.campaign_id ? campaignName(l.campaign_id) || 'Campaign' : l.automation_id ? 'Automation' : '')) },
      { label: 'Status', render: (l) => h('div', {}, badge(l.status),
        l.error_message ? h('div', { class: 'cell-sub', style: { maxWidth: '300px' }, title: l.error_message }, l.error_message.slice(0, 90)) : null) },
      { label: 'Sent', render: (l) => h('span', { class: 'nowrap' }, fmtDate(l.sent_at)) },
      { label: 'Opened', render: (l) => h('span', { class: 'nowrap' }, fmtDate(l.opened_at)) },
      { label: 'Clicked', render: (l) => h('span', { class: 'nowrap' }, fmtDate(l.clicked_at)) },
    ], data.items, { empty: emptyState('list', 'Nothing here', 'No emails match these filters.') }),
    pager(data, (p) => { state.page = p; load(); }));
  }
  await load();
}
