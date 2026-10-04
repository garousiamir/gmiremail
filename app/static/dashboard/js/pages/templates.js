import { api, errorMessage } from '../api.js';
import {
  busy, clear, confirmDialog, debounce, field, h, icon, loading, modal, navigate, pageHead, pager, relTime,
  table, toast, toastError,
} from '../ui.js';

export async function renderList(main) {
  let page = 1;
  const host = h('div', {}, loading());
  clear(main, pageHead('Templates', 'Reusable email designs with {{ variables }}', [
    h('button', { onclick: libraryDialog }, 'Start from library'),
    h('button', { class: 'primary', onclick: () => navigate('templates/new') }, icon('plus'), 'New template'),
  ]), h('div', { class: 'card' }, host));

  async function load() {
    const data = await api.get('/api/templates', { page, per_page: 25 });
    clear(host, table([
      { label: 'Name', render: (t) => h('a', { href: `#/templates/${t.id}` }, t.name) },
      { label: 'Subject', key: 'subject_line' },
      { label: 'Variables', render: (t) => t.template_variables.length
        ? t.template_variables.map((v) => h('span', { class: 'chip' }, v)) : h('span', { class: 'muted' }, '—') },
      { label: 'Updated', render: (t) => relTime(t.updated_at) },
    ], data.items, {
      onRowClick: (t) => navigate(`templates/${t.id}`),
      empty: h('div', {}, 'No templates yet.', h('br'),
        h('button', { class: 'primary', onclick: libraryDialog }, 'Start from a ready-made template')),
    }), pager(data, (p) => { page = p; load(); }));
  }
  await load();
}

async function libraryDialog() {
  const { templates } = await api.get('/api/templates/library');
  const m = modal({
    title: 'Template library',
    wide: true,
    body: h('div', { class: 'grid grid-3' }, templates.map((t) => {
      const frame = h('iframe', { class: 'preview-frame', style: { height: '220px', pointerEvents: 'none' }, sandbox: '', title: t.name, srcdoc: t.html_content });
      const useBtn = h('button', { class: 'primary sm', onclick: () => busy(useBtn, async () => {
        const created = await api.post(`/api/templates/library/${t.key}`, {});
        m.close();
        toast('Template created');
        navigate(`templates/${created.id}`);
      }) }, 'Use this');
      return h('div', { class: 'card', style: { padding: '12px' } }, frame,
        h('div', { class: 'row spread', style: { marginTop: '10px' } }, h('strong', {}, t.name), useBtn),
        h('div', { class: 'small muted' }, t.subject_line));
    })),
  });
}

const STARTER_HTML = `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
</head>
<body style="font-family: Arial, sans-serif; background:#f4f4f5; margin:0; padding:24px;">
  <div style="max-width:600px; margin:0 auto; background:#ffffff; padding:32px; border-radius:8px;">
    <h1>Hi {{ first_name or "there" }},</h1>
    <p>Write your message here.</p>
    <p><a href="https://example.com">Visit our site</a></p>
  </div>
  <p style="text-align:center; font-size:12px; color:#71717a;">
    {{ business_name }} · {{ physical_address }}<br>
    <a href="{{ unsubscribe_url }}">Unsubscribe</a>
  </p>
</body>
</html>`;

const SNIPPETS = [
  ['First name', '{{ first_name }}'],
  ['Name or fallback', '{{ first_name or "there" }}'],
  ['Email', '{{ email }}'],
  ['Unsubscribe link', '{{ unsubscribe_url }}'],
  ['Business name', '{{ business_name }}'],
  ['Postal address', '{{ physical_address }}'],
  ['If / else', '{% if first_name %}Hi {{ first_name }}{% else %}Hello{% endif %}'],
];

