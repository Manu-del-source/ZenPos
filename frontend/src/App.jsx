import React, { useState } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, NavLink, useLocation } from 'react-router-dom';
import {
  LayoutDashboard, ShoppingCart, Package, ReceiptText, Users, BarChart3,
  Settings, LogOut, Menu, X, ChevronRight, Store, Bell
} from 'lucide-react';
import POS from './pages/POS';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Inventory from './pages/Inventory';
import Orders from './pages/Orders';
import Customers from './pages/Customers';
import Landing from './pages/Landing';
import SettingsPage from './pages/Settings';
import useOfflineSync from './hooks/useOfflineSync';
import toast, { Toaster } from 'react-hot-toast';

const ProtectedRoute = ({ children }) => {
  const token = localStorage.getItem('token');
  return token ? children : <Navigate to="/login" replace />;
};

const navItems = [
  { to: '/dashboard', label: 'Overview', icon: LayoutDashboard },
  { to: '/pos', label: 'Point of Sale', icon: ShoppingCart, primary: true },
  { to: '/inventory', label: 'Inventory', icon: Package },
  { to: '/orders', label: 'Sales', icon: ReceiptText },
  { to: '/customers', label: 'Customers', icon: Users },
];

const AppLayout = ({ token, user, handleLogout }) => {
  const { pathname } = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const roles = Array.isArray(user?.roles) ? user.roles : [];
  const isAdmin = user?.is_superuser === true || roles.some((role) => String(role).toLowerCase() === 'admin');
  const showAppNav = Boolean(token) && pathname !== '/' && pathname !== '/login';
  const current = navItems.find((item) => pathname === item.to || pathname.startsWith(item.to + '/'));
  const organization = user?.organization_name || user?.organization?.name || 'ZenPOS Store';

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
            <div className="grid h-10 w-10 place-items-center rounded-xl bg-blue-600 text-lg font-black text-white shadow-lg shadow-blue-600/20">Z</div>
            <div>
              <div className="text-lg font-black tracking-tight text-white">Zen<span className="text-blue-500">POS</span></div>
              <div className="text-[9px] font-bold uppercase tracking-[0.18em] text-slate-500">Retail platform</div>
            </div>
          </NavLink>
          <button onClick={() => setMobileOpen(false)} className="text-slate-500 lg:hidden"><X size={20} /></button>
        </div>

        <div className="px-4 pt-5">
          <NavLink to="/pos" onClick={() => setMobileOpen(false)} className="flex items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 py-3 text-sm font-bold text-white shadow-lg shadow-blue-600/20 transition hover:bg-blue-500">
            <ShoppingCart size={18} /> New Sale
          </NavLink>
        </div>

        <nav className="flex-1 space-y-1 px-3 py-6">
          <p className="px-3 pb-3 text-[10px] font-bold uppercase tracking-[0.18em] text-slate-600">Workspace</p>
          {navItems.map(({ to, label, icon: Icon, primary }) => (
            <NavLink
              key={to}
              to={to}
              onClick={() => setMobileOpen(false)}
              className={({ isActive }) => `group flex items-center gap-3 rounded-xl px-3 py-3 text-sm font-semibold transition ${isActive ? 'bg-slate-800 text-white' : 'text-slate-400 hover:bg-slate-900 hover:text-white'} ${primary ? 'hidden' : ''}`}
            >
              {({ isActive }) => <><Icon size={19} className={isActive ? 'text-blue-400' : 'text-slate-500 group-hover:text-slate-300'} /><span>{label}</span>{isActive && <ChevronRight size={15} className="ml-auto text-slate-600" />}</>}
            </NavLink>
          ))}
          {isAdmin && (
            <>
              <p className="px-3 pb-3 pt-6 text-[10px] font-bold uppercase tracking-[0.18em] text-slate-600">Management</p>
              <NavLink to="/dashboard" onClick={() => setMobileOpen(false)} className="flex items-center gap-3 rounded-xl px-3 py-3 text-sm font-semibold text-slate-400 hover:bg-slate-900 hover:text-white">
                <BarChart3 size={19} className="text-slate-500" /><span>Reports</span>
              </NavLink>
              <NavLink to="/settings" onClick={() => setMobileOpen(false)} className={({ isActive }) => `flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left text-sm font-semibold ${isActive ? 'bg-slate-800 text-white' : 'text-slate-400 hover:bg-slate-900 hover:text-white'}`}>
                <Settings size={19} className={({}) => ''} /><span>Settings</span>
              </NavLink>
            </>
          )}
        </nav>

        <div className="border-t border-slate-800 p-3">
          <div className="mb-2 flex items-center gap-3 rounded-xl bg-slate-900 p-3">
            <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-slate-800 text-xs font-black text-blue-400">{(user?.username || 'U').slice(0, 1).toUpperCase()}</div>
            <div className="min-w-0">
              <div className="truncate text-sm font-bold text-white">{user?.username || 'User'}</div>
              <div className="truncate text-[10px] uppercase tracking-wider text-slate-500">{organization}</div>
            </div>
          </div>
          <button onClick={handleLogout} className="flex w-full items-center gap-3 rounded-xl px-3 py-3 text-sm font-semibold text-slate-500 hover:bg-red-500/10 hover:text-red-400">
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
            <button onClick={() => setMobileOpen(true)} className="rounded-lg p-2 text-slate-400 hover:bg-slate-900 lg:hidden"><Menu size={21} /></button>
            <div>
              <div className="text-sm font-bold text-white">{current?.label || (pathname === '/settings' ? 'Settings' : 'ZenPOS')}</div>
              <div className="hidden text-[10px] uppercase tracking-wider text-slate-600 sm:block">{organization}</div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => toast('You are all caught up.')} aria-label="Notifications" className="relative rounded-lg p-2 text-slate-500 hover:bg-slate-900 hover:text-slate-200"><Bell size={19} /><span className="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full bg-blue-500" /></button>
            <div className="hidden items-center gap-2 border-l border-slate-800 pl-3 sm:flex"><Store size={17} className="text-slate-500" /><span className="text-xs font-semibold text-slate-400">Main Store</span></div>
          </div>
        </header>
        <main className="min-h-[calc(100vh-4rem)]">
          <Routes>
            <Route path="/pos" element={<ProtectedRoute><POS /></ProtectedRoute>} />
            <Route path="/inventory" element={<ProtectedRoute><Inventory /></ProtectedRoute>} />
            <Route path="/customers" element={<ProtectedRoute><Customers /></ProtectedRoute>} />
            <Route path="/orders" element={<ProtectedRoute><Orders /></ProtectedRoute>} />
            <Route path="/dashboard" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
            <Route path="/settings" element={<ProtectedRoute><SettingsPage /></ProtectedRoute>} />
            <Route path="*" element={<Navigate to="/pos" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  );
};

function App() {
  const token = localStorage.getItem('token');
  let user = {};
  try { user = JSON.parse(localStorage.getItem('user') || '{}'); } catch { localStorage.removeItem('user'); }
  useOfflineSync(token);
  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('refreshToken');
    localStorage.removeItem('user');
    window.location.href = '/login';
  };
  return <Router><Toaster position="top-right" toastOptions={{ style: { background: '#172033', color: '#fff', border: '1px solid #263247' } }} /><AppLayout token={token} user={user} handleLogout={handleLogout} /></Router>;
}

export default App;
