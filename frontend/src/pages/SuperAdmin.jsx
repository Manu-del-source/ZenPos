import React, { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, Building2, ChevronLeft, ChevronRight, Copy, HeartPulse, Loader2, Plus, RefreshCw, ScrollText, Search, ShieldCheck, Store, Users, X } from 'lucide-react';
import toast from 'react-hot-toast';
import api, { apiError } from '../services/api';

/**
 * Platform console. Every figure and action here comes from `/api/v2/platform/*`,
 * which the backend restricts to active platform administrators. The route guard
 * in App.jsx only decides what to render; it is not the security boundary.
 */

const TABS = [
  { id: 'overview', label: 'Overview', icon: ShieldCheck },
  { id: 'organizations', label: 'Organizations', icon: Building2 },
  { id: 'branches', label: 'Branches', icon: Store },
  { id: 'users', label: 'Platform users', icon: Users },
  { id: 'audit', label: 'Audit logs', icon: ScrollText },
  { id: 'health', label: 'System health', icon: HeartPulse },
];

const fmt = (value) => (value ? new Date(value).toLocaleString('en-KE') : '—');

/** Paged, searchable, filterable list backed by one platform endpoint. */
function useList(path, initialFilters = {}) {
  const [rows, setRows] = useState([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [debounced, setDebounced] = useState('');
  const [filters, setFilters] = useState(initialFilters);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const pageSize = 20;

  useEffect(() => {
    const timer = setTimeout(() => { setDebounced(search); setPage(1); }, 300);
    return () => clearTimeout(timer);
  }, [search]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    const params = { page, page_size: pageSize };
    if (debounced) params.search = debounced;
    Object.entries(filters).forEach(([key, value]) => { if (value !== '' && value != null) params[key] = value; });
    try {
      const { data } = await api.get(path, { params });
      setRows(data.results || []);
      setCount(data.count || 0);
    } catch (err) {
      setRows([]);
      setCount(0);
      setError(apiError(err, 'Could not load this list.'));
    } finally {
      setLoading(false);
    }
  }, [path, page, debounced, filters]);

  useEffect(() => { load(); }, [load]);

  const setFilter = (key, value) => { setFilters((prev) => ({ ...prev, [key]: value })); setPage(1); };
  return { rows, count, page, setPage, search, setSearch, filters, setFilter, loading, error, reload: load, pages: Math.max(1, Math.ceil(count / pageSize)) };
}

function Toolbar({ list, placeholder, children, action }) {
  return (
    <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center">
      <div className="relative flex-1">
        <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
        <input className="input !py-2 pl-9" placeholder={placeholder} value={list.search} onChange={(e) => list.setSearch(e.target.value)} />
      </div>
      {children}
      <button className="btn-secondary !py-2" onClick={list.reload} disabled={list.loading} aria-label="Refresh">
        <RefreshCw size={15} className={list.loading ? 'animate-spin' : ''} />
      </button>
      {action}
    </div>
  );
}

function Select({ value, onChange, options, label }) {
  return (
    <select className="input !w-auto !py-2" value={value} onChange={(e) => onChange(e.target.value)} aria-label={label}>
      {options.map(([val, text]) => <option key={val} value={val}>{text}</option>)}
    </select>
  );
}

function DataTable({ list, columns, empty }) {
  return (
    <div className="overflow-hidden rounded-xl border border-slate-800">
      {list.error && (
        <div className="flex items-center gap-2 border-b border-red-500/20 bg-red-500/10 px-4 py-2 text-sm text-red-300">
          <AlertTriangle size={15} /> {list.error}
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-900 text-xs uppercase tracking-wide text-slate-500">
            <tr>{columns.map((c) => <th key={c.key} className="whitespace-nowrap px-3 py-2 font-semibold">{c.label}</th>)}</tr>
          </thead>
          <tbody className="divide-y divide-slate-800/70">
            {list.loading && list.rows.length === 0 && (
              <tr><td colSpan={columns.length} className="px-3 py-8 text-center text-slate-500"><Loader2 className="mx-auto animate-spin" size={18} /></td></tr>
            )}
            {!list.loading && !list.error && list.rows.length === 0 && (
              <tr><td colSpan={columns.length} className="px-3 py-8 text-center text-slate-500">{empty}</td></tr>
            )}
            {list.rows.map((row) => (
              <tr key={row.id} className="hover:bg-slate-900/60">
                {columns.map((c) => <td key={c.key} className="whitespace-nowrap px-3 py-2 text-slate-300">{c.render ? c.render(row) : row[c.key] ?? '—'}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between border-t border-slate-800 bg-slate-900/60 px-3 py-2 text-xs text-slate-500">
        <span>{list.count} record{list.count === 1 ? '' : 's'}</span>
        <div className="flex items-center gap-2">
          <button className="rounded p-1 hover:bg-slate-800 disabled:opacity-30" disabled={list.page <= 1} onClick={() => list.setPage(list.page - 1)} aria-label="Previous page"><ChevronLeft size={16} /></button>
          <span>Page {list.page} of {list.pages}</span>
          <button className="rounded p-1 hover:bg-slate-800 disabled:opacity-30" disabled={list.page >= list.pages} onClick={() => list.setPage(list.page + 1)} aria-label="Next page"><ChevronRight size={16} /></button>
        </div>
      </div>
    </div>
  );
}

const Badge = ({ on, yes = 'Active', no = 'Inactive' }) => (
  <span className={`rounded-full border px-2 py-0.5 text-xs font-semibold ${on ? 'border-green-500/20 bg-green-500/10 text-green-400' : 'border-slate-700 bg-slate-800 text-slate-400'}`}>{on ? yes : no}</span>
);

function Modal({ title, onClose, children }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" role="dialog" aria-modal="true">
      <div className="w-full max-w-md rounded-2xl border border-slate-800 bg-slate-950 p-5 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-bold text-white">{title}</h2>
          <button onClick={onClose} className="rounded p-1 text-slate-400 hover:bg-slate-800" aria-label="Close"><X size={16} /></button>
        </div>
        {children}
      </div>
    </div>
  );
}

/** Destructive or privilege-changing actions always pass through here. */
function Confirm({ title, message, confirmLabel, onConfirm, onClose }) {
  const [busy, setBusy] = useState(false);
  const run = async () => { setBusy(true); try { await onConfirm(); onClose(); } finally { setBusy(false); } };
  return (
    <Modal title={title} onClose={onClose}>
      <p className="mb-5 text-sm text-slate-400">{message}</p>
      <div className="flex justify-end gap-2">
        <button className="btn-secondary !py-2" onClick={onClose}>Cancel</button>
        <button className="btn-primary !bg-red-600 !py-2 hover:!bg-red-500" onClick={run} disabled={busy}>{busy ? 'Working…' : confirmLabel}</button>
      </div>
    </Modal>
  );
}

function Field({ label, error, children }) {
  return (
    <label className="mb-3 block text-sm">
      <span className="mb-1 block font-semibold text-slate-400">{label}</span>
      {children}
      {error && <span className="mt-1 block text-xs text-red-400">{error}</span>}
    </label>
  );
}

/** Generic create form: posts to `path`, shows server validation inline. */
function CreateForm({ title, path, fields, initial, onDone, onClose, transform }) {
  const [form, setForm] = useState(initial);
  const [errors, setErrors] = useState({});
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setErrors({});
    try {
      const { data } = await api.post(path, transform ? transform(form) : form);
      onDone(data);
    } catch (err) {
      const body = err?.response?.data;
      if (body && typeof body === 'object' && !body.detail) {
        setErrors(Object.fromEntries(Object.entries(body).map(([k, v]) => [k, Array.isArray(v) ? v[0] : String(v)])));
      } else {
        toast.error(apiError(err, 'Could not save.'));
      }
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal title={title} onClose={onClose}>
      <form onSubmit={submit}>
        {fields.map((f) => (
          <Field key={f.name} label={f.label} error={errors[f.name]}>
            {f.options ? (
              <select className="input !py-2" value={form[f.name]} onChange={(e) => setForm({ ...form, [f.name]: e.target.value })} required={f.required}>
                <option value="">Select…</option>
                {f.options.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
              </select>
            ) : (
              <input className="input !py-2" type={f.type || 'text'} value={form[f.name]} required={f.required} onChange={(e) => setForm({ ...form, [f.name]: e.target.value })} />
            )}
          </Field>
        ))}
        <div className="mt-4 flex justify-end gap-2">
          <button type="button" className="btn-secondary !py-2" onClick={onClose}>Cancel</button>
          <button className="btn-primary !py-2" disabled={busy}>{busy ? 'Saving…' : 'Save'}</button>
        </div>
      </form>
    </Modal>
  );
}

const ACTIVE_FILTER = [['', 'All statuses'], ['true', 'Active'], ['false', 'Inactive']];

/** Organization options for forms and filters; loaded once per tab that needs them. */
function useOrgOptions() {
  const [orgs, setOrgs] = useState([]);
  useEffect(() => {
    api.get('/platform/organizations/', { params: { page_size: 200 } })
      .then(({ data }) => setOrgs((data.results || []).map((o) => [o.id, o.name])))
      .catch(() => setOrgs([]));
  }, []);
  return orgs;
}

function Overview() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const load = useCallback(() => {
    setError(null);
    api.get('/platform/overview/').then(({ data: d }) => setData(d)).catch((e) => setError(apiError(e, 'Could not load overview.')));
  }, []);
  useEffect(() => { load(); }, [load]);
  if (error) return <div className="rounded-xl border border-red-500/20 bg-red-500/10 p-4 text-sm text-red-300">{error}</div>;
  if (!data) return <Loader2 className="animate-spin text-slate-500" />;
  const cards = [
    ['Organizations', `${data.organizations.active} active`, `${data.organizations.total} total`],
    ['Branches', `${data.branches.active} active`, `${data.branches.total} total`],
    ['User accounts', `${data.users.active} active`, `${data.users.total} total`],
    ['Platform administrators', `${data.users.platform_admins}`, 'active accounts'],
    ['Audit events (24h)', `${data.audit.events_24h}`, 'recorded actions'],
    ['Failed sign-ins (24h)', `${data.audit.failed_logins_24h}`, 'login failures'],
  ];
  return (
    <div>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
        {cards.map(([label, value, sub]) => (
          <div key={label} className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</div>
            <div className="mt-1 text-2xl font-black text-white">{value}</div>
            <div className="text-xs text-slate-500">{sub}</div>
          </div>
        ))}
      </div>
      <p className="mt-3 text-xs text-slate-600">Counted from the database at {fmt(data.generated_at)}.</p>
    </div>
  );
}

function Organizations() {
  const list = useList('/platform/organizations/', { is_active: '' });
  const [creating, setCreating] = useState(false);
  const [owner, setOwner] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [invite, setInvite] = useState(null);

  const setActive = (org, value) => api.patch(`/platform/organizations/${org.id}/`, { is_active: value })
    .then(() => { toast.success(`${org.name} ${value ? 'activated' : 'deactivated'}`); list.reload(); })
    .catch((e) => { toast.error(apiError(e)); throw e; });

  const columns = [
    { key: 'name', label: 'Organization', render: (o) => <span className="font-semibold text-white">{o.name}</span> },
    { key: 'slug', label: 'Slug' },
    { key: 'branch_count', label: 'Branches' },
    { key: 'user_count', label: 'Users' },
    { key: 'currency', label: 'Currency' },
    { key: 'is_active', label: 'Status', render: (o) => <Badge on={o.is_active} /> },
    { key: 'created_at', label: 'Created', render: (o) => fmt(o.created_at) },
    {
      key: 'actions', label: '', render: (o) => (
        <div className="flex gap-2">
          <button className="text-xs font-semibold text-blue-400 hover:underline" onClick={() => setOwner(o)}>Invite owner</button>
          {o.is_active ? (
            <button className="text-xs font-semibold text-red-400 hover:underline" onClick={() => setConfirm({
              title: `Deactivate ${o.name}?`,
              message: 'All staff of this organization will immediately lose access to the POS and API. Data is kept and the organization can be reactivated.',
              label: 'Deactivate', run: () => setActive(o, false),
            })}>Deactivate</button>
          ) : (
            <button className="text-xs font-semibold text-green-400 hover:underline" onClick={() => setActive(o, true)}>Activate</button>
          )}
        </div>
      ),
    },
  ];

  return (
    <div>
      <Toolbar list={list} placeholder="Search name or slug" action={<button className="btn-primary !py-2" onClick={() => setCreating(true)}><Plus size={15} /> New</button>}>
        <Select label="Status" value={list.filters.is_active} onChange={(v) => list.setFilter('is_active', v)} options={ACTIVE_FILTER} />
      </Toolbar>
      <DataTable list={list} columns={columns} empty="No organizations match." />
      {creating && (
        <CreateForm title="New organization" path="/platform/organizations/" onClose={() => setCreating(false)}
          initial={{ name: '', slug: '', currency: 'KES', timezone: 'Africa/Nairobi' }}
          fields={[{ name: 'name', label: 'Name', required: true }, { name: 'slug', label: 'Slug (URL-safe)', required: true }, { name: 'currency', label: 'Currency (ISO)', required: true }, { name: 'timezone', label: 'Timezone', required: true }]}
          onDone={() => { toast.success('Organization created'); setCreating(false); list.reload(); }} />
      )}
      {owner && (
        <CreateForm title={`Invite owner — ${owner.name}`} path="/platform/owners/" onClose={() => setOwner(null)}
          initial={{ organization: owner.id, username: '', email: '', first_name: '', last_name: '' }}
          fields={[{ name: 'username', label: 'Username', required: true }, { name: 'email', label: 'Email', type: 'email', required: true }, { name: 'first_name', label: 'First name' }, { name: 'last_name', label: 'Last name' }]}
          onDone={(data) => { setOwner(null); setInvite(data.invite); list.reload(); }} />
      )}
      {invite && (
        <Modal title="Owner invite" onClose={() => setInvite(null)}>
          <p className="mb-3 text-sm text-amber-300">{invite.note} It will not be shown again.</p>
          <div className="break-all rounded-lg bg-slate-900 p-3 font-mono text-xs text-slate-300">{`${window.location.origin}/accept-invite?uid=${invite.uid}&token=${invite.token}`}</div>
          <button className="btn-secondary mt-3 !py-2" onClick={() => { navigator.clipboard?.writeText(`${window.location.origin}/accept-invite?uid=${invite.uid}&token=${invite.token}`); toast.success('Copied'); }}><Copy size={14} /> Copy link</button>
        </Modal>
      )}
      {confirm && <Confirm title={confirm.title} message={confirm.message} confirmLabel={confirm.label} onConfirm={confirm.run} onClose={() => setConfirm(null)} />}
    </div>
  );
}

function Branches() {
  const orgs = useOrgOptions();
  const list = useList('/platform/branches/', { organization: '', is_active: '' });
  const [creating, setCreating] = useState(false);
  const [confirm, setConfirm] = useState(null);
  const setActive = (b, value) => api.patch(`/platform/branches/${b.id}/`, { is_active: value })
    .then(() => { toast.success(`${b.name} ${value ? 'activated' : 'deactivated'}`); list.reload(); })
    .catch((e) => { toast.error(apiError(e)); throw e; });
  const columns = [
    { key: 'name', label: 'Branch', render: (b) => <span className="font-semibold text-white">{b.name}</span> },
    { key: 'code', label: 'Code' },
    { key: 'organization_name', label: 'Organization' },
    { key: 'phone', label: 'Phone' },
    { key: 'is_active', label: 'Status', render: (b) => <Badge on={b.is_active} /> },
    {
      key: 'actions', label: '', render: (b) => (b.is_active ? (
        <button className="text-xs font-semibold text-red-400 hover:underline" onClick={() => setConfirm({ title: `Deactivate ${b.name}?`, message: 'The branch stops accepting new activity. Its history is kept.', label: 'Deactivate', run: () => setActive(b, false) })}>Deactivate</button>
      ) : (
        <button className="text-xs font-semibold text-green-400 hover:underline" onClick={() => setActive(b, true)}>Activate</button>
      )),
    },
  ];
  return (
    <div>
      <Toolbar list={list} placeholder="Search name or code" action={<button className="btn-primary !py-2" onClick={() => setCreating(true)}><Plus size={15} /> New</button>}>
        <Select label="Organization" value={list.filters.organization} onChange={(v) => list.setFilter('organization', v)} options={[['', 'All organizations'], ...orgs]} />
        <Select label="Status" value={list.filters.is_active} onChange={(v) => list.setFilter('is_active', v)} options={ACTIVE_FILTER} />
      </Toolbar>
      <DataTable list={list} columns={columns} empty="No branches match." />
      {creating && (
        <CreateForm title="New branch" path="/platform/branches/" onClose={() => setCreating(false)}
          initial={{ organization: '', name: '', code: '', phone: '', address: '' }}
          fields={[{ name: 'organization', label: 'Organization', options: orgs, required: true }, { name: 'name', label: 'Name', required: true }, { name: 'code', label: 'Code (unique per organization)', required: true }, { name: 'phone', label: 'Phone' }, { name: 'address', label: 'Address' }]}
          onDone={() => { toast.success('Branch created'); setCreating(false); list.reload(); }} />
      )}
      {confirm && <Confirm title={confirm.title} message={confirm.message} confirmLabel={confirm.label} onConfirm={confirm.run} onClose={() => setConfirm(null)} />}
    </div>
  );
}

function PlatformUsers({ me }) {
  const orgs = useOrgOptions();
  const list = useList('/platform/users/', { organization: '', platform_admin: '', is_active: '' });
  const [confirm, setConfirm] = useState(null);
  const act = (user, path, body, ok) => api.post(`/platform/users/${user.id}/${path}/`, body)
    .then(() => { toast.success(ok); list.reload(); })
    .catch((e) => { toast.error(apiError(e)); throw e; });
  const columns = [
    { key: 'username', label: 'Username', render: (u) => <span className="font-semibold text-white">{u.username}</span> },
    { key: 'email', label: 'Email', render: (u) => u.email || '—' },
    { key: 'organization_name', label: 'Organization', render: (u) => u.organization_name || 'Platform' },
    { key: 'roles', label: 'Roles', render: (u) => (u.roles.length ? u.roles.join(', ') : '—') },
    { key: 'is_platform_admin', label: 'Platform admin', render: (u) => <Badge on={u.is_platform_admin} yes="Yes" no="No" /> },
    { key: 'is_active', label: 'Status', render: (u) => <Badge on={u.is_active} /> },
    { key: 'last_login', label: 'Last sign-in', render: (u) => fmt(u.last_login) },
    {
      key: 'actions', label: '', render: (u) => (u.id === me?.id ? <span className="text-xs text-slate-600">You</span> : (
        <div className="flex gap-3">
          <button className="text-xs font-semibold text-blue-400 hover:underline" onClick={() => setConfirm(u.is_platform_admin ? {
            title: `Revoke platform access from ${u.username}?`, message: 'They will lose all platform-level authority.', label: 'Revoke',
            run: () => act(u, 'set-platform-admin', { is_platform_admin: false }, 'Platform access revoked'),
          } : {
            title: `Grant platform access to ${u.username}?`, message: 'This gives full control over every organization on ZenPOS. Only do this for a trusted operator.', label: 'Grant',
            run: () => act(u, 'set-platform-admin', { is_platform_admin: true }, 'Platform access granted'),
          })}>{u.is_platform_admin ? 'Revoke admin' : 'Make admin'}</button>
          <button className="text-xs font-semibold text-slate-400 hover:underline" onClick={() => setConfirm({
            title: `${u.is_active ? 'Deactivate' : 'Activate'} ${u.username}?`, message: u.is_active ? 'They will be unable to sign in.' : 'They will be able to sign in again.', label: u.is_active ? 'Deactivate' : 'Activate',
            run: () => act(u, 'set-active', { is_active: !u.is_active }, u.is_active ? 'Deactivated' : 'Activated'),
          })}>{u.is_active ? 'Deactivate' : 'Activate'}</button>
        </div>
      )),
    },
  ];
  return (
    <div>
      <Toolbar list={list} placeholder="Search username, name or email">
        <Select label="Organization" value={list.filters.organization} onChange={(v) => list.setFilter('organization', v)} options={[['', 'All organizations'], ...orgs]} />
        <Select label="Platform admin" value={list.filters.platform_admin} onChange={(v) => list.setFilter('platform_admin', v)} options={[['', 'Any access'], ['true', 'Platform admins'], ['false', 'Not platform admins']]} />
        <Select label="Status" value={list.filters.is_active} onChange={(v) => list.setFilter('is_active', v)} options={ACTIVE_FILTER} />
      </Toolbar>
      <DataTable list={list} columns={columns} empty="No users match." />
      {confirm && <Confirm title={confirm.title} message={confirm.message} confirmLabel={confirm.label} onConfirm={confirm.run} onClose={() => setConfirm(null)} />}
    </div>
  );
}

function AuditLogs() {
  const orgs = useOrgOptions();
  const list = useList('/platform/audit-logs/', { organization: '', action: '', date_from: '', date_to: '' });
  const columns = [
    { key: 'created_at', label: 'When', render: (r) => fmt(r.created_at) },
    { key: 'action', label: 'Action', render: (r) => <span className="font-mono text-xs text-slate-200">{r.action}</span> },
    { key: 'actor_username', label: 'Actor', render: (r) => r.actor_username || (r.attempted_username ? `${r.attempted_username} (unauthenticated)` : '—') },
    { key: 'organization_name', label: 'Organization' },
    { key: 'entity_type', label: 'Entity' },
    { key: 'ip_address', label: 'IP' },
  ];
  return (
    <div>
      <Toolbar list={list} placeholder="Search actor or action">
        <Select label="Organization" value={list.filters.organization} onChange={(v) => list.setFilter('organization', v)} options={[['', 'All organizations'], ...orgs]} />
        <Select label="Category" value={list.filters.action} onChange={(v) => list.setFilter('action', v)} options={[['', 'All actions'], ['platform.', 'Platform admin'], ['auth.', 'Authentication']]} />
        <input type="date" className="input !w-auto !py-2" aria-label="From date" value={list.filters.date_from} onChange={(e) => list.setFilter('date_from', e.target.value)} />
        <input type="date" className="input !w-auto !py-2" aria-label="To date" value={list.filters.date_to} onChange={(e) => list.setFilter('date_to', e.target.value)} />
      </Toolbar>
      <DataTable list={list} columns={columns} empty="No audit events match." />
    </div>
  );
}

function Health() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const load = useCallback(() => {
    setError(null);
    api.get('/platform/health/').then(({ data: d }) => setData(d)).catch((e) => setError(apiError(e, 'Could not load health.')));
  }, []);
  useEffect(() => { load(); }, [load]);
  if (error) return <div className="rounded-xl border border-red-500/20 bg-red-500/10 p-4 text-sm text-red-300">{error}</div>;
  if (!data) return <Loader2 className="animate-spin text-slate-500" />;
  const rows = [
    ['Database', data.database === 'ok', data.database === 'ok' ? 'Reachable' : 'Unavailable'],
    ['Pending migrations', data.pending_migrations === 0, data.pending_migrations == null ? 'Unknown' : String(data.pending_migrations)],
    ['Debug mode', !data.debug_mode, data.debug_mode ? 'ON — must be off in production' : 'Off'],
    ['M-Pesa callback secret', data.mpesa_callback_secret_configured, data.mpesa_callback_secret_configured ? 'Configured' : 'Not configured'],
    ['Latest audit event', true, fmt(data.latest_audit_event_at)],
  ];
  return (
    <div>
      <div className="overflow-hidden rounded-xl border border-slate-800">
        {rows.map(([label, ok, value]) => (
          <div key={label} className="flex items-center justify-between border-b border-slate-800/70 px-4 py-3 last:border-0">
            <span className="text-sm text-slate-400">{label}</span>
            <span className={`text-sm font-semibold ${ok ? 'text-green-400' : 'text-red-400'}`}>{value}</span>
          </div>
        ))}
      </div>
      <p className="mt-3 text-xs text-slate-600">Checked {fmt(data.checked_at)}. Only signals the API can measure directly are shown.</p>
      <button className="btn-secondary mt-3 !py-2" onClick={load}><RefreshCw size={14} /> Re-check</button>
    </div>
  );
}

export default function SuperAdmin() {
  const [tab, setTab] = useState('overview');
  const me = (() => { try { return JSON.parse(localStorage.getItem('user') || 'null'); } catch { return null; } })();
  const View = { overview: Overview, organizations: Organizations, branches: Branches, users: PlatformUsers, audit: AuditLogs, health: Health }[tab];
  return (
    <div className="page-shell space-y-5">
      <div>
        <div className="text-xs font-bold uppercase tracking-widest text-blue-400">Platform</div>
        <h1 className="page-title">Super Admin</h1>
        <p className="page-subtitle">Cross-organization administration. All actions are audited.</p>
      </div>
      <nav className="flex gap-1 overflow-x-auto border-b border-slate-800" aria-label="Super Admin sections">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button key={id} onClick={() => setTab(id)} aria-current={tab === id ? 'page' : undefined}
            className={`flex shrink-0 items-center gap-2 border-b-2 px-3 py-2 text-sm font-semibold transition ${tab === id ? 'border-blue-500 text-white' : 'border-transparent text-slate-500 hover:text-slate-300'}`}>
            <Icon size={15} /> {label}
          </button>
        ))}
      </nav>
      <View me={me} />
    </div>
  );
}
