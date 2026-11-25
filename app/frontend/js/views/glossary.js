// UC06 Từ điển thuật ngữ — tri thức nghiệp vụ được ghép vào prompt (vai trò của "evidence" trong BIRD)
import { api, can, confirmDialog, dataTable, esc, fmt, formModal, h, icon, toast, toastError } from '../core.js';

function termForm(t, reload) {
  return formModal({
    title: t ? 'Edit term' : 'Add term', values: t || { is_active: true },
    fields: [
      { name: 'term', label: 'Term', required: true, span: 2, placeholder: 'e.g. end-of-year party', help: 'When a question contains this phrase (case-insensitive), the definition is added to the prompt.' },
      { name: 'definition', label: 'Definition in database terms', type: 'textarea', required: true, span: 2, placeholder: "e.g. event.type = 'Social'", help: 'Use the database table/column names so the model generates correct SQL.' },
      { name: 'is_active', type: 'checkbox', text: 'Active', span: 2 },
    ],
    onSubmit: async (v) => {
      await api(t ? `/api/glossary/${t.id}` : '/api/glossary', { method: t ? 'PUT' : 'POST', body: v });
      toast(t ? 'Term updated.' : 'Term added.');
      reload();
    },
  });
}

export default async function glossary({ view, setHeader }) {
  const load = async () => {
    const rows = await api('/api/glossary');
    const w = can('glossary.write');
    setHeader(`${rows.filter((r) => r.is_active).length} active terms`, w ? [{ label: 'Add term', icon: 'plus', onClick: () => termForm(null, load) }] : []);
    view.innerHTML = `<div class="alert info">${icon('info')}<div><b>The glossary teaches the AI how your club talks</b>
      <p>The BIRD paper shows that adding domain knowledge ("evidence") to the prompt makes models generate correct SQL far more often (GPT-3.5-Turbo on the dev set: 31.2% → 47.8% EX).
      The system finds active terms in each question and adds a <code>-- External Knowledge</code> line to the prompt.</p></div></div>`;
    const card = h('<section class="card"></section>');
    card.append(dataTable({
      rows, pageSize: 15, searchKeys: ['term', 'definition'],
      columns: [
        { key: 'term', label: 'Term', render: (r) => `<b>${esc(r.term)}</b>` },
        { key: 'definition', label: 'Definition', render: (r) => `<code>${esc(r.definition)}</code>` },
        { key: 'is_active', label: 'Status', render: (r) => (r.is_active ? '<span class="badge good">Active</span>' : '<span class="badge muted">Off</span>') },
        { key: 'updated_at', label: 'Updated', render: (r) => `<small>${fmt.datetime(r.updated_at)}${r.updated_by_name ? `<br>${esc(r.updated_by_name)}` : ''}</small>` },
        ...(w ? [{ label: '', sortable: false, render: (r) => `<span class="row-actions"><button class="icon-btn" title="Edit" aria-label="Edit" data-edit="${r.id}">${icon('edit')}</button><button class="icon-btn" title="Delete" aria-label="Delete" data-del="${r.id}">${icon('trash')}</button></span>` }] : []),
      ],
    }));
    view.append(card);
    card.addEventListener('click', async (e) => {
      const ed = e.target.closest('[data-edit]'), del = e.target.closest('[data-del]');
      if (ed) return termForm(rows.find((r) => r.id === +ed.dataset.edit), load);
      if (del) {
        const t = rows.find((r) => r.id === +del.dataset.del);
        if (await confirmDialog(`Delete term "${t.term}"?`, { danger: true, ok: 'Delete' })) {
          try { await api(`/api/glossary/${t.id}`, { method: 'DELETE' }); toast('Term deleted.'); load(); } catch (err) { toastError(err); }
        }
      }
    });
  };
  await load();
}
