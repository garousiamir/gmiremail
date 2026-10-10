import { api } from '../api.js';
import { columnChart, lineChart } from '../charts.js';
import { badge, clear, compact, emptyState, fmtNum, fmtPct, h, icon, loadingTiles, loading, navigate, pageHead, table, tile } from '../ui.js';
import { dateRange } from '../components/daterange.js';

const shortDate = (iso) => new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });

export async function render(main) {
  const range = dateRange({ preset: '30', allowAll: false, label: 'Period', onChange: () => load() });
  const body = h('div', {}, loadingTiles(7), h('div', { class: 'card' }, loading(5)));
  const hour = new Date().getHours();
  const greeting = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';
  clear(main, pageHead(greeting, 'Here is how your email program is doing', [range.el]), body);

  async function load() {
    const { from, to } = range.get();
    const period = { date_from: from, date_to: to };
    const [overview, engagement, growth, comparison] = await Promise.all([
      api.get('/api/analytics/overview'),
      api.get('/api/analytics/engagement', period),
      api.get('/api/analytics/subscribers', period),
      api.get('/api/analytics/campaigns', { limit: 5 }),
    ]);
    const e = overview.emails;
    const quota = e.daily_limit ? (e.sent_today / e.daily_limit) * 100 : 0;

    clear(body,
      h('div', { class: 'tiles' },
        tile('Active subscribers', compact(overview.subscribers.active), `${fmtNum(overview.subscribers.total)} total`, undefined, 'users'),
        tile('Emails sent', compact(e.sent), e.queued ? `${fmtNum(e.queued)} queued` : 'All time', undefined, 'send'),
        tile('Open rate', fmtPct(overview.open_rate), `${fmtNum(e.unique_opens)} unique opens`, undefined, 'eye'),
        tile('Click rate', fmtPct(overview.click_rate), `${fmtPct(overview.click_to_open_rate)} of openers clicked`, undefined, 'click'),
        tile('Bounce rate', fmtPct(overview.bounce_rate), `${fmtNum(e.bounces)} bounces`, undefined, 'bounce'),
        tile('Unsubscribe rate', fmtPct(overview.unsubscribe_rate), `${fmtNum(e.unsubscribes)} unsubscribes`, undefined, 'userx'),
        tile('Sent today', fmtNum(e.sent_today), `of ${fmtNum(e.daily_limit)} daily limit`, quota, 'gauge')),

      h('div', { class: 'card' },
        h('div', { class: 'card-head' }, h('div', {}, h('h2', {}, 'Engagement'),
          h('div', { class: 'sub' }, `Emails sent, opens and clicks per day · ${fmtPct(engagement.open_rate)} open rate in this period`))),
        lineChart({
          data: engagement.daily, x: 'date', formatX: shortDate, ariaLabel: 'Sent, opens and clicks per day',
          series: [
            { key: 'sent', label: 'Sent', color: '--series-1' },
            { key: 'opens', label: 'Opens', color: '--series-2' },
            { key: 'clicks', label: 'Clicks', color: '--series-3' },
          ],
        })),

      h('div', { class: 'grid grid-2', style: { marginTop: '16px' } },
        h('div', { class: 'card' },
          h('div', { class: 'card-head' }, h('div', {}, h('h2', {}, 'Total subscribers'),
            h('div', { class: 'sub' }, `${growth.net_growth >= 0 ? '+' : ''}${fmtNum(growth.net_growth)} net · ${fmtNum(growth.new_subscribers)} joined, ${fmtNum(growth.unsubscribes)} left`))),
          lineChart({ data: growth.daily, x: 'date', formatX: shortDate, height: 200, ariaLabel: 'Total subscribers per day',
            series: [{ key: 'total', label: 'Subscribers', color: '--series-1' }] })),
        h('div', { class: 'card' },
          h('div', { class: 'card-head' }, h('div', {}, h('h2', {}, 'Opens by hour'),
            h('div', { class: 'sub' }, 'When subscribers open your emails (your local time)'))),
          columnChart({ data: localHours(engagement.opens_by_hour_utc), x: 'hour', y: 'opens', label: 'Opens',
            formatX: (hr) => `${String(hr).padStart(2, '0')}h`, height: 200, ariaLabel: 'Opens by hour of day' }))),

      h('div', { class: 'card', style: { marginTop: '16px' } },
        h('div', { class: 'card-head' }, h('h2', {}, 'Recent campaigns'),
          h('a', { href: '#/campaigns' }, 'All campaigns')),
        table([
          { label: 'Campaign', render: (c) => h('a', { href: `#/campaigns/${c.id}` }, c.name) },
          { label: 'Status', render: (c) => badge(c.status) },
          { label: 'Sent', class: 'num', render: (c) => fmtNum(c.total_sent) },
          { label: 'Open rate', class: 'num', render: (c) => fmtPct(c.open_rate) },
          { label: 'Click rate', class: 'num', render: (c) => fmtPct(c.click_rate) },
        ], comparison.campaigns, {
          onRowClick: (c) => navigate(`campaigns/${c.id}`),
          empty: emptyState('send', 'No campaigns sent yet', 'Your sent campaigns and their results will show up here.',
            h('button', { class: 'primary', onclick: () => navigate('campaigns') }, icon('plus'), 'Create a campaign')),
        })));
  }

  await load();
}

function localHours(utcHours) {
  const offset = -new Date().getTimezoneOffset() / 60;
  const out = Array.from({ length: 24 }, (_, hour) => ({ hour, opens: 0 }));
  for (const { hour, opens } of utcHours) {
    const local = Math.floor((((hour + offset) % 24) + 24) % 24);
    out[local].opens += opens;
  }
  return out;
}
