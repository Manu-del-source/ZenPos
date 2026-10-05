import React, { useCallback, useEffect, useState } from 'react';
import { Archive, Building2, Plus, Search } from 'lucide-react';
import toast from 'react-hot-toast';
import api, { apiError } from '../services/api';

const STATUS_STYLES = {
  ACTIVE: 'bg-green-500/10 text-green-500 border-green-500/20',
  BLOCKED: 'bg-red-500/10 text-red-400 border-red-500/20',
};

const emptyForm = {
  name: '', contact_name: '', phone: '', email: '',
  address: '', payment_terms: '', status: 'ACTIVE', notes: '',
};

const Suppliers = () => {
  const [suppliers, setSuppliers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [showModal, setShowModal] = useState(false);
  const [editingSupplier, setEditingSupplier] = useState(null);
  const [formData, setFormData] = useState(emptyForm);
  const [saving, setSaving] = useState(false);

  const fetchSuppliers = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const { data } = await api.get('/suppliers/', { params: { search: searchTerm } });
      setSuppliers(Array.isArray(data) ? data : (data.results || []));
    } catch (err) {
      const message = apiError(err, 'Failed to load suppliers');
      setLoadError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, [searchTerm]);

  useEffect(() => { fetchSuppliers(); }, [fetchSuppliers]);

  const openModal = (supplier = null) => {
    setEditingSupplier(supplier);
    setFormData(supplier ? {
      name: supplier.name || '',
      contact_name: supplier.contact_name || '',
      phone: supplier.phone || '',
      email: supplier.email || '',
      address: supplier.address || '',
      payment_terms: supplier.payment_terms || '',
      status: supplier.status || 'ACTIVE',
      notes: supplier.notes || '',
    } : { ...emptyForm });
    setShowModal(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!formData.name.trim()) {
      return toast.error('Supplier name is required.');
    }
    setSaving(true);
    try {
      if (editingSupplier) {
        await api.patch(`/suppliers/${editingSupplier.id}/`, formData);
      } else {
        await api.post('/suppliers/', formData);
      }
      toast.success(editingSupplier ? 'Supplier updated' : 'Supplier added');
      setShowModal(false);
      await fetchSuppliers();
    } catch (err) {
      toast.error(apiError(err, 'Could not save the supplier'));
    } finally {
      setSaving(false);
    }
  };

  const handleArchive = async (supplier) => {
    if (!window.confirm(`Archive ${supplier.name}? They will no longer appear in the supplier list.`)) return;
    try {
      await api.delete(`/suppliers/${supplier.id}/`);
      toast.success('Supplier archived');
      fetchSuppliers();
    } catch (err) {
      toast.error(apiError(err, 'Could not archive the supplier'));
    }
  };

  return (
    <div className="p-8 max-w-7xl mx-auto min-h-screen">
      <div className="flex justify-between items-center mb-8 gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-black tracking-tight text-white">Suppliers</h1>
          <p className="text-slate-500 text-sm">Who the business buys stock from.</p>
        </div>
        <button onClick={() => openModal()} className="btn-primary flex items-center">
          <Plus size={18} className="mr-2" /> Add supplier
        </button>
      </div>

      <div className="mb-6 relative">
        <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-500" size={20} />
        <input
          className="w-full bg-slate-900 border border-slate-800 p-4 pl-12 rounded-2xl text-white outline-none focus:border-blue-500 transition-all"
          placeholder="Search name, contact, phone or email..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
        />
      </div>

      {loadError && !loading && (
        <div className="panel mb-6 p-6 text-center">
          <p className="text-red-400 font-semibold">Could not load suppliers</p>
          <p className="text-slate-500 text-sm mt-1">{loadError}</p>
          <button className="btn-secondary mt-4" onClick={fetchSuppliers}>Try again</button>
        </div>
      )}

      <div className="bg-slate-900 rounded-3xl border border-slate-800 overflow-hidden shadow-2xl">
        <table className="w-full text-left">
          <thead className="bg-slate-800/50">
            <tr className="text-slate-400 text-[10px] font-black uppercase tracking-[0.2em]">
              <th className="p-5">Supplier</th>
              <th className="p-5">Contact</th>
              <th className="p-5">Payment terms</th>
              <th className="p-5 text-center">Status</th>
              <th className="p-5 text-center">Manage</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {suppliers.map((s) => (
              <tr key={s.id} className="hover:bg-slate-800/30 transition group">
                <td className="p-5">
                  <div className="font-bold text-white group-hover:text-blue-400">{s.name}</div>
                  {s.address && <div className="text-xs text-slate-500 mt-1">{s.address}</div>}
                </td>
                <td className="p-5">
                  <div className="text-slate-300">{s.contact_name || '—'}</div>
                  <div className="text-xs text-slate-500">{s.phone || s.email || ''}</div>
                </td>
                <td className="p-5 text-slate-300">{s.payment_terms || '—'}</td>
                <td className="p-5 text-center">
                  <span className={`px-3 py-1 rounded-lg text-[10px] font-black uppercase tracking-widest border ${STATUS_STYLES[s.status] || ''}`}>
                    {s.status}
                  </span>
                </td>
                <td className="p-5 text-center">
                  <button
                    onClick={() => openModal(s)}
                    className="px-3 py-2 bg-slate-800 rounded-lg text-slate-400 hover:text-white text-xs font-bold"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => handleArchive(s)}
                    className="ml-2 p-2 bg-slate-800 rounded-lg text-slate-400 hover:text-red-500"
                    aria-label={`Archive ${s.name}`}
                    title="Archive supplier"
                  >
                    <Archive size={16} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {loading && <div className="p-16 text-center text-slate-500 font-bold uppercase tracking-widest text-sm">Loading suppliers…</div>}

        {!loading && !loadError && suppliers.length === 0 && (
          <div className="p-20 text-center flex flex-col items-center">
            <Building2 size={64} className="text-slate-800 mb-4" />
            <p className="text-slate-500 font-bold uppercase tracking-widest text-sm">
              {searchTerm ? 'No suppliers match that search' : 'No suppliers yet — add your first one'}
            </p>
            {!searchTerm && (
              <button className="btn-primary mt-6 flex items-center" onClick={() => openModal()}>
                <Plus size={18} className="mr-2" /> Add supplier
              </button>
            )}
          </div>
        )}
      </div>

      {showModal && (
        <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center z-[100] p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-3xl p-8 w-full max-w-lg shadow-2xl max-h-[90vh] overflow-y-auto">
            <h3 className="text-2xl font-black mb-6 text-white tracking-tight">
              {editingSupplier ? 'Edit supplier' : 'New supplier'}
            </h3>
            <form onSubmit={handleSubmit} className="space-y-4">
              {[
                ['name', 'Supplier name', 'text', true],
                ['contact_name', 'Contact person', 'text', false],
                ['phone', 'Phone', 'text', false],
                ['email', 'Email', 'email', false],
                ['payment_terms', 'Payment terms', 'text', false],
              ].map(([key, label, type, required]) => (
                <div key={key}>
                  <label className="block text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">
                    {label}{required ? ' *' : ''}
                  </label>
                  <input
                    required={required}
                    type={type}
                    className="w-full bg-slate-950 border border-slate-800 p-4 rounded-xl text-white outline-none focus:border-blue-500"
                    value={formData[key]}
                    onChange={(e) => setFormData({ ...formData, [key]: e.target.value })}
                  />
                </div>
              ))}
              <div>
                <label className="block text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">Address</label>
                <textarea
                  rows={2}
                  className="w-full bg-slate-950 border border-slate-800 p-4 rounded-xl text-white outline-none focus:border-blue-500"
                  value={formData.address}
                  onChange={(e) => setFormData({ ...formData, address: e.target.value })}
                />
              </div>
              <div>
                <label className="block text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">Status</label>
                <select
                  className="w-full bg-slate-950 border border-slate-800 p-4 rounded-xl text-white outline-none focus:border-blue-500"
                  value={formData.status}
                  onChange={(e) => setFormData({ ...formData, status: e.target.value })}
                >
                  <option value="ACTIVE">Active</option>
                  <option value="BLOCKED">Blocked</option>
                </select>
              </div>
              <div>
                <label className="block text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">Notes</label>
                <textarea
                  rows={2}
                  className="w-full bg-slate-950 border border-slate-800 p-4 rounded-xl text-white outline-none focus:border-blue-500"
                  value={formData.notes}
                  onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                />
              </div>
              <div className="flex space-x-3 pt-2">
                <button type="button" onClick={() => setShowModal(false)} className="flex-1 bg-slate-800 text-slate-400 py-4 rounded-2xl font-bold uppercase">
                  Cancel
                </button>
                <button type="submit" disabled={saving} className="flex-1 bg-blue-600 text-white py-4 rounded-2xl font-black uppercase disabled:opacity-50">
                  {saving ? 'Saving…' : 'Save supplier'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default Suppliers;
