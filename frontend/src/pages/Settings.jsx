import React, { useCallback, useEffect, useState } from 'react';
import { Building2, LogOut, Plus, ShieldCheck, Store, UserRound, X } from 'lucide-react';
import toast from 'react-hot-toast';
import api, { apiError, logout } from '../services/api';

export default function Settings() {
  let user = {};
  try { user = JSON.parse(localStorage.getItem('user') || '{}'); } catch { /* ignore */ }
  const organization = user?.organization_name || user?.organization?.name || 'ZenPOS Store';
  const canManage = user?.is_superuser || (Array.isArray(user?.permissions) && user.permissions.includes('branches.manage'));

  const [branches, setBranches] = useState([]);
  const [users, setUsers] = useState([]);
  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const { data } = await api.get('/branches/', { params: { page_size: 100 } });
      setBranches(Array.isArray(data) ? data : data.results || []);
    } catch (err) {
      toast.error(apiError(err, 'Could not load branches'));
    }
    try {
      const { data } = await api.get('/users/', { params: { page_size: 100 } });
      setUsers(Array.isArray(data) ? data : data.results || []);
    } catch { /* view-only users may 403 */ }
  }, []);

  useEffect(() => { load(); }, [load]);

  const saveBranch = async (event) => {
    event.preventDefault();
    if (!form.name.trim() || !form.code.trim()) return toast.error('Name and code are required.');
    setSaving(true);
    const payload = {
      name: form.name.trim(),
      code: form.code.trim(),
      address: form.address || '',
      phone: form.phone || '',
      timezone: form.timezone || 'Africa/Nairobi',
      manager: form.manager || null,
      is_active: form.is_active !== false,
    };
    try {
      if (form.id) await api.patch(`/branches/${form.id}/`, payload);
      else await api.post('/branches/', payload);
      toast.success(form.id ? 'Branch updated' : 'Branch created');
      setForm(null);
      await load();
    } catch (err) {
      toast.error(apiError(err, 'Could not save branch'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="page-shell">
      <div>
        <div className="eyebrow">Workspace configuration</div>
        <h1 className="page-title">Settings</h1>
        <p className="page-subtitle">Organization, branches and the account on this terminal.</p>
      </div>

      <div className="mt-6 grid gap-5 lg:grid-cols-2">
        <section className="panel">
          <div className="panel-header">
            <div><h2 className="panel-title">Workspace</h2><p className="panel-subtitle">Current organization context</p></div>
            <Building2 size={18} className="text-blue-400" />
          </div>
          <div className="space-y-4 p-5">
            <div className="rounded-xl border border-slate-800 bg-slate-950 p-4"><p className="text-xs uppercase tracking-wider text-slate-500">Organization</p><p className="mt-1 font-semibold text-white">{organization}</p></div>
            <div className="rounded-xl border border-slate-800 bg-slate-950 p-4"><p className="text-xs uppercase tracking-wider text-slate-500">Currency</p><p className="mt-1 font-semibold text-white">KES — Kenyan Shilling</p></div>
            <div className="rounded-xl border border-slate-800 bg-slate-950 p-4"><p className="text-xs uppercase tracking-wider text-slate-500">Timezone</p><p className="mt-1 font-semibold text-white">Africa/Nairobi</p></div>
          </div>
        </section>
        <section className="panel">
          <div className="panel-header">
            <div><h2 className="panel-title">Your account</h2><p className="panel-subtitle">Signed-in staff identity</p></div>
            <UserRound size={18} className="text-violet-400" />
          </div>
          <div className="space-y-4 p-5">
            <div className="flex items-center gap-3 rounded-xl border border-slate-800 bg-slate-950 p-4">
              <div className="grid h-10 w-10 place-items-center rounded-full bg-slate-800 font-bold text-blue-400">{(user?.username || 'U').slice(0, 1).toUpperCase()}</div>
              <div>
                <p className="font-semibold text-white">{user?.username || 'User'}</p>
                <p className="text-xs text-slate-500">{(user?.roles || []).join(', ') || (user?.is_superuser ? 'Administrator' : 'Staff account')}</p>
              </div>
            </div>
            <div className="flex items-center gap-3 rounded-xl border border-slate-800 bg-slate-950 p-4">
              <ShieldCheck size={18} className="text-emerald-400" />
              <div><p className="font-semibold text-slate-200">Authenticated</p><p className="text-xs text-slate-500">JWT session is active on this device.</p></div>
            </div>
            <button className="btn-secondary w-full !border-red-500/20 !text-red-400 hover:!bg-red-500/10" onClick={() => logout()}><LogOut size={17} /> Sign out</button>
          </div>
        </section>
      </div>

      <section className="panel mt-5">
        <div className="panel-header">
          <div>
            <h2 className="panel-title">Branches</h2>
            <p className="panel-subtitle">Shops this organization operates. Deactivate a branch instead of deleting it.</p>
          </div>
          {canManage && (
            <button className="btn-primary !py-2" onClick={() => setForm({ name: '', code: '', address: '', phone: '', timezone: 'Africa/Nairobi', manager: '', is_active: true })}>
              <Plus size={16} /> New branch
            </button>
          )}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-800/40 text-slate-400 text-[10px] uppercase tracking-widest">
              <tr>
                <th className="p-4 text-left">Branch</th>
                <th className="p-4 text-left">Code</th>
                <th className="p-4 text-left">Phone</th>
                <th className="p-4 text-left">Manager</th>
                <th className="p-4 text-center">Status</th>
                {canManage && <th className="p-4"></th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {branches.map((b) => (
                <tr key={b.id}>
                  <td className="p-4 text-white font-semibold"><Store size={14} className="inline mr-2 text-slate-500" />{b.name}</td>
                  <td className="p-4 text-slate-300">{b.code}</td>
                  <td className="p-4 text-slate-400">{b.phone || '—'}</td>
                  <td className="p-4 text-slate-300">{b.manager_name || '—'}</td>
                  <td className="p-4 text-center">
                    <span className={`px-2 py-0.5 rounded-lg text-[10px] font-bold uppercase border ${b.is_active ? 'text-green-400 border-green-500/20' : 'text-slate-500 border-slate-700'}`}>
                      {b.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  {canManage && (
                    <td className="p-4 text-right">
                      <button className="px-3 py-2 bg-slate-800 rounded-lg text-xs font-bold text-slate-300" onClick={() => setForm({ ...b, manager: b.manager || '' })}>Edit</button>
                    </td>
                  )}
                </tr>
              ))}
              {branches.length === 0 && (
                <tr><td className="p-8 text-center text-slate-500" colSpan={6}>No branches yet</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {form && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4">
          <form onSubmit={saveBranch} className="panel w-full max-w-lg">
            <div className="panel-header">
              <h2 className="panel-title">{form.id ? 'Edit branch' : 'New branch'}</h2>
              <button type="button" className="btn-secondary !px-3" onClick={() => setForm(null)}><X size={16} /></button>
            </div>
            <div className="p-5 grid grid-cols-2 gap-3">
              <input className="input col-span-2" placeholder="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
              <input className="input" placeholder="Code" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} required />
              <input className="input" placeholder="Phone" value={form.phone || ''} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
              <input className="input col-span-2" placeholder="Address" value={form.address || ''} onChange={(e) => setForm({ ...form, address: e.target.value })} />
              <input className="input" placeholder="Timezone" value={form.timezone || 'Africa/Nairobi'} onChange={(e) => setForm({ ...form, timezone: e.target.value })} />
              <select className="input" value={form.manager || ''} onChange={(e) => setForm({ ...form, manager: e.target.value })}>
                <option value="">Manager…</option>
                {users.map((u) => <option key={u.id} value={u.id}>{u.username}</option>)}
              </select>
              <label className="col-span-2 flex items-center gap-2 text-sm text-slate-300">
                <input type="checkbox" checked={form.is_active !== false} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} /> Active
              </label>
            </div>
            <div className="px-5 pb-5 flex gap-2">
              <button type="button" className="btn-secondary flex-1" onClick={() => setForm(null)}>Cancel</button>
              <button type="submit" className="btn-primary flex-1" disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
