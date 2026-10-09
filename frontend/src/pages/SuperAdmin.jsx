import React, { useCallback, useEffect, useState } from 'react';
import { Activity, Building2, RefreshCw, ShieldCheck, Store, Users, AlertTriangle, ExternalLink } from 'lucide-react';
import toast from 'react-hot-toast';
import api, { apiError } from '../services/api';

const unwrap = (data) => Array.isArray(data) ? data : (data?.results || []);

export default function SuperAdmin() {
  const [organizations, setOrganizations] = useState([]);
  const [branches, setBranches] = useState([]);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [errors, setErrors] = useState([]);

  const load = useCallback(async () => {
    setLoading(true);
    const nextErrors = [];
    const requests = await Promise.allSettled([
      api.get('/organizations/', { params: { page_size: 100 } }),
      api.get('/branches/', { params: { page_size: 100 } }),
      api.get('/users/', { params: { page_size: 100 } }),
    ]);
    const setters = [setOrganizations, setBranches, setUsers];
    const labels = ['organizations', 'branches', 'users'];
    requests.forEach((result, index) => {
      if (result.status === 'fulfilled') setters[index](unwrap(result.value.data));
      else {
        setters[index]([]);
        nextErrors.push(`Could not load ${labels[index]}: ${apiError(result.reason, 'request failed')}`);
      }
    });
    setErrors(nextErrors);
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const cards = [
    { label: 'Organizations', value: organizations.length, icon: Building2, detail: 'Businesses on ZenPOS' },
    { label: 'Branches', value: branches.length, icon: Store, detail: 'Locations returned by API' },
    { label: 'User accounts', value: users.length, icon: Users, detail: 'Accounts visible to this admin' },
    { label: 'Platform access', value: 'Enabled', icon: ShieldCheck, detail: 'Signed in as superuser' },
  ];

  return (
    <div className="page-shell space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="eyebrow">ZenPOS platform operations</div>
          <h1 className="page-title">Super Admin</h1>
          <p className="page-subtitle">Head Office control centre for organizations, branches and platform access.</p>
        </div>
        <button className="btn-secondary" onClick={load} disabled={loading}>
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} /> Refresh data
        </button>
      </div>

      {errors.length > 0 && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-200">
          <div className="mb-2 flex items-center gap-2 font-bold"><AlertTriangle size={17} /> Some platform data could not be loaded</div>
          {errors.map((error) => <p key={error}>{error}</p>)}
          <p className="mt-2 text-amber-100/70">Counts below show only successful API responses. Access is still enforced by the server.</p>
        </div>
      )}

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {cards.map(({ label, value, icon: Icon, detail }) => (
          <article key={label} className="panel p-5">
            <div className="flex items-start justify-between">
              <div><p className="text-sm text-slate-400">{label}</p><p className="mt-2 text-3xl font-black text-white">{loading ? '—' : value}</p></div>
              <div className="rounded-xl border border-slate-700 bg-slate-800/70 p-3 text-blue-300"><Icon size={20} /></div>
            </div>
            <p className="mt-3 text-xs text-slate-500">{detail}</p>
          </article>
        ))}
      </section>

      <section className="panel">
        <div className="panel-header">
          <div><h2 className="panel-title">Organizations</h2><p className="panel-subtitle">Businesses registered on the platform</p></div>
          <span className="rounded-lg border border-slate-700 px-3 py-1 text-xs text-slate-400">{organizations.length} loaded</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-800/40 text-[10px] uppercase tracking-widest text-slate-400">
              <tr><th className="p-4 text-left">Organization</th><th className="p-4 text-left">Slug</th><th className="p-4 text-left">Currency</th><th className="p-4 text-left">Timezone</th><th className="p-4 text-left">Status</th></tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {organizations.map((org) => (
                <tr key={org.id}>
                  <td className="p-4 font-semibold text-white">{org.name || 'Unnamed organization'}</td>
                  <td className="p-4 text-slate-400">{org.slug || '—'}</td>
                  <td className="p-4 text-slate-300">{org.currency || '—'}</td>
                  <td className="p-4 text-slate-400">{org.timezone || '—'}</td>
                  <td className="p-4"><span className="rounded-md border border-emerald-500/20 px-2 py-1 text-xs text-emerald-300">{org.is_active === false ? 'Inactive' : 'Active'}</span></td>
                </tr>
              ))}
              {!loading && organizations.length === 0 && (
                <tr><td colSpan={5} className="p-8 text-center text-slate-500">No organizations returned, or this endpoint is not available to this account.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <article className="panel p-5">
          <div className="flex items-center gap-3"><div className="rounded-lg bg-blue-500/10 p-2 text-blue-300"><Activity size={19} /></div><h2 className="panel-title">Platform operations</h2></div>
          <p className="mt-3 text-sm leading-6 text-slate-400">Use this view to monitor the organizations and accounts exposed by the platform API. Detailed audit logs and operational actions remain governed by backend permissions.</p>
        </article>
        <article className="panel p-5">
          <div className="flex items-center gap-3"><div className="rounded-lg bg-violet-500/10 p-2 text-violet-300"><ShieldCheck size={19} /></div><h2 className="panel-title">Security boundary</h2></div>
          <p className="mt-3 text-sm leading-6 text-slate-400">This console is only a navigation and monitoring surface. It does not grant privileges itself; Django must verify superuser status for every platform-level operation.</p>
          <a href="/admin/" target="_blank" rel="noreferrer" className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-blue-300 hover:text-blue-200">Open Django technical admin <ExternalLink size={14} /></a>
        </article>
      </section>
    </div>
  );
}
