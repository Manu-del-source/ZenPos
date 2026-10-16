import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { KeyRound, Plus, RefreshCw, ShieldCheck, Users, X } from 'lucide-react';
import toast from 'react-hot-toast';
import api, { apiError } from '../services/api';

const unwrap = (data) => (Array.isArray(data) ? data : data?.results || []);
const EMPTY = {
  username: '',
  email: '',
  first_name: '',
  last_name: '',
  password: '',
  role: 'CASHIER',
  branches: [],
};

export default function AccessManagement() {
  const [users, setUsers] = useState([]);
  const [roles, setRoles] = useState([]);
  const [branches, setBranches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState(null);
  const [query, setQuery] = useState('');
  const [caller, setCaller] = useState({});

  useEffect(() => {
    try { setCaller(JSON.parse(localStorage.getItem('user') || '{}') || {}); } catch { setCaller({}); }
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [u, r, b] = await Promise.all([
        api.get('/users/', { params: { page_size: 100 } }),
        api.get('/roles/', { params: { page_size: 100 } }),
        api.get('/branches/', { params: { page_size: 100 } }),
      ]);
      setUsers(unwrap(u.data));
      setRoles(unwrap(r.data));
      setBranches(unwrap(b.data).filter((branch) => branch.is_active !== false));
    } catch (error) {
      toast.error(apiError(error, 'Could not load staff access.'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const limitedHr = (caller.roles || []).includes('HR_MANAGER')
    && !(caller.roles || []).includes('ADMIN')
    && !caller.is_superuser;
  const availableRoles = useMemo(() => {
    const hrAllowed = new Set(['MANAGER', 'CASHIER', 'SUPERVISOR', 'INVENTORY_MANAGER', 'ACCOUNTANT']);
    return roles.filter((role) => !limitedHr || (role.is_system && hrAllowed.has(role.name)))
      .filter((role) => role.name !== 'SUPER_ADMIN');
  }, [roles, limitedHr]);

  const filteredUsers = useMemo(() => {
    const value = query.trim().toLowerCase();
    if (!value) return users;
    return users.filter((user) =>
      [user.username, user.email, user.first_name, user.last_name, ...(user.roles || [])]
        .filter(Boolean).some((part) => String(part).toLowerCase().includes(value)),
    );
  }, [users, query]);

  const setField = (key, value) => setForm((current) => ({ ...current, [key]: value }));
  const toggleBranch = (branchId) => setForm((current) => ({
    ...current,
    branches: current.branches.includes(branchId)
      ? current.branches.filter((id) => id !== branchId)
      : [...current.branches, branchId],
  }));

  const submit = async (event) => {
    event.preventDefault();
    if (!form) return;
    if (!form.username.trim() || !form.password) return toast.error('Username and temporary password are required.');
    if (!form.role) return toast.error('Choose an access role.');
    if (!form.branches.length) return toast.error('Select at least one branch for this account.');
    setSaving(true);
    let createdUser = null;
    try {
      const created = await api.post('/users/', {
        username: form.username.trim(),
        email: form.email.trim(),
        first_name: form.first_name.trim(),
        last_name: form.last_name.trim(),
        password: form.password,
      });
      createdUser = created.data;
      // Keep the new account roleless until branch access is safely configured.
      await api.post(`/users/${createdUser.id}/set-branch-access/`, {
        branches: form.branches.map((branch) => ({ branch, is_default: branch === form.branches[0] })),
      });
      await api.post(`/users/${createdUser.id}/set-roles/`, {
        roles: form.branches.map((branch) => ({ role: form.role, branch })),
      });
      toast.success(`Login access created for ${createdUser.username}.`);
      setForm(null);
      await load();
    } catch (error) {
      const message = apiError(error, 'Could not finish granting access.');
      if (createdUser) {
        toast.error(`Account ${createdUser.username} was created but access setup did not finish. Keep it unassigned and retry after checking the account.`);
      } else {
        toast.error(message);
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mx-auto min-h-screen max-w-7xl p-4 sm:p-6 lg:p-8">
      <div className="mb-8 flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="mb-2 flex items-center gap-2 text-sm font-bold text-[#FF5938]">
            <ShieldCheck size={17} /> ACCESS CONTROL
          </div>
          <h1 className="text-3xl font-black tracking-tight text-[#171715]">Staff access</h1>
          <p className="mt-2 max-w-2xl text-sm text-slate-500">
            Create login accounts, assign an approved role, and limit each person to the branches where they work.
          </p>
        </div>
        <button className="btn-primary" onClick={() => setForm({ ...EMPTY, role: availableRoles.some((role) => role.name === 'CASHIER') ? 'CASHIER' : availableRoles[0]?.name || '' , branches: branches[0] ? [branches[0].id] : [] })}>
          <Plus size={16} /> Grant access
        </button>
      </div>

      <div className="mb-5 flex flex-wrap items-center gap-3">
        <div className="relative min-w-[220px] flex-1">
          <Users className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-500" size={18} />
          <input className="input w-full pl-11" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search users, email, or role..." />
        </div>
        <button className="btn-secondary" onClick={load} disabled={loading}><RefreshCw size={15} className={loading ? 'animate-spin' : ''} /> Refresh</button>
      </div>

      <section className="panel overflow-hidden">
        <div className="panel-header">
          <div><h2 className="panel-title">Login accounts</h2><p className="panel-subtitle">Access is enforced by the API, not just by the screens shown here.</p></div>
          <span className="rounded-full border border-slate-700 px-3 py-1 text-xs font-bold text-slate-400">{filteredUsers.length} users</span>
        </div>
        {loading ? (
          <div className="p-10 text-center text-sm text-slate-500">Loading staff accounts...</div>
        ) : filteredUsers.length === 0 ? (
          <div className="p-10 text-center"><Users className="mx-auto mb-3 text-slate-600" size={30} /><p className="font-bold text-slate-300">No accounts found</p><p className="mt-1 text-sm text-slate-500">Create a login for an employee to give them access to ZenPOS.</p></div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead className="bg-slate-900/70 text-[11px] uppercase tracking-wider text-slate-500">
                <tr><th className="px-5 py-3">Account</th><th className="px-5 py-3">Assigned roles</th><th className="px-5 py-3">Branch access</th><th className="px-5 py-3">Status</th></tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {filteredUsers.map((user) => (
                  <tr key={user.id} className="hover:bg-slate-900/40">
                    <td className="px-5 py-4">
                      <div className="font-bold text-slate-200">{[user.first_name, user.last_name].filter(Boolean).join(' ') || user.username}</div>
                      <div className="mt-1 text-xs text-slate-500">@{user.username}{user.email ? ` · ${user.email}` : ''}</div>
                    </td>
                    <td className="px-5 py-4"><div className="flex flex-wrap gap-1.5">{(user.roles || []).length ? user.roles.map((role) => <span key={role} className="rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-300">{role}</span>) : <span className="text-xs text-amber-400">No role assigned</span>}</div></td>
                    <td className="px-5 py-4 text-slate-400">{(user.branch_ids || []).length ? `${user.branch_ids.length} branch(es)` : 'Organization-wide'}</td>
                    <td className="px-5 py-4"><span className={`rounded-full px-2.5 py-1 text-xs font-bold ${user.is_active ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'}`}>{user.is_active ? 'Active' : 'Inactive'}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {form && (
        <div className="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-black/70 p-4">
          <form onSubmit={submit} className="panel my-6 w-full max-w-2xl">
            <div className="panel-header">
              <div><h2 className="panel-title">Grant login access</h2><p className="panel-subtitle">Create a separate account for one staff member. Never share your owner login.</p></div>
              <button type="button" className="btn-secondary !px-3" onClick={() => setForm(null)}><X size={16} /></button>
            </div>
            <div className="grid gap-4 p-5 sm:grid-cols-2">
              <label className="text-xs font-bold uppercase tracking-wider text-slate-500">Username<input className="input mt-2" value={form.username} onChange={(event) => setField('username', event.target.value)} required autoComplete="off" /></label>
              <label className="text-xs font-bold uppercase tracking-wider text-slate-500">Email (optional)<input className="input mt-2" type="email" value={form.email} onChange={(event) => setField('email', event.target.value)} autoComplete="off" /></label>
              <label className="text-xs font-bold uppercase tracking-wider text-slate-500">First name<input className="input mt-2" value={form.first_name} onChange={(event) => setField('first_name', event.target.value)} /></label>
              <label className="text-xs font-bold uppercase tracking-wider text-slate-500">Last name<input className="input mt-2" value={form.last_name} onChange={(event) => setField('last_name', event.target.value)} /></label>
              <label className="text-xs font-bold uppercase tracking-wider text-slate-500 sm:col-span-2">Temporary password<input className="input mt-2" type="password" minLength={8} value={form.password} onChange={(event) => setField('password', event.target.value)} required autoComplete="new-password" /><span className="mt-1 block text-[11px] font-normal normal-case tracking-normal text-slate-600">Share this privately with the employee. Password reset is available to authorized managers.</span></label>
              <label className="text-xs font-bold uppercase tracking-wider text-slate-500 sm:col-span-2">Role<select className="input mt-2" value={form.role} onChange={(event) => setField('role', event.target.value)} required>{availableRoles.map((role) => <option key={role.id} value={role.name}>{role.name.replaceAll('_', ' ')} — {role.description}</option>)}</select>{form.role === 'MANAGER' && <span className="mt-2 block text-xs font-normal normal-case tracking-normal text-amber-600">Manager permissions will apply only to the branch or branches selected below. The manager cannot manage unassigned branches.</span>}</label>
              <div className="sm:col-span-2">
                <div className="mb-2 text-xs font-bold uppercase tracking-wider text-slate-500">Allowed branches</div>
                {branches.length ? <div className="grid gap-2 sm:grid-cols-2">{branches.map((branch) => <label key={branch.id} className="flex items-center gap-3 rounded-lg border border-slate-800 bg-slate-900/50 p-3 text-sm text-slate-300"><input type="checkbox" checked={form.branches.includes(branch.id)} onChange={() => toggleBranch(branch.id)} /><span>{branch.name}<span className="ml-2 text-xs text-slate-600">{branch.code}</span></span></label>)}</div> : <p className="text-sm text-amber-400">Create a branch before granting staff access.</p>}
                <p className="mt-2 text-[11px] text-slate-600">Select at least one branch. Users are not given organization-wide branch access by default.</p>
              </div>
            </div>
            <div className="flex justify-end gap-3 border-t border-slate-800 p-5">
              <button type="button" className="btn-secondary" onClick={() => setForm(null)} disabled={saving}>Cancel</button>
              <button type="submit" className="btn-primary" disabled={saving || !branches.length}>{saving ? 'Creating access...' : <><KeyRound size={15} /> Create login access</>}</button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
