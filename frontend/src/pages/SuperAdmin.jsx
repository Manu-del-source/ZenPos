import React, { useCallback, useEffect, useState } from 'react';
import { Activity, Building2, Plus, RefreshCw, ShieldCheck, Store, Users, AlertTriangle, ExternalLink, PowerOff, Power, X } from 'lucide-react';
import toast from 'react-hot-toast';
import api, { apiError } from '../services/api';

const unwrap = (data) => (Array.isArray(data) ? data : data?.results || []);

/** Field-level errors out of a DRF 400, as { field: "message" }. */
const fieldErrors = (error) => {
  const data = error?.response?.data;
  const out = {};
  if (data && typeof data === 'object' && !Array.isArray(data)) {
    for (const [key, value] of Object.entries(data)) {
      if (key === 'detail') continue;
      if (Array.isArray(value) && value.length) out[key] = String(value[0]);
      else if (typeof value === 'string') out[key] = value;
    }
  }
  return out;
};

const Field = ({ label, error, children, hint }) => (
  <div>
    <label className="mb-1 block text-xs font-bold uppercase tracking-wider text-slate-500">{label}</label>
    {children}
    {hint && !error && <p className="mt-1 text-[11px] text-slate-600">{hint}</p>}
    {error && <p className="mt-1 text-[11px] font-semibold text-red-400">{error}</p>}
  </div>
);

const EMPTY_FORM = {
  name: '',
  slug: '',
  currency: 'KES',
  timezone: 'Africa/Nairobi',
  branch_name: '',
  branch_code: '',
  admin_username: '',
  admin_password: '',
  admin_email: '',
};

