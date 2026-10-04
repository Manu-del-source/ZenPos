import React from 'react';
import { BrowserRouter as Router, Routes, Route, Link, Navigate, useLocation } from 'react-router-dom';
import POS from './pages/POS';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Inventory from './pages/Inventory';
import Orders from './pages/Orders';
import Customers from './pages/Customers';
import Landing from './pages/Landing';
import useOfflineSync from './hooks/useOfflineSync';

const ProtectedRoute = ({ children }) => {
  const token = localStorage.getItem('token');
  if (!token) return <Navigate to="/login" />;
  return children;
};

import { Toaster } from 'react-hot-toast';

const AppLayout = ({ token, user, handleLogout }) => {
  const { pathname } = useLocation();
  const showAppNav = token && pathname !== '/' && pathname !== '/login';

  return (
    <div className="min-h-screen flex flex-col">
      {showAppNav && (
        <nav className="bg-slate-900 text-white p-4 flex justify-between items-center border-b border-slate-800 shadow-xl">
          <div className="flex items-center space-x-3">
            <div className="bg-blue-600 p-2 rounded-lg">
              <span className="text-lg font-black italic">K</span>
            </div>
            <div className="text-xl font-black tracking-tighter uppercase">ZEN<span className="text-blue-500">POS</span></div>
          </div>
          <div className="flex items-center space-x-2">
            <Link to="/pos" className="hover:bg-slate-800 px-4 py-2 rounded-lg font-medium transition">POS</Link>
            <Link to="/inventory" className="hover:bg-slate-800 px-4 py-2 rounded-lg font-medium transition">Inventory</Link>
            <Link to="/orders" className="hover:bg-slate-800 px-4 py-2 rounded-lg font-medium transition">Sales</Link>
            {user.role?.toLowerCase() === 'admin' && (
              <Link to="/dashboard" className="hover:bg-slate-800 px-4 py-2 rounded-lg font-medium transition text-blue-400">Reports</Link>
            )}
            <button onClick={handleLogout} className="bg-red-500/10 text-red-500 hover:bg-red-500 hover:text-white px-4 py-2 rounded-lg font-bold transition">
              Logout
            </button>
          </div>
        </nav>
      )}
      <main className="flex-grow bg-gray-50">
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<Landing />} />
          <Route path="/pos" element={<ProtectedRoute><POS /></ProtectedRoute>} />
          <Route path="/inventory" element={<ProtectedRoute><Inventory /></ProtectedRoute>} />
          <Route path="/customers" element={<ProtectedRoute><Customers /></ProtectedRoute>} />
          <Route path="/orders" element={<ProtectedRoute><Orders /></ProtectedRoute>} />
          <Route path="/dashboard" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
        </Routes>
      </main>
    </div>
  );
};

function App() {
  const token = localStorage.getItem('token');
  const user = JSON.parse(localStorage.getItem('user') || '{}');
  useOfflineSync(token);

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    window.location.href = '/login';
  };

  return (
    <Router>
      <Toaster position="top-right" />
      <AppLayout token={token} user={user} handleLogout={handleLogout} />
    </Router>
  );
}


export default App;
