import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../services/api';
import toast from 'react-hot-toast';
import { AlertTriangle, ArrowUpRight, Package, RefreshCw, ShoppingCart, TrendingUp } from 'lucide-react';

const money = (value) => `KES ${Number(value || 0).toLocaleString()}`;

const ManagerDashboard = () => {
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
    <div className="zen-dashboard-page page-shell">
      <div className="mb-7 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="mb-2 text-xs font-bold uppercase tracking-[0.18em] text-[#FF5938]">Business overview</p>
          <h1 className="page-title">Overview</h1>
          <p className="page-subtitle">Today's takings and the stock that needs attention.</p>
        </div>
        <button onClick={load} disabled={loading} className="btn-secondary self-start sm:self-auto">
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} /> Refresh
        </button>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[
          { label: 'Today’s revenue', value: money(todayRevenue), icon: TrendingUp, accent: 'text-[#FF5938]' },
          { label: 'Sales today', value: todaySales, icon: ShoppingCart, accent: 'text-emerald-400' },
          { label: 'Inventory value', value: money(stockValue), icon: Package, accent: 'text-[#FF5938]' },
          { label: 'Low stock', value: lowStockCount, icon: AlertTriangle, accent: lowStock.length ? 'text-amber-400' : 'text-slate-400' },
        ].map(({ label, value, icon: Icon, accent }) => (
          <div key={label} className="panel p-5">
            <div className="mb-5 flex items-center justify-between">
              <span className="text-xs font-semibold text-[#756F66]">{label}</span>
              <Icon size={18} className={accent} />
            </div>
            <div className="text-2xl font-black tracking-tight text-[#171715]">{loading ? '—' : value}</div>
          </div>
        ))}
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-[1.6fr_1fr]">
        <section className="panel p-5">
          <div className="mb-6 flex items-center justify-between">
            <div>
              <h2 className="font-bold text-[#171715]">Sales activity</h2>
              <p className="mt-1 text-xs text-[#756F66]">Last 7 recorded days</p>
            </div>
            <Link to="/orders" className="flex items-center gap-1 text-xs font-bold text-[#FF5938] hover:text-[#E94A2B]">View sales <ArrowUpRight size={14} /></Link>
          </div>
          <div className="flex h-56 items-end gap-2 sm:gap-4">
            {trend.slice(-7).map((row) => {
              const height = Math.max(8, (Number(row.revenue || 0) / maxRevenue) * 100);
              return (
                <div key={row.date} className="flex h-full flex-1 flex-col justify-end gap-2">
                  <div className="text-center text-[9px] font-bold text-[#756F66]">{Number(row.revenue || 0) > 0 ? money(row.revenue) : ''}</div>
                  <div className="group relative flex flex-1 items-end">
                    <div style={{ height: `${height}%` }} className="w-full rounded-t-lg bg-[#FF5938]/80 transition group-hover:bg-[#E94A2B]" />
                  </div>
                  <div className="text-center text-[9px] font-semibold text-[#756F66]">{new Date(row.date).toLocaleDateString(undefined, { weekday: 'short' })}</div>
                </div>
              );
            })}
            {!trend.length && <div className="flex w-full items-center justify-center text-sm text-[#756F66]">No sales recorded yet.</div>}
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">
            <div><h2 className="font-bold text-[#171715]">Stock attention</h2><p className="mt-1 text-xs text-[#756F66]">Items at or below threshold</p></div>
            <Link to="/inventory" className="text-xs font-bold text-[#FF5938]">Inventory</Link>
          </div>
          <div className="max-h-64 overflow-auto">
            {lowStock.slice(0, 6).map((item) => (
              <div key={item.id} className="flex items-center justify-between border-b border-slate-800 px-5 py-4 last:border-0">
                <div className="min-w-0"><div className="truncate text-sm font-semibold text-[#171715]">{item.name}</div><div className="mt-1 text-[11px] text-[#756F66]">{item.sku || 'No SKU'}</div></div>
                <span className="ml-4 shrink-0 rounded-lg bg-amber-500/10 px-2.5 py-1 text-xs font-bold text-amber-400">{item.stock_level} left</span>
              </div>
            ))}
            {!lowStock.length && <div className="p-8 text-center text-sm text-[#756F66]">Inventory levels look healthy.</div>}
          </div>
        </section>
      </div>

      <section className="mt-5 panel">
        <div className="panel-header">
          <div><h2 className="font-bold text-[#171715]">Quick actions</h2><p className="mt-1 text-xs text-[#756F66]">Common tasks for your team</p></div>
        </div>
        <div className="grid gap-3 p-4 sm:grid-cols-3">
          <Link to="/pos" className="rounded-xl border border-slate-800 bg-slate-950 p-4 transition hover:border-[#FF5938]/40 hover:bg-slate-900"><ShoppingCart size={20} className="mb-3 text-[#FF5938]" /><div className="text-sm font-bold text-[#171715]">Start a sale</div><div className="mt-1 text-xs text-[#756F66]">Open the checkout terminal.</div></Link>
          <Link to="/inventory" className="rounded-xl border border-slate-800 bg-slate-950 p-4 transition hover:border-[#FF5938]/40 hover:bg-slate-900"><Package size={20} className="mb-3 text-[#FF5938]" /><div className="text-sm font-bold text-[#171715]">Manage inventory</div><div className="mt-1 text-xs text-[#756F66]">Add products or adjust stock.</div></Link>
          <Link to="/orders" className="rounded-xl border border-slate-800 bg-slate-950 p-4 transition hover:border-[#FF5938]/40 hover:bg-slate-900"><TrendingUp size={20} className="mb-3 text-emerald-400" /><div className="text-sm font-bold text-[#171715]">Review sales</div><div className="mt-1 text-xs text-[#756F66]">Check recent transactions.</div></Link>
        </div>
      </section>
    </div>
  );
};


