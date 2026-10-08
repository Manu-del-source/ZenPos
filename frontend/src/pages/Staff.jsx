import React, { useCallback, useEffect, useState } from 'react';
import { Contact, Plus, Search, X } from 'lucide-react';
import toast from 'react-hot-toast';
import api, { apiError } from '../services/api';

const STATUS_STYLES = {
  ACTIVE: 'bg-green-500/10 text-green-400 border-green-500/20',
  INACTIVE: 'bg-slate-500/10 text-slate-400 border-slate-500/20',
  SUSPENDED: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  TERMINATED: 'bg-red-500/10 text-red-400 border-red-500/20',
};

const emptyForm = {
  first_name: '', last_name: '', phone: '', email: '', branch: '', role: '', status: 'ACTIVE', start_date: '', notes: '',
};

export default function Staff() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [branches, setBranches] = useState([]);
  const [roles, setRoles] = useState([]);
  const [form, setForm] = useState(null);
  const [editing, setEditing] = useState(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/employees/', {
        params: { search: searchTerm || undefined, status: statusFilter || undefined },
      });
      setRows(Array.isArray(data) ? data : data.results || []);
    } catch (err) {
      toast.error(apiError(err, 'Failed to load staff'));
    } finally {
      setLoading(false);
    }
  }, [searchTerm, statusFilter]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    Promise.all([
      api.get('/branches/', { params: { page_size: 100 } }).catch(() => ({ data: { results: [] } })),
      api.get('/roles/', { params: { page_size: 50 } }).catch(() => ({ data: { results: [] } })),
    ]).then(([b, r]) => {
      setBranches(Array.isArray(b.data) ? b.data : b.data.results || []);
      setRoles(Array.isArray(r.data) ? r.data : r.data.results || []);
    });
  }, []);

  const save = async (event) => {
    event.preventDefault();
    if (!form.first_name.trim() || !form.last_name.trim()) return toast.error('First and last name are required.');
    setSaving(true);
    const payload = {
      ...form,
      branch: form.branch || null,
      role: form.role || null,
      start_date: form.start_date || null,
    };
    try {
      if (editing) {
        await api.patch(`/employees/${editing.id}/`, payload);
        toast.success('Staff record updated');
      } else {
        await api.post('/employees/', payload);
        toast.success('Staff record created');
      }
      setForm(null);
      setEditing(null);
      await load();
    } catch (err) {
      toast.error(apiError(err, 'Could not save staff record'));
    } finally {
      setSaving(false);
    }
  };

  const setStatus = async (row, status) => {
    try {
      await api.patch(`/employees/${row.id}/`, { status });
      toast.success(`Marked ${status.toLowerCase()}`);
      await load();
    } catch (err) {
      toast.error(apiError(err, 'Could not change status'));
    }
  };

  return (
    <div className="p-8 max-w-7xl mx-auto min-h-screen">
      <div className="flex justify-between items-center mb-8 gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-black tracking-tight text-white">Staff</h1>
          <p className="text-slate-500 text-sm">Employee records for this organization. Login accounts are linked when issued.</p>
        </div>
        <button className="btn-primary" onClick={() => { setEditing(null); setForm({ ...emptyForm, branch: branches[0]?.id || '' }); }}>
          <Plus size={16} /> New employee
        </button>
      </div>

      <div className="mb-6 flex gap-3 flex-wrap">
        <div className="relative flex-1 min-w-[240px]">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-500" size={18} />
          <input className="w-full bg-slate-900 border border-slate-800 p-4 pl-12 rounded-2xl text-white outline-none focus:border-blue-500" placeholder="Search name or employee #…" value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)} />
        </div>
        <select className="bg-slate-900 border border-slate-800 p-4 rounded-2xl text-white" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">All statuses</option>
          {Object.keys(STATUS_STYLES).map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>

      <div className="bg-slate-900 rounded-3xl border border-slate-800 overflow-hidden">
        <table className="w-full text-sm text-left">
          <thead className="bg-slate-800/50">
            <tr className="text-slate-400 text-[10px] font-black uppercase tracking-[0.18em]">
              <th className="p-4">Employee #</th>
              <th className="p-4">Name</th>
              <th className="p-4">Branch</th>
              <th className="p-4">Role</th>
              <th className="p-4 text-center">Status</th>
              <th className="p-4 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {rows.map((row) => (
              <tr key={row.id} className="hover:bg-slate-800/30">
                <td className="p-4 font-bold text-white">{row.employee_number}</td>
                <td className="p-4 text-slate-200">{row.full_name}<div className="text-xs text-slate-500">{row.phone}</div></td>
                <td className="p-4 text-slate-300">{row.branch_name || '—'}</td>
                <td className="p-4 text-slate-300">{row.role_name || '—'}</td>
                <td className="p-4 text-center">
                  <span className={`px-3 py-1 rounded-lg text-[10px] font-black uppercase tracking-widest border ${STATUS_STYLES[row.status] || ''}`}>{row.status}</span>
                </td>
                <td className="p-4 text-right whitespace-nowrap">
                  <button className="px-3 py-2 bg-slate-800 rounded-lg text-xs font-bold text-slate-300" onClick={() => { setEditing(row); setForm({ ...emptyForm, ...row, branch: row.branch || '', role: row.role || '' }); }}>Edit</button>
                  {row.status === 'ACTIVE' && <button className="ml-2 px-3 py-2 bg-slate-800 rounded-lg text-xs font-bold text-amber-400" onClick={() => setStatus(row, 'SUSPENDED')}>Suspend</button>}
                  {row.status !== 'ACTIVE' && row.status !== 'TERMINATED' && <button className="ml-2 px-3 py-2 bg-slate-800 rounded-lg text-xs font-bold text-green-400" onClick={() => setStatus(row, 'ACTIVE')}>Activate</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {loading && <div className="p-16 text-center text-slate-500 text-sm font-bold uppercase tracking-widest">Loading staff…</div>}
        {!loading && rows.length === 0 && (
          <div className="p-20 text-center flex flex-col items-center">
            <Contact size={56} className="text-slate-800 mb-4" />
            <p className="text-slate-500 font-bold uppercase tracking-widest text-sm">No employees yet</p>
          </div>
        )}
      </div>

      {form && (
        <div className="fixed inset-0 bg-slate-950/80 z-[100] flex items-center justify-center p-4">
          <form onSubmit={save} className="bg-slate-900 border border-slate-800 rounded-3xl p-6 w-full max-w-lg">
            <div className="flex justify-between mb-4">
              <h3 className="text-xl font-black text-white">{editing ? 'Edit employee' : 'New employee'}</h3>
              <button type="button" onClick={() => setForm(null)} className="text-slate-500"><X size={18} /></button>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <input className="bg-slate-950 border border-slate-800 p-3 rounded-xl text-white" placeholder="First name" value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} required />
              <input className="bg-slate-950 border border-slate-800 p-3 rounded-xl text-white" placeholder="Last name" value={form.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} required />
              <input className="bg-slate-950 border border-slate-800 p-3 rounded-xl text-white" placeholder="Phone" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
              <input className="bg-slate-950 border border-slate-800 p-3 rounded-xl text-white" placeholder="Email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
              <select className="bg-slate-950 border border-slate-800 p-3 rounded-xl text-white" value={form.branch} onChange={(e) => setForm({ ...form, branch: e.target.value })}>
                <option value="">Branch…</option>
                {branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
              </select>
              <select className="bg-slate-950 border border-slate-800 p-3 rounded-xl text-white" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
                <option value="">Role…</option>
                {roles.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
              </select>
              <input type="date" className="bg-slate-950 border border-slate-800 p-3 rounded-xl text-white" value={form.start_date || ''} onChange={(e) => setForm({ ...form, start_date: e.target.value })} />
              <select className="bg-slate-950 border border-slate-800 p-3 rounded-xl text-white" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                {Object.keys(STATUS_STYLES).map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <textarea className="mt-3 w-full bg-slate-950 border border-slate-800 p-3 rounded-xl text-white" rows={2} placeholder="Notes" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
            <div className="flex gap-2 mt-4">
              <button type="button" className="flex-1 bg-slate-800 py-3 rounded-2xl font-bold text-slate-300" onClick={() => setForm(null)}>Cancel</button>
              <button type="submit" disabled={saving} className="flex-1 bg-blue-600 py-3 rounded-2xl font-black text-white">{saving ? 'Saving…' : 'Save'}</button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
