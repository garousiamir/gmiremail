import { api } from '../api.js';
import { lineChart } from '../charts.js';
import {
  badge, busy, clear, confirmDialog, field, fmtDate, fmtNum, fmtPct, h, icon, loading, localInputToIso, modal,
  navigate, pageHead, pager, select, table, tile, toast,
} from '../ui.js';

const STATUS_TABS = ['', 'draft', 'scheduled', 'sending', 'paused', 'sent'];

export async function renderList(main) {
  const state = { page: 1, status: '' };
  const host = h('div', {}, loading());
  const tabs = h('div', { class: 'tabs', style: { margin: '0 0 14px', maxWidth: '560px' } });
  const drawTabs = () => clear(tabs, STATUS_TABS.map((st) => h('button', {
    class: state.status === st ? 'active' : '', onclick: () => { state.status = st; state.page = 1; drawTabs(); load(); },
  }, st ? st[0].toUpperCase() + st.slice(1) : 'All')));

  clear(main, pageHead('Campaigns', 'One-off emails to your list or a segment', [
    h('button', { class: 'primary', onclick: () => campaignDialog(null) }, icon('plus'), 'New campaign'),
  ]), h('div', { class: 'card' }, tabs, host));
  drawTabs();

  async function load() {
    const data = await api.get('/api/campaigns', { page: state.page, per_page: 25, status: state.status });
    clear(host, table([
      { label: 'Campaign', render: (c) => h('div', {}, h('a', { href: `#/campaigns/${c.id}` }, c.name),
        h('div', { class: 'small muted' }, c.template_name || '')) },
      { label: 'Status', render: (c) => badge(c.status) },
      { label: 'Audience', render: (c) => c.segment_name || h('span', { class: 'muted' }, 'All active') },
      { label: 'Sent', class: 'num', render: (c) => `${fmtNum(c.total_sent)}${c.total_recipients ? ` / ${fmtNum(c.total_recipients)}` : ''}` },
      { label: 'Opens', class: 'num', render: (c) => (c.total_sent ? fmtPct(c.open_rate) : '—') },
      { label: 'Clicks', class: 'num', render: (c) => (c.total_sent ? fmtPct(c.click_rate) : '—') },
      { label: 'Date', render: (c) => h('span', { class: 'nowrap' }, c.status === 'scheduled'
        ? `Scheduled ${fmtDate(c.scheduled_time)}` : fmtDate(c.send_time || c.created_at)) },
    ], data.items, {
      onRowClick: (c) => navigate(`campaigns/${c.id}`),
      empty: state.status ? `No ${state.status} campaigns.` : h('div', {}, 'No campaigns yet.', h('br'),
        h('button', { class: 'primary', onclick: () => campaignDialog(null) }, 'Create your first campaign')),
    }), pager(data, (p) => { state.page = p; load(); }));
  }
  await load();
}

async function campaignDialog(campaign, onSaved) {
  const [templates, segments] = await Promise.all([
    api.get('/api/templates', { per_page: 100 }).then((d) => d.items),
    api.get('/api/segments', { per_page: 100 }).then((d) => d.items),
  ]);
  if (!templates.length) {
    if (await confirmDialog('You need a template first', 'Campaigns send a template. Create one now?', { confirmLabel: 'Create template' })) {
      navigate('templates/new');
    }
    return;
  }
  const isNew = !campaign;
  const name = h('input', { required: true, value: campaign?.name || '' });
  const template = select(templates.map((t) => ({ value: t.id, label: t.name })), campaign?.template_id || templates[0].id);
  const segment = select([{ value: '', label: 'All active subscribers' }, ...segments.map((s) => ({ value: s.id, label: `${s.name} (${fmtNum(s.subscriber_count)})` }))],
    campaign?.segment_id || '');
  const subject = h('input', { value: campaign?.subject_line || '', placeholder: "Leave empty to use the template's subject" });
  const variants = h('textarea', { style: { minHeight: '70px' }, value: (campaign?.subject_variants || []).join('\n'),
    placeholder: 'One subject per line. Recipients are split evenly between them.' });
  const saveBtn = h('button', { class: 'primary', onclick: save }, isNew ? 'Create campaign' : 'Save');

  const m = modal({
    title: isNew ? 'New campaign' : 'Edit campaign',
    body: h('div', { class: 'form' },
      field('Campaign name', name, 'Only you see this'),
      field('Template', template),
      field('Send to', segment),
      field('Subject line override', subject, 'Variables like {{ first_name }} work here too'),
      h('details', { class: 'more', open: (campaign?.subject_variants || []).length > 0 },
        h('summary', {}, 'A/B test subject lines'), variants)),
    actions: [h('button', { onclick: () => m.close() }, 'Cancel'), saveBtn],
  });

  async function save() {
    if (!name.value.trim()) { toast('Give the campaign a name', 'error'); name.focus(); return; }
    const body = {
      name: name.value.trim(), template_id: template.value, segment_id: segment.value || null,
      subject_line: subject.value.trim() || null,
      subject_variants: variants.value.split('\n').map((v) => v.trim()).filter(Boolean),
    };
    if (body.subject_variants.length === 1) { toast('Add at least two subject lines for an A/B test', 'error'); return; }
    await busy(saveBtn, async () => {
      const saved = isNew ? await api.post('/api/campaigns', body) : await api.put(`/api/campaigns/${campaign.id}`, body);
      m.close();
      toast(isNew ? 'Campaign created' : 'Campaign saved');
      if (isNew) navigate(`campaigns/${saved.id}`); else onSaved?.();
    });
  }
}

