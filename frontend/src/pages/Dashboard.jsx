import React, { useState, useEffect } from 'react';
import api from '../services/api';
import toast from 'react-hot-toast';
import { BarChart3, Package, TrendingUp, AlertTriangle } from 'lucide-react';

const Dashboard = () => {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  
  const user = JSON.parse(localStorage.getItem('user') || '{}');

  const fetchStats = async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/reports/dashboard');
      setStats(data);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to load dashboard stats');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStats();
  }, []);

  if (loading && !stats) return <div className="p-8 text-center text-slate-400">Loading shop performance...</div>;

  return (
    <div className="p-8 max-w-7xl mx-auto bg-slate-950 min-h-screen text-white">
      <div className="flex justify-between items-center mb-8">
        <div>
          <h1 className="text-3xl font-black tracking-tight uppercase italic">SHOP <span className="text-blue-500">PERFORMANCE</span></h1>
          <p className="text-slate-500 text-sm font-bold uppercase tracking-widest">ROHI Hardware & Moto POS Metrics</p>
        </div>
        <button 
          onClick={fetchStats}
          className="bg-blue-600 hover:bg-blue-700 px-6 py-2 rounded-lg font-bold transition flex items-center"
        >
          <TrendingUp className="mr-2" size={18} /> REFRESH
        </button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
        <div className="bg-slate-900 p-6 rounded-2xl border border-slate-800 shadow-xl">
          <div className="flex items-center text-blue-500 mb-4">
            <TrendingUp size={20} className="mr-2" />
            <span className="text-[10px] font-black uppercase tracking-widest">Revenue</span>
          </div>
          <h2 className="text-2xl font-black text-white">KES {Number(stats?.revenueToday || 0).toLocaleString()}</h2>
        </div>
        
        <div className="bg-slate-900 p-6 rounded-2xl border border-slate-800 shadow-xl">
          <div className="flex items-center text-green-500 mb-4">
            <BarChart3 size={20} className="mr-2" />
            <span className="text-[10px] font-black uppercase tracking-widest">Orders</span>
          </div>
          <h2 className="text-2xl font-black text-white">{stats?.salesToday || 0}</h2>
        </div>

        <div className="bg-slate-900 p-6 rounded-2xl border border-slate-800 shadow-xl border-l-4 border-l-emerald-500">
          <div className="flex items-center text-emerald-500 mb-4">
            <TrendingUp size={20} className="mr-2" />
            <span className="text-[10px] font-black uppercase tracking-widest">Net Profit</span>
          </div>
          <h2 className="text-2xl font-black text-white">KES {Number(stats?.profitToday || 0).toLocaleString()}</h2>
        </div>

        <div className="bg-slate-900 p-6 rounded-2xl border border-slate-800 shadow-xl">
          <div className="flex items-center text-amber-500 mb-4">
            <AlertTriangle size={20} className="mr-2" />
            <span className="text-[10px] font-black uppercase tracking-widest">Warnings</span>
          </div>
          <h2 className="text-2xl font-black text-white">{stats?.lowStockCount || 0}</h2>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Top Selling Table */}
        <div className="bg-slate-900 p-6 rounded-2xl border border-slate-800 shadow-xl">
          <h3 className="text-xl font-bold mb-6 text-white flex items-center italic uppercase tracking-tighter">
            <TrendingUp className="mr-2 text-blue-500" /> Top Selling Parts
          </h3>
          <div className="space-y-4">
            {stats?.topSelling?.map((item, i) => (
              <div key={i} className="flex items-center justify-between p-4 bg-slate-800/40 rounded-xl border border-slate-800">
                <div>
                  <div className="font-bold text-white text-sm uppercase">{item.name}</div>
                  <div className="text-[10px] text-slate-500 font-bold uppercase tracking-widest">{item.totalSold} units sold</div>
                </div>
                <div className="text-blue-400 font-black">
                  KES {Number(item.revenue).toLocaleString()}
                </div>
              </div>
            ))}
            {(!stats?.topSelling || stats.topSelling.length === 0) && (
               <div className="text-center py-10 text-slate-600 font-bold uppercase text-xs tracking-widest">No Sales Data Today</div>
            )}
          </div>
        </div>

        {/* Low Stock Table */}
        <div className="bg-slate-900 p-6 rounded-2xl border border-slate-800 shadow-xl">
          <h3 className="text-xl font-bold mb-6 text-white flex items-center">
            <Package className="mr-2 text-blue-500" /> Inventory Warnings
          </h3>
          <div className="overflow-hidden rounded-xl border border-slate-800">
            <table className="w-full text-left">
              <thead>
                <tr className="bg-slate-800/50 text-slate-400 text-[10px] uppercase tracking-widest">
                  <th className="p-4">Product Name</th>
                  <th className="p-4 text-right">Current Stock</th>
                </tr>
              </thead>
              <tbody>
                {stats?.lowStock?.map((item, i) => (
                  <tr key={i} className="border-t border-slate-800 hover:bg-slate-800/30 transition">
                    <td className="p-4 font-medium text-slate-200">{item.name}</td>
                    <td className="p-4 text-right">
                      <span className="bg-red-500/10 text-red-400 px-3 py-1 rounded-full text-xs font-black">
                        {item.stockLevel} left
                      </span>
                    </td>
                  </tr>
                ))}
                {(!stats?.lowStock || stats.lowStock.length === 0) && (
                  <tr>
                    <td colSpan="2" className="p-8 text-center text-slate-600 italic">No inventory warnings</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Quick Tips */}
        <div className="bg-slate-900 p-6 rounded-2xl border border-slate-800 shadow-xl">
          <h3 className="text-xl font-bold mb-6 text-white">System Status</h3>
          <div className="space-y-4">
            <div className="flex items-center p-4 bg-blue-500/5 rounded-xl border border-blue-500/10">
              <div className="w-2 h-2 bg-blue-500 rounded-full mr-4 animate-pulse"></div>
              <span className="text-sm text-slate-300">Express API: <b className="text-blue-400">Connected</b></span>
            </div>
            <div className="flex items-center p-4 bg-green-500/5 rounded-xl border border-green-500/10">
              <div className="w-2 h-2 bg-green-500 rounded-full mr-4"></div>
              <span className="text-sm text-slate-300">M-Pesa STK Service: <b className="text-green-400">Online</b></span>
            </div>
            <div className="flex items-center p-4 bg-slate-800/50 rounded-xl">
              <div className="w-2 h-2 bg-slate-600 rounded-full mr-4"></div>
              <span className="text-sm text-slate-500">Database Engine: PostgreSQL</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
