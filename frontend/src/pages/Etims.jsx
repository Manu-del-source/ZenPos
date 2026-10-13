import React, { useCallback, useEffect, useState } from 'react';
import { FileText, RefreshCw } from 'lucide-react';
import toast from 'react-hot-toast';
import api, { apiError } from '../services/api';

const unwrap = (data) => (Array.isArray(data) ? data : data?.results || []);

const fmtMoney = (value) => {
  const n = Number(value);
  if (value === null || value === undefined || !Number.isFinite(n)) return '—';
  return `KES ${n.toFixed(2)}`;
};

export default function Etims() {
  const [invoices, setInvoices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [expanded, setExpanded] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/etims/invoices/', { params: { page_size: 100 } });
      setInvoices(unwrap(data));
      setError('');
    } catch (err) {
      setError(apiError(err, 'Could not load eTIMS invoices'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="page-shell space-y-5">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="eyebrow">KRA eTIMS</div>
          <h1 className="page-title">Electronic Invoices</h1>
          <p className="page-subtitle">
            The compliance documents behind your sales. A document is written when the
            domain records it — issuing and cancelling happen on the server, never from
            the till — and are locked once written: the row, its lines and its tax
            breakdown describe the sale exactly as it happened.
          </p>
        </div>
        <button className="btn-secondary" onClick={load} disabled={loading}>
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} /> Refresh
        </button>
      </div>

      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-200">{error}</div>
      )}

      <section className="panel">
        <div className="panel-header">
          <div><h2 className="panel-title">Invoice ledger</h2><p className="panel-subtitle">One document per sale, narrowed to your branches</p></div>
          <span className="rounded-lg border border-slate-700 px-3 py-1 text-xs text-slate-400">{invoices.length} loaded</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-800/40 text-[10px] uppercase tracking-widest text-slate-400">
              <tr>
                <th className="p-4 text-left">Sale</th>
                <th className="p-4 text-left">Branch</th>
                <th className="p-4 text-left">UIN</th>
                <th className="p-4 text-left">Status</th>
                <th className="p-4 text-right">Total</th>
                <th className="p-4 text-left">Issued</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {invoices.map((inv) => {
                const isOpen = expanded === inv.id;
                return [
                  <tr
                    key={inv.id}
                    className="cursor-pointer hover:bg-slate-900/60"
                    onClick={() => setExpanded(isOpen ? null : inv.id)}
                  >
                    <td className="p-4 font-bold text-white">{inv.sale_number || `#${inv.sale}`}</td>
                    <td className="p-4 text-slate-300">{inv.branch_name || '—'}</td>
                    <td className="p-4 font-mono text-xs text-slate-400">{inv.uin || '—'}</td>
                    <td className="p-4">
                      <span className={`rounded-md border px-2 py-1 text-xs ${inv.status === 'ISSUED' ? 'border-emerald-500/20 text-emerald-300' : 'border-red-500/30 text-red-300'}`}>
                        {inv.status}
                      </span>
                    </td>
                    <td className="p-4 text-right text-slate-200">{fmtMoney(inv.total_amount)}</td>
                    <td className="p-4 text-slate-400">{inv.issued_at ? new Date(inv.issued_at).toLocaleString() : '—'}</td>
                  </tr>,
                  isOpen && (
                    <tr key={`${inv.id}-detail`}>
                      <td colSpan={6} className="bg-slate-950/60 p-4">
                        <div className="grid gap-4 lg:grid-cols-2">
                          <div>
                            <p className="mb-2 text-[10px] font-bold uppercase tracking-widest text-slate-500">Lines</p>
                            <table className="w-full text-xs">
                              <tbody className="divide-y divide-slate-800/70">
                                {(inv.line_items || []).map((line, i) => (
                                  <tr key={i}>
                                    <td className="p-2 text-slate-200">
                                      {line.name || '—'}
                                      <span className="block text-[10px] text-slate-500">
                                        {line.quantity ?? ''} × {fmtMoney(line.unit_price)}
                                        {line.tax_rate_percent ? ` · ${line.tax_rate_name} ${line.tax_rate_percent}%` : ''}
                                      </span>
                                    </td>
                                    <td className="p-2 text-right text-slate-200">{fmtMoney(line.line_total)}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                            <p className="mt-2 text-right text-xs text-slate-500">
                              Subtotal {fmtMoney(inv.subtotal)} · Tax {fmtMoney(inv.tax_amount)}
                            </p>
                          </div>
                          <div>
                            <p className="mb-2 text-[10px] font-bold uppercase tracking-widest text-slate-500">Tax breakdown</p>
                            <table className="w-full text-xs">
                              <tbody className="divide-y divide-slate-800/70">
                                {(inv.tax_breakdown || []).map((group, i) => (
                                  <tr key={i}>
                                    <td className="p-2 text-slate-200">{group.name}</td>
                                    <td className="p-2 text-right text-slate-400">{group.rate !== null ? `${group.rate}%` : 'exempt'}</td>
                                    <td className="p-2 text-right text-slate-400">{fmtMoney(group.net)}</td>
                                    <td className="p-2 text-right text-slate-200">{fmtMoney(group.tax)}</td>
                                  </tr>
                                ))}
                                {(inv.tax_breakdown || []).length === 0 && (
                                  <tr><td className="p-2 text-slate-500">No taxed lines on this document.</td></tr>
                                )}
                              </tbody>
                            </table>
                            {inv.status === 'CANCELLED' && (
                              <p className="mt-3 rounded-lg border border-red-500/20 bg-red-500/5 p-3 text-xs text-red-300">
                                Cancelled {inv.cancelled_at ? new Date(inv.cancelled_at).toLocaleString() : ''}
                                {inv.cancellation_reason ? ` — “${inv.cancellation_reason}”` : ''}
                              </p>
                            )}
                          </div>
                        </div>
                      </td>
                    </tr>
                  ),
                ];
              })}
              {!loading && invoices.length === 0 && (
                <tr><td colSpan={6} className="p-8 text-center text-slate-500">No eTIMS documents recorded yet in your branches.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel p-5">
        <div className="flex items-start gap-3">
          <div className="rounded-lg bg-blue-500/10 p-2 text-blue-300"><FileText size={19} /></div>
          <div>
            <h2 className="panel-title">How documents get written</h2>
            <p className="mt-2 text-sm leading-6 text-slate-400">
              A sale's invoice is created when the domain issues it (the service layer,
              which is idempotent — a sale can never hold two documents) and is
              cancelled, with a reason, when the sale is voided. This console is the
              ledger those writes leave behind: every document shows its frozen lines
              and tax breakdown, so a later catalogue or rate change can never rewrite
              what a customer was charged.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}
