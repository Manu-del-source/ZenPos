import React, { useState, useEffect } from 'react';
import api from '../services/api';
import toast from 'react-hot-toast';
import { Package, Plus, Pencil, Trash2, Search } from 'lucide-react';

const Inventory = () => {
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [showModal, setShowModal] = useState(false);
  const [editingProduct, setEditingProduct] = useState(null);
  
  const user = JSON.parse(localStorage.getItem('user') || '{}');
  const isAdmin = user.role === 'admin';

  const [formData, setFormData] = useState({
    name: '',
    sku: '',
    price: '',
    cost_price: '',
    stock: '',
    category_id: ''
  });

  const fetchProducts = async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/v1/inventory/products?search=${searchTerm}`);
      setProducts(data);
    } catch (err) {
      toast.error('Failed to load products');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id) => {
    if (!isAdmin) return toast.error("Only admins can delete stock");
    if (!window.confirm("Delete this part from inventory permanently?")) return;
    
    try {
      await api.delete(`/v1/inventory/products/${id}`, { params: { role: user.role } });
      toast.success('Part deleted');
      fetchProducts();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Delete failed');
    }
  };

  useEffect(() => {
    fetchProducts();
  }, [searchTerm]);

  const handleOpenModal = (product = null) => {
    if (product) {
      setEditingProduct(product);
      setFormData({
        name: product.name,
        sku: product.sku,
        price: product.price,
        cost_price: product.cost_price,
        stock: product.stock,
        category_id: product.category_id || ''
      });
    } else {
      setEditingProduct(null);
      setFormData({ name: '', sku: '', price: '', cost_price: '', stock: '', category_id: '' });
    }
    setShowModal(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      // In this version, we'll implement simple add/edit via the database
      // The backend should have endpoints for these
      toast.error("Cloud edit restricted in demo - use Terminal UI for bulk updates");
      setShowModal(false);
    } catch (err) {
      toast.error('Operation failed');
    }
  };

  return (
    <div className="p-8 max-w-7xl mx-auto bg-slate-950 min-h-screen text-white">
      <div className="flex justify-between items-center mb-8">
        <div>
          <h1 className="text-3xl font-black tracking-tight uppercase italic">STOCK <span className="text-blue-500">CONTROL</span></h1>
          <p className="text-slate-500 text-sm font-bold uppercase tracking-widest">Hardware & Motorcycle Spare Parts</p>
        </div>
        <button 
          onClick={() => handleOpenModal()}
          className="bg-blue-600 text-white px-6 py-3 rounded-xl font-black uppercase tracking-tighter hover:bg-blue-700 transition shadow-lg shadow-blue-600/20 flex items-center"
        >
          <Plus size={20} className="mr-2" /> NEW ITEM
        </button>
      </div>

      <div className="mb-6 relative">
        <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-500" size={20} />
        <input 
          className="w-full bg-slate-900 border border-slate-800 p-4 pl-12 rounded-2xl text-white outline-none focus:border-blue-500 transition-all"
          placeholder="Filter by SKU or Part Name..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
        />
      </div>

      <div className="bg-slate-900 rounded-3xl border border-slate-800 overflow-hidden shadow-2xl">
        <table className="w-full text-left">
          <thead className="bg-slate-800/50">
            <tr className="text-slate-400 text-[10px] font-black uppercase tracking-[0.2em]">
              <th className="p-5">Product Details</th>
              <th className="p-5 text-right">Unit Price</th>
              <th className="p-5 text-right">Stock</th>
              <th className="p-5 text-center">Manage</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {products.map((p) => (
              <tr key={p.id} className="hover:bg-slate-800/30 transition group">
                <td className="p-5">
                  <div className="font-bold text-white group-hover:text-blue-400 transition-colors">{p.name}</div>
                  <div className="text-[10px] text-slate-500 font-mono mt-1 uppercase tracking-wider">{p.sku} • {p.category || 'NO CATEGORY'}</div>
                </td>
                <td className="p-5 text-right font-black text-blue-400">
                  KES {Number(p.price).toLocaleString()}
                </td>
                <td className="p-5 text-right">
                  <span className={`px-3 py-1 rounded-lg text-[10px] font-black uppercase tracking-widest ${
                    p.stock <= 10 
                      ? 'bg-red-500/10 text-red-500 border border-red-500/20' 
                      : 'bg-green-500/10 text-green-500 border border-green-500/20'
                  }`}>
                    {p.stock} units
                  </span>
                </td>
                <td className="p-5 text-center">
                   <div className="flex justify-center space-x-2">
                      <button onClick={() => handleOpenModal(p)} className="p-2 bg-slate-800 hover:bg-slate-700 rounded-lg text-slate-400 hover:text-white transition">
                        <Pencil size={16} />
                      </button>
                      {isAdmin && (
                        <button onClick={() => handleDelete(p.id)} className="p-2 bg-slate-800 hover:bg-red-900/30 rounded-lg text-slate-400 hover:text-red-500 transition">
                          <Trash2 size={16} />
                        </button>
                      )}
                   </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {products.length === 0 && !loading && (
          <div className="p-20 text-center flex flex-col items-center">
            <Package size={64} className="text-slate-800 mb-4" />
            <p className="text-slate-500 font-bold uppercase tracking-widest text-sm">Inventory Archive Empty</p>
          </div>
        )}
      </div>

      {/* Modern Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center z-[100] p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-3xl p-8 w-full max-w-lg shadow-2xl">
            <h3 className="text-2xl font-black mb-8 text-white tracking-tighter uppercase italic">
              {editingProduct ? 'Update Stock Item' : 'New Inventory Record'}
            </h3>
            <form onSubmit={handleSubmit} className="space-y-6">
              <div>
                <label className="block text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2 ml-1">Part Name</label>
                <input 
                  className="w-full bg-slate-950 border border-slate-800 p-4 rounded-xl text-white outline-none focus:border-blue-500"
                  value={formData.name}
                  onChange={(e) => setFormData({...formData, name: e.target.value})}
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2 ml-1">SKU / Barcode</label>
                  <input 
                    className="w-full bg-slate-950 border border-slate-800 p-4 rounded-xl text-white outline-none focus:border-blue-500"
                    value={formData.sku}
                    onChange={(e) => setFormData({...formData, sku: e.target.value})}
                  />
                </div>
                <div>
                  <label className="block text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2 ml-1">Stock Level</label>
                  <input 
                    type="number"
                    className="w-full bg-slate-950 border border-slate-800 p-4 rounded-xl text-white outline-none focus:border-blue-500"
                    value={formData.stock}
                    onChange={(e) => setFormData({...formData, stock: e.target.value})}
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2 ml-1">Selling Price</label>
                  <input 
                    type="number"
                    className="w-full bg-slate-950 border border-slate-800 p-4 rounded-xl text-white outline-none focus:border-blue-500"
                    value={formData.price}
                    onChange={(e) => setFormData({...formData, price: e.target.value})}
                  />
                </div>
                <div>
                  <label className="block text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2 ml-1">Cost Price</label>
                  <input 
                    type="number"
                    className="w-full bg-slate-950 border border-slate-800 p-4 rounded-xl text-white outline-none focus:border-blue-500"
                    value={formData.cost_price}
                    onChange={(e) => setFormData({...formData, cost_price: e.target.value})}
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
                  Archive Item
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default Inventory;
