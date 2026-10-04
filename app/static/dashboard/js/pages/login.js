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
    errorBox.textContent = '';
    try {
      session.set(await api.publicPost(path, data));
      navigate('overview');
    } catch (err) {
      errorBox.textContent = errorMessage(err);
    } finally {
      button.disabled = false;
    }
  }

  function loginForm() {
    return h('form', { class: 'form', onsubmit: (e) => submit(e, '/api/auth/login') },
      field('Email', h('input', { name: 'email', type: 'email', required: true, autocomplete: 'username' })),
      field('Password', h('input', { name: 'password', type: 'password', required: true, autocomplete: 'current-password' })),
      errorBox,
      h('button', { type: 'submit', class: 'primary', style: { justifyContent: 'center' } }, 'Sign in'));
  }

  function registerForm() {
    return h('form', { class: 'form', onsubmit: (e) => submit(e, '/api/auth/register') },
      field('Business name', h('input', { name: 'name', required: true, autocomplete: 'organization' })),
      field('Login email', h('input', { name: 'email', type: 'email', required: true, autocomplete: 'username' })),
      field('Password', h('input', { name: 'password', type: 'password', required: true, minlength: 8, autocomplete: 'new-password' }),
        'At least 8 characters'),
      h('details', { class: 'more' }, h('summary', {}, 'Sender & SMTP settings (you can also set these later)'),
        h('div', { class: 'form' },
          h('div', { class: 'form-row' },
            field('Sender email', h('input', { name: 'email_from', type: 'email', placeholder: 'Defaults to login email' })),
            field('Sender name', h('input', { name: 'email_from_name' }))),
          field('Postal address', h('input', { name: 'physical_address' }), 'Shown in email footers (anti-spam laws require it)'),
          h('div', { class: 'form-row' },
            field('SMTP host', h('input', { name: 'smtp_host', placeholder: 'smtp.gmail.com' })),
            field('SMTP port', h('input', { name: 'smtp_port', type: 'number', placeholder: '587' }))),
          h('div', { class: 'form-row' },
            field('SMTP username', h('input', { name: 'smtp_username', autocomplete: 'off' })),
            field('SMTP password', h('input', { name: 'smtp_password', type: 'password', autocomplete: 'new-password' }))),
          h('label', { class: 'check' }, h('input', { name: 'smtp_tls', type: 'checkbox', checked: true }), 'Use STARTTLS'))),
      errorBox,
      h('button', { type: 'submit', class: 'primary', style: { justifyContent: 'center' } }, 'Create account'));
  }

  clear(root, h('div', { class: 'auth' }, h('div', { class: 'card' },
    h('div', { class: 'brand' }, h('div', { class: 'brand-mark' }, h('span', { style: { color: '#fff', display: 'grid' } }, icon('mail'))), 'gmiremail'),
    h('p', { class: 'muted', style: { textAlign: 'center' } }, 'Email marketing for your businesses'),
    tabs, formHost)));
  draw();
}
