import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../services/api';
import toast from 'react-hot-toast';
import { AlertTriangle, ArrowUpRight, Package, RefreshCw, ShoppingCart, TrendingUp } from 'lucide-react';

const money = (value) => `KES ${Number(value || 0).toLocaleString()}`;

const Dashboard = () => {
  const [trend, setTrend] = useState([]);
  const [lowStock, setLowStock] = useState([]);
  const [lowStockCount, setLowStockCount] = useState(0);
  const [stockValue, setStockValue] = useState(0);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const [trendRes, stockRes, lowStockRes, statusRes] = await Promise.all([
        api.get('/analytics/daily_sales_trend/'),
        api.get('/analytics/stock_value/'),
        api.get('/analytics/low_stock/'),
        api.get('/analytics/inventory_status/'),
      ]);
      setTrend(Array.isArray(trendRes.data) ? trendRes.data : []);
      setStockValue(stockRes.data?.total || 0);
      setLowStock(Array.isArray(lowStockRes.data) ? lowStockRes.data : []);
      setLowStockCount(Number(statusRes.data?.low_stock_count || 0));
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Unable to load dashboard data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const today = new Date().toISOString().slice(0, 10);
  const todayRow = trend.find((row) => String(row.date).slice(0, 10) === today);
  const todayRevenue = Number(todayRow?.revenue || 0);
  const todaySales = Number(todayRow?.count || 0);
  const maxRevenue = Math.max(...trend.slice(-7).map((x) => Number(x.revenue || 0)), 1);

  return (
    <div className="page-shell">
      <div className="mb-7 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="mb-2 text-xs font-bold uppercase tracking-[0.18em] text-blue-400">Business overview</p>
          <h1 className="page-title">Good business starts with visibility.</h1>
          <p className="page-subtitle">A live snapshot of sales and inventory across your store.</p>
        </div>
        <button onClick={load} disabled={loading} className="btn-secondary self-start sm:self-auto">
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} /> Refresh
        </button>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[
          { label: 'Today’s revenue', value: money(todayRevenue), icon: TrendingUp, accent: 'text-blue-400' },
          { label: 'Sales today', value: todaySales, icon: ShoppingCart, accent: 'text-emerald-400' },
          { label: 'Inventory value', value: money(stockValue), icon: Package, accent: 'text-violet-400' },
          { label: 'Low stock', value: lowStockCount, icon: AlertTriangle, accent: lowStock.length ? 'text-amber-400' : 'text-slate-400' },
        ].map(({ label, value, icon: Icon, accent }) => (
          <div key={label} className="panel p-5">
            <div className="mb-5 flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-500">{label}</span>
              <Icon size={18} className={accent} />
            </div>
            <div className="text-2xl font-black tracking-tight text-white">{loading ? '—' : value}</div>
          </div>
        ))}
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-[1.6fr_1fr]">
        <section className="panel p-5">
          <div className="mb-6 flex items-center justify-between">
            <div>
              <h2 className="font-bold text-white">Sales activity</h2>
              <p className="mt-1 text-xs text-slate-500">Last 7 recorded days</p>
            </div>
            <Link to="/orders" className="flex items-center gap-1 text-xs font-bold text-blue-400 hover:text-blue-300">View sales <ArrowUpRight size={14} /></Link>
          </div>
          <div className="flex h-56 items-end gap-2 sm:gap-4">
            {trend.slice(-7).map((row) => {
              const height = Math.max(8, (Number(row.revenue || 0) / maxRevenue) * 100);
              return (
                <div key={row.date} className="flex h-full flex-1 flex-col justify-end gap-2">
                  <div className="text-center text-[9px] font-bold text-slate-600">{Number(row.revenue || 0) > 0 ? money(row.revenue) : ''}</div>
                  <div className="group relative flex flex-1 items-end">
                    <div style={{ height: `${height}%` }} className="w-full rounded-t-lg bg-blue-600/80 transition group-hover:bg-blue-500" />
                  </div>
                  <div className="text-center text-[9px] font-semibold text-slate-600">{new Date(row.date).toLocaleDateString(undefined, { weekday: 'short' })}</div>
                </div>
              );
            })}
            {!trend.length && <div className="flex w-full items-center justify-center text-sm text-slate-600">No sales recorded yet.</div>}
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">
            <div><h2 className="font-bold text-white">Stock attention</h2><p className="mt-1 text-xs text-slate-500">Items at or below threshold</p></div>
            <Link to="/inventory" className="text-xs font-bold text-blue-400">Inventory</Link>
          </div>
          <div className="max-h-64 overflow-auto">
            {lowStock.slice(0, 6).map((item) => (
              <div key={item.id} className="flex items-center justify-between border-b border-slate-800 px-5 py-4 last:border-0">
                <div className="min-w-0"><div className="truncate text-sm font-semibold text-slate-200">{item.name}</div><div className="mt-1 text-[11px] text-slate-600">{item.sku || 'No SKU'}</div></div>
                <span className="ml-4 shrink-0 rounded-lg bg-amber-500/10 px-2.5 py-1 text-xs font-bold text-amber-400">{item.stock_level} left</span>
              </div>
            ))}
            {!lowStock.length && <div className="p-8 text-center text-sm text-slate-600">Inventory levels look healthy.</div>}
          </div>
        </section>
      </div>

      <section className="mt-5 panel">
        <div className="panel-header">
          <div><h2 className="font-bold text-white">Quick actions</h2><p className="mt-1 text-xs text-slate-500">Common tasks for your team</p></div>
        </div>
        <div className="grid gap-3 p-4 sm:grid-cols-3">
          <Link to="/pos" className="rounded-xl border border-slate-800 bg-slate-950 p-4 transition hover:border-blue-500/40 hover:bg-slate-900"><ShoppingCart size={20} className="mb-3 text-blue-400" /><div className="text-sm font-bold text-white">Start a sale</div><div className="mt-1 text-xs text-slate-500">Open the checkout terminal.</div></Link>
          <Link to="/inventory" className="rounded-xl border border-slate-800 bg-slate-950 p-4 transition hover:border-blue-500/40 hover:bg-slate-900"><Package size={20} className="mb-3 text-violet-400" /><div className="text-sm font-bold text-white">Manage inventory</div><div className="mt-1 text-xs text-slate-500">Add products or adjust stock.</div></Link>
          <Link to="/orders" className="rounded-xl border border-slate-800 bg-slate-950 p-4 transition hover:border-blue-500/40 hover:bg-slate-900"><TrendingUp size={20} className="mb-3 text-emerald-400" /><div className="text-sm font-bold text-white">Review sales</div><div className="mt-1 text-xs text-slate-500">Check recent transactions.</div></Link>
        </div>
      </section>
    </div>
  );
};

export default Dashboard;
