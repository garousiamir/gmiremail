import { api, errorMessage } from '../api.js';
import {
  busy, clear, confirmDialog, debounce, emptyState, field, fmtNum, h, icon, loading, navigate, pageHead, pager,
  relTime, spinner, table, toast, toastError,
} from '../ui.js';
import { loadRuleContext, ruleBuilder } from '../components/rules.js';

export async function renderList(main) {
  let page = 1;
  let search = '';
  const host = h('div', {}, loading());
  const searchBox = h('input', { type: 'search', placeholder: 'Search segments', 'aria-label': 'Search segments',
    oninput: debounce(() => { search = searchBox.value.trim().toLowerCase(); page = 1; load(); }) });
  clear(main, pageHead('Segments', 'Groups of subscribers defined by rules. Membership updates automatically.', [
    h('button', { class: 'primary', onclick: () => navigate('segments/new') }, icon('plus'), 'New segment'),
  ]), h('div', { class: 'card' }, h('div', { class: 'toolbar' }, searchBox), host));

  async function load() {
    const data = await api.get('/api/segments', { page: search ? 1 : page, per_page: search ? 100 : 25 });
    const items = search ? data.items.filter((s) => `${s.name} ${s.description || ''}`.toLowerCase().includes(search)) : data.items;
    clear(host, table([
      { label: 'Segment', render: (s) => h('div', {}, h('a', { class: 'cell-main', href: `#/segments/${s.id}` }, s.name),
        s.description ? h('div', { class: 'cell-sub' }, s.description) : null) },
      { label: 'Rules', class: 'num', render: (s) => (s.filter_rules?.rules || []).length },
      { label: 'Subscribers', class: 'num', render: (s) => h('strong', {}, fmtNum(s.subscriber_count)) },
      { label: 'Counted', render: (s) => h('span', { class: 'muted' }, relTime(s.count_updated_at)) },
    ], items, {
      onRowClick: (s) => navigate(`segments/${s.id}`),
      empty: search ? 'No segments match your search.' : emptyState('filter', 'No segments yet',
        'A segment lets you target a campaign at part of your list, e.g. people who joined this month.',
        h('button', { class: 'primary', onclick: () => navigate('segments/new') }, icon('plus'), 'Create a segment')),
    }), search ? null : pager(data, (p) => { page = p; load(); }));
  }
  await load();
}

export async function renderEditor(main, id) {
  const isNew = id === 'new';
  const [segment, context] = await Promise.all([
    isNew ? Promise.resolve({ name: '', description: '', filter_rules: { logic: 'AND', rules: [] } }) : api.get(`/api/segments/${id}`),
    loadRuleContext(),
  ]);

  const name = h('input', { value: segment.name, required: true, 'aria-label': 'Segment name', placeholder: 'e.g. Joined this month' });
  const description = h('input', { value: segment.description || '', placeholder: 'Optional' });
  const previewHost = h('div', {}, h('span', { class: 'muted' }, 'Add a rule to see who matches.'));

  const refreshPreview = debounce(async () => {
    const current = builder?.get();
    if (!current) { clear(previewHost, h('div', { class: 'error-text' }, 'Invalid JSON')); return; }
    clear(previewHost, h('div', { class: 'loader' }, spinner(true)));
    try {
      const result = await api.post('/api/segments/preview', { filter_rules: current });
      clear(previewHost,
        h('div', { class: 'aud-summary', style: { marginBottom: '14px' } },
          h('div', { class: 'big' }, fmtNum(result.subscriber_count)), h('strong', {}, 'matching subscribers')),
        result.sample.length ? h('div', {}, h('div', { class: 'small muted', style: { marginBottom: '6px' } }, 'Most recent matches'),
          table([
            { label: 'Email', render: (s) => s.email },
            { label: 'Status', render: (s) => h('span', { class: `badge ${s.status === 'active' ? 'good' : ''}` }, s.status) },
          ], result.sample)) : null);
    } catch (err) {
      clear(previewHost, h('div', { class: 'error-text' }, errorMessage(err)));
    }
  }, 400);

  const builder = ruleBuilder({ rules: segment.filter_rules, context, onChange: refreshPreview });

  const saveBtn = h('button', { class: 'primary', onclick: save }, icon('check'), isNew ? 'Create segment' : 'Save');
  const actions = [h('button', { onclick: () => navigate('segments') }, 'Cancel'), saveBtn];
  if (!isNew) actions.unshift(h('button', { class: 'danger', onclick: remove }, icon('trash'), 'Delete'));

  clear(main,
    pageHead(isNew ? 'New segment' : segment.name, 'Combine rules on any field. Dates support ranges like "between two dates".',
      actions, h('a', { href: '#/segments' }, '← Segments')),
    h('div', { class: 'editor' },
      h('div', { class: 'stack' },
        h('div', { class: 'card form' }, h('div', { class: 'form-row' }, field('Name', name), field('Description', description))),
        h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Rules')), builder.el)),
      h('div', { class: 'card', style: { position: 'sticky', top: '16px' } }, h('div', { class: 'card-head' }, h('h2', {}, 'Live preview')), previewHost)));
  refreshPreview();

  async function save() {
    const filterRules = builder.get();
    if (!filterRules) { toast('The rules JSON is not valid', 'error'); return; }
    if (!name.value.trim()) { toast('Give the segment a name', 'error'); name.focus(); return; }
    await busy(saveBtn, async () => {
      const body = { name: name.value.trim(), description: description.value.trim() || null, filter_rules: filterRules };
      const saved = isNew ? await api.post('/api/segments', body) : await api.put(`/api/segments/${id}`, body);
      toast({ title: isNew ? 'Segment created' : 'Segment saved', message: `${fmtNum(saved.subscriber_count)} subscribers match.` });
      if (isNew) navigate(`segments/${saved.id}`);
    });
  }

  async function remove() {
    if (!await confirmDialog('Delete segment?', 'Campaigns already sent keep their history.', { confirmLabel: 'Delete', danger: true })) return;
    try {
      await api.del(`/api/segments/${id}`);
      toast('Segment deleted');
      navigate('segments');
    } catch (err) { toastError(err); }
  }
}
