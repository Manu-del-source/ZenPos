import React, { useEffect, useMemo, useState } from 'react';
import { Pencil, Plus, Search, UserRound, Users, X } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../services/api';

const emptyForm = { name: '', phone: '' };

export default function Customers() {
  const [customers, setCustomers] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingCustomer, setEditingCustomer] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [ledger, setLedger] = useState(null);

  const fetchCustomers = async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/customers/');
      const rows = Array.isArray(data) ? data : (data.results || []);
      setCustomers(rows);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to load customers.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchCustomers(); }, []);

  const filteredCustomers = useMemo(() => {
    const q = searchTerm.trim().toLowerCase();
    if (!q) return customers;
    return customers.filter((customer) =>
      customer.name?.toLowerCase().includes(q) ||
      customer.phone?.toLowerCase().includes(q)
    );
  }, [customers, searchTerm]);

  const openCreate = () => {
    setEditingCustomer(null);
    setForm(emptyForm);
    setModalOpen(true);
  };

  const openEdit = (customer) => {
    setEditingCustomer(customer);
    setForm({ name: customer.name || '', phone: customer.phone || '' });
    setModalOpen(true);
  };

  const closeModal = () => {
    if (!saving) setModalOpen(false);
  };

  const saveCustomer = async (event) => {
    event.preventDefault();
    const name = form.name.trim();
    const phone = form.phone.trim();

    if (!name || !phone) {
      toast.error('Name and phone number are required.');
      return;
    }

    setSaving(true);
    try {
      if (editingCustomer) {
        await api.patch(`/customers/${editingCustomer.id}/`, { name, phone });
        toast.success('Customer updated.');
      } else {
        await api.post('/customers/', { name, phone });
        toast.success('Customer added.');
      }
      setModalOpen(false);
      await fetchCustomers();
    } catch (err) {
      const data = err.response?.data;
      const detail = data?.detail || Object.values(data || {}).flat().find((value) => typeof value === 'string');
      toast.error(detail || 'Could not save customer.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="page-shell">
      <div className="flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="eyebrow">Customer management</div>
          <h1 className="page-title">Customers</h1>
          <p className="page-subtitle">Keep customer contacts ready for faster checkout and repeat business.</p>
        </div>
        <button className="btn-primary" onClick={openCreate}>
          <Plus size={17} /> Add customer
        </button>
      </div>

      <div className="panel mt-6">
        <div className="panel-header">
          <div>
            <h2 className="panel-title">Customer directory</h2>
            <p className="panel-subtitle">{customers.length} customer{customers.length === 1 ? '' : 's'} registered</p>
          </div>
          <div className="relative w-full sm:w-80">
            <Search size={17} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
            <input
              className="input pl-10"
              placeholder="Search name or phone"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>
        </div>

        {loading ? (
          <div className="p-10 text-center text-slate-500">Loading customers…</div>
        ) : filteredCustomers.length === 0 ? (
          <div className="p-12 text-center">
            <Users className="mx-auto mb-3 text-slate-600" size={34} />
            <p className="font-semibold text-slate-300">{searchTerm ? 'No matching customers' : 'No customers yet'}</p>
            <p className="mt-1 text-sm text-slate-500">{searchTerm ? 'Try another name or phone number.' : 'Add your first customer to get started.'}</p>
          </div>
        ) : (
          <div className="divide-y divide-slate-800/70">
            {filteredCustomers.map((customer) => (
              <div key={customer.id} className="flex items-center gap-4 px-5 py-4 hover:bg-slate-900/60">
                <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-slate-700 bg-slate-900 text-slate-300">
                  <UserRound size={18} />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-semibold text-white">{customer.name}</p>
                  <p className="mt-0.5 text-sm text-slate-500">{customer.phone}</p>
                </div>
                <div className="hidden text-right sm:block">
                  <p className="text-xs uppercase tracking-wider text-slate-500">Loyalty</p>
                  <p className="font-semibold text-slate-200">{customer.loyalty_points ?? 0} pts</p>
                </div>
                <button className="btn-secondary !px-3" onClick={async () => {
                  try {
                    const { data } = await api.get('/loyalty-accounts/', { params: { customer: customer.id } });
                    const rows = Array.isArray(data) ? data : data.results || [];
                    setLedger({ customer, account: rows[0] || { points_balance: customer.loyalty_points, entries: [] } });
                  } catch {
                    setLedger({ customer, account: { points_balance: customer.loyalty_points, entries: [] } });
                  }
                }}>Ledger</button>
                <button className="btn-secondary !px-3" onClick={() => openEdit(customer)} aria-label={`Edit ${customer.name}`}>
                  <Pencil size={15} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {ledger && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4">
          <div className="panel w-full max-w-lg max-h-[85vh] overflow-y-auto">
            <div className="panel-header">
              <div>
                <h2 className="panel-title">{ledger.customer.name}</h2>
                <p className="panel-subtitle">{ledger.account.points_balance || 0} points</p>
              </div>
              <button className="btn-secondary !px-3" onClick={() => setLedger(null)}><X size={16} /></button>
            </div>
            <div className="p-5">
              {(ledger.account.entries || []).length === 0 ? (
                <p className="text-sm text-slate-500">No ledger entries yet. Points are awarded on completed sales.</p>
              ) : (
                <table className="w-full text-sm">
                  <tbody>
                    {ledger.account.entries.map((row) => (
                      <tr key={row.id} className="border-t border-slate-800">
                        <td className="py-2 text-slate-400 text-xs">{new Date(row.created_at).toLocaleString()}</td>
                        <td className="py-2 text-slate-300">{row.action}</td>
                        <td className={`py-2 text-right font-bold ${row.points < 0 ? 'text-red-400' : 'text-emerald-400'}`}>{row.points > 0 ? '+' : ''}{row.points}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>
      )}
      {modalOpen && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4 backdrop-blur-sm">
          <div className="panel w-full max-w-md shadow-2xl">
            <div className="panel-header">
              <div>
                <h2 className="panel-title">{editingCustomer ? 'Edit customer' : 'Add customer'}</h2>
                <p className="panel-subtitle">Name and phone are required by the current API.</p>
              </div>
              <button className="btn-secondary !px-3" onClick={closeModal}><X size={17} /></button>
            </div>
            <form onSubmit={saveCustomer} className="space-y-4 p-5">
              <label className="block">
                <span className="mb-1.5 block text-sm font-medium text-slate-300">Full name</span>
                <input className="input" autoFocus value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
              </label>
              <label className="block">
                <span className="mb-1.5 block text-sm font-medium text-slate-300">Phone number</span>
                <input className="input" placeholder="0712345678" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
              </label>
              <div className="flex justify-end gap-3 pt-2">
                <button type="button" className="btn-secondary" onClick={closeModal}>Cancel</button>
                <button type="submit" className="btn-primary" disabled={saving}>{saving ? 'Saving…' : editingCustomer ? 'Save changes' : 'Add customer'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