const OnboardForm = ({ onClose, onCreated }) => {
  const [form, setForm] = useState(EMPTY_FORM);
  const [errors, setErrors] = useState({});
  const [saving, setSaving] = useState(false);

  const set = (key) => (event) => setForm({ ...form, [key]: event.target.value });

  const submit = async (event) => {
    event.preventDefault();
    setSaving(true);
    setErrors({});
    const payload = { ...form };
    Object.keys(payload).forEach((key) => { if (!payload[key]) delete payload[key]; });
    try {
      const { data } = await api.post('/platform/organizations/', payload);
      toast.success(`Organization "${data.name}" is live.`);
      onCreated();
    } catch (err) {
      const nextErrors = fieldErrors(err);
      setErrors(nextErrors);
      if (Object.keys(nextErrors).length === 0) {
        toast.error(apiError(err, 'Could not create the organization'));
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-black/70 p-4">
      <form onSubmit={submit} className="panel w-full max-w-2xl">
        <div className="panel-header">
          <div>
            <h2 className="panel-title">Open a new organization</h2>
            <p className="panel-subtitle">
              Creates the organization, its first branch and its first administrator
              in one audited transaction.
            </p>
          </div>
          <button type="button" className="btn-secondary !px-3" onClick={onClose}><X size={16} /></button>
        </div>
        <div className="grid grid-cols-2 gap-3 p-5">
          <Field label="Organization name" error={errors.name}>
            <input className="input" value={form.name} onChange={set('name')} required />
          </Field>
          <Field label="Slug" error={errors.slug} hint="Leave blank to derive it from the name.">
            <input className="input" value={form.slug} onChange={set('slug')} placeholder="savannah-traders" />
          </Field>
          <Field label="Currency (ISO 4217)" error={errors.currency}>
            <input className="input" value={form.currency} onChange={set('currency')} maxLength={3} />
          </Field>
          <Field label="Timezone" error={errors.timezone}>
            <input className="input" value={form.timezone} onChange={set('timezone')} />
          </Field>
          <Field label="First branch name" error={errors.branch_name}>
            <input className="input" value={form.branch_name} onChange={set('branch_name')} required />
          </Field>
          <Field label="First branch code" error={errors.branch_code}>
            <input className="input" value={form.branch_code} onChange={set('branch_code')} placeholder="NAK-001" required />
          </Field>
          <Field label="Administrator username" error={errors.admin_username}>
            <input className="input" value={form.admin_username} onChange={set('admin_username')} required />
          </Field>
          <Field label="Administrator password" error={errors.admin_password} hint="Minimum 10 characters, not a common password.">
            <input className="input" type="password" value={form.admin_password} onChange={set('admin_password')} required />
          </Field>
          <Field label="Administrator email (optional)" error={errors.admin_email}>
            <input className="input" type="email" value={form.admin_email} onChange={set('admin_email')} />
          </Field>
        </div>
        <div className="flex gap-2 border-t border-slate-800 px-5 py-4">
          <button type="button" className="btn-secondary flex-1" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn-primary flex-1" disabled={saving}>
            <Building2 size={16} />{saving ? 'Opening…' : 'Open organization'}
          </button>
        </div>
      </form>
    </div>
  );
};

export default function SuperAdmin() {
  const [organizations, setOrganizations] = useState([]);
  const [branches, setBranches] = useState([]);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [errors, setErrors] = useState([]);
  const [flipping, setFlipping] = useState(null);
  const [flippingBranch, setFlippingBranch] = useState(null);
  const [onboarding, setOnboarding] = useState(false);

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

  const flip = async (org, activate) => {
    if (!activate && !window.confirm(
      `Suspend "${org.name}"? Every account in that organization stops working `
      + 'immediately (login, refresh and all API calls) until the platform activates it again.',
    )) return;
    setFlipping(org.id);
    try {
      await api.post(`/platform/organizations/${org.id}/${activate ? 'activate' : 'suspend'}/`);
      toast.success(`${org.name} is now ${activate ? 'active' : 'suspended'}.`);
      await load();
    } catch (err) {
      toast.error(apiError(err, 'Could not change the organization status'));
    } finally {
      setFlipping(null);
    }
  };

  const setBranchActive = async (branch, activate) => {
    const action = activate ? 'reactivate' : 'deactivate';
    if (!window.confirm(
      `${activate ? 'Reactivate' : 'Deactivate'} "${branch.name}" (${branch.organization_name || 'business'})? `
      + 'Historical sales, stock, tills, and cash-session records will be retained.',
    )) return;
    setFlippingBranch(branch.id);
    try {
      if (activate) await api.patch(`/branches/${branch.id}/`, { is_active: true });
      else await api.delete(`/branches/${branch.id}/`);
      toast.success(`Branch "${branch.name}" ${activate ? 'reactivated' : 'deactivated'}.`);
      await load();
    } catch (error) {
      toast.error(apiError(error, `Could not ${action} branch`));
    } finally {
      setFlippingBranch(null);
    }
  };

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
          <p className="page-subtitle">Open, suspend and monitor the organizations on the platform.</p>
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
          <div className="flex items-center gap-3">
            <span className="rounded-lg border border-slate-700 px-3 py-1 text-xs text-slate-400">{organizations.length} loaded</span>
            <button className="btn-primary !py-2" onClick={() => setOnboarding(true)}>
              <Plus size={16} /> New organization
            </button>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-800/40 text-[10px] uppercase tracking-widest text-slate-400">
              <tr>
                <th className="p-4 text-left">Organization</th>
                <th className="p-4 text-left">Slug</th>
                <th className="p-4 text-left">Currency</th>
                <th className="p-4 text-left">Timezone</th>
                <th className="p-4 text-left">Status</th>
                <th className="p-4 text-right"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {organizations.map((org) => (
                <tr key={org.id}>
                  <td className="p-4 font-semibold text-white">{org.name || 'Unnamed organization'}</td>
                  <td className="p-4 text-slate-400">{org.slug || '—'}</td>
                  <td className="p-4 text-slate-300">{org.currency || '—'}</td>
                  <td className="p-4 text-slate-400">{org.timezone || '—'}</td>
                  <td className="p-4">
                    <span className={`rounded-md border px-2 py-1 text-xs ${org.is_active === false ? 'border-red-500/30 text-red-300' : 'border-emerald-500/20 text-emerald-300'}`}>
                      {org.is_active === false ? 'Suspended' : 'Active'}
                    </span>
                  </td>
                  <td className="p-4 text-right">
                    {org.is_active === false ? (
                      <button className="btn-secondary !py-1.5 !text-xs" disabled={flipping === org.id} onClick={() => flip(org, true)}>
                        <Power size={14} /> {flipping === org.id ? 'Working…' : 'Activate'}
                      </button>
                    ) : (
                      <button
                        className="rounded-lg border border-red-500/30 px-3 py-1.5 text-xs font-bold text-red-400 hover:bg-red-500/10 disabled:opacity-50"
                        disabled={flipping === org.id}
                        onClick={() => flip(org, false)}
                      >
                        <PowerOff size={14} className="mr-1 inline" />{flipping === org.id ? 'Working…' : 'Suspend'}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {!loading && organizations.length === 0 && (
                <tr><td colSpan={6} className="p-8 text-center text-slate-500">No organizations returned, or this endpoint is not available to this account.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <div><h2 className="panel-title">All branches</h2><p className="panel-subtitle">Platform-wide branch controls. Deactivation preserves historical records.</p></div>
          <span className="rounded-lg border border-slate-700 px-3 py-1 text-xs text-slate-400">{branches.length} loaded</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-sm">
            <thead className="bg-slate-800/40 text-[10px] uppercase tracking-widest text-slate-400">
              <tr><th className="p-4 text-left">Branch</th><th className="p-4 text-left">Business</th><th className="p-4 text-left">Code</th><th className="p-4 text-left">Status</th><th className="p-4 text-right">Action</th></tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {branches.map((branch) => (
                <tr key={branch.id}>
                  <td className="p-4 font-semibold text-white">{branch.name}</td>
                  <td className="p-4 text-slate-400">{branch.organization_name || branch.organization}</td>
                  <td className="p-4 text-slate-400">{branch.code}</td>
                  <td className="p-4"><span className={`rounded-md border px-2 py-1 text-xs ${branch.is_active ? 'border-emerald-500/20 text-emerald-300' : 'border-red-500/30 text-red-300'}`}>{branch.is_active ? 'Active' : 'Inactive'}</span></td>
                  <td className="p-4 text-right">
                    {branch.is_active ? (
                      <button className="rounded-lg border border-red-500/30 px-3 py-1.5 text-xs font-bold text-red-400 hover:bg-red-500/10 disabled:opacity-50" disabled={flippingBranch === branch.id} onClick={() => setBranchActive(branch, false)}>
                        <PowerOff size={14} className="mr-1 inline" />{flippingBranch === branch.id ? 'Working…' : 'Deactivate'}
                      </button>
                    ) : (
                      <button className="btn-secondary !py-1.5 !text-xs" disabled={flippingBranch === branch.id} onClick={() => setBranchActive(branch, true)}>
                        <Power size={14} />{flippingBranch === branch.id ? 'Working…' : 'Reactivate'}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {!loading && branches.length === 0 && <tr><td colSpan={5} className="p-8 text-center text-slate-500">No branches returned.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <article className="panel p-5">
          <div className="flex items-center gap-3"><div className="rounded-lg bg-blue-500/10 p-2 text-blue-300"><Activity size={19} /></div><h2 className="panel-title">Platform operations</h2></div>
          <p className="mt-3 text-sm leading-6 text-slate-400">
            Opening an organization creates it with its first branch and its first
            administrator in one audited transaction. Suspending cuts the tenant off
            at login, refresh and every API call immediately; activating puts it
            back. Both actions are recorded in the audit log with you as the actor.
          </p>
        </article>
        <article className="panel p-5">
          <div className="flex items-center gap-3"><div className="rounded-lg bg-violet-500/10 p-2 text-violet-300"><ShieldCheck size={19} /></div><h2 className="panel-title">Security boundary</h2></div>
          <p className="mt-3 text-sm leading-6 text-slate-400">
            These actions exist only for superuser accounts — the platform routes
            refuse every other caller, even a tenant administrator holding every
            tenant permission. This console is a navigation surface; Django verifies
            superuser status for every platform-level operation.
          </p>
          <a href="/admin/" target="_blank" rel="noreferrer" className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-blue-300 hover:text-blue-200">Open Django technical admin <ExternalLink size={14} /></a>
        </article>
      </section>

      {onboarding && <OnboardForm onClose={() => setOnboarding(false)} onCreated={() => { setOnboarding(false); load(); }} />}
    </div>
  );
}