export async function renderEditor(main, id) {
  const isNew = id === 'new';
  const template = isNew
    ? { name: '', subject_line: 'Hello {{ first_name }}', preview_text: '', html_content: STARTER_HTML, text_content: '' }
    : await api.get(`/api/templates/${id}`);

  const name = h('input', { value: template.name, required: true });
  const subject = h('input', { value: template.subject_line, required: true, oninput: () => refresh() });
  const previewText = h('input', { value: template.preview_text || '', placeholder: 'Shown next to the subject in the inbox', oninput: () => refresh() });
  const html = h('textarea', { class: 'code', spellcheck: false, value: template.html_content, oninput: () => refresh() });
  const text = h('textarea', { class: 'code', spellcheck: false, style: { minHeight: '140px' }, value: template.text_content || '',
    placeholder: 'Optional. Generated from the HTML when empty.', oninput: () => refresh() });
  const sampleName = h('input', { value: 'Jane', oninput: () => refresh(), 'aria-label': 'Sample first name' });
  let lastFocused = html;
  [subject, previewText, html, text].forEach((el) => el.addEventListener('focus', () => { lastFocused = el; }));

  // Tab inserts spaces in the code editor instead of moving focus
  html.addEventListener('keydown', (e) => {
    if (e.key === 'Tab' && !e.shiftKey) { e.preventDefault(); insertAt(html, '  '); }
  });

  const subjectOut = h('div', { class: 'preview-subject' });
  const frame = h('iframe', { class: 'preview-frame', sandbox: '', title: 'Email preview' });
  const textOut = h('pre', { class: 'mono small', style: { whiteSpace: 'pre-wrap', margin: 0 } });
  const variablesOut = h('div');
  const errorOut = h('div', { class: 'error-text' });
  let showText = false;
  const viewToggle = h('div', { class: 'tabs', style: { margin: '0 0 10px' } });

  function drawToggle() {
    clear(viewToggle,
      h('button', { class: showText ? '' : 'active', onclick: () => { showText = false; drawToggle(); } }, 'HTML'),
      h('button', { class: showText ? 'active' : '', onclick: () => { showText = true; drawToggle(); } }, 'Plain text'));
    frame.hidden = showText;
    textWrap.hidden = !showText;
  }

  const refresh = debounce(async () => {
    try {
      const r = await api.post('/api/templates/render', {
        subject_line: subject.value, html_content: html.value, text_content: text.value, preview_text: previewText.value,
        sample_data: { first_name: sampleName.value, full_name: `${sampleName.value} Doe`.trim() },
      });
      errorOut.textContent = '';
      clear(subjectOut, h('div', { class: 'small muted' }, 'Subject'), h('strong', {}, r.subject || '(empty)'),
        r.preview_text ? h('div', { class: 'small secondary' }, r.preview_text) : null);
      frame.srcdoc = r.html;
      textOut.textContent = r.text;
      clear(variablesOut, r.template_variables.length
        ? [h('span', { class: 'small muted' }, 'Variables used: '), r.template_variables.map((v) => h('span', { class: 'chip' }, v))]
        : null);
    } catch (err) {
      errorOut.textContent = errorMessage(err);
    }
  }, 400);

  const saveBtn = h('button', { class: 'primary', onclick: save }, isNew ? 'Create template' : 'Save');
  const actions = [h('button', { onclick: () => navigate('templates') }, 'Cancel'), saveBtn];
  if (!isNew) actions.unshift(h('button', { class: 'danger', onclick: remove }, icon('trash'), 'Delete'));

  const textWrap = h('div', { class: 'card', style: { padding: '12px', minHeight: '200px' }, hidden: true }, textOut);
  clear(main,
    pageHead(isNew ? 'New template' : template.name, null, actions, h('a', { href: '#/templates' }, '← Templates')),
    h('div', { class: 'editor' },
      h('div', { class: 'stack' },
        h('div', { class: 'card form' },
          field('Template name', name),
          field('Subject line', subject),
          field('Preview text', previewText)),
        h('div', { class: 'card form' },
          h('div', {}, h('div', { class: 'small muted', style: { marginBottom: '6px' } }, 'Insert:'),
            SNIPPETS.map(([label, snippet]) => h('button', { type: 'button', class: 'chip button', onclick: () => {
              insertAt(lastFocused, snippet);
              refresh();
            } }, label))),
          field('HTML', html, 'Links are tracked automatically. If there is no {{ unsubscribe_url }}, a footer with one is added when sending.'),
          field('Plain-text version', text)),
        errorOut),
      h('div', { class: 'card', style: { position: 'sticky', top: '16px' } },
        h('div', { class: 'card-head' }, h('h2', {}, 'Preview'),
          h('label', { class: 'row small secondary' }, 'Sample first name', h('div', { style: { width: '120px' } }, sampleName))),
        viewToggle, subjectOut, frame, textWrap, h('div', { style: { marginTop: '10px' } }, variablesOut))));
  drawToggle();
  refresh();

  async function save() {
    if (!name.value.trim()) { toast('Give the template a name', 'error'); name.focus(); return; }
    await busy(saveBtn, async () => {
      const body = { name: name.value.trim(), subject_line: subject.value, preview_text: previewText.value || null,
        html_content: html.value, text_content: text.value || null };
      const saved = isNew ? await api.post('/api/templates', body) : await api.put(`/api/templates/${id}`, body);
      toast(isNew ? 'Template created' : 'Template saved');
      if (isNew) navigate(`templates/${saved.id}`);
    });
  }

  async function remove() {
    if (!await confirmDialog('Delete template?', 'This cannot be undone. Templates used by campaigns cannot be deleted.',
      { confirmLabel: 'Delete', danger: true })) return;
    try {
      await api.del(`/api/templates/${id}`);
      toast('Template deleted');
      navigate('templates');
    } catch (err) { toastError(err); }
  }
}

function insertAt(input, snippet) {
  const start = input.selectionStart ?? input.value.length;
  const end = input.selectionEnd ?? input.value.length;
  input.value = input.value.slice(0, start) + snippet + input.value.slice(end);
  input.focus();
  input.selectionStart = input.selectionEnd = start + snippet.length;
}
