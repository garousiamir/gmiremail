import { onUnauthorized, session } from './api.js';
import { clear, emptyState, h, icon, initials, navigate, toastError } from './ui.js';
import { themeButton } from './theme.js';
import * as login from './pages/login.js';
import * as overview from './pages/overview.js';
import * as subscribers from './pages/subscribers.js';
import * as segments from './pages/segments.js';
import * as templates from './pages/templates.js';
import * as campaigns from './pages/campaigns.js';
import * as automations from './pages/automations.js';
import * as logs from './pages/logs.js';
import * as settings from './pages/settings.js';

const NAV = [
  { section: 'Insights' },
  { path: 'overview', label: 'Overview', icon: 'overview' },
  { section: 'Audience' },
  { path: 'subscribers', label: 'Subscribers', icon: 'users' },
  { path: 'segments', label: 'Segments', icon: 'filter' },
  { section: 'Messages' },
  { path: 'campaigns', label: 'Campaigns', icon: 'send' },
  { path: 'templates', label: 'Templates', icon: 'template' },
  { path: 'automations', label: 'Automations', icon: 'zap' },
  { section: 'System' },
  { path: 'logs', label: 'Email logs', icon: 'list' },
  { path: 'settings', label: 'Settings', icon: 'settings' },
];

const ROUTES = [
  [/^overview$/, overview.render],
  [/^subscribers$/, subscribers.render],
  [/^segments$/, segments.renderList],
  [/^segments\/(new|[\w-]+)$/, segments.renderEditor],
  [/^templates$/, templates.renderList],
  [/^templates\/(new|[\w-]+)$/, templates.renderEditor],
  [/^campaigns$/, campaigns.renderList],
  [/^campaigns\/([\w-]+)$/, campaigns.renderDetail],
  [/^automations$/, automations.renderList],
  [/^automations\/(new|[\w-]+)$/, automations.renderEditor],
  [/^logs$/, logs.render],
  [/^settings$/, settings.render],
];

const root = document.getElementById('root');
let cleanup = null;
let renderId = 0;

function shell(section) {
  const business = session.business;
  const main = h('main', { class: 'main', id: 'main' });
  const nav = h('nav', { class: 'nav', 'aria-label': 'Main' }, NAV.map((item) => (item.section
    ? h('div', { class: 'nav-label' }, item.section)
    : h('a', {
      href: `#/${item.path}`, class: section === item.path ? 'active' : null,
      'aria-current': section === item.path ? 'page' : null, title: item.label,
    }, icon(item.icon), h('span', {}, item.label)))));
  const layout = h('div', { class: 'shell' },
    h('aside', { class: 'sidebar' },
      h('div', { class: 'brand' }, h('div', { class: 'brand-mark' }, icon('mail')), h('span', {}, 'gmiremail')),
      nav,
      h('div', { class: 'sidebar-foot' },
        h('div', { class: 'avatar', 'aria-hidden': 'true' }, initials(business?.name)),
        h('div', { class: 'who', title: business?.account_email },
          h('strong', {}, business?.name || ''), h('span', {}, business?.account_email || '')),
        themeButton(),
        h('button', { class: 'icon', onclick: logout, title: 'Sign out', 'aria-label': 'Sign out' }, icon('logout')))),
    main);
  clear(root, layout);
  return main;
}

function logout() {
  session.clear();
  navigate('login');
}

async function route() {
  const id = ++renderId;
  if (typeof cleanup === 'function') cleanup();
  cleanup = null;

  const [rawPath, query = ''] = location.hash.replace(/^#\/?/, '').split('?');
  const path = rawPath || 'overview';
  const params = new URLSearchParams(query);
  if (path === 'login') {
    if (session.loggedIn) return navigate('overview');
    login.render(root);
    return;
  }
  if (!session.loggedIn) return navigate('login');

  const match = ROUTES.map(([re, fn]) => [path.match(re), fn]).find(([m]) => m);
  if (!match) return navigate('overview');
  const [m, render] = match;
  const main = shell(path.split('/')[0]);
  window.scrollTo(0, 0);
  try {
    const result = await render(main, ...m.slice(1), params);
    if (id === renderId) cleanup = result; else if (typeof result === 'function') result();
  } catch (err) {
    if (id !== renderId || err.status === 401) return;
    toastError(err);
    clear(main, h('div', { class: 'card' }, emptyState('alert', err.status === 404 ? 'Not found' : 'Could not load this page',
      err.status === 404 ? 'It may have been deleted.' : 'Check your connection and try again.')));
  }
}

onUnauthorized(() => navigate('login'));
window.addEventListener('hashchange', route);
route();