const HRWorkspace = () => {
  const [employees, setEmployees] = useState([]);
  const [branches, setBranches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    Promise.all([
      api.get('/employees/'),
      api.get('/branches/', { params: { page_size: 100 } }),
    ]).then(([employeeRes, branchRes]) => {
      if (!active) return;
      const employeeData = employeeRes.data;
      const branchData = branchRes.data;
      setEmployees(Array.isArray(employeeData) ? employeeData : employeeData.results || []);
      setBranches(Array.isArray(branchData) ? branchData : branchData.results || []);
    }).catch((err) => {
      if (active) setError(err.response?.data?.detail || 'Unable to load staff information. Check the account permissions.');
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const activeEmployees = employees.filter((employee) => employee.status === 'ACTIVE').length;
  const inactiveEmployees = employees.filter((employee) => employee.status && employee.status !== 'ACTIVE').length;
  const cards = [
    { label: 'Total employee records', value: employees.length, icon: Users },
    { label: 'Active employees', value: activeEmployees, icon: Contact },
    { label: 'Inactive / other status', value: inactiveEmployees, icon: AlertTriangle },
    { label: 'Branches', value: branches.length, icon: Package },
  ];

  return (
    <div className="zen-dashboard-page page-shell">
      <div className="mb-7 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="mb-2 text-xs font-bold uppercase tracking-[0.18em] text-[#FF5938]">People operations</p>
          <h1 className="page-title">HR workspace</h1>
          <p className="page-subtitle">Employee records and staff administration for your organization.</p>
        </div>
        <Link to="/staff" className="btn-primary"><Users size={16} /> Manage employees</Link>
      </div>

      {error && <div role="alert" className="mb-5 rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-700">{error}</div>}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {cards.map(({ label, value, icon: Icon }) => (
          <div key={label} className="panel p-5">
            <div className="mb-5 flex items-center justify-between">
              <span className="text-xs font-semibold text-[#756F66]">{label}</span>
              <Icon size={18} className="text-[#FF5938]" />
            </div>
            <div className="text-2xl font-black tracking-tight text-[#171715]">{loading ? '—' : value}</div>
          </div>
        ))}
      </div>

      <section className="mt-5 panel">
        <div className="panel-header">
          <div><h2 className="font-bold text-[#171715]">Staff administration</h2><p className="mt-1 text-xs text-[#756F66]">Current employee-record tools available in ZenPOS.</p></div>
        </div>
        <div className="grid gap-3 p-4 sm:grid-cols-2">
          <Link to="/staff" className="rounded-xl border border-slate-800 bg-slate-950 p-4 transition hover:border-[#FF5938]/40 hover:bg-slate-900">
            <Users size={20} className="mb-3 text-[#FF5938]" /><div className="text-sm font-bold text-[#171715]">Employee directory</div><div className="mt-1 text-xs text-[#756F66]">Create, search, update and maintain employee records.</div>
          </Link>
          <Link to="/staff" className="rounded-xl border border-slate-800 bg-slate-950 p-4 transition hover:border-[#FF5938]/40 hover:bg-slate-900">
            <Contact size={20} className="mb-3 text-[#FF5938]" /><div className="text-sm font-bold text-[#171715]">Employment status</div><div className="mt-1 text-xs text-[#756F66]">Review active, inactive, suspended and terminated records.</div>
          </Link>
        </div>
      </section>

      <section className="mt-5 rounded-2xl border border-amber-500/25 bg-amber-500/5 p-5">
        <h2 className="font-bold text-[#171715]">HR capabilities to build next</h2>
        <p className="mt-2 text-sm leading-6 text-[#756F66]">Leave requests and balances, attendance and shifts, recruitment and onboarding, performance reviews, training, confidential employee relations, and payroll preparation are not yet exposed as complete workflows in the current application. They should be added with dedicated records, approval rules and server-side permissions rather than displayed as if already working.</p>
      </section>
    </div>
  );
};

const Dashboard = () => {
  let user = {};
  try { user = JSON.parse(localStorage.getItem('user') || '{}') || {}; } catch { /* invalid session profile */ }
  const roles = Array.isArray(user.roles) ? user.roles : [];
  return roles.includes('HR_MANAGER') ? <HRWorkspace /> : <ManagerDashboard />;
};

export default Dashboard;
