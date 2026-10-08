import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  CheckCircle2, ClipboardList, FileText, Plus, RotateCcw, Search, Send, Trash2, X,
} from 'lucide-react';
import toast from 'react-hot-toast';
import api, { apiError } from '../services/api';

const STATUS_STYLES = {
  DRAFT: 'bg-slate-500/10 text-slate-400 border-slate-500/20',
  SUBMITTED: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  APPROVED: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
  PARTIALLY_RECEIVED: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
  RECEIVED: 'bg-green-500/10 text-green-400 border-green-500/20',
  CANCELLED: 'bg-red-500/10 text-red-400 border-red-500/20',
};

/** Actions the signed-in user may take on an order in this status. */
const STATUS_ACTIONS = {
  DRAFT: ['submit', 'cancel'],
  SUBMITTED: ['approve', 'reject', 'cancel'],
  APPROVED: ['cancel'],
  PARTIALLY_RECEIVED: [],
  RECEIVED: [],
  CANCELLED: [],
};

const money = (value) =>
  Number(value || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const emptyLine = { product: '', quantity: '', unit_cost: '' };

const PurchaseOrders = () => {
  const [orders, setOrders] = useState([]);
  const [suppliers, setSuppliers] = useState([]);
  const [branches, setBranches] = useState([]);
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('');

  const [showModal, setShowModal] = useState(false);
  const [draft, setDraft] = useState(null); // { branch, supplier, expected_date, notes, lines }
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState(null);

  const fetchOrders = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const params = {};
      if (searchTerm) params.search = searchTerm;
      if (statusFilter) params.status = statusFilter;
      const { data } = await api.get('/purchase-orders/', { params });
      setOrders(Array.isArray(data) ? data : data.results || []);
    } catch (err) {
      const message = apiError(err, 'Failed to load purchase orders');
      setLoadError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, [searchTerm, statusFilter]);

  useEffect(() => { fetchOrders(); }, [fetchOrders]);

  useEffect(() => {
    // The order form needs three directories. Each may 403 for a
    // view-only user; a read-only user still sees the list.
    Promise.all([
      api.get('/suppliers/', { params: { page_size: 200 } }).catch(() => ({ data: { results: [] } })),
      api.get('/branches/', { params: { page_size: 100 } }).catch(() => ({ data: { results: [] } })),
      api.get('/products/', { params: { page_size: 500 } }).catch(() => ({ data: { results: [] } })),
    ]).then(([s, b, p]) => {
      setSuppliers(Array.isArray(s.data) ? s.data : s.data.results || []);
      setBranches(Array.isArray(b.data) ? b.data : b.data.results || []);
      setProducts(Array.isArray(p.data) ? p.data : p.data.results || []);
    });
  }, []);

  const openNewDraft = () => {
    setDraft({
      branch: branches[0]?.id || '',
      supplier: '',
      expected_date: '',
      notes: '',
      lines: [{ ...emptyLine }],
    });
    setShowModal(true);
  };

  const updateLine = (index, key, value) => {
    setDraft((current) => {
      const lines = current.lines.map((line, i) =>
        i === index ? { ...line, [key]: value } : line,
      );
      return { ...current, lines };
    });
  };

  const addLine = () => setDraft((c) => ({ ...c, lines: [...c.lines, { ...emptyLine }] }));
  const removeLine = (index) =>
    setDraft((c) => ({
      ...c,
      lines: c.lines.length > 1 ? c.lines.filter((_, i) => i !== index) : c.lines,
    }));

  const draftTotal = useMemo(
    () =>
      (draft?.lines || []).reduce((sum, line) => {
        const qty = Number(line.quantity);
        const cost = Number(line.unit_cost || products.find((p) => p.id === line.product)?.cost_price);
        return sum + (Number.isFinite(qty) && Number.isFinite(cost) ? qty * cost : 0);
      }, 0),
    [draft, products],
  );

  const handleSaveDraft = async () => {
    if (!draft.branch) return toast.error('Choose a branch to deliver to.');
    if (!draft.supplier) return toast.error('Choose a supplier.');
    const lines = draft.lines
      .filter((line) => line.product && Number(line.quantity) > 0)
      .map((line) => ({
        product: line.product,
        quantity: String(line.quantity),
        ...(line.unit_cost !== '' ? { unit_cost: String(line.unit_cost) } : {}),
      }));
    if (lines.length === 0) return toast.error('Add at least one product with a quantity.');

    setSaving(true);
    try {
      await api.post('/purchase-orders/', { ...draft, lines });
      toast.success('Purchase order created as draft');
      setShowModal(false);
      await fetchOrders();
    } catch (err) {
      toast.error(apiError(err, 'Could not save the purchase order'));
    } finally {
      setSaving(false);
    }
  };

  const act = async (order, action, body = {}) => {
    setBusyId(order.id);
    try {
      await api.post(`/purchase-orders/${order.id}/${action}/`, body);
      toast.success(
        { submit: 'Order submitted for approval', approve: 'Order approved', reject: 'Order returned to draft', cancel: 'Order cancelled' }[action],
      );
      await fetchOrders();
    } catch (err) {
      toast.error(apiError(err, `Could not ${action} the order`));
    } finally {
      setBusyId(null);
    }
  };

  const reject = (order) => {
    const note = window.prompt('Return this order to draft — what should change?');
    if (note === null) return;
    if (!note.trim()) return toast.error('A note is required to reject an order.');
    act(order, 'reject', { notes: note.trim() });
  };

  const remove = async (order) => {
    if (!window.confirm(`Delete draft ${order.number}? This cannot be undone.`)) return;
    try {
      await api.delete(`/purchase-orders/${order.id}/`);
      toast.success('Draft deleted');
      await fetchOrders();
    } catch (err) {
      toast.error(apiError(err, 'Could not delete the draft'));
    }
  };

  const userCan = (code) => {
    let user = {};
    try { user = JSON.parse(localStorage.getItem('user') || '{}'); } catch { /* ignore */ }
    if (user.is_superuser) return true;
    return Array.isArray(user.permissions) && user.permissions.includes(code);
  };
  const canCreate = userCan('purchases.create');
  const canApprove = userCan('purchases.approve');

  const actionButton = (order, action) => {
    const styles = {
      submit: { icon: Send, label: 'Submit', cls: 'hover:text-blue-400' },
      approve: { icon: CheckCircle2, label: 'Approve', cls: 'hover:text-green-400' },
      reject: { icon: RotateCcw, label: 'Reject', cls: 'hover:text-amber-400' },
      cancel: { icon: X, label: 'Cancel', cls: 'hover:text-red-400' },
    };
    const { icon: Icon, label, cls } = styles[action];
    if (action === 'approve' && !canApprove) return null;
    if (action !== 'approve' && !canCreate) return null;
    return (
      <button
        key={action}
        onClick={() => (action === 'reject' ? reject(order) : act(order, action))}
        disabled={busyId === order.id}
        className={`px-3 py-2 bg-slate-800 rounded-lg text-slate-400 text-xs font-bold disabled:opacity-50 ${cls}`}
      >
        {label}
      </button>
    );
  };

  return (
    <div className="p-8 max-w-7xl mx-auto min-h-screen">
      <div className="flex justify-between items-center mb-8 gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-black tracking-tight text-white">Purchase Orders</h1>
          <p className="text-slate-500 text-sm">What the business has asked its suppliers for.</p>
        </div>
        {canCreate && (
          <button onClick={openNewDraft} className="btn-primary flex items-center">
            <Plus size={18} className="mr-2" /> New order
          </button>
        )}
      </div>

      <div className="mb-6 flex gap-3 flex-wrap">
        <div className="relative flex-1 min-w-[240px]">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-500" size={20} />
          <input
            className="w-full bg-slate-900 border border-slate-800 p-4 pl-12 rounded-2xl text-white outline-none focus:border-blue-500 transition-all"
            placeholder="Search by number or supplier..."
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
          {Object.keys(STATUS_STYLES).map((s) => (
            <option key={s} value={s}>{s.replace('_', ' ')}</option>
          ))}
        </select>
      </div>

      {loadError && !loading && (
        <div className="panel mb-6 p-6 text-center">
          <p className="text-red-400 font-semibold">Could not load purchase orders</p>
          <p className="text-slate-500 text-sm mt-1">{loadError}</p>
          <button className="btn-secondary mt-4" onClick={fetchOrders}>Try again</button>
        </div>
      )}

      <div className="bg-slate-900 rounded-3xl border border-slate-800 overflow-hidden shadow-2xl">
        <table className="w-full text-left">
          <thead className="bg-slate-800/50">
            <tr className="text-slate-400 text-[10px] font-black uppercase tracking-[0.2em]">
              <th className="p-5">Order</th>
              <th className="p-5">Supplier</th>
              <th className="p-5">Branch</th>
              <th className="p-5 text-right">Total</th>
              <th className="p-5 text-center">Status</th>
              <th className="p-5 text-center">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {orders.map((order) => (
              <tr key={order.id} className="hover:bg-slate-800/30 transition group">
                <td className="p-5">
                  <div className="font-bold text-white flex items-center gap-2">
                    <FileText size={15} className="text-slate-600" />
                    {order.number}
                  </div>
                  <div className="text-xs text-slate-500 mt-1">
                    {order.lines?.length || 0} item{(order.lines?.length || 0) === 1 ? '' : 's'}
                  </div>
                </td>
                <td className="p-5 text-slate-300">{order.supplier_name || '—'}</td>
                <td className="p-5 text-slate-300">{order.branch_name || '—'}</td>
                <td className="p-5 text-right font-bold text-white">{money(order.total_cost)}</td>
                <td className="p-5 text-center">
                  <span className={`px-3 py-1 rounded-lg text-[10px] font-black uppercase tracking-widest border ${STATUS_STYLES[order.status] || ''}`}>
                    {(order.status || '').replace('_', ' ')}
                  </span>
                </td>
                <td className="p-5 text-center whitespace-nowrap">
                  {(STATUS_ACTIONS[order.status] || []).map((a) => actionButton(order, a))}
                  {order.status === 'DRAFT' && canCreate && (
                    <button
                      onClick={() => remove(order)}
                      className="ml-2 p-2 bg-slate-800 rounded-lg text-slate-400 hover:text-red-500"
                      aria-label={`Delete draft ${order.number}`}
                      title="Delete draft"
                    >
                      <Trash2 size={16} />
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {loading && (
          <div className="p-16 text-center text-slate-500 font-bold uppercase tracking-widest text-sm">
            Loading purchase orders…
          </div>
        )}

        {!loading && !loadError && orders.length === 0 && (
          <div className="p-20 text-center flex flex-col items-center">
            <ClipboardList size={64} className="text-slate-800 mb-4" />
            <p className="text-slate-500 font-bold uppercase tracking-widest text-sm">
              {searchTerm || statusFilter ? 'No orders match those filters' : 'No purchase orders yet'}
            </p>
          </div>
        )}
      </div>

      {showModal && draft && (
        <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center z-[100] p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-3xl p-8 w-full max-w-2xl shadow-2xl max-h-[90vh] overflow-y-auto">
            <h3 className="text-2xl font-black mb-6 text-white tracking-tight">New purchase order</h3>
            <form
              onSubmit={(e) => { e.preventDefault(); handleSaveDraft(); }}
              className="space-y-4"
            >
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">Branch *</label>
                  <select
                    required
                    className="w-full bg-slate-950 border border-slate-800 p-4 rounded-xl text-white outline-none focus:border-blue-500"
                    value={draft.branch}
                    onChange={(e) => setDraft({ ...draft, branch: e.target.value })}
                  >
                    <option value="">Choose…</option>
                    {branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">Supplier *</label>
                  <select
                    required
                    className="w-full bg-slate-950 border border-slate-800 p-4 rounded-xl text-white outline-none focus:border-blue-500"
                    value={draft.supplier}
                    onChange={(e) => setDraft({ ...draft, supplier: e.target.value })}
                  >
                    <option value="">Choose…</option>
                    {suppliers.filter((s) => s.status === 'ACTIVE').map((s) => (
                      <option key={s.id} value={s.id}>{s.name}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">Expected date</label>
                  <input
                    type="date"
                    className="w-full bg-slate-950 border border-slate-800 p-4 rounded-xl text-white outline-none focus:border-blue-500"
                    value={draft.expected_date}
                    onChange={(e) => setDraft({ ...draft, expected_date: e.target.value })}
                  />
                </div>
                <div>
                  <label className="block text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">Notes</label>
                  <input
                    className="w-full bg-slate-950 border border-slate-800 p-4 rounded-xl text-white outline-none focus:border-blue-500"
                    value={draft.notes}
                    onChange={(e) => setDraft({ ...draft, notes: e.target.value })}
                  />
                </div>
              </div>

              <div className="border-t border-slate-800 pt-4">
                <div className="flex items-center justify-between mb-3">
                  <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Items</label>
                  <button type="button" onClick={addLine} className="text-xs font-bold text-blue-400 hover:text-blue-300 flex items-center">
                    <Plus size={14} className="mr-1" /> Add item
                  </button>
                </div>
                {draft.lines.map((line, index) => (
                  <div key={index} className="grid grid-cols-[1fr_90px_110px_40px] gap-2 mb-2">
                    <select
                      required
                      className="bg-slate-950 border border-slate-800 p-3 rounded-xl text-white outline-none focus:border-blue-500 text-sm"
                      value={line.product}
                      onChange={(e) => updateLine(index, 'product', e.target.value)}
                    >
                      <option value="">Product…</option>
                      {products.map((p) => (
                        <option key={p.id} value={p.id}>{p.name}</option>
                      ))}
                    </select>
                    <input
                      required
                      min="0.001"
                      step="any"
                      type="number"
                      placeholder="Qty"
                      className="bg-slate-950 border border-slate-800 p-3 rounded-xl text-white outline-none focus:border-blue-500 text-sm"
                      value={line.quantity}
                      onChange={(e) => updateLine(index, 'quantity', e.target.value)}
                    />
                    <input
                      min="0"
                      step="0.01"
                      type="number"
                      placeholder="Unit cost"
                      className="bg-slate-950 border border-slate-800 p-3 rounded-xl text-white outline-none focus:border-blue-500 text-sm"
                      value={line.unit_cost}
                      onChange={(e) => updateLine(index, 'unit_cost', e.target.value)}
                    />
                    <button
                      type="button"
                      onClick={() => removeLine(index)}
                      className="p-3 rounded-xl bg-slate-950 border border-slate-800 text-slate-500 hover:text-red-400"
                      aria-label="Remove line"
                    >
                      <X size={15} className="mx-auto" />
                    </button>
                  </div>
                ))}
                <div className="text-right text-sm font-bold text-white pt-2">
                  Estimated total: <span className="text-blue-400">{money(draftTotal)}</span>
                </div>
              </div>

              <div className="flex space-x-3 pt-2">
                <button type="button" onClick={() => setShowModal(false)} className="flex-1 bg-slate-800 text-slate-400 py-4 rounded-2xl font-bold uppercase">
                  Discard
                </button>
                <button type="submit" disabled={saving} className="flex-1 bg-blue-600 text-white py-4 rounded-2xl font-black uppercase disabled:opacity-50">
                  {saving ? 'Saving…' : 'Save draft'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default PurchaseOrders;
