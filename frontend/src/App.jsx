import React, { useEffect, useState } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, NavLink, useLocation } from 'react-router-dom';
import {
  LayoutDashboard, ShoppingCart, Package, ReceiptText, Users, Settings,
  LogOut, Menu, X, ChevronRight, Store, ShieldAlert, Truck, ClipboardList,
  PackageCheck, ScrollText, ArrowLeftRight, Contact, BarChart3, ShieldCheck,
} from 'lucide-react';
import POS from './pages/POS';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Inventory from './pages/Inventory';
import Orders from './pages/Orders';
import Customers from './pages/Customers';
import Suppliers from './pages/Suppliers';
import PurchaseOrders from './pages/PurchaseOrders';
import GoodsReceiving from './pages/GoodsReceiving';
import StockLedger from './pages/StockLedger';
import Transfers from './pages/Transfers';
import Staff from './pages/Staff';
import Reports from './pages/Reports';
import Landing from './pages/Landing';
import SettingsPage from './pages/Settings';
import SuperAdmin from './pages/SuperAdmin';
import { logout } from './services/api';
import useOfflineSync from './hooks/useOfflineSync';
import { Toaster } from 'react-hot-toast';

/** Permission codes are read from the server's `/auth/me/`; hiding a menu item
 * is a convenience, never a control — every endpoint re-checks server-side. */
export const can = (user, code) => {
  if (!user) return false;
  if (user.is_superuser) return true;
  return Array.isArray(user.permissions) && user.permissions.includes(code);
};

// Each entry names the permission the API actually enforces for that screen,
// so a cashier is not shown a menu item that answers 403.
const NAV_ITEMS = [
  { to: '/pos', label: 'Point of Sale', icon: ShoppingCart, permission: 'sales.create' },
  { to: '/orders', label: 'Sales', icon: ReceiptText, permission: 'sales.view' },
  { to: '/inventory', label: 'Inventory', icon: Package, permission: ['inventory.view', 'products.view'] },
  { to: '/suppliers', label: 'Suppliers', icon: Truck, permission: ['purchases.view', 'purchases.create'] },
  { to: '/purchase-orders', label: 'Purchase Orders', icon: ClipboardList, permission: ['purchases.view', 'purchases.create'] },
  { to: '/goods-receiving', label: 'Goods Receiving', icon: PackageCheck, permission: ['purchases.view', 'purchases.create'] },
  { to: '/stock-ledger', label: 'Stock Ledger', icon: ScrollText, permission: 'inventory.view' },
  { to: '/transfers', label: 'Transfers', icon: ArrowLeftRight, permission: ['inventory.view', 'inventory.transfer'] },
  { to: '/customers', label: 'Customers', icon: Users, permission: 'customers.manage' },
  { to: '/staff', label: 'Staff', icon: Contact, permission: 'users.manage' },
  { to: '/dashboard', label: 'Overview', icon: LayoutDashboard, permission: 'reports.view' },
  { to: '/reports', label: 'Reports', icon: BarChart3, permission: 'reports.view' },
];

const MANAGEMENT_ITEMS = [
  { to: '/settings', label: 'Settings', icon: Settings, permission: 'settings.manage' },
  { to: '/super-admin', label: 'Super Admin', icon: ShieldCheck, platformOnly: true },
];

/** The first screen this account may actually open. */
export const homePath = (user) => {
  const first = [...NAV_ITEMS, ...MANAGEMENT_ITEMS].find((item) => {
    const codes = Array.isArray(item.permission) ? item.permission : [item.permission];
    return codes.some((code) => can(user, code));
  });
  return first?.to || null;
};

const readAuth = () => {
  const token = localStorage.getItem('token');
  let user = {};
  try {
    user = JSON.parse(localStorage.getItem('user') || '{}') || {};
  } catch {
    localStorage.removeItem('user');
    user = {};
  }
  return { token, user };
};

const ProtectedRoute = ({ children }) => {
  const token = localStorage.getItem('token');
  return token ? children : <Navigate to="/login" replace />;
};

