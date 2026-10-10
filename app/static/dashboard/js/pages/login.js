import { api, errorMessage, session } from '../api.js';
import { clear, field, formData, h, icon, navigate } from '../ui.js';

export function render(root) {
  let mode = 'login';
  const errorBox = h('div', { class: 'error-text', role: 'alert' });
  const formHost = h('div');
  const tabs = h('div', { class: 'tabs', role: 'tablist' });

  function draw() {
    clear(tabs,
      h('button', { type: 'button', class: mode === 'login' ? 'active' : '', onclick: () => { mode = 'login'; draw(); } }, 'Sign in'),
      h('button', { type: 'button', class: mode === 'register' ? 'active' : '', onclick: () => { mode = 'register'; draw(); } }, 'Create account'));
    errorBox.textContent = '';
    clear(formHost, mode === 'login' ? loginForm() : registerForm());
    formHost.querySelector('input')?.focus();
  }

  async function submit(e, path) {
    e.preventDefault();
    const form = e.target;
    const button = form.querySelector('button[type=submit]');
    const data = formData(form);
    for (const key of Object.keys(data)) if (data[key] === '' || data[key] === null) delete data[key];
    button.disabled = true;
    button.classList.add('is-loading');
    const spin = h('span', { class: 'spinner' });
    button.append(spin);
    errorBox.textContent = '';
    try {
      session.set(await api.publicPost(path, data));
      navigate('overview');
    } catch (err) {
      errorBox.textContent = errorMessage(err);
    } finally {
      button.disabled = false;
      button.classList.remove('is-loading');
      spin.remove();
    }
  }

  function loginForm() {
    return h('form', { class: 'form', onsubmit: (e) => submit(e, '/api/auth/login') },
      field('Email', h('input', { name: 'email', type: 'email', required: true, autocomplete: 'username' })),
      field('Password', h('input', { name: 'password', type: 'password', required: true, autocomplete: 'current-password' })),
      errorBox,
      h('button', { type: 'submit', class: 'primary', style: { width: '100%', minHeight: '44px' } }, 'Sign in'));
  }

  function registerForm() {
    return h('form', { class: 'form', onsubmit: (e) => submit(e, '/api/auth/register') },
      field('Business name', h('input', { name: 'name', required: true, autocomplete: 'organization' })),
      field('Login email', h('input', { name: 'email', type: 'email', required: true, autocomplete: 'username' })),
      field('Password', h('input', { name: 'password', type: 'password', required: true, minlength: 8, autocomplete: 'new-password' }),
        'At least 8 characters'),
      h('details', { class: 'more' }, h('summary', {}, 'Sender & SMTP settings (optional: leave SMTP empty to use this server\'s defaults)'),
        h('div', { class: 'form' },
          h('div', { class: 'form-row' },
            field('Sender email', h('input', { name: 'email_from', type: 'email', placeholder: 'Defaults to login email' })),
            field('Sender name', h('input', { name: 'email_from_name' }))),
          field('Postal address', h('input', { name: 'physical_address' }), 'Shown in email footers (anti-spam laws require it)'),
          h('div', { class: 'form-row' },
            field('SMTP host', h('input', { name: 'smtp_host', placeholder: 'Server default' })),
            field('SMTP port', h('input', { name: 'smtp_port', type: 'number', placeholder: 'Server default' }))),
          h('div', { class: 'form-row' },
            field('SMTP username', h('input', { name: 'smtp_username', autocomplete: 'off' })),
            field('SMTP password', h('input', { name: 'smtp_password', type: 'password', autocomplete: 'new-password' }))),
          h('label', { class: 'check' }, h('input', { name: 'smtp_tls', type: 'checkbox', checked: true }), 'Use STARTTLS (ignored for a relay on this server)'))),
      errorBox,
      h('button', { type: 'submit', class: 'primary', style: { width: '100%', minHeight: '44px' } }, 'Create account'));
  }

  const feature = (iconName, text) => h('li', {}, h('span', { class: 'ic' }, icon(iconName)), text);
  clear(root, h('div', { class: 'auth' },
    h('section', { class: 'auth-hero' },
      h('div', { class: 'brand', style: { padding: 0 } }, h('div', { class: 'brand-mark' }, icon('mail')), h('span', {}, 'gmiremail')),
      h('div', {},
        h('h1', {}, 'Email marketing that runs on your own server.'),
        h('p', {}, 'Campaigns, automations and analytics for every brand you manage, with your data staying yours.'),
        h('ul', {},
          feature('target', 'Send to segments, tags or hand-picked people'),
          feature('zap', 'Automations that welcome and re-engage subscribers'),
          feature('overview', 'Opens, clicks and growth at a glance'),
          feature('shield', 'Self-hosted, DKIM-signed, private by default'))),
      h('div', { class: 'small', style: { color: 'rgba(255,255,255,.6)' } }, 'Self-hosted · Multi-brand · Open source')),
    h('section', { class: 'auth-panel' }, h('div', { class: 'auth-card' },
      h('div', { class: 'brand' }, h('div', { class: 'brand-mark' }, icon('mail')), h('span', {}, 'gmiremail')),
      h('h2', {}, 'Welcome'),
      h('p', { class: 'muted' }, 'Sign in to your workspace or create a new one.'),
      tabs, formHost))));
  draw();
}