export async function renderDetail(main, id) {
  let timer = null;
  const body = h('div', {}, loading());

  async function load() {
    const a = await api.get(`/api/campaigns/${id}/analytics`);
    const c = a.campaign;
    clear(main, pageHead(c.name, null, actionsFor(c), h('a', { href: '#/campaigns' }, '← Campaigns')), body);
    draw(a);
    clearInterval(timer);
    if (['sending', 'scheduled'].includes(c.status)) timer = setInterval(() => load().catch(() => {}), 10000);
  }

  function actionsFor(c) {
    const act = (label, iconName, fn, cls = '') => {
      const b = h('button', { class: cls, onclick: () => busy(b, fn) }, iconName ? icon(iconName) : null, label);
      return b;
    };
    const out = [];
    if (['draft', 'scheduled'].includes(c.status)) {
      out.push(act('Edit', null, () => campaignDialog(c, load)));
      out.push(act('Send test', null, () => testDialog(c)));
      out.push(act('Schedule', 'clock', () => scheduleDialog(c, load)));
      out.push(act('Send now', 'send', async () => {
        const audience = c.segment_name ? `subscribers in "${c.segment_name}"` : 'all active subscribers';
        if (!await confirmDialog('Send campaign now?', `This emails ${audience}. It cannot be undone.`, { confirmLabel: 'Send now' })) return;
        const r = await api.post(`/api/campaigns/${c.id}/send`, {});
        toast(r.message);
        await load();
      }, 'primary'));
    }
    if (c.status === 'sending') out.push(act('Pause', 'pause', async () => { await api.post(`/api/campaigns/${c.id}/pause`); toast('Campaign paused'); await load(); }));
    if (c.status === 'scheduled') out.unshift(act('Unschedule', null, async () => { await api.put(`/api/campaigns/${c.id}`, { scheduled_time: null }); toast('Back to draft'); await load(); }));
    if (c.status === 'paused') out.push(act('Resume', 'play', async () => { await api.post(`/api/campaigns/${c.id}/resume`); toast('Campaign resumed'); await load(); }, 'primary'));
    if (c.status !== 'sending') {
      out.unshift(act('Delete', 'trash', async () => {
        if (!await confirmDialog('Delete campaign?', 'Its email history and stats are deleted too.', { confirmLabel: 'Delete', danger: true })) return;
        await api.del(`/api/campaigns/${c.id}`);
        toast('Campaign deleted');
        navigate('campaigns');
      }, 'danger'));
    }
    return out;
  }

  function draw(a) {
    const c = a.campaign;
    const progress = a.recipients ? ((a.sent + a.bounces + a.failed) / a.recipients) * 100 : 0;
    const details = h('div', { class: 'card' },
      h('div', { class: 'card-head' }, h('h2', {}, 'Details'), badge(c.status)),
      h('dl', { class: 'dl' },
        h('dt', {}, 'Template'), h('dd', {}, c.template_id ? h('a', { href: `#/templates/${c.template_id}` }, c.template_name || 'Template') : '—'),
        h('dt', {}, 'Audience'), h('dd', {}, c.segment_id ? h('a', { href: `#/segments/${c.segment_id}` }, c.segment_name) : 'All active subscribers'),
        h('dt', {}, 'Subject'), h('dd', {}, c.subject_line || h('span', { class: 'muted' }, "Template's subject")),
        c.subject_variants.length ? [h('dt', {}, 'A/B subjects'), h('dd', {}, c.subject_variants.map((v) => h('div', {}, v)))] : null,
        c.scheduled_time ? [h('dt', {}, 'Scheduled'), h('dd', {}, fmtDate(c.scheduled_time))] : null,
        c.send_time ? [h('dt', {}, 'Started'), h('dd', {}, fmtDate(c.send_time))] : null,
        c.completed_at ? [h('dt', {}, 'Finished'), h('dd', {}, fmtDate(c.completed_at))] : null));

    if (c.status === 'draft' || (c.status === 'scheduled' && !c.send_time)) {
      clear(body, details, h('div', { class: 'card empty' },
        c.status === 'draft' ? 'Not sent yet. Send a test to yourself, then send it now or schedule it.'
          : `Scheduled for ${fmtDate(c.scheduled_time)}. Stats appear here once sending starts.`));
      return;
    }

    clear(body,
      h('div', { class: 'tiles' },
        tile('Delivered', fmtNum(a.sent), `of ${fmtNum(a.recipients)} recipients`, c.status === 'sending' || c.status === 'paused' ? progress : undefined),
        tile('Open rate', fmtPct(a.open_rate), `${fmtNum(a.unique_opens)} unique · ${fmtNum(a.total_opens)} total`),
        tile('Click rate', fmtPct(a.click_rate), `${fmtNum(a.unique_clicks)} unique · ${fmtNum(a.total_clicks)} total`),
        tile('Click-to-open', fmtPct(a.click_to_open_rate), 'Clicks among openers'),
        tile('Bounces', fmtNum(a.bounces), fmtPct(a.bounce_rate)),
        tile('Unsubscribes', fmtNum(a.unsubscribes), fmtPct(a.unsubscribe_rate)),
        a.pending || a.failed ? tile('Queued / failed', `${fmtNum(a.pending)} / ${fmtNum(a.failed)}`, c.status === 'paused' ? 'Paused' : 'Sending continues automatically') : null),
      h('div', { class: 'grid grid-2' },
        h('div', { class: 'card' },
          h('div', { class: 'card-head' }, h('div', {}, h('h2', {}, 'Opens and clicks over time'), h('div', { class: 'sub' }, 'Hours after sending started'))),
          a.engagement_timeline.length
            ? lineChart({ data: fillHours(a.engagement_timeline), x: 'hour_after_send', formatX: (hr) => `+${hr}h`, height: 200,
              ariaLabel: 'Opens and clicks by hour after send',
              series: [{ key: 'opens', label: 'Opens', color: '--series-2' }, { key: 'clicks', label: 'Clicks', color: '--series-3' }] })
            : h('div', { class: 'empty' }, 'No opens or clicks yet.')),
        details),
      h('div', { class: 'grid grid-2', style: { marginTop: '16px' } },
        h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Top links')),
          table([
            { label: 'URL', render: (l) => h('a', { href: l.url, target: '_blank', rel: 'noopener noreferrer', style: { wordBreak: 'break-all' } }, l.url) },
            { label: 'Clicks', class: 'num', render: (l) => fmtNum(l.clicks) },
            { label: 'Unique', class: 'num', render: (l) => fmtNum(l.unique_clicks) },
          ], a.top_links, { empty: 'No clicks yet.' })),
        a.ab_test ? h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'A/B test'),
          a.ab_test.leader && (a.ab_test.leader.open_rate || a.ab_test.leader.click_rate) ? h('span', { class: 'badge good' }, `Leading: ${a.ab_test.leader.subject_line}`) : null),
        table([
          { label: 'Subject', key: 'subject_line' },
          { label: 'Sent', class: 'num', render: (v) => fmtNum(v.sent) },
          { label: 'Open rate', class: 'num', render: (v) => fmtPct(v.open_rate) },
          { label: 'Click rate', class: 'num', render: (v) => fmtPct(v.click_rate) },
        ], a.ab_test.variants))
          : h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Delivery status')),
            table([{ label: 'Status', render: (r) => badge(r[0]) }, { label: 'Emails', class: 'num', render: (r) => fmtNum(r[1]) }],
              Object.entries(a.status_breakdown)))),
      h('div', { style: { marginTop: '16px' } }, h('a', { href: `#/logs?campaign_id=${c.id}` }, 'View individual email logs →')));
  }

  await load();
  return () => clearInterval(timer);
}

