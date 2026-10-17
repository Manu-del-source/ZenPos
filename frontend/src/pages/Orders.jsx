import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Ban, CheckCircle2, ChevronLeft, ChevronRight, Eye, FileText, Printer, RefreshCw, Search, Smartphone, X } from 'lucide-react';
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

export default function Orders({ user: userProp }) {
  let storedUser = {};
  try { storedUser = JSON.parse(localStorage.getItem('user') || '{}'); } catch { /* ignore */ }
  const user = userProp || storedUser;
  const [sales, setSales] = useState([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ search: '', status: '', date_from: '', date_to: '' });
  const [applied, setApplied] = useState({ search: '', status: '', date_from: '', date_to: '' });
  const [selected, setSelected] = useState(null);
  const [voiding, setVoiding] = useState(false);
  const [returning, setReturning] = useState(null);
  const [returnBusy, setReturnBusy] = useState(false);
  const [showTillMatch, setShowTillMatch] = useState(false);
  const [tillTransactions, setTillTransactions] = useState([]);
  const [tillLoading, setTillLoading] = useState(false);
  const [matchingReceipt, setMatchingReceipt] = useState(null);

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

  const loadTillTransactions = async (sale) => {
    if (!sale?.id) return;
    setTillLoading(true);
    try {
      const { data } = await api.get('/mpesa/till-transactions/', { params: { sale: sale.id } });
      setTillTransactions(data?.results || []);
    } catch (error) {
      toast.error(apiError(error, 'Could not load unmatched Till payments.'));
    } finally {
      setTillLoading(false);
    }
  };

  const openTillMatch = async () => {
    setShowTillMatch(true);
    await loadTillTransactions(selected);
  };

  const matchTillReceipt = async (receipt) => {
    if (!selected?.id || !receipt?.id) return;
    setMatchingReceipt(receipt.id);
    try {
      await api.post('/mpesa/till-transactions/match/', {
        transaction_id: receipt.id,
        sale_id: selected.id,
      });
      toast.success(`M-Pesa receipt ${receipt.receipt_number} matched to ${selected.sale_number}.`);
      setShowTillMatch(false);
      const { data } = await api.get(`/sales/${selected.id}/`);
      setSelected(data);
      await load();
    } catch (error) {
      toast.error(apiError(error, 'Could not match this Till payment.'));
      await loadTillTransactions(selected);
    } finally {
      setMatchingReceipt(null);
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
            <thead className="bg-[#F1EDE4] text-left text-[11px] uppercase tracking-wider text-[#756F66]">
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

              {showTillMatch && (
                <section className="rounded-2xl border border-amber-500/25 bg-amber-500/[0.04] p-4" aria-label="Match Till payment">
                  <div className="mb-3 flex items-start justify-between gap-3">
                    <div>
                      <h3 className="font-bold text-slate-100">Match Till Payment</h3>
                      <p className="mt-1 text-xs text-slate-400">Select the exact receipt from Safaricom's confirmed incoming payments. Amount alone does not identify a customer.</p>
                    </div>
                    <button className="btn-secondary !px-2 !py-1.5" onClick={() => setShowTillMatch(false)} aria-label="Close Till matching"><X size={15} /></button>
                  </div>
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <p className="text-sm text-slate-300">Outstanding balance <strong className="text-white">{money(Math.max(0, Number(selected.total_amount || 0) - (selected.payments || []).filter((payment) => payment.status === 'COMPLETED').reduce((sum, payment) => sum + Number(payment.amount || 0), 0)))}</strong></p>
                    <button className="btn-secondary !px-3 !py-2" onClick={() => loadTillTransactions(selected)} disabled={tillLoading}>
                      <RefreshCw size={14} className={tillLoading ? 'animate-spin' : ''} /> Refresh
                    </button>
                  </div>
                  {tillLoading ? (
                    <p className="py-5 text-center text-sm text-slate-400">Loading confirmed receipts…</p>
                  ) : tillTransactions.length === 0 ? (
                    <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-4 text-center">
                      <Smartphone size={22} className="mx-auto mb-2 text-slate-500" />
                      <p className="text-sm font-semibold text-slate-200">No matching Till payments found</p>
                      <p className="mt-1 text-xs text-slate-500">Keep the sale unpaid and refresh after the customer’s payment appears in Safaricom’s C2B confirmation feed.</p>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {tillTransactions.map((receipt) => (
                        <div key={receipt.id} className="flex flex-col gap-3 rounded-xl border border-slate-800 bg-slate-950/70 p-3 sm:flex-row sm:items-center sm:justify-between">
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="font-mono text-sm font-bold text-white">{receipt.receipt_number}</span>
                              <span className="text-sm font-bold text-emerald-300">KES {money(receipt.amount)}</span>
                            </div>
                            <p className="mt-1 text-xs text-slate-400">{new Date(receipt.transaction_time).toLocaleString('en-KE')} · {receipt.payer_phone || 'Phone unavailable'}</p>
                            <p className="mt-1 text-xs text-slate-500">Bill reference: {receipt.bill_reference || 'Not provided'}{receipt.payer_name ? ` · ${receipt.payer_name}` : ''}</p>
                          </div>
                          <button className="btn-primary shrink-0 !px-3 !py-2" disabled={Boolean(matchingReceipt)} onClick={() => matchTillReceipt(receipt)}>
                            <CheckCircle2 size={15} /> {matchingReceipt === receipt.id ? 'Matching…' : 'Match this receipt'}
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </section>
              )}

              {selected.status === 'VOIDED' && (
                <div className="rounded-xl border border-red-900/50 bg-red-500/10 p-4 text-sm text-red-200">
                  Voided{selected.voided_by_name ? ` by ${selected.voided_by_name}` : ''}
                  {selected.void_reason ? ` — ${selected.void_reason}` : ''}. Stock was returned and payments refunded.
                </div>
              )}

              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-800 pt-4">
                <div className="flex gap-2">
                  {selected.status === 'COMPLETED' && can(user, 'sales.create') && (
                    <button className="btn-secondary !border-amber-500/30 !text-amber-200" onClick={openTillMatch}>
                      <Smartphone size={16} /> Match Till Payment
                    </button>
                  )}
                  <button className="btn-secondary" onClick={() => printReceipt(selected.id)}>
                    <Printer size={16} /> Print receipt
                  </button>
                  {selected.status === 'COMPLETED' && (
                    <button
                      className="btn-secondary"
                      onClick={() => setReturning({
                        sale: selected,
                        reason: 'CUSTOMER_CHANGE',
                        refund_method: 'CASH',
                        lines: (selected.items || []).map((item) => ({
                          sale_item: item.id,
                          product_name: item.product_name,
                          original: item.quantity,
                          already: item.quantity_returned || 0,
                          quantity: 0,
                          restock: true,
                          unit_price: item.unit_price,
                        })),
                      })}
                    >
                      Return items
                    </button>
                  )}
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

      {returning && (
        <div className="fixed inset-0 z-[60] grid place-items-center bg-black/70 p-4 backdrop-blur-sm">
          <div className="panel w-full max-w-2xl max-h-[90vh] overflow-y-auto">
            <div className="panel-header">
              <div>
                <h2 className="panel-title">Return items</h2>
                <p className="panel-subtitle">{returning.sale.sale_number}</p>
              </div>
              <button className="btn-secondary !px-3" onClick={() => setReturning(null)}><X size={17} /></button>
            </div>
            <div className="p-5 space-y-3">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-slate-500 text-[10px] uppercase tracking-widest">
                    <th className="text-left pb-2">Product</th>
                    <th className="text-right pb-2">Sold</th>
                    <th className="text-right pb-2">Returned</th>
                    <th className="text-right pb-2">Available</th>
                    <th className="text-right pb-2">Return qty</th>
                  </tr>
                </thead>
                <tbody>
                  {returning.lines.map((line, i) => (
                    <tr key={line.sale_item} className="border-t border-slate-800">
                      <td className="py-2 text-white">{line.product_name}</td>
                      <td className="py-2 text-right text-slate-400">{line.original}</td>
                      <td className="py-2 text-right text-slate-400">{line.already}</td>
                      <td className="py-2 text-right text-slate-300">{line.original - line.already}</td>
                      <td className="py-2 text-right">
                        <input
                          type="number"
                          min="0"
                          max={line.original - line.already}
                          className="w-20 bg-slate-950 border border-slate-800 p-2 rounded-lg text-white text-right"
                          value={line.quantity}
                          onChange={(e) => {
                            const lines = returning.lines.map((l, idx) => idx === i ? { ...l, quantity: Number(e.target.value) } : l);
                            setReturning({ ...returning, lines });
                          }}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="grid grid-cols-2 gap-3">
                <select className="bg-slate-950 border border-slate-800 p-3 rounded-xl text-white" value={returning.reason} onChange={(e) => setReturning({ ...returning, reason: e.target.value })}>
                  <option value="CUSTOMER_CHANGE">Customer changed mind</option>
                  <option value="DAMAGED">Damaged</option>
                  <option value="WRONG_ITEM">Wrong item</option>
                  <option value="EXPIRED">Expired</option>
                  <option value="OTHER">Other</option>
                </select>
                <select className="bg-slate-950 border border-slate-800 p-3 rounded-xl text-white" value={returning.refund_method} onChange={(e) => setReturning({ ...returning, refund_method: e.target.value })}>
                  <option value="CASH">Cash refund</option>
                  <option value="MPESA">M-Pesa</option>
                  <option value="STORE_CREDIT">Store credit</option>
                </select>
              </div>
              <p className="text-sm text-white font-bold">
                Refund {money(returning.lines.reduce((s, l) => s + Number(l.quantity || 0) * Number(l.unit_price || 0), 0))}
              </p>
              <div className="flex gap-2 justify-end">
                <button className="btn-secondary" onClick={() => setReturning(null)}>Cancel</button>
                <button
                  className="btn-primary"
                  disabled={returnBusy}
                  onClick={async () => {
                    const lines = returning.lines.filter((l) => Number(l.quantity) > 0).map((l) => ({
                      sale_item: l.sale_item,
                      quantity: l.quantity,
                      restock: returning.reason !== 'DAMAGED',
                    }));
                    if (!lines.length) return toast.error('Enter a quantity to return.');
                    setReturnBusy(true);
                    try {
                      const { data } = await api.post(`/sales/${returning.sale.id}/returns/`, {
                        reason: returning.reason,
                        refund_method: returning.refund_method,
                        lines,
                      });
                      if (can(user, 'sales.refund')) {
                        await api.post(`/returns/${data.id}/complete/`);
                        toast.success('Return completed and refund recorded');
                      } else {
                        toast.success('Return requested — waiting for authorization');
                      }
                      setReturning(null);
                      setSelected(null);
                      load();
                    } catch (err) {
                      toast.error(apiError(err, 'Could not process the return'));
                    } finally {
                      setReturnBusy(false);
                    }
                  }}
                >
                  {returnBusy ? 'Submitting…' : 'Submit return'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
