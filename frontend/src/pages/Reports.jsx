import React, { useEffect, useState } from 'react';
import { BarChart3, RefreshCw } from 'lucide-react';
import toast from 'react-hot-toast';
import api, { apiError } from '../services/api';

const money = (v) => `KES ${Number(v || 0).toLocaleString('en-KE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const Card = ({ title, children }) => (
  <section className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden">
    <div className="px-5 py-3 border-b border-slate-800">
      <h2 className="text-sm font-bold text-white">{title}</h2>
    </div>
    <div className="p-5">{children}</div>
  </section>
);

export default function Reports() {
  const [loading, setLoading] = useState(true);
  const [purchasing, setPurchasing] = useState(null);
  const [movements, setMovements] = useState([]);
  const [transfers, setTransfers] = useState([]);
  const [returns, setReturns] = useState(null);
  const [loyalty, setLoyalty] = useState(null);
  const [branches, setBranches] = useState([]);
  const [range, setRange] = useState({ date_from: '', date_to: '' });

  const load = async () => {
    setLoading(true);
    const params = { date_from: range.date_from || undefined, date_to: range.date_to || undefined };
    try {
      const [p, m, t, r, l, b] = await Promise.all([
        api.get('/analytics/purchasing/', { params }),
        api.get('/analytics/inventory_movements/', { params }),
        api.get('/analytics/transfers/', { params }),
        api.get('/analytics/returns/', { params }),
        api.get('/analytics/loyalty/', { params }),
        api.get('/analytics/branch_performance/', { params }),
      ]);
      setPurchasing(p.data);
      setMovements(Array.isArray(m.data) ? m.data : []);
      setTransfers(Array.isArray(t.data) ? t.data : []);
      setReturns(r.data);
      setLoyalty(l.data);
      setBranches(Array.isArray(b.data) ? b.data : []);
    } catch (err) {
      toast.error(apiError(err, 'Failed to load reports'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  return (
    <div className="p-8 max-w-7xl mx-auto min-h-screen">
      <div className="flex justify-between items-end mb-8 gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-black tracking-tight text-white">Reports</h1>
          <p className="text-slate-500 text-sm">Purchasing, inventory, returns, loyalty and branch performance. Filtered on the server.</p>
        </div>
        <div className="flex gap-2 items-center">
          <input type="date" className="bg-slate-900 border border-slate-800 p-3 rounded-xl text-white text-sm" value={range.date_from} onChange={(e) => setRange({ ...range, date_from: e.target.value })} />
          <input type="date" className="bg-slate-900 border border-slate-800 p-3 rounded-xl text-white text-sm" value={range.date_to} onChange={(e) => setRange({ ...range, date_to: e.target.value })} />
          <button className="btn-secondary" onClick={load} disabled={loading}><RefreshCw size={16} className={loading ? 'animate-spin' : ''} /> Run</button>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Purchasing">
          {!purchasing ? <p className="text-slate-500 text-sm">No data</p> : (
            <dl className="grid grid-cols-2 gap-3 text-sm">
              <div><dt className="text-slate-500">Orders</dt><dd className="text-white font-bold text-lg">{purchasing.order_count}</dd></div>
              <div><dt className="text-slate-500">Outstanding POs</dt><dd className="text-white font-bold text-lg">{purchasing.outstanding}</dd></div>
              <div><dt className="text-slate-500">Fully received</dt><dd className="text-white font-bold text-lg">{purchasing.received}</dd></div>
              <div><dt className="text-slate-500">Posted GRNs</dt><dd className="text-white font-bold text-lg">{purchasing.posted_grns}</dd></div>
            </dl>
          )}
        </Card>
        <Card title="Returns">
          {!returns ? <p className="text-slate-500 text-sm">No data</p> : (
            <>
              <p className="text-white font-bold text-lg mb-3">{money(returns.total_amount)} · {returns.count} returns</p>
              <table className="w-full text-sm">
                <tbody>
                  {(returns.by_reason || []).map((row) => (
                    <tr key={row.reason} className="border-t border-slate-800">
                      <td className="py-2 text-slate-300">{row.reason}</td>
                      <td className="py-2 text-right text-slate-400">{row.count}</td>
                      <td className="py-2 text-right text-white">{money(row.amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </Card>
        <Card title="Stock movements">
          <table className="w-full text-sm">
            <tbody>
              {movements.map((row) => (
                <tr key={row.movement_type} className="border-t border-slate-800">
                  <td className="py-2 text-slate-300">{(row.movement_type || '').replaceAll('_', ' ')}</td>
                  <td className="py-2 text-right text-slate-400">{row.count}</td>
                  <td className="py-2 text-right text-white">{Number(row.qty || 0).toLocaleString()}</td>
                </tr>
              ))}
              {movements.length === 0 && <tr><td className="text-slate-500 text-sm">No movements in range</td></tr>}
            </tbody>
          </table>
        </Card>
        <Card title="Loyalty">
          {!loyalty ? <p className="text-slate-500 text-sm">No data</p> : (
            <dl className="grid grid-cols-3 gap-3 text-sm">
              <div><dt className="text-slate-500">Earned</dt><dd className="text-white font-bold text-lg">{loyalty.points_earned}</dd></div>
              <div><dt className="text-slate-500">Redeemed</dt><dd className="text-white font-bold text-lg">{loyalty.points_redeemed}</dd></div>
              <div><dt className="text-slate-500">Outstanding</dt><dd className="text-white font-bold text-lg">{loyalty.outstanding_balances}</dd></div>
            </dl>
          )}
        </Card>
        <Card title="Transfers">
          <table className="w-full text-sm">
            <tbody>
              {transfers.map((row) => (
                <tr key={row.status} className="border-t border-slate-800">
                  <td className="py-2 text-slate-300">{row.status}</td>
                  <td className="py-2 text-right text-white">{row.count}</td>
                </tr>
              ))}
              {transfers.length === 0 && <tr><td className="text-slate-500 text-sm">No transfers in range</td></tr>}
            </tbody>
          </table>
        </Card>
        <Card title="Branch performance">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-500 text-[10px] uppercase tracking-widest">
                <th className="text-left pb-2">Branch</th>
                <th className="text-right pb-2">Sales</th>
                <th className="text-right pb-2">Revenue</th>
              </tr>
            </thead>
            <tbody>
              {branches.map((row) => (
                <tr key={row.branch_id || row.branch__name} className="border-t border-slate-800">
                  <td className="py-2 text-slate-200">{row.branch__name || 'Unassigned'}</td>
                  <td className="py-2 text-right text-slate-400">{row.sales_count}</td>
                  <td className="py-2 text-right text-white">{money(row.revenue)}</td>
                </tr>
              ))}
              {branches.length === 0 && <tr><td className="text-slate-500 text-sm" colSpan={3}><BarChart3 className="inline mr-2" size={14} />No sales in range</td></tr>}
            </tbody>
          </table>
        </Card>
      </div>
    </div>
  );
}