const AppLayout = ({ token, user, handleLogout }) => {
  const { pathname } = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);

  const allows = (item) => {
    if (item.platformOnly) return Boolean(user?.is_superuser);
    const codes = Array.isArray(item.permission) ? item.permission : [item.permission];
    return codes.some((code) => can(user, code));
  };
  const items = NAV_ITEMS.filter(allows);
  const management = MANAGEMENT_ITEMS.filter(allows);
  const showAppNav = Boolean(token) && pathname !== '/' && pathname !== '/login';
  const current = [...NAV_ITEMS, ...MANAGEMENT_ITEMS].find(
    (item) => pathname === item.to || pathname.startsWith(`${item.to}/`),
  );
  const organization = user?.organization_name || user?.organization?.name || 'ZenPOS store';

  if (showAppNav && !homePath(user)) {
    return (
      <div className="page-shell grid min-h-screen place-items-center">
        <section className="panel max-w-md p-8 text-center">
          <ShieldAlert className="mx-auto mb-3 text-amber-400" size={34} />
          <h1 className="page-title">No access yet</h1>
          <p className="page-subtitle">
            This account is signed in but has no role assigned. Ask an administrator to give you a role before using the till.
          </p>
          <button className="btn-secondary mt-6 w-full" onClick={handleLogout}>
            <LogOut size={17} /> Sign out
          </button>
        </section>
      </div>
    );
  }

  if (!showAppNav) {
    return (
      <main className="min-h-screen bg-slate-950">
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<Landing />} />
          <Route path="*" element={<Navigate to={token ? '/pos' : '/login'} replace />} />
        </Routes>
      </main>
    );
  }

  const Sidebar = () => (
    <aside className={`fixed inset-y-0 left-0 z-50 w-64 border-r border-slate-800 bg-slate-950/95 backdrop-blur-xl transition-transform lg:translate-x-0 ${mobileOpen ? 'translate-x-0' : '-translate-x-full'}`}>
      <div className="flex h-full flex-col">
        <div className="flex h-20 items-center justify-between border-b border-slate-800 px-5">
          <NavLink to="/dashboard" onClick={() => setMobileOpen(false)} className="flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-xl bg-blue-600 text-lg font-black text-white">Z</div>
            <div>
              <div className="text-lg font-black tracking-tight text-white">Zen<span className="text-blue-500">POS</span></div>
              <div className="text-[9px] font-bold uppercase tracking-[0.18em] text-slate-500">Retail platform</div>
            </div>
          </NavLink>
          <button onClick={() => setMobileOpen(false)} className="text-slate-500 lg:hidden"><X size={20} /></button>
        </div>

        {can(user, 'sales.create') && (
          <div className="px-4 pt-5">
            <NavLink to="/pos" onClick={() => setMobileOpen(false)} className="flex items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 py-3 text-sm font-bold text-white transition hover:bg-blue-500">
              <ShoppingCart size={18} /> New sale
            </NavLink>
          </div>
        )}

        <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-6">
          <p className="px-3 pb-3 text-[10px] font-bold uppercase tracking-[0.18em] text-slate-600">Workspace</p>
          {items.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              onClick={() => setMobileOpen(false)}
              className={({ isActive }) => `group flex items-center gap-3 rounded-xl px-3 py-3 text-sm font-semibold transition ${isActive ? 'bg-slate-800 text-white' : 'text-slate-400 hover:bg-slate-900 hover:text-white'}`}
            >
              {({ isActive }) => (
                <>
                  <Icon size={19} className={isActive ? 'text-blue-400' : 'text-slate-500 group-hover:text-slate-300'} />
                  <span>{label}</span>
                  {isActive && <ChevronRight size={15} className="ml-auto text-slate-600" />}
                </>
              )}
            </NavLink>
          ))}
          {management.length > 0 && (
            <>
              <p className="px-3 pb-3 pt-6 text-[10px] font-bold uppercase tracking-[0.18em] text-slate-600">Management</p>
              {management.map(({ to, label, icon: Icon }) => (
                <NavLink
                  key={to}
                  to={to}
                  onClick={() => setMobileOpen(false)}
                  className={({ isActive }) => `flex items-center gap-3 rounded-xl px-3 py-3 text-sm font-semibold ${isActive ? 'bg-slate-800 text-white' : 'text-slate-400 hover:bg-slate-900 hover:text-white'}`}
                >
                  <Icon size={19} className="text-slate-500" /><span>{label}</span>
                </NavLink>
              ))}
            </>
          )}
        </nav>

        <div className="border-t border-slate-800 p-3">
          <div className="mb-2 flex items-center gap-3 rounded-xl bg-slate-900 p-3">
            <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-slate-800 text-xs font-black text-blue-400">
              {(user?.username || 'U').slice(0, 1).toUpperCase()}
            </div>
            <div className="min-w-0">
              <div className="truncate text-sm font-bold text-white">{user?.username || 'User'}</div>
              <div className="truncate text-[10px] uppercase tracking-wider text-slate-500">
                {(user?.roles || []).join(', ') || organization}
              </div>
            </div>
          </div>
          <button onClick={handleLogout} className="flex w-full items-center gap-3 rounded-xl px-3 py-3 text-sm font-semibold text-slate-500 transition hover:bg-red-500/10 hover:text-red-400">
            <LogOut size={18} /><span>Sign out</span>
          </button>
        </div>
      </div>
    </aside>
  );

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <Sidebar />
      {mobileOpen && <button aria-label="Close menu" onClick={() => setMobileOpen(false)} className="fixed inset-0 z-40 bg-black/60 lg:hidden" />}
      <div className="lg:pl-64">
        <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-slate-800/80 bg-slate-950/90 px-4 backdrop-blur-xl sm:px-6">
          <div className="flex items-center gap-3">
            <button onClick={() => setMobileOpen(true)} className="rounded-lg p-2 text-slate-400 hover:bg-slate-900 lg:hidden" aria-label="Open menu"><Menu size={21} /></button>
            <div>
              <div className="text-sm font-bold text-white">{current?.label || 'ZenPOS'}</div>
              <div className="hidden text-[10px] uppercase tracking-wider text-slate-600 sm:block">{organization}</div>
            </div>
          </div>
          <div className="hidden items-center gap-2 text-xs font-semibold text-slate-500 sm:flex">
            <Store size={17} className="text-slate-600" />
            {organization}
          </div>
        </header>
        <main className="min-h-[calc(100vh-4rem)]">
          <Routes>
            <Route path="/pos" element={<ProtectedRoute><POS /></ProtectedRoute>} />
            <Route path="/inventory" element={<ProtectedRoute><Inventory /></ProtectedRoute>} />
            <Route path="/suppliers" element={<ProtectedRoute><Suppliers /></ProtectedRoute>} />
            <Route path="/purchase-orders" element={<ProtectedRoute><PurchaseOrders /></ProtectedRoute>} />
            <Route path="/goods-receiving" element={<ProtectedRoute><GoodsReceiving /></ProtectedRoute>} />
            <Route path="/stock-ledger" element={<ProtectedRoute><StockLedger /></ProtectedRoute>} />
            <Route path="/transfers" element={<ProtectedRoute><Transfers /></ProtectedRoute>} />
            <Route path="/customers" element={<ProtectedRoute><Customers /></ProtectedRoute>} />
            <Route path="/staff" element={<ProtectedRoute><Staff /></ProtectedRoute>} />
            <Route path="/reports" element={<ProtectedRoute><Reports /></ProtectedRoute>} />
            <Route path="/orders" element={<ProtectedRoute><Orders /></ProtectedRoute>} />
            <Route path="/dashboard" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
            <Route path="/settings" element={<ProtectedRoute><SettingsPage user={user} /></ProtectedRoute>} />
            <Route path="/super-admin" element={<ProtectedRoute>{user?.is_superuser ? <SuperAdmin /> : <Navigate to={homePath(user) || '/login'} replace />}</ProtectedRoute>} />
            <Route path="*" element={<Navigate to={homePath(user) || '/login'} replace />} />
          </Routes>
        </main>
      </div>
    </div>
  );
};

function App() {
  const [auth, setAuth] = useState(readAuth);
  useOfflineSync(auth.token);

  // `localStorage` is not reactive, and Login writes to it before navigating.
  // Without re-reading it here (on the event Login fires, or on a change from
  // another tab) the shell keeps rendering the signed-out layout and bounces a
  // just-authenticated user back to /login.
  useEffect(() => {
    const sync = () => setAuth(readAuth());
    window.addEventListener('zenpos:auth', sync);
    window.addEventListener('storage', sync);
    return () => {
      window.removeEventListener('zenpos:auth', sync);
      window.removeEventListener('storage', sync);
    };
  }, []);

  const handleLogout = () => {
    logout();
  };

  return (
    <Router>
      <Toaster position="top-right" toastOptions={{ style: { background: '#172033', color: '#fff', border: '1px solid #263247' } }} />
      <AppLayout token={auth.token} user={auth.user} handleLogout={handleLogout} />
    </Router>
  );
}

export default App;
