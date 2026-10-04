import React, { useEffect, useState } from 'react';
import api from '../services/api';
import toast from 'react-hot-toast';
import { Package, Plus, Pencil, Trash2, Search } from 'lucide-react';

const emptyForm = { name: '', sku: '', price: '', cost_price: '', stock_level: '', low_stock_threshold: 10, track_inventory: true, is_active: true };

const Inventory = () => {
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [showModal, setShowModal] = useState(false);
  const [editingProduct, setEditingProduct] = useState(null);
  const [formData, setFormData] = useState(emptyForm);

  const fetchProducts = async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/products/', { params: { search: searchTerm } });
      setProducts(Array.isArray(data) ? data : (data.results || []));
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to load products');
    } finally { setLoading(false); }
  };

  useEffect(() => { fetchProducts(); }, [searchTerm]);

  const handleOpenModal = (product = null) => {
    setEditingProduct(product);
    setFormData(product ? {
      name: product.name || '', sku: product.sku || '', price: product.price || '',
      cost_price: product.cost_price || '', stock_level: product.stock_level || 0,
      low_stock_threshold: product.low_stock_threshold ?? 10,
      track_inventory: product.track_inventory ?? true, is_active: product.is_active ?? true,
    } : { ...emptyForm });
    setShowModal(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      const payload = {
        name: formData.name.trim(), sku: formData.sku.trim(),
        price: Number(formData.price), cost_price: Number(formData.cost_price),
        low_stock_threshold: Number(formData.low_stock_threshold),
        track_inventory: formData.track_inventory, is_active: formData.is_active,
      };
      if (!payload.name || payload.price <= 0 || payload.cost_price < 0) {
        return toast.error('Enter a name, valid selling price and cost price.');
      }

      let product;
      if (editingProduct) {
        ({ data: product } = await api.patch('/products/' + editingProduct.id + '/', payload));
      } else {
        ({ data: product } = await api.post('/products/', payload));
      }

      const desiredStock = Number(formData.stock_level);
      const currentStock = Number(product.stock_level || 0);
      if (desiredStock !== currentStock) {
        await api.post('/adjustments/', {
          product: product.id, quantity: desiredStock - currentStock,
          type: 'ADJUST', notes: editingProduct ? 'Inventory opening balance update' : 'Opening stock',
        });
      }

      toast.success(editingProduct ? 'Product updated' : 'Product created');
      setShowModal(false);
      await fetchProducts();
    } catch (err) {
      const data = err.response?.data;
      const detail = data?.detail || (data && Object.values(data).flat().find(v => typeof v === 'string'));
      toast.error(detail || 'Operation failed. Check organization and permissions.');
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this product?')) return;
    try {
      await api.delete('/products/' + id + '/');
      toast.success('Product archived');
      fetchProducts();
    } catch (err) { toast.error(err.response?.data?.detail || 'Delete failed'); }
  };

  return (
    <div className="p-8 max-w-7xl mx-auto bg-slate-950 min-h-screen text-white">
      <div className="flex justify-between items-center mb-8">
        <div><h1 className="text-3xl font-black tracking-tight">Inventory</h1>
          <p className="text-slate-500 text-sm">Manage products, pricing and stock levels.</p></div>
        <button onClick={() => handleOpenModal()} className="btn-primary flex items-center">
          <Plus size={18} className="mr-2" /> Add product
        </button>
      </div>
      <div className="mb-6 relative"><Search className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-500" size={20} />
        <input className="w-full bg-slate-900 border border-slate-800 p-4 pl-12 rounded-2xl text-white outline-none focus:border-blue-500 transition-all"
          placeholder="Search product name or SKU..." value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)} /></div>

      <div className="bg-slate-900 rounded-3xl border border-slate-800 overflow-hidden shadow-2xl">
        <table className="w-full text-left"><thead className="bg-slate-800/50"><tr className="text-slate-400 text-[10px] font-black uppercase tracking-[0.2em]">
          <th className="p-5">Product Details</th><th className="p-5 text-right">Unit Price</th><th className="p-5 text-right">Stock</th><th className="p-5 text-center">Manage</th>
        </tr></thead><tbody className="divide-y divide-slate-800">
          {products.map((p) => <tr key={p.id} className="hover:bg-slate-800/30 transition group">
            <td className="p-5"><div className="font-bold text-white group-hover:text-blue-400">{p.name}</div><div className="text-[10px] text-slate-500 font-mono mt-1 uppercase tracking-wider">{p.sku || 'NO SKU'}</div></td>
            <td className="p-5 text-right font-black text-blue-400">KES {Number(p.price).toLocaleString()}</td>
            <td className="p-5 text-right"><span className="px-3 py-1 rounded-lg text-[10px] font-black uppercase tracking-widest bg-green-500/10 text-green-500 border border-green-500/20">{p.stock_level} units</span></td>
            <td className="p-5 text-center"><div className="flex justify-center space-x-2">
              <button onClick={() => handleOpenModal(p)} className="p-2 bg-slate-800 rounded-lg text-slate-400 hover:text-white"><Pencil size={16} /></button>
              <button onClick={() => handleDelete(p.id)} className="p-2 bg-slate-800 rounded-lg text-slate-400 hover:text-red-500"><Trash2 size={16} /></button>
            </div></td>
          </tr>)}
        </tbody></table>
        {products.length === 0 && !loading && <div className="p-20 text-center flex flex-col items-center"><Package size={64} className="text-slate-800 mb-4" /><p className="text-slate-500 font-bold uppercase tracking-widest text-sm">Inventory Archive Empty — create your first product</p></div>}
      </div>

      {showModal && <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center z-[100] p-4"><div className="bg-slate-900 border border-slate-800 rounded-3xl p-8 w-full max-w-lg shadow-2xl">
        <h3 className="text-2xl font-black mb-8 text-white tracking-tighter uppercase italic">{editingProduct ? 'Update Stock Item' : 'New Inventory Record'}</h3>
        <form onSubmit={handleSubmit} className="space-y-5">
          {[
            ['name','Part Name','text'], ['sku','SKU / Barcode','text'], ['price','Selling Price','number'],
            ['cost_price','Cost Price','number'], ['stock_level','Opening Stock','number'], ['low_stock_threshold','Low Stock Alert','number']
          ].map(([key,label,type]) => <div key={key}><label className="block text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">{label}</label>
            <input required={['name','price','cost_price'].includes(key)} type={type} min={type === 'number' ? '0' : undefined}
              className="w-full bg-slate-950 border border-slate-800 p-4 rounded-xl text-white outline-none focus:border-blue-500"
              value={formData[key]} onChange={(e) => setFormData({...formData, [key]: e.target.value})} /></div>)}
          <div className="flex space-x-3 pt-4"><button type="button" onClick={() => setShowModal(false)} className="flex-1 bg-slate-800 text-slate-400 py-4 rounded-2xl font-bold uppercase">Discard</button>
            <button type="submit" className="flex-1 bg-blue-600 text-white py-4 rounded-2xl font-black uppercase">Save Item</button></div>
          <label className="flex items-center gap-3 text-sm text-slate-300">
            <input type="checkbox" checked={formData.track_inventory} onChange={(e) => setFormData({ ...formData, track_inventory: e.target.checked })} />
            Track inventory for this product
          </label>
        </form>
      </div></div>}
    </div>
  );
};
export default Inventory;