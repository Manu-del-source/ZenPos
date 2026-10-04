import React, { useEffect, useState } from 'react';
import { Eye, FileText, Printer, RefreshCw, X } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../services/api';

const money = (value) => `KES ${Number(value || 0).toLocaleString('en-KE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export default function Orders() {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [detailsLoading, setDetailsLoading] = useState(false);

  const fetchOrders = async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/sales/');
      setOrders(Array.isArray(data) ? data : (data.results || []));
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to load sales.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchOrders(); }, []);

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
    } catch {
      toast.error('Could not prepare the receipt.');
    }
  };

  const openSale = async (sale) => {
    setSelected({ ...sale, items: [] });
    setDetailsLoading(true);
    try {
      const { data } = await api.get(`/sales/${sale.id}/`);
      setSelected(data);
    } catch (err) {
      toast.error('Could not load sale details.');
    } finally {
      setDetailsLoading(false);
    }
  };

  return (
    <div className="page-shell">
      <div className="flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="eyebrow">Transactions</div>
          <h1 className="page-title">Sales</h1>
          <p className="page-subtitle">Review completed sales, payment methods and line items.</p>
        </div>
        <button className="btn-secondary" onClick={fetchOrders} disabled={loading}>
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} /> Refresh
        </button>
      </div>

      <div className="panel mt-6 overflow-hidden">
        <div className="hidden grid-cols-[1.2fr_1fr_1fr_.8fr_auto] gap-4 border-b border-slate-800 px-5 py-3 text-xs font-semibold uppercase tracking-wider text-slate-500 md:grid">
          <span>Sale</span><span>Date</span><span>Customer</span><span>Payment</span><span>Total</span>
        </div>

        {loading ? (
          <div className="p-10 text-center text-slate-500">Loading sales…</div>
        ) : orders.length === 0 ? (
          <div className="p-12 text-center">
            <FileText className="mx-auto mb-3 text-slate-600" size={34} />
            <p className="font-semibold text-slate-300">No sales recorded</p>
            <p className="mt-1 text-sm text-slate-500">Completed transactions will appear here.</p>
          </div>
        ) : (
          <div className="divide-y divide-slate-800/70">
            {orders.map((sale) => (
              <button
                key={sale.id}
                className="grid w-full grid-cols-1 gap-2 px-5 py-4 text-left transition hover:bg-slate-900/60 md:grid-cols-[1.2fr_1fr_1fr_.8fr_auto] md:items-center md:gap-4"
                onClick={() => openSale(sale)}
              >
                <div>
                  <p className="font-semibold text-white">{sale.sale_number}</p>
                  <p className="text-xs text-slate-500">{sale.cashier_name || 'Cashier'}</p>
                </div>
                <span className="text-sm text-slate-400">{new Date(sale.created_at).toLocaleString()}</span>
                <span className="text-sm text-slate-400">{sale.customer_name || 'Walk-in customer'}</span>
                <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">{sale.payment_method}</span>
                <span className="font-semibold text-white">{money(sale.total_amount)}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {selected && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4 backdrop-blur-sm">
          <div className="panel max-h-[90vh] w-full max-w-lg overflow-y-auto">
            <div className="panel-header sticky top-0 bg-slate-950/95 backdrop-blur">
              <div>
                <p className="eyebrow">Sale receipt</p>
                <h2 className="panel-title">{selected.sale_number}</h2>
              </div>
              <button className="btn-secondary !px-3" onClick={() => setSelected(null)}><X size={17} /></button>
            </div>
            <div className="space-y-4 p-5">
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3">
                  <p className="text-xs text-slate-500">Customer</p>
                  <p className="mt-1 font-medium text-slate-200">{selected.customer_name || 'Walk-in customer'}</p>
                </div>
                <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3">
                  <p className="text-xs text-slate-500">Payment</p>
                  <p className="mt-1 font-medium text-slate-200">{selected.payment_method}</p>
                </div>
              </div>

              {detailsLoading ? (
                <div className="py-8 text-center text-slate-500">Loading items…</div>
              ) : (
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
              )}

              <div className="flex items-center justify-between border-t border-slate-800 pt-4">
                <button className="btn-secondary" onClick={() => printReceipt(selected.id)} disabled={detailsLoading}>
                  <Printer size={16} /> Print receipt
                </button>
                <span className="text-sm font-medium text-slate-400">Total</span>
                <span className="text-xl font-bold text-white">{money(selected.total_amount)}</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
