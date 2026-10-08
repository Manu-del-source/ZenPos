import React, { useCallback, useEffect, useState } from 'react';
import { ChevronLeft, ChevronRight, ScrollText, Search } from 'lucide-react';
import toast from 'react-hot-toast';
import api, { apiError } from '../services/api';

const TYPES = [
  'OPENING_BALANCE', 'PURCHASE_RECEIPT', 'SALE', 'RETURN',
  'TRANSFER_OUT', 'TRANSFER_IN', 'ADJUSTMENT', 'DAMAGE', 'STOCK_COUNT', 'OTHER',
];

const TYPE_STYLES = {
  PURCHASE_RECEIPT: 'text-emerald-400',
  SALE: 'text-sky-400',
  RETURN: 'text-violet-400',
  TRANSFER_OUT: 'text-amber-400',
  TRANSFER_IN: 'text-amber-300',
  ADJUSTMENT: 'text-slate-300',
  DAMAGE: 'text-red-400',
};

const qty = (value) => {
  const n = Number(value || 0);
  return `${n > 0 ? '+' : ''}${n.toLocaleString(undefined, { maximumFractionDigits: 3 })}`;
};

const PAGE_SIZE = 25;

export default function StockLedger() {
  const [rows, setRows] = useState([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [branches, setBranches] = useState([]);
  const [filters, setFilters] = useState({
    search: '', branch: '', movement_type: '', date_from: '', date_to: '',
  });
  const [applied, setApplied] = useState(filters);

  useEffect(() => {
    api.get('/branches/', { params: { page_size: 100 } }).then(({ data }) => {
      setBranches(Array.isArray(data) ? data : data.results || []);
    }).catch(() => {});
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/inventory-movements/', {
        params: {
          page,
          page_size: PAGE_SIZE,
          search: applied.search || undefined,
          branch: applied.branch || undefined,
          movement_type: applied.movement_type || undefined,
          date_from: applied.date_from || undefined,
          date_to: applied.date_to || undefined,
        },
      });
      setRows(data?.results || []);
      setCount(data?.count || 0);
    } catch (err) {
      toast.error(apiError(err, 'Failed to load stock ledger'));
    } finally {
      setLoading(false);
    }
  }, [page, applied]);

  useEffect(() => { load(); }, [load]);

  const pages = Math.max(1, Math.ceil(count / PAGE_SIZE));

  return (
    <div className="p-8 max-w-7xl mx-auto min-h-screen">
      <div className="mb-8">
        <h1 className="text-3xl font-black tracking-tight text-white">Stock Ledger</h1>
        <p className="text-slate-500 text-sm">Every inventory movement, in order. Balances are not edited here.</p>
      </div>

      <form
        className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-6"
        onSubmit={(e) => { e.preventDefault(); setPage(1); setApplied({ ...filters }); }}
      >
        <div className="relative lg:col-span-2">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" size={16} />
          <input
            className="w-full bg-slate-900 border border-slate-800 p-3 pl-10 rounded-xl text-white outline-none focus:border-blue-500 text-sm"
            placeholder="Product, reference…"
            value={filters.search}
            onChange={(e) => setFilters({ ...filters, search: e.target.value })}
          />
        </div>
        <select className="bg-slate-900 border border-slate-800 p-3 rounded-xl text-white text-sm" value={filters.branch} onChange={(e) => setFilters({ ...filters, branch: e.target.value })}>
          <option value="">All branches</option>
          {branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
        </select>
        <select className="bg-slate-900 border border-slate-800 p-3 rounded-xl text-white text-sm" value={filters.movement_type} onChange={(e) => setFilters({ ...filters, movement_type: e.target.value })}>
          <option value="">All movements</option>
          {TYPES.map((t) => <option key={t} value={t}>{t.replaceAll('_', ' ')}</option>)}
        </select>
        <input type="date" className="bg-slate-900 border border-slate-800 p-3 rounded-xl text-white text-sm" value={filters.date_from} onChange={(e) => setFilters({ ...filters, date_from: e.target.value })} />
        <button type="submit" className="btn-primary">Filter</button>
      </form>

      <div className="bg-slate-900 rounded-3xl border border-slate-800 overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-800/50">
            <tr className="text-slate-400 text-[10px] font-black uppercase tracking-[0.18em]">
              <th className="p-3">Date</th>
              <th className="p-3">Product</th>
              <th className="p-3">Movement</th>
              <th className="p-3">Reference</th>
              <th className="p-3 text-right">Qty change</th>
              <th className="p-3 text-right">Before</th>
              <th className="p-3 text-right">After</th>
              <th className="p-3">User</th>
              <th className="p-3">Branch</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {rows.map((row) => (
              <tr key={row.id} className="hover:bg-slate-800/30">
                <td className="p-3 text-slate-400 text-xs whitespace-nowrap">{new Date(row.created_at).toLocaleString()}</td>
                <td className="p-3 text-white font-semibold">{row.product_name}</td>
                <td className={`p-3 text-xs font-bold ${TYPE_STYLES[row.movement_type] || 'text-slate-300'}`}>{row.movement_type.replaceAll('_', ' ')}</td>
                <td className="p-3 text-slate-400 text-xs">{[row.reference_type, row.reference_id].filter(Boolean).join(' ') || '—'}</td>
                <td className={`p-3 text-right font-bold ${Number(row.quantity) < 0 ? 'text-red-400' : 'text-emerald-400'}`}>{qty(row.quantity)}</td>
                <td className="p-3 text-right text-slate-400">{Number(row.quantity_before).toLocaleString()}</td>
                <td className="p-3 text-right text-white">{Number(row.quantity_after).toLocaleString()}</td>
                <td className="p-3 text-slate-400">{row.actor_name || '—'}</td>
                <td className="p-3 text-slate-400">{row.branch_name || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {loading && <div className="p-16 text-center text-slate-500 text-sm font-bold uppercase tracking-widest">Loading ledger…</div>}
        {!loading && rows.length === 0 && (
          <div className="p-20 text-center flex flex-col items-center">
            <ScrollText size={56} className="text-slate-800 mb-4" />
            <p className="text-slate-500 font-bold uppercase tracking-widest text-sm">No movements match those filters</p>
          </div>
        )}
      </div>

      {count > PAGE_SIZE && (
        <div className="mt-4 flex items-center justify-end gap-2 text-sm text-slate-400">
          <button className="btn-secondary !py-2" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}><ChevronLeft size={16} /></button>
          <span>Page {page} of {pages}</span>
          <button className="btn-secondary !py-2" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}><ChevronRight size={16} /></button>
        </div>
      )}
    </div>
  );
}
