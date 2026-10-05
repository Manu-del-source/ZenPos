import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Ban, ChevronLeft, ChevronRight, Eye, FileText, Printer, RefreshCw, Search, X } from 'lucide-react';
import toast from 'react-hot-toast';
import api, { apiError } from '../services/api';
import { can } from '../App';

const money = (value) => `KES ${Number(value || 0).toLocaleString('en-KE', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})}`;

const PAGE_SIZE = 25;

const STATUS_STYLES = {
  COMPLETED: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  VOIDED: 'bg-red-500/10 text-red-400 border-red-500/20',
  PENDING: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  FAILED: 'bg-red-500/10 text-red-400 border-red-500/20',
  REFUNDED: 'bg-violet-500/10 text-violet-300 border-violet-500/20',
};

const StatusPill = ({ status }) => (
  <span className={`inline-flex rounded-lg border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${STATUS_STYLES[status] || 'border-slate-700 text-slate-400'}`}>
    {status}
  </span>
);

const today = () => new Date().toISOString().slice(0, 10);

export default function Orders({ user }) {
  const [sales, setSales] = useState([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ search: '', status: '', date_from: '', date_to: '' });
  const [applied, setApplied] = useState({ search: '', status: '', date_from: '', date_to: '' });
  const [selected, setSelected] = useState(null);
  const [voiding, setVoiding] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/sales/', {
        params: {
          page,
          page_size: PAGE_SIZE,
          search: applied.search || undefined,
          status: applied.status || undefined,
          date_from: applied.date_from || undefined,
          date_to: applied.date_to || undefined,
        },
      });
      setSales(data?.results || []);
      setCount(data?.count || 0);
    } catch (error) {
      toast.error(apiError(error, 'Failed to load sales.'));
    } finally {
      setLoading(false);
    }
  }, [page, applied]);

  useEffect(() => { load(); }, [load]);

  const openSale = async (sale) => {
    setSelected(sale);
    try {
      const { data } = await api.get(`/sales/${sale.id}/`);
      setSelected(data);
    } catch (error) {
      toast.error(apiError(error, 'Could not load the sale.'));
    }
  };

  const printReceipt = async (saleId) => {
    try {
      const { data } = await api.get(`/sales/${saleId}/receipt/?paper=80mm`, { responseType: 'text' });
      const printWindow = window.open('', '_blank', 'width=480,height=760');
      if (!printWindow) return toast.error('Allow pop-ups to print receipts.');
      printWindow.document.open();
      printWindow.document.write(data);
      printWindow.document.close();
      printWindow.focus();
      printWindow.onload = () => printWindow.print();
    } catch (error) {
      toast.error(apiError(error, 'Could not prepare the receipt.'));
    }
  };

  const voidSale = async (sale) => {
    const reason = window.prompt('Reason for voiding this sale? (recorded in the audit log)');
    if (reason === null) return;
    setVoiding(true);
    try {
      const { data } = await api.post(`/sales/${sale.id}/void/`, { reason });
      setSelected(data);
      toast.success('Sale voided. Payments refunded and stock returned.');
      await load();
    } catch (error) {
      toast.error(apiError(error, 'The sale could not be voided.'));
    } finally {
      setVoiding(false);
    }
  };

  const pages = Math.max(1, Math.ceil(count / PAGE_SIZE));
  const filterRow = useMemo(() => (
    <div className="flex flex-col gap-3 border-b border-slate-800 p-4 lg:flex-row lg:items-end">
      <label className="flex-1">
        <span className="mb-1.5 block text-xs font-semibold text-slate-400">Search</span>
        <div className="relative">
          <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            className="input pl-10"
            placeholder="Sale number, customer name or phone"
            value={filters.search}
            onChange={(event) => setFilters({ ...filters, search: event.target.value })}
            onKeyDown={(event) => { if (event.key === 'Enter') { setPage(1); setApplied(filters); } }}
          />
        </div>
      </label>
      <label className="lg:w-40">
        <span className="mb-1.5 block text-xs font-semibold text-slate-400">Status</span>
        <select className="input" value={filters.status} onChange={(event) => setFilters({ ...filters, status: event.target.value })}>
          <option value="">All</option>
          <option value="COMPLETED">Completed</option>
          <option value="VOIDED">Voided</option>
        </select>
      </label>
      <label className="lg:w-44">
        <span className="mb-1.5 block text-xs font-semibold text-slate-400">From</span>
        <input type="date" className="input" value={filters.date_from} onChange={(event) => setFilters({ ...filters, date_from: event.target.value })} />
      </label>
      <label className="lg:w-44">
        <span className="mb-1.5 block text-xs font-semibold text-slate-400">To</span>
        <input type="date" className="input" value={filters.date_to} onChange={(event) => setFilters({ ...filters, date_to: event.target.value })} />
      </label>
      <div className="flex gap-2">
        <button className="btn-primary" onClick={() => { setPage(1); setApplied(filters); }}>Apply</button>
        <button
          className="btn-secondary"
          onClick={() => { const cleared = { search: '', status: '', date_from: '', date_to: '' }; setFilters(cleared); setApplied(cleared); setPage(1); }}
        >
          Clear
        </button>
      </div>
    </div>
  ), [filters]);

  return (
    <div className="page-shell">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="eyebrow">Sales history</div>
          <h1 className="page-title">Sales</h1>
          <p className="page-subtitle">{count} recorded sale{count === 1 ? '' : 's'} in your scope.</p>
        </div>
        <button className="btn-secondary" onClick={load} disabled={loading}>
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} /> Refresh
        </button>
      </div>

      <section className="panel mt-6 overflow-hidden">
        {filterRow}
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-950 text-left text-[11px] uppercase tracking-wider text-slate-500">
              <tr>
                <th className="p-4">Sale</th>
                <th className="p-4">When</th>
                <th className="p-4">Cashier</th>
                <th className="p-4">Customer</th>
                <th className="p-4">Method</th>
                <th className="p-4">Status</th>
                <th className="p-4 text-right">Total</th>
                <th className="p-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {loading ? (
                <tr><td colSpan={8} className="p-10 text-center text-slate-500">Loading sales…</td></tr>
              ) : sales.length === 0 ? (
                <tr>
                  <td colSpan={8} className="p-12 text-center">
                    <FileText className="mx-auto mb-3 text-slate-600" size={30} />
                    <p className="font-semibold text-slate-300">No sales match these filters</p>
                    <p className="mt-1 text-sm text-slate-500">Completed sales appear here as soon as they are rung up.</p>
                  </td>
                </tr>
              ) : (
                sales.map((sale) => (
                  <tr key={sale.id} className="hover:bg-slate-900/40">
                    <td className="p-4">
                      <div className="font-mono text-xs text-slate-300">{sale.sale_number}</div>
                      {sale.branch_name && <div className="mt-1 text-[11px] text-slate-500">{sale.branch_name}</div>}
                    </td>
                    <td className="p-4 text-slate-400">{new Date(sale.created_at).toLocaleString('en-KE')}</td>
                    <td className="p-4 text-slate-300">{sale.cashier_name}</td>
                    <td className="p-4 text-slate-300">{sale.customer_name || 'Walk-in'}</td>
                    <td className="p-4 text-slate-400">{sale.payment_method}</td>
                    <td className="p-4"><StatusPill status={sale.status} /></td>
                    <td className="p-4 text-right font-semibold text-white">{money(sale.total_amount)}</td>
                    <td className="p-4">
                      <div className="flex justify-end gap-2">
                        <button className="btn-secondary !px-3 !py-2" onClick={() => openSale(sale)} aria-label="View sale"><Eye size={15} /></button>
                        <button className="btn-secondary !px-3 !py-2" onClick={() => printReceipt(sale.id)} aria-label="Print receipt"><Printer size={15} /></button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        <div className="flex items-center justify-between border-t border-slate-800 px-4 py-3 text-sm text-slate-400">
          <span>Page {page} of {pages}</span>
          <div className="flex gap-2">
            <button className="btn-secondary !px-3 !py-2" disabled={page <= 1 || loading} onClick={() => setPage((value) => Math.max(1, value - 1))}>
              <ChevronLeft size={15} /> Previous
            </button>
            <button className="btn-secondary !px-3 !py-2" disabled={page >= pages || loading} onClick={() => setPage((value) => value + 1)}>
              Next <ChevronRight size={15} />
            </button>
          </div>
        </div>
      </section>

      {selected && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4 backdrop-blur-sm">
          <div className="panel max-h-[90vh] w-full max-w-2xl overflow-y-auto">
            <div className="panel-header sticky top-0 bg-slate-950/95 backdrop-blur">
              <div>
                <p className="eyebrow">Sale detail</p>
                <h2 className="panel-title">{selected.sale_number}</h2>
              </div>
              <button className="btn-secondary !px-3" onClick={() => setSelected(null)} aria-label="Close"><X size={17} /></button>
            </div>
            <div className="space-y-4 p-5">
              <div className="grid gap-3 sm:grid-cols-4">
                <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3">
                  <p className="text-xs text-slate-500">Status</p>
                  <div className="mt-1"><StatusPill status={selected.status} /></div>
                </div>
                <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3">
                  <p className="text-xs text-slate-500">Cashier</p>
                  <p className="mt-1 font-medium text-slate-200">{selected.cashier_name}</p>
                </div>
                <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3">
                  <p className="text-xs text-slate-500">Customer</p>
                  <p className="mt-1 font-medium text-slate-200">{selected.customer_name || 'Walk-in'}</p>
                </div>
                <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3">
                  <p className="text-xs text-slate-500">Branch</p>
                  <p className="mt-1 font-medium text-slate-200">{selected.branch_name || '—'}</p>
                </div>
              </div>

              <div className="divide-y divide-slate-800 rounded-xl border border-slate-800">
                {(selected.items || []).map((item) => (
                  <div key={item.id} className="flex items-center justify-between gap-4 p-3">
                    <div className="min-w-0">
                      <p className="truncate font-medium text-slate-200">{item.product_name}</p>
                      <p className="text-xs text-slate-500">{item.quantity} × {money(item.unit_price)}</p>
                    </div>
                    <p className="font-semibold text-white">{money(item.line_total)}</p>
                  </div>
                ))}
              </div>

              {(selected.payments || []).length > 0 && (
                <div className="rounded-xl border border-slate-800">
                  <div className="border-b border-slate-800 px-4 py-2 text-xs font-bold uppercase tracking-wider text-slate-500">Payments</div>
                  {selected.payments.map((payment) => (
                    <div key={payment.id} className="flex items-center justify-between gap-4 border-b border-slate-800/60 p-3 last:border-0">
                      <div>
                        <p className="text-sm font-medium text-slate-200">{payment.method}</p>
                        {payment.provider_reference && <p className="text-xs text-slate-500">Ref {payment.provider_reference}</p>}
                      </div>
                      <div className="flex items-center gap-3">
                        <StatusPill status={payment.status} />
                        <span className="font-semibold text-white">{money(payment.amount)}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {selected.status === 'VOIDED' && (
                <div className="rounded-xl border border-red-900/50 bg-red-500/10 p-4 text-sm text-red-200">
                  Voided{selected.voided_by_name ? ` by ${selected.voided_by_name}` : ''}
                  {selected.void_reason ? ` — ${selected.void_reason}` : ''}. Stock was returned and payments refunded.
                </div>
              )}

              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-800 pt-4">
                <div className="flex gap-2">
                  <button className="btn-secondary" onClick={() => printReceipt(selected.id)}>
                    <Printer size={16} /> Print receipt
                  </button>
                  {selected.status !== 'VOIDED' && can(user, 'sales.refund') && (
                    <button
                      className="btn-secondary !border-red-500/30 !text-red-300 hover:!bg-red-500/10"
                      disabled={voiding}
                      onClick={() => voidSale(selected)}
                    >
                      <Ban size={16} /> {voiding ? 'Voiding…' : 'Void sale'}
                    </button>
                  )}
                </div>
                <div className="text-right">
                  <p className="text-xs uppercase tracking-wider text-slate-500">Total</p>
                  <p className="text-2xl font-black text-white">{money(selected.total_amount)}</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
