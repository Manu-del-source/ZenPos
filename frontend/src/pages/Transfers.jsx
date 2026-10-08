import React, { useCallback, useEffect, useState } from 'react';
import { ArrowLeftRight, Plus, Truck, X } from 'lucide-react';
import toast from 'react-hot-toast';
import api, { apiError } from '../services/api';

const STATUS_STYLES = {
  DRAFT: 'bg-slate-500/10 text-slate-400 border-slate-500/20',
  REQUESTED: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  APPROVED: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
  DISPATCHED: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
  IN_TRANSIT: 'bg-violet-500/10 text-violet-300 border-violet-500/20',
  RECEIVED: 'bg-green-500/10 text-green-400 border-green-500/20',
  CANCELLED: 'bg-red-500/10 text-red-400 border-red-500/20',
};

const qty = (v) => Number(v || 0).toLocaleString(undefined, { maximumFractionDigits: 3 });

const userCan = (code) => {
  let user = {};
  try { user = JSON.parse(localStorage.getItem('user') || '{}'); } catch { /* ignore */ }
  if (user.is_superuser) return true;
  return Array.isArray(user.permissions) && user.permissions.includes(code);
};

export default function Transfers() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('');
  const [branches, setBranches] = useState([]);
  const [products, setProducts] = useState([]);
  const [selected, setSelected] = useState(null);
  const [draft, setDraft] = useState(null);
  const [busy, setBusy] = useState(false);
  const canManage = userCan('inventory.transfer');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/transfers/', { params: statusFilter ? { status: statusFilter } : {} });
      setRows(Array.isArray(data) ? data : data.results || []);
    } catch (err) {
      toast.error(apiError(err, 'Failed to load transfers'));
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    Promise.all([
      api.get('/branches/', { params: { page_size: 100 } }).catch(() => ({ data: { results: [] } })),
      api.get('/products/', { params: { page_size: 500 } }).catch(() => ({ data: { results: [] } })),
    ]).then(([b, p]) => {
      setBranches(Array.isArray(b.data) ? b.data : b.data.results || []);
      setProducts(Array.isArray(p.data) ? p.data : p.data.results || []);
    });
  }, []);

  const open = async (row) => {
    try {
      const { data } = await api.get(`/transfers/${row.id}/`);
      setSelected(data);
    } catch (err) {
      toast.error(apiError(err, 'Could not load transfer'));
    }
  };

  const act = async (id, action, body = {}) => {
    setBusy(true);
    try {
      const { data } = await api.post(`/transfers/${id}/${action}/`, body);
      toast.success(`Transfer ${action}d`);
      setSelected(data);
      await load();
    } catch (err) {
      toast.error(apiError(err, `Could not ${action} the transfer`));
    } finally {
      setBusy(false);
    }
  };

  const saveDraft = async () => {
    if (!draft.source_branch || !draft.destination_branch) return toast.error('Choose source and destination.');
    const lines = draft.lines.filter((l) => l.product && Number(l.requested_quantity) > 0)
      .map((l) => ({ product: l.product, requested_quantity: String(l.requested_quantity) }));
    if (!lines.length) return toast.error('Add at least one product.');
    setBusy(true);
    try {
      await api.post('/transfers/', { ...draft, lines });
      toast.success('Transfer draft created');
      setDraft(null);
      await load();
    } catch (err) {
      toast.error(apiError(err, 'Could not save transfer'));
    } finally {
      setBusy(false);
    }
  };

  const receiveQuantities = {};
  (selected?.lines || []).forEach((line) => {
    receiveQuantities[line.id] = Number(line.dispatched_quantity) - Number(line.received_quantity);
  });

  return (
    <div className="p-8 max-w-7xl mx-auto min-h-screen">
      <div className="flex justify-between items-center mb-8 gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-black tracking-tight text-white">Stock Transfers</h1>
          <p className="text-slate-500 text-sm">Move stock between branches. Dispatch takes it off the source shelf; receive puts it on the destination.</p>
        </div>
        {canManage && (
          <button
            className="btn-primary"
            onClick={() => setDraft({
              source_branch: branches[0]?.id || '',
              destination_branch: branches[1]?.id || '',
              notes: '',
              lines: [{ product: '', requested_quantity: '' }],
            })}
          >
            <Plus size={16} /> New transfer
          </button>
        )}
      </div>

      <div className="mb-6">
        <select className="bg-slate-900 border border-slate-800 p-3 rounded-xl text-white" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">All statuses</option>
          {Object.keys(STATUS_STYLES).map((s) => <option key={s} value={s}>{s.replaceAll('_', ' ')}</option>)}
        </select>
      </div>

      <div className="bg-slate-900 rounded-3xl border border-slate-800 overflow-hidden">
        <table className="w-full text-sm text-left">
          <thead className="bg-slate-800/50">
            <tr className="text-slate-400 text-[10px] font-black uppercase tracking-[0.18em]">
              <th className="p-4">Transfer</th>
              <th className="p-4">From</th>
              <th className="p-4">To</th>
              <th className="p-4 text-center">Status</th>
              <th className="p-4"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {rows.map((row) => (
              <tr key={row.id} className="hover:bg-slate-800/30">
                <td className="p-4 font-bold text-white">{row.number}</td>
                <td className="p-4 text-slate-300">{row.source_branch_name}</td>
                <td className="p-4 text-slate-300">{row.destination_branch_name}</td>
                <td className="p-4 text-center">
                  <span className={`px-3 py-1 rounded-lg text-[10px] font-black uppercase tracking-widest border ${STATUS_STYLES[row.status] || ''}`}>
                    {(row.status || '').replaceAll('_', ' ')}
                  </span>
                </td>
                <td className="p-4 text-right">
                  <button className="px-3 py-2 bg-slate-800 rounded-lg text-xs font-bold text-slate-300" onClick={() => open(row)}>Open</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {loading && <div className="p-16 text-center text-slate-500 text-sm font-bold uppercase tracking-widest">Loading transfers…</div>}
        {!loading && rows.length === 0 && (
          <div className="p-20 text-center flex flex-col items-center">
            <ArrowLeftRight size={56} className="text-slate-800 mb-4" />
            <p className="text-slate-500 font-bold uppercase tracking-widest text-sm">No transfers yet</p>
          </div>
        )}
      </div>

      {draft && (
        <div className="fixed inset-0 bg-slate-950/80 z-[100] flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 w-full max-w-lg">
            <div className="flex justify-between mb-4">
              <h3 className="text-xl font-black text-white">New transfer</h3>
              <button onClick={() => setDraft(null)} className="text-slate-500"><X size={18} /></button>
            </div>
            <div className="space-y-3">
              <select className="w-full bg-slate-950 border border-slate-800 p-3 rounded-xl text-white" value={draft.source_branch} onChange={(e) => setDraft({ ...draft, source_branch: e.target.value })}>
                <option value="">Source branch…</option>
                {branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
              </select>
              <select className="w-full bg-slate-950 border border-slate-800 p-3 rounded-xl text-white" value={draft.destination_branch} onChange={(e) => setDraft({ ...draft, destination_branch: e.target.value })}>
                <option value="">Destination branch…</option>
                {branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
              </select>
              {draft.lines.map((line, i) => (
                <div key={i} className="grid grid-cols-[1fr_90px] gap-2">
                  <select className="bg-slate-950 border border-slate-800 p-3 rounded-xl text-white text-sm" value={line.product} onChange={(e) => {
                    const lines = draft.lines.map((l, idx) => idx === i ? { ...l, product: e.target.value } : l);
                    setDraft({ ...draft, lines });
                  }}>
                    <option value="">Product…</option>
                    {products.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                  </select>
                  <input type="number" min="0.001" step="any" placeholder="Qty" className="bg-slate-950 border border-slate-800 p-3 rounded-xl text-white text-sm" value={line.requested_quantity} onChange={(e) => {
                    const lines = draft.lines.map((l, idx) => idx === i ? { ...l, requested_quantity: e.target.value } : l);
                    setDraft({ ...draft, lines });
                  }} />
                </div>
              ))}
              <button type="button" className="text-xs font-bold text-blue-400" onClick={() => setDraft({ ...draft, lines: [...draft.lines, { product: '', requested_quantity: '' }] })}>+ Add line</button>
              <div className="flex gap-2 pt-2">
                <button className="flex-1 bg-slate-800 py-3 rounded-2xl font-bold text-slate-300" onClick={() => setDraft(null)}>Discard</button>
                <button className="flex-1 bg-blue-600 py-3 rounded-2xl font-black text-white disabled:opacity-50" disabled={busy} onClick={saveDraft}>Save draft</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {selected && (
        <div className="fixed inset-0 bg-slate-950/80 z-[100] flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 w-full max-w-3xl max-h-[90vh] overflow-y-auto">
            <div className="flex justify-between mb-4">
              <div>
                <h3 className="text-xl font-black text-white">{selected.number}</h3>
                <p className="text-slate-500 text-sm">{selected.source_branch_name} → {selected.destination_branch_name}</p>
              </div>
              <button onClick={() => setSelected(null)} className="text-slate-500"><X size={18} /></button>
            </div>
            <span className={`inline-flex px-3 py-1 rounded-lg text-[10px] font-black uppercase tracking-widest border mb-4 ${STATUS_STYLES[selected.status] || ''}`}>
              {(selected.status || '').replaceAll('_', ' ')}
            </span>
            <table className="w-full text-sm mb-4">
              <thead>
                <tr className="text-slate-500 text-[10px] uppercase tracking-widest">
                  <th className="p-2 text-left">Product</th>
                  <th className="p-2 text-right">Requested</th>
                  <th className="p-2 text-right">Approved</th>
                  <th className="p-2 text-right">Dispatched</th>
                  <th className="p-2 text-right">Received</th>
                </tr>
              </thead>
              <tbody>
                {(selected.lines || []).map((line) => (
                  <tr key={line.id} className="border-t border-slate-800">
                    <td className="p-2 text-white">{line.product_name}</td>
                    <td className="p-2 text-right">{qty(line.requested_quantity)}</td>
                    <td className="p-2 text-right">{qty(line.approved_quantity)}</td>
                    <td className="p-2 text-right">{qty(line.dispatched_quantity)}</td>
                    <td className="p-2 text-right">{qty(line.received_quantity)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {canManage && (
              <div className="flex flex-wrap gap-2">
                {selected.status === 'DRAFT' && <button className="btn-primary" disabled={busy} onClick={() => act(selected.id, 'request')}>Request</button>}
                {selected.status === 'REQUESTED' && <button className="btn-primary" disabled={busy} onClick={() => act(selected.id, 'approve')}>Approve</button>}
                {selected.status === 'APPROVED' && <button className="btn-primary" disabled={busy} onClick={() => act(selected.id, 'dispatch')}><Truck size={14} /> Dispatch</button>}
                {['DISPATCHED', 'IN_TRANSIT'].includes(selected.status) && (
                  <button className="btn-primary" disabled={busy} onClick={() => act(selected.id, 'receive', { quantities: receiveQuantities })}>Receive outstanding</button>
                )}
                {['DRAFT', 'REQUESTED', 'APPROVED'].includes(selected.status) && (
                  <button className="btn-secondary !text-red-400" disabled={busy} onClick={() => act(selected.id, 'cancel')}>Cancel</button>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
