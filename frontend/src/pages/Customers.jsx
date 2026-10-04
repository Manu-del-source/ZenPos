import React, { useState, useEffect } from 'react';
import api from '../services/api';
import toast from 'react-hot-toast';
import { Users, UserPlus, Pencil, Search, Phone } from 'lucide-react';

const Customers = () => {
  const [customers, setCustomers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [showModal, setShowModal] = useState(false);
  const [editingCustomer, setEditingCustomer] = useState(null);
  const [formData, setFormData] = useState({ name: '', phone: '', email: '' });

  const fetchCustomers = async () => {
    setLoading(true);
    try {
      const res = await api.get('/customers/', { params: { search: searchTerm } });
      setCustomers(res.data);
    } catch (err) {
      toast.error('Failed to load customer directory');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCustomers();
  }, [searchTerm]);

  const handleOpenModal = (customer = null) => {
    if (customer) {
      setEditingCustomer(customer);
      setFormData({ name: customer.name, phone: customer.phone || '', email: customer.email || '' });
    } else {
      setEditingCustomer(null);
      setFormData({ name: '', phone: '', email: '' });
    }
    setShowModal(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      // In this version, we'll implement simple add/edit via the database
      toast.error("Cloud edit restricted - use Terminal UI for bulk updates");
      setShowModal(false);
    } catch (err) {
      toast.error('Operation failed');
    }
  };

  return (
    <div className="p-8 max-w-7xl mx-auto bg-slate-950 min-h-screen text-white">
      <div className="flex justify-between items-center mb-8">
        <div>
          <h1 className="text-3xl font-black tracking-tight uppercase italic">CLIENT <span className="text-blue-500">DATABASE</span></h1>
          <p className="text-slate-500 text-sm font-bold uppercase tracking-widest">Customer Loyalty & Contact Records</p>
        </div>
        <button 
          onClick={() => handleOpenModal()}
          className="bg-blue-600 text-white px-6 py-3 rounded-xl font-black uppercase tracking-tighter hover:bg-blue-700 transition shadow-lg shadow-blue-600/20 flex items-center"
        >
          <UserPlus size={20} className="mr-2" /> REGISTER CLIENT
        </button>
      </div>

      <div className="mb-6 relative">
        <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-500" size={20} />
        <input 
          className="w-full bg-slate-900 border border-slate-800 p-4 pl-12 rounded-2xl text-white outline-none focus:border-blue-500 transition-all"
          placeholder="Search by name or phone number..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
        />
      </div>

      <div className="bg-slate-900 rounded-3xl border border-slate-800 overflow-hidden shadow-2xl">
        <table className="w-full text-left">
          <thead className="bg-slate-800/50">
            <tr className="text-slate-400 text-[10px] font-black uppercase tracking-[0.2em]">
              <th className="p-5">Client Name</th>
              <th className="p-5">Contact Details</th>
              <th className="p-5 text-center">Manage</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {customers.map((c) => (
              <tr key={c.id} className="hover:bg-slate-800/30 transition group">
                <td className="p-5">
                  <div className="font-bold text-white group-hover:text-blue-400 transition-colors">{c.name}</div>
                  <div className="text-[10px] text-slate-500 font-mono mt-1 uppercase tracking-wider">ID: #CUST-{c.id}</div>
                </td>
                <td className="p-5">
                  <div className="flex flex-col space-y-1">
                    <span className="text-sm text-slate-300 flex items-center"><Phone size={12} className="mr-2 text-blue-500" /> {c.phone || 'N/A'}</span>
                    <span className="text-[11px] text-slate-500">{c.email || 'No email provided'}</span>
                  </div>
                </td>
                <td className="p-5 text-center">
                   <button onClick={() => handleOpenModal(c)} className="p-2 bg-slate-800 hover:bg-slate-700 rounded-lg text-slate-400 hover:text-white transition">
                     <Pencil size={16} />
                   </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {customers.length === 0 && !loading && (
          <div className="p-20 text-center flex flex-col items-center">
            <Users size={64} className="text-slate-800 mb-4" />
            <p className="text-slate-500 font-bold uppercase tracking-widest text-sm">No clients registered</p>
          </div>
        )}
      </div>

      {showModal && (
        <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center z-[100] p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-3xl p-8 w-full max-w-lg shadow-2xl">
            <h3 className="text-2xl font-black mb-8 text-white tracking-tighter uppercase italic">
              {editingCustomer ? 'Update Client Info' : 'New Client Registration'}
            </h3>
            <form onSubmit={handleSubmit} className="space-y-6">
              <div>
                <label className="block text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2 ml-1">Full Name</label>
                <input 
                  className="w-full bg-slate-950 border border-slate-800 p-4 rounded-xl text-white outline-none focus:border-blue-500"
                  value={formData.name}
                  onChange={(e) => setFormData({...formData, name: e.target.value})}
                  required
                />
              </div>
              <div className="grid grid-cols-1 gap-6">
                <div>
                  <label className="block text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2 ml-1">Phone Number (M-Pesa)</label>
                  <input 
                    className="w-full bg-slate-950 border border-slate-800 p-4 rounded-xl text-white outline-none focus:border-blue-500"
                    placeholder="e.g. 0712345678"
                    value={formData.phone}
                    onChange={(e) => setFormData({...formData, phone: e.target.value})}
                  />
                </div>
                <div>
                  <label className="block text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2 ml-1">Email Address</label>
                  <input 
                    type="email"
                    className="w-full bg-slate-950 border border-slate-800 p-4 rounded-xl text-white outline-none focus:border-blue-500"
                    value={formData.email}
                    onChange={(e) => setFormData({...formData, email: e.target.value})}
                  />
                </div>
              </div>
              
              <div className="flex space-x-3 pt-6">
                <button 
                  type="button" 
                  onClick={() => setShowModal(false)}
                  className="flex-1 bg-slate-800 text-slate-400 py-4 rounded-2xl font-bold uppercase tracking-widest hover:bg-slate-700 transition"
                >
                  Discard
                </button>
                <button 
                  type="submit" 
                  className="flex-1 bg-blue-600 text-white py-4 rounded-2xl font-black uppercase tracking-widest shadow-lg shadow-blue-600/20 hover:bg-blue-700 transition"
                >
                  Save Record
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default Customers;
