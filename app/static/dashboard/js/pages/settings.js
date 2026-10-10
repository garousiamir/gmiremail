import { api, session } from '../api.js';
import { busy, clear, copyText, field, fmtNum, formData, h, icon, modal, navigate, pageHead, toast } from '../ui.js';

export async function render(main) {
  const business = await api.get('/api/businesses/me');
  session.setBusiness(business);

  const profile = h('form', { class: 'form', onsubmit: (e) => { e.preventDefault(); saveProfile(); } },
    h('div', { class: 'form-row' },
      field('Business name', h('input', { name: 'name', required: true, value: business.name })),
      field('Daily sending limit', h('input', { name: 'daily_email_limit', type: 'number', min: 0, value: business.daily_email_limit }),
        `${business.emails_sent_today} sent today`)),
    h('div', { class: 'form-row' },
      field('Sender email', h('input', { name: 'email_from', type: 'email', required: true, value: business.email_from })),
      field('Sender name', h('input', { name: 'email_from_name', value: business.email_from_name || '' }))),
    h('div', { class: 'form-row' },
      field('Sender domain', h('input', { name: 'sender_domain', required: true, value: business.sender_domain }),
        'Used for Message-IDs and the mailto unsubscribe address'),
      field('Postal address', h('input', { name: 'physical_address', value: business.physical_address || '' }), 'Shown in email footers')));
  const profileBtn = h('button', { class: 'primary', onclick: saveProfile }, 'Save');

  const smtp = h('form', { class: 'form', onsubmit: (e) => { e.preventDefault(); saveSmtp(); } },
    h('div', { class: 'form-row' },
      field('SMTP host', h('input', { name: 'smtp_host', required: true, value: business.smtp_host })),
      field('Port', h('input', { name: 'smtp_port', type: 'number', required: true, value: business.smtp_port }), '587 = STARTTLS, 465 = SSL')),
    h('div', { class: 'form-row' },
      field('Username', h('input', { name: 'smtp_username', value: business.smtp_username || '', autocomplete: 'off' }), 'Leave empty if the server needs no login'),
      field('Password', h('input', { name: 'smtp_password', type: 'password', placeholder: 'Unchanged', autocomplete: 'new-password' }))),
    h('label', { class: 'check' }, h('input', { name: 'smtp_tls', type: 'checkbox', checked: business.smtp_tls }), 'Use STARTTLS'));
  const smtpBtn = h('button', { class: 'primary', onclick: saveSmtp }, 'Save');
  const testBtn = h('button', { onclick: () => busy(testBtn, async () => {
    const r = await api.post('/api/businesses/me/smtp/test');
    toast(r.message);
  }) }, 'Test connection');

  const apiKey = h('input', { readonly: true, value: business.api_key, 'aria-label': 'API key' });
  const rotateBtn = h('button', { onclick: () => busy(rotateBtn, async () => {
    const r = await api.post('/api/businesses/me/api-key/rotate');
    apiKey.value = r.api_key;
    toast('New API key created; the old one no longer works');
  }) }, icon('refresh'), 'Rotate');

  const password = h('form', { class: 'form', onsubmit: (e) => { e.preventDefault(); changePassword(); } },
    h('div', { class: 'form-row' },
      field('Current password', h('input', { name: 'current_password', type: 'password', required: true, autocomplete: 'current-password' })),
      field('New password', h('input', { name: 'password', type: 'password', required: true, minlength: 8, autocomplete: 'new-password' }))));
  const passwordBtn = h('button', { class: 'primary', onclick: changePassword }, 'Change password');

  const card = (title, sub, content, actions) => h('div', { class: 'card' },
    h('div', { class: 'card-head' }, h('div', {}, h('h2', {}, title), sub ? h('div', { class: 'sub' }, sub) : null)),
    content, actions ? h('div', { class: 'row', style: { marginTop: '16px', justifyContent: 'flex-end' } }, actions) : null);

  clear(main, pageHead('Settings', business.account_email),
    h('div', { class: 'stack' },
      card('Business & sender', 'How your emails are addressed', profile, [profileBtn]),
      card('SMTP server', 'Your emails are sent through this server', smtp, [testBtn, smtpBtn]),
      card('API key', 'Use as an X-API-Key header to call the API from your own scripts',
        h('div', { class: 'copy-field' }, apiKey,
          h('button', { onclick: () => copyText(apiKey.value) }, icon('copy'), 'Copy'), rotateBtn)),
      business.is_admin ? backupCard() : null,
      card('Password', 'Changing it signs you out everywhere', password, [passwordBtn]),
      card('Sessions', null, h('p', { class: 'secondary' }, 'Sign out of every browser and invalidate all tokens.'), [
        h('button', { class: 'danger', onclick: async () => {
          try { await api.post('/api/auth/logout'); } finally { session.clear(); navigate('login'); }
        } }, icon('logout'), 'Sign out everywhere')]),
      dangerCard()));

  function dangerCard() {
    const uninstall = 'sudo /opt/gmiremail/deploy/uninstall.sh';
    return h('div', { class: 'card danger-zone' },
      h('div', { class: 'card-head' }, h('div', {}, h('h2', {}, 'Danger zone'),
        h('div', { class: 'sub' }, 'Permanent actions. Download a backup first if you may need the data again.'))),
      h('div', { class: 'danger-row' },
        h('div', {}, h('strong', {}, 'Delete this account'),
          h('p', { class: 'secondary' }, `Deletes ${business.name} with all its subscribers, templates, segments, campaigns, `
            + 'automations, email logs and analytics. Other accounts on this server are not affected.')),
        h('button', { class: 'danger', onclick: deleteAccountDialog }, icon('trash'), 'Delete account')),
      business.is_admin ? h('div', { class: 'danger-row' },
        h('div', {}, h('strong', {}, 'Remove gmiremail from this server'),
          h('p', { class: 'secondary' }, 'Run this over SSH. It saves a final backup to /root, then removes the app, its database, '
            + 'services, nginx site and certificate. It asks you to type DELETE before doing anything.'),
          h('div', { class: 'copy-field' }, h('input', { value: uninstall, readonly: true, 'aria-label': 'Uninstall command' }),
            h('button', { onclick: () => copyText(uninstall) }, icon('copy'), 'Copy'))),
      ) : null);
  }

  function deleteAccountDialog() {
    const pw = h('input', { type: 'password', autocomplete: 'current-password', required: true });
    const confirmInput = h('input', { placeholder: 'DELETE', autocomplete: 'off', 'aria-label': 'Type DELETE to confirm' });
    const btn = h('button', { class: 'danger solid', disabled: true, onclick: () => busy(btn, async () => {
      await api.del('/api/businesses/me', { password: pw.value, confirm: confirmInput.value });
      m.close();
      session.clear();
      toast({ title: 'Account deleted', message: 'All of its data has been removed.' });
      navigate('login');
    }) }, icon('trash'), 'Delete everything');
    const update = () => { btn.disabled = !(pw.value && confirmInput.value.trim().toUpperCase() === 'DELETE'); };
    pw.addEventListener('input', update);
    confirmInput.addEventListener('input', update);
    const m = modal({
      title: 'Delete this account?',
      body: h('div', { class: 'form' },
        h('p', { style: { marginTop: 0 } }, 'This permanently deletes ', h('strong', {}, business.name), ' and ',
          h('strong', {}, 'all'), ' of its subscribers, campaigns, templates, automations and analytics. It cannot be undone.'),
        business.is_admin ? h('p', { class: 'error-text' }, 'You are the server owner. After this, backups can only be downloaded '
          + 'by the next oldest account (or by ADMIN_EMAILS), so download a backup first.') : null,
        field('Your password', pw),
        field('Type DELETE to confirm', confirmInput)),
      actions: [h('button', { onclick: () => m.close() }, 'Cancel'), btn],
    });
    pw.focus();
  }

  function backupCard() {
    const counts = h('div', { class: 'small muted' }, 'Counting…');
    api.get('/api/admin/backup').then(({ counts: c }) => {
      counts.textContent = `Includes ${fmtNum(c.businesses)} business${c.businesses === 1 ? '' : 'es'}, `
        + `${fmtNum(c.subscribers)} subscribers, ${fmtNum(c.campaigns)} campaigns, ${fmtNum(c.automations)} automations `
        + `and ${fmtNum(c.email_logs)} email records with their analytics.`;
    }).catch(() => { counts.textContent = ''; });
    const pw = h('input', { type: 'password', autocomplete: 'current-password', placeholder: 'Your password',
      style: { fontFamily: 'inherit', fontSize: '14px' },
      'aria-label': 'Password', onkeydown: (e) => { if (e.key === 'Enter') download(); } });
    const btn = h('button', { class: 'primary', onclick: download }, icon('download'), 'Download backup');
    async function download() {
      if (!pw.value) { toast('Enter your password to download a backup', 'error'); pw.focus(); return; }
      await busy(btn, async () => {
        await api.download('/api/admin/backup', { password: pw.value },
          `gmiremail-backup-${new Date().toISOString().slice(0, 10)}.tar.gz`);
        pw.value = '';
        toast('Backup downloaded. Keep it somewhere safe.');
      });
    }
    return card('Backup', 'Everything on this server in one file, to keep or to move to a new server',
      h('div', { class: 'stack', style: { gap: '10px' } },
        counts,
        h('p', { class: 'secondary', style: { margin: 0 } },
          'The file contains all data and the secret keys (so links in emails you already sent keep working). ',
          'Store it safely. To restore on a new server: ', h('code', {}, 'sudo deploy/restore.sh <file>'), '.'),
        h('div', { class: 'copy-field' }, pw, btn)));
  }

  async function saveProfile() {
    if (!profile.reportValidity()) return;
    const data = formData(profile);
    data.physical_address = data.physical_address || null;
    await busy(profileBtn, async () => {
      session.setBusiness(await api.put('/api/businesses/me', data));
      toast('Settings saved');
    });
  }

  async function saveSmtp() {
    if (!smtp.reportValidity()) return;
    const data = formData(smtp);
    if (!data.smtp_password) delete data.smtp_password;
    await busy(smtpBtn, async () => {
      await api.put('/api/businesses/me', data);
      smtp.querySelector('[name=smtp_password]').value = '';
      toast('SMTP settings saved');
    });
  }

  async function changePassword() {
    if (!password.reportValidity()) return;
    await busy(passwordBtn, async () => {
      await api.put('/api/businesses/me', formData(password));
      session.clear();
      toast('Password changed. Please sign in again.');
      navigate('login');
    });
  }
}
