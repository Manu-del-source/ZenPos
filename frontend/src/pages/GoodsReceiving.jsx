import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ClipboardCheck, PackageCheck, Search, X } from 'lucide-react';
import toast from 'react-hot-toast';
import api, { apiError } from '../services/api';

const STATUS_STYLES = {
  DRAFT: 'bg-slate-500/10 text-slate-400 border-slate-500/20',
  POSTED: 'bg-green-500/10 text-green-400 border-green-500/20',
  CANCELLED: 'bg-red-500/10 text-red-400 border-red-500/20',
};

const money = (value) =>
  Number(value || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const qty = (value) => Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 3 });

const userCan = (code) => {
  let user = {};
  try { user = JSON.parse(localStorage.getItem('user') || '{}'); } catch { /* ignore */ }
  if (user.is_superuser) return true;
  return Array.isArray(user.permissions) && user.permissions.includes(code);
};

const GoodsReceiving = () => {
  const [params, setParams] = useSearchParams();
  const poId = params.get('po');

  const [notes, setNotes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [busyId, setBusyId] = useState(null);

  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);

  const canCreate = userCan('purchases.create');
  const canReceive = userCan('purchases.receive');

  const fetchNotes = useCallback(async () => {
    setLoading(true);
    try {
      const query = {};
      if (searchTerm) query.search = searchTerm;
      if (statusFilter) query.status = statusFilter;
      const { data } = await api.get('/goods-receipts/', { params: query });
      setNotes(Array.isArray(data) ? data : data.results || []);
    } catch (err) {
      toast.error(apiError(err, 'Failed to load goods received notes'));
    } finally {
      setLoading(false);
    }
  }, [searchTerm, statusFilter]);

  useEffect(() => { fetchNotes(); }, [fetchNotes]);

  const openFromPo = useCallback(async (id) => {
    try {
      const { data: order } = await api.get(`/purchase-orders/${id}/`);
      if (!['APPROVED', 'PARTIALLY_RECEIVED'].includes(order.status)) {
        toast.error('Goods can only be received against an approved order.');
        return;
      }
      setForm({
        id: null,
        purchase_order: order.id,
        purchase_order_number: order.number,
        supplier_name: order.supplier_name,
        branch_name: order.branch_name,
        delivery_note: '',
        received_date: new Date().toISOString().slice(0, 10),
        notes: '',
        lines: (order.lines || [])
          .filter((line) => Number(line.quantity_outstanding || line.quantity) > 0)
          .map((line) => ({
            purchase_order_line: line.id,
            product_name: line.product_name,
            ordered_quantity: line.quantity,
            previously_received: line.quantity_received || 0,
            quantity_outstanding: line.quantity_outstanding,
            quantity_received: line.quantity_outstanding,
            unit_cost: line.unit_cost,
          })),
      });
    } catch (err) {
      toast.error(apiError(err, 'Could not load the purchase order'));
    }
  }, []);

  useEffect(() => {
    if (poId) openFromPo(poId);
  }, [poId, openFromPo]);

  const openExisting = async (grn) => {
    try {
      const { data } = await api.get(`/goods-receipts/${grn.id}/`);
      setForm({
        id: data.id,
        status: data.status,
        purchase_order: data.purchase_order,
        purchase_order_number: data.purchase_order_number,
        supplier_name: data.supplier_name,
        branch_name: data.branch_name,
        delivery_note: data.delivery_note || '',
        received_date: data.received_date,
        notes: data.notes || '',
        lines: (data.lines || []).map((line) => ({
          purchase_order_line: line.purchase_order_line,
          product_name: line.product_name,
          ordered_quantity: line.ordered_quantity,
          previously_received: line.previously_received,
          quantity_outstanding: line.quantity_outstanding,
          quantity_received: line.quantity_received,
          unit_cost: line.unit_cost,
        })),
      });
    } catch (err) {
      toast.error(apiError(err, 'Could not load the GRN'));
    }
  };

  const closeForm = () => {
    setForm(null);
    if (poId) {
      params.delete('po');
      setParams(params, { replace: true });
    }
  };

  const updateLine = (index, key, value) => {
    setForm((current) => {
      const lines = current.lines.map((line, i) => (i === index ? { ...line, [key]: value } : line));
      return { ...current, lines };
    });
  };

  const payloadFromForm = () => ({
    purchase_order: form.purchase_order,
    delivery_note: form.delivery_note,
    received_date: form.received_date,
    notes: form.notes,
    lines: form.lines
      .filter((line) => Number(line.quantity_received) > 0)
      .map((line) => ({
        purchase_order_line: line.purchase_order_line,
        quantity_received: String(line.quantity_received),
        unit_cost: String(line.unit_cost),
      })),
  });

  const saveDraft = async () => {
    const body = payloadFromForm();
    if (body.lines.length === 0) return toast.error('Enter a quantity to receive on at least one line.');
    setSaving(true);
    try {
      if (form.id) {
        await api.patch(`/goods-receipts/${form.id}/`, body);
        toast.success('Draft updated');
      } else {
        const { data } = await api.post('/goods-receipts/', body);
        setForm((current) => ({ ...current, id: data.id, status: data.status }));
        toast.success('GRN saved as draft');
      }
      await fetchNotes();
    } catch (err) {
      toast.error(apiError(err, 'Could not save the GRN'));
    } finally {
      setSaving(false);
    }
  };

  const postGrn = async () => {
    if (!window.confirm('Post this GRN? Stock will be updated and this cannot be undone.')) return;
    setSaving(true);
    try {
      let id = form.id;
      const body = payloadFromForm();
      if (body.lines.length === 0) {
        setSaving(false);
        return toast.error('Enter a quantity to receive on at least one line.');
      }
      if (!id) {
        const { data } = await api.post('/goods-receipts/', body);
        id = data.id;
      } else if (form.status === 'DRAFT' || !form.status) {
        await api.patch(`/goods-receipts/${id}/`, body);
      }
      await api.post(`/goods-receipts/${id}/post/`);
      toast.success('GRN posted — inventory updated');
      closeForm();
      await fetchNotes();
    } catch (err) {
      toast.error(apiError(err, 'Could not post the GRN'));
    } finally {
      setSaving(false);
    }
  };

  const cancelGrn = async (grn) => {
    if (!window.confirm(`Cancel ${grn.number}?`)) return;
    setBusyId(grn.id);
    try {
      await api.post(`/goods-receipts/${grn.id}/cancel/`);
      toast.success('GRN cancelled');
      await fetchNotes();
    } catch (err) {
      toast.error(apiError(err, 'Could not cancel the GRN'));
    } finally {
      setBusyId(null);
    }
  };

  const formTotal = useMemo(
    () => (form?.lines || []).reduce((sum, line) => sum + Number(line.quantity_received || 0) * Number(line.unit_cost || 0), 0),
    [form],
  );

  return (
    <div className="p-8 max-w-7xl mx-auto min-h-screen">
      <div className="flex justify-between items-center mb-8 gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-black tracking-tight text-white">Goods Receiving</h1>
          <p className="text-slate-500 text-sm">Record deliveries against approved purchase orders. Stock moves only when a GRN is posted.</p>
        </div>
      </div>

      <div className="mb-6 flex gap-3 flex-wrap">
        <div className="relative flex-1 min-w-[240px]">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-500" size={20} />
          <input
            className="w-full bg-slate-900 border border-slate-800 p-4 pl-12 rounded-2xl text-white outline-none focus:border-blue-500"
            placeholder="Search by GRN, PO or delivery note…"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
        <select
          className="bg-slate-900 border border-slate-800 p-4 rounded-2xl text-white outline-none focus:border-blue-500"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
        >
          <option value="">All statuses</option>
          {Object.keys(STATUS_STYLES).map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>

      <div className="bg-slate-900 rounded-3xl border border-slate-800 overflow-hidden shadow-2xl">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-800/50">
            <tr className="text-slate-400 text-[10px] font-black uppercase tracking-[0.2em]">
              <th className="p-4">GRN</th>
              <th className="p-4">Purchase order</th>
              <th className="p-4">Supplier</th>
              <th className="p-4">Branch</th>
              <th className="p-4">Received</th>
              <th className="p-4 text-center">Status</th>
              <th className="p-4 text-center">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {notes.map((grn) => (
              <tr key={grn.id} className="hover:bg-slate-800/30">
                <td className="p-4 font-bold text-white">{grn.number}</td>
                <td className="p-4 text-slate-300">{grn.purchase_order_number}</td>
                <td className="p-4 text-slate-300">{grn.supplier_name}</td>
                <td className="p-4 text-slate-300">{grn.branch_name}</td>
                <td className="p-4 text-slate-400 text-xs">{grn.received_date}</td>
                <td className="p-4 text-center">
                  <span className={`px-3 py-1 rounded-lg text-[10px] font-black uppercase tracking-widest border ${STATUS_STYLES[grn.status] || ''}`}>
                    {grn.status}
                  </span>
                </td>
                <td className="p-4 text-center whitespace-nowrap">
                  <button onClick={() => openExisting(grn)} className="px-3 py-2 bg-slate-800 rounded-lg text-slate-300 text-xs font-bold hover:text-white">
                    Open
                  </button>
                  {grn.status === 'DRAFT' && canCreate && (
                    <button
                      onClick={() => cancelGrn(grn)}
                      disabled={busyId === grn.id}
                      className="ml-2 px-3 py-2 bg-slate-800 rounded-lg text-slate-400 text-xs font-bold hover:text-red-400"
                    >
                      Cancel
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {loading && <div className="p-16 text-center text-slate-500 font-bold uppercase tracking-widest text-sm">Loading receipts…</div>}
        {!loading && notes.length === 0 && (
          <div className="p-20 text-center flex flex-col items-center">
            <PackageCheck size={64} className="text-slate-800 mb-4" />
            <p className="text-slate-500 font-bold uppercase tracking-widest text-sm">No goods received notes yet</p>
            <p className="text-slate-600 text-xs mt-2">Open an approved purchase order and choose Receive Goods.</p>
          </div>
        )}
      </div>

      {form && (
        <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center z-[100] p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 w-full max-w-5xl shadow-2xl max-h-[92vh] overflow-y-auto">
            <div className="flex items-start justify-between mb-4">
              <div>
                <h3 className="text-2xl font-black text-white tracking-tight">Receive goods</h3>
                <p className="text-slate-500 text-sm mt-1">
                  {form.purchase_order_number} · {form.supplier_name} · {form.branch_name}
                </p>
              </div>
              <button onClick={closeForm} className="p-2 text-slate-500 hover:text-white"><X size={20} /></button>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
              <div>
                <label className="block text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">Delivery note</label>
                <input
                  className="w-full bg-slate-950 border border-slate-800 p-3 rounded-xl text-white outline-none focus:border-blue-500"
                  value={form.delivery_note}
                  onChange={(e) => setForm({ ...form, delivery_note: e.target.value })}
                  disabled={form.status && form.status !== 'DRAFT'}
                />
              </div>
              <div>
                <label className="block text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">Received date</label>
                <input
                  type="date"
                  className="w-full bg-slate-950 border border-slate-800 p-3 rounded-xl text-white outline-none focus:border-blue-500"
                  value={form.received_date}
                  onChange={(e) => setForm({ ...form, received_date: e.target.value })}
                  disabled={form.status && form.status !== 'DRAFT'}
                />
              </div>
              <div>
                <label className="block text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">Notes</label>
                <input
                  className="w-full bg-slate-950 border border-slate-800 p-3 rounded-xl text-white outline-none focus:border-blue-500"
                  value={form.notes}
                  onChange={(e) => setForm({ ...form, notes: e.target.value })}
                  disabled={form.status && form.status !== 'DRAFT'}
                />
              </div>
            </div>

            <div className="border border-slate-800 rounded-2xl overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-slate-800/60">
                  <tr className="text-slate-400 text-[10px] font-black uppercase tracking-[0.16em]">
                    <th className="p-3 text-left">Product</th>
                    <th className="p-3 text-right">Ordered</th>
                    <th className="p-3 text-right">Previously received</th>
                    <th className="p-3 text-right">Outstanding</th>
                    <th className="p-3 text-right">Receiving now</th>
                    <th className="p-3 text-right">Unit cost</th>
                    <th className="p-3 text-right">Line total</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {form.lines.map((line, index) => (
                    <tr key={line.purchase_order_line}>
                      <td className="p-3 text-white font-semibold">{line.product_name}</td>
                      <td className="p-3 text-right text-slate-300">{qty(line.ordered_quantity)}</td>
                      <td className="p-3 text-right text-slate-400">{qty(line.previously_received)}</td>
                      <td className="p-3 text-right text-slate-300">{qty(line.quantity_outstanding)}</td>
                      <td className="p-3 text-right">
                        <input
                          type="number"
                          min="0"
                          step="any"
                          className="w-24 bg-slate-950 border border-slate-800 p-2 rounded-lg text-white text-right outline-none focus:border-blue-500"
                          value={line.quantity_received}
                          onChange={(e) => updateLine(index, 'quantity_received', e.target.value)}
                          disabled={form.status && form.status !== 'DRAFT'}
                        />
                      </td>
                      <td className="p-3 text-right text-slate-300">{money(line.unit_cost)}</td>
                      <td className="p-3 text-right font-bold text-white">
                        {money(Number(line.quantity_received || 0) * Number(line.unit_cost || 0))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {form.lines.length === 0 && (
                <div className="p-8 text-center text-slate-500 text-sm">Nothing outstanding on this order.</div>
              )}
            </div>

            <div className="flex items-center justify-between mt-4 gap-3 flex-wrap">
              <div className="text-sm font-bold text-white">Total receiving: <span className="text-blue-400">{money(formTotal)}</span></div>
              <div className="flex gap-2">
                <button type="button" onClick={closeForm} className="px-4 py-3 rounded-2xl bg-slate-800 text-slate-300 font-bold">Close</button>
                {(!form.status || form.status === 'DRAFT') && canCreate && (
                  <button type="button" onClick={saveDraft} disabled={saving} className="px-4 py-3 rounded-2xl bg-slate-800 text-white font-bold disabled:opacity-50">
                    {saving ? 'Saving…' : 'Save draft'}
                  </button>
                )}
                {(!form.status || form.status === 'DRAFT') && canReceive && (
                  <button type="button" onClick={postGrn} disabled={saving} className="px-4 py-3 rounded-2xl bg-blue-600 text-white font-black disabled:opacity-50 inline-flex items-center gap-2">
                    <ClipboardCheck size={16} /> {saving ? 'Posting…' : 'Post GRN'}
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default GoodsReceiving;
