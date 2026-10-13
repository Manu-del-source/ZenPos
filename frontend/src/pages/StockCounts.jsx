import React, { useCallback, useEffect, useState } from 'react';
import { ClipboardCheck, PackageSearch, Plus, RefreshCw, Search, X } from 'lucide-react';
import toast from 'react-hot-toast';
import api, { apiError } from '../services/api';
import { can } from '../App';

const unwrap = (data) => (Array.isArray(data) ? data : data?.results || []);

const readUser = () => {
  try { return JSON.parse(localStorage.getItem('user') || '{}') || {}; } catch { return {}; }
};

const fmtQty = (value) => {
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value ?? '—');
  return n % 1 === 0 ? String(n) : n.toFixed(2);
};

const fmtMoney = (value) => {
  const n = Number(value);
  if (value === null || value === undefined || !Number.isFinite(n)) return '—';
  return `KES ${n.toFixed(2)}`;
};

const NewCountForm = ({ branches, onPosted, onClose }) => {
  const [branch, setBranch] = useState('');
  const [search, setSearch] = useState('');
  const [matches, setMatches] = useState([]);
  const [lines, setLines] = useState([]);
  const [notes, setNotes] = useState('');
  const [posting, setPosting] = useState(false);

  useEffect(() => {
    if (!search.trim()) { setMatches([]); return undefined; }
    const timer = setTimeout(() => {
      api.get('/products/', { params: { search: search.trim(), page_size: 20 } })
        .then(({ data }) => setMatches(unwrap(data)))
        .catch(() => setMatches([]));
    }, 250);
    return () => clearTimeout(timer);
  }, [search]);

  const addLine = (product) => {
    setLines((prev) => (
      prev.some((line) => line.product === product.id)
        ? prev
        : [...prev, { product: product.id, name: product.name, counted_quantity: '' }]
    ));
    setSearch('');
    setMatches([]);
  };

  const submit = async (event) => {
    event.preventDefault();
    if (!branch) return toast.error('Choose the branch being counted.');
    if (lines.length === 0) return toast.error('Add at least one product from the shelf.');
    const counts = lines.map((line) => ({
      product: line.product,
      counted_quantity: line.counted_quantity,
    }));
    if (counts.some((line) => line.counted_quantity === '' || Number(line.counted_quantity) < 0)) {
      return toast.error('Every counted quantity needs a number of zero or more.');
    }
    setPosting(true);
    try {
      const { data } = await api.post('/stock-counts/', { branch, counts, notes });
      toast.success(`Count ${data.number} posted — the shelf now agrees with the books.`);
      onPosted(data);
    } catch (err) {
      toast.error(apiError(err, 'Could not post the count'));
    } finally {
      setPosting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-black/70 p-4">
      <form onSubmit={submit} className="panel w-full max-w-2xl">
        <div className="panel-header">
          <div>
            <h2 className="panel-title">New stock count</h2>
            <p className="panel-subtitle">Counting posts the correction as you submit — no draft, no edits afterwards.</p>
          </div>
          <button type="button" className="btn-secondary !px-3" onClick={onClose}><X size={16} /></button>
        </div>
        <div className="space-y-4 p-5">
          <select className="input" value={branch} onChange={(e) => setBranch(e.target.value)} required>
            <option value="">Branch being counted…</option>
            {branches.map((b) => <option key={b.id} value={b.id}>{b.name} ({b.code})</option>)}
          </select>

          <div>
            <label className="mb-1 block text-xs font-bold uppercase tracking-wider text-slate-500">Add products from the shelf</label>
            <div className="relative">
              <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
              <input
                className="input pl-9"
                placeholder="Search name, SKU or barcode…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            {matches.length > 0 && (
              <ul className="mt-1 max-h-48 overflow-y-auto rounded-xl border border-slate-800 bg-slate-950">
                {matches.map((p) => (
                  <li key={p.id}>
                    <button
                      type="button"
                      className="flex w-full items-center justify-between px-4 py-2 text-left text-sm text-slate-300 hover:bg-slate-900"
                      onClick={() => addLine(p)}
                    >
                      <span className="flex items-center gap-2"><PackageSearch size={14} className="text-slate-500" />{p.name}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {lines.length > 0 && (
            <table className="w-full text-sm">
              <thead className="bg-slate-800/40 text-[10px] uppercase tracking-widest text-slate-400">
                <tr><th className="p-3 text-left">Product</th><th className="w-40 p-3 text-left">Counted quantity</th><th className="w-10 p-3"></th></tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {lines.map((line) => (
                  <tr key={line.product}>
                    <td className="p-3 text-white">{line.name}</td>
                    <td className="p-3">
                      <input
                        className="input"
                        inputMode="decimal"
                        step="any"
                        min="0"
                        placeholder="0"
                        value={line.counted_quantity}
                        onChange={(e) => setLines((prev) => prev.map((l) => (l.product === line.product ? { ...l, counted_quantity: e.target.value } : l)))}
                      />
                    </td>
                    <td className="p-3 text-center">
                      <button type="button" className="text-slate-500 hover:text-red-400" aria-label={`Remove ${line.name}`}
                        onClick={() => setLines((prev) => prev.filter((l) => l.product !== line.product))}>
                        <X size={15} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <textarea
            className="input min-h-20 resize-y"
            placeholder="Notes (why this count, what was found)…"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            maxLength={1000}
          />
        </div>
        <div className="flex gap-2 border-t border-slate-800 px-5 py-4">
          <button type="button" className="btn-secondary flex-1" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn-primary flex-1" disabled={posting}>
            <ClipboardCheck size={16} />{posting ? 'Posting…' : 'Post count'}
          </button>
        </div>
      </form>
    </div>
  );
};

export default function StockCounts() {
  const user = readUser();
  const canCount = can(user, 'inventory.adjust');
  const [counts, setCounts] = useState([]);
  const [branches, setBranches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [expanded, setExpanded] = useState(null);
  const [freshNumber, setFreshNumber] = useState(null);
  const [formOpen, setFormOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [{ data }, { data: branchData }] = await Promise.all([
        api.get('/stock-counts/', { params: { page_size: 100 } }),
        api.get('/branches/', { params: { page_size: 100 } }).catch(() => ({ data: [] })),
      ]);
      setCounts(unwrap(data));
      setBranches(unwrap(branchData));
      setError('');
    } catch (err) {
      setError(apiError(err, 'Could not load stock counts'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const totalVariance = (count) =>
    (count.lines || []).reduce((sum, line) => sum + Number(line.variance || 0), 0);

  return (
    <div className="page-shell space-y-5">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="eyebrow">Stock accuracy</div>
          <h1 className="page-title">Stock Take</h1>
          <p className="page-subtitle">
            Physical counts per branch. Posting a count writes its correcting movements
            straight into the ledger — afterwards it is history, and correcting the
            correction is a new count.
          </p>
        </div>
        <div className="flex gap-2">
          <button className="btn-secondary" onClick={load} disabled={loading}>
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} /> Refresh
          </button>
          {canCount && (
            <button className="btn-primary" onClick={() => setFormOpen(true)}>
              <Plus size={16} /> New count
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-200">{error}</div>
      )}

      <section className="panel">
        <div className="panel-header">
          <div><h2 className="panel-title">Posted counts</h2><p className="panel-subtitle">Newest first, narrowed to your branches</p></div>
          <span className="rounded-lg border border-slate-700 px-3 py-1 text-xs text-slate-400">{counts.length} loaded</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-800/40 text-[10px] uppercase tracking-widest text-slate-400">
              <tr>
                <th className="p-4 text-left">Count</th>
                <th className="p-4 text-left">Branch</th>
                <th className="p-4 text-left">Counted</th>
                <th className="p-4 text-left">By</th>
                <th className="p-4 text-right">Lines</th>
                <th className="p-4 text-right">Net variance</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {counts.map((count) => {
                const net = totalVariance(count);
                const isOpen = expanded === count.id;
                return [
                  <tr
                    key={count.id}
                    className={`cursor-pointer hover:bg-slate-900/60 ${freshNumber === count.number ? 'bg-blue-500/10' : ''}`}
                    onClick={() => setExpanded(isOpen ? null : count.id)}
                  >
                    <td className="p-4 font-bold text-white">{count.number}</td>
                    <td className="p-4 text-slate-300">{count.branch_name || '—'}</td>
                    <td className="p-4 text-slate-400">{count.counted_at ? new Date(count.counted_at).toLocaleString() : '—'}</td>
                    <td className="p-4 text-slate-300">{count.counted_by_name || '—'}</td>
                    <td className="p-4 text-right text-slate-400">{(count.lines || []).length}</td>
                    <td className={`p-4 text-right font-bold ${net > 0 ? 'text-emerald-400' : net < 0 ? 'text-red-400' : 'text-slate-400'}`}>
                      {net > 0 ? '+' : ''}{fmtQty(net)}
                    </td>
                  </tr>,
                  isOpen && (
                    <tr key={`${count.id}-detail`}>
                      <td colSpan={6} className="bg-slate-950/60 p-4">
                        <table className="w-full text-xs">
                          <thead className="text-[10px] uppercase tracking-widest text-slate-500">
                            <tr>
                              <th className="p-2 text-left">Product</th>
                              <th className="p-2 text-right">Book</th>
                              <th className="p-2 text-right">Counted</th>
                              <th className="p-2 text-right">Variance</th>
                              <th className="p-2 text-right">Variance value</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-800/70">
                            {(count.lines || []).map((line) => (
                              <tr key={line.id}>
                                <td className="p-2 text-slate-200">{line.product_name || '—'}</td>
                                <td className="p-2 text-right text-slate-400">{fmtQty(line.book_quantity)}</td>
                                <td className="p-2 text-right text-slate-200">{fmtQty(line.counted_quantity)}</td>
                                <td className={`p-2 text-right font-bold ${Number(line.variance) > 0 ? 'text-emerald-400' : Number(line.variance) < 0 ? 'text-red-400' : 'text-slate-400'}`}>
                                  {Number(line.variance) > 0 ? '+' : ''}{fmtQty(line.variance)}
                                </td>
                                <td className="p-2 text-right text-slate-400">{fmtMoney(line.variance_cost)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                        {count.notes && <p className="mt-3 text-xs italic text-slate-500">“{count.notes}”</p>}
                      </td>
                    </tr>
                  ),
                ];
              })}
              {!loading && counts.length === 0 && (
                <tr><td colSpan={6} className="p-8 text-center text-slate-500">No stock counts posted yet in your branches.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {formOpen && (
        <NewCountForm
          branches={branches}
          onClose={() => setFormOpen(false)}
          onPosted={(posted) => {
            setFormOpen(false);
            setFreshNumber(posted.number);
            load();
            setExpanded(posted.id);
          }}
        />
      )}
    </div>
  );
}