function fillHours(points) {
  const last = Math.max(...points.map((p) => p.hour_after_send), 1);
  const byHour = new Map(points.map((p) => [p.hour_after_send, p]));
  return Array.from({ length: last + 1 }, (_, hr) => byHour.get(hr) || { hour_after_send: hr, opens: 0, clicks: 0 });
}

function scheduleDialog(c, reload) {
  const pad = (n) => String(n).padStart(2, '0');
  const toLocal = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  const initial = c.scheduled_time ? new Date(`${c.scheduled_time}Z`) : new Date(Date.now() + 3600 * 1000);
  const input = h('input', { type: 'datetime-local', value: toLocal(initial), min: toLocal(new Date()) });
  const btn = h('button', { class: 'primary', onclick: () => busy(btn, async () => {
    await api.post(`/api/campaigns/${c.id}/schedule`, { scheduled_time: localInputToIso(input.value) });
    m.close();
    toast('Campaign scheduled');
    reload();
  }) }, 'Schedule');
  const m = modal({ title: 'Schedule campaign', body: h('div', { class: 'form' },
    field('Send at', input, `Your local time (${Intl.DateTimeFormat().resolvedOptions().timeZone})`)),
  actions: [h('button', { onclick: () => m.close() }, 'Cancel'), btn] });
}

function testDialog(c) {
  const input = h('input', { type: 'text', placeholder: 'you@example.com, colleague@example.com' });
  const btn = h('button', { class: 'primary', onclick: () => busy(btn, async () => {
    const emails = input.value.split(',').map((e) => e.trim()).filter(Boolean);
    const r = await api.post(`/api/campaigns/${c.id}/test`, { emails });
    m.close();
    toast(`Test sent to ${r.sent_to.join(', ')}`);
  }) }, icon('send'), 'Send test');
  const m = modal({ title: 'Send a test email', body: h('div', { class: 'form' },
    field('Send to', input, 'Up to 5 addresses, comma separated. Sample data is used for variables.')),
  actions: [h('button', { onclick: () => m.close() }, 'Cancel'), btn] });
}

