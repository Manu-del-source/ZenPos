import React, { useEffect, useState } from 'react';
import api from '../services/api';
import toast from 'react-hot-toast';
import { Package, Plus, Pencil, Trash2, Search } from 'lucide-react';

const emptyForm = { name: '', sku: '', price: '', cost_price: '', stock_level: '', low_stock_threshold: 10, track_inventory: true, is_active: true };

const Inventory = ({ user = {} }) => {
  const roles = Array.isArray(user.roles) ? user.roles : [];
  const permissions = Array.isArray(user.permissions) ? user.permissions : [];
  const isPlatformAdmin = Boolean(user.is_superuser);
  const canCreateProducts = isPlatformAdmin || permissions.includes('products.create');
  const canUpdateProducts = isPlatformAdmin || permissions.includes('products.update');
  const canAdjustInventory = isPlatformAdmin || permissions.includes('inventory.adjust');
  const canManageProducts = canCreateProducts || canUpdateProducts;
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
    <div className="zen-inventory-page mx-auto min-h-screen max-w-7xl p-4 text-[#171715] sm:p-6 lg:p-8">
      <div className="flex justify-between items-center mb-8">
        <div><h1 className="text-3xl font-black tracking-tight">Inventory</h1>
          <p className="text-slate-500 text-sm">{canManageProducts ? 'Manage products, pricing and stock levels.' : 'View product names, selling prices and available stock.'}</p></div>
        {canCreateProducts && <button onClick={() => handleOpenModal()} className="btn-primary flex items-center">
          <Plus size={18} className="mr-2" /> Add product
        </button>}
      </div>
      <div className="mb-6 relative"><Search className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-500" size={20} />
        <input className="w-full rounded-xl border border-[#E4DED3] bg-white p-4 pl-12 text-[#171715] outline-none transition focus:border-[#FF5938]"
          placeholder="Search product name or SKU..." value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)} /></div>

      <div className="overflow-hidden rounded-2xl border border-[#E4DED3] bg-white shadow-sm">
        <div className="overflow-x-auto"><table className="w-full min-w-[680px] text-left"><thead className="bg-[#F1EDE4]"><tr className="text-slate-400 text-[10px] font-black uppercase tracking-[0.2em]">
          <th className="p-5">Product Details</th><th className="p-5 text-right">Unit Price</th><th className="p-5 text-right">Stock</th>{canManageProducts && <th className="p-5 text-center">Manage</th>}
        </tr></thead><tbody className="divide-y divide-slate-800">
          {products.map((p) => <tr key={p.id} className="group border-t border-[#EEE9DF] transition-colors hover:bg-[#FFFCF7]">
            <td className="p-5"><div className="font-bold text-white group-hover:text-blue-400">{p.name}</div><div className="text-[10px] text-slate-500 font-mono mt-1 uppercase tracking-wider">{p.sku || 'NO SKU'}</div></td>
            <td className="p-5 text-right font-black text-blue-400">KES {Number(p.price).toLocaleString()}</td>
            <td className="p-5 text-right"><span className={`inline-flex rounded-full border px-3 py-1 text-[10px] font-bold uppercase tracking-wider ${Number(p.stock_level || 0) <= Number(p.low_stock_threshold || 0) ? "border-amber-200 bg-amber-50 text-amber-700" : "border-emerald-200 bg-emerald-50 text-emerald-700"}`}>{p.stock_level} units</span></td>
            {canManageProducts && <td className="p-5 text-center"><div className="flex justify-center space-x-2">
              {canUpdateProducts && <button onClick={() => handleOpenModal(p)} aria-label={`Edit ${p.name}`} className="rounded-lg border border-[#E4DED3] bg-white p-2 text-[#756F66] transition hover:border-[#FF5938] hover:text-[#171715]"><Pencil size={16} /></button>}
              {canUpdateProducts && <button onClick={() => handleDelete(p.id)} aria-label={`Archive ${p.name}`} className="rounded-lg border border-[#E4DED3] bg-white p-2 text-[#756F66] transition hover:border-red-200 hover:text-red-600"><Trash2 size={16} /></button>}
            </div></td>}
          </tr>)}
        </tbody></table></div>
        {products.length === 0 && !loading && <div className="p-20 text-center flex flex-col items-center"><Package size={64} className="text-slate-800 mb-4" /><p className="text-slate-500 font-bold uppercase tracking-widest text-sm">Inventory Archive Empty — create your first product</p></div>}
      </div>

      {showModal && <div className="fixed inset-0 z-[100] flex items-center justify-center overflow-y-auto bg-black/50 p-4 backdrop-blur-sm"><div className="my-auto w-full max-w-lg rounded-2xl border border-[#E4DED3] bg-[#F7F4ED] p-5 shadow-2xl sm:p-8">
        <h3 className="text-2xl font-black mb-8 text-white tracking-tighter uppercase italic">{editingProduct ? 'Update Stock Item' : 'New Inventory Record'}</h3>
        <form onSubmit={handleSubmit} className="space-y-5">
          {[
            ['name','Part Name','text'], ['sku','SKU / Barcode','text'], ['price','Selling Price','number'],
            ...(canUpdateProducts || canCreateProducts ? [['cost_price','Cost Price','number']] : []),
            ...(canAdjustInventory ? [['stock_level','Opening Stock','number'], ['low_stock_threshold','Low Stock Alert','number']] : []),
          ].map(([key,label,type]) => <div key={key}><label className="block text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">{label}</label>
            <input required={['name','price','cost_price'].includes(key)} type={type} min={type === 'number' ? '0' : undefined}
              className="w-full rounded-xl border border-[#E4DED3] bg-white p-3.5 text-[#171715] outline-none focus:border-[#FF5938]"
              value={formData[key]} onChange={(e) => setFormData({...formData, [key]: e.target.value})} /></div>)}
          <div className="flex space-x-3 pt-4"><button type="button" onClick={() => setShowModal(false)} className="flex-1 bg-slate-800 text-slate-400 py-4 rounded-2xl font-bold uppercase">Discard</button>
            <button type="submit" className="flex-1 bg-blue-600 text-white py-4 rounded-2xl font-black uppercase">Save Item</button></div>
          {(canUpdateProducts || canCreateProducts) && <label className="flex items-center gap-3 text-sm text-slate-300">
            <input type="checkbox" checked={formData.track_inventory} onChange={(e) => setFormData({ ...formData, track_inventory: e.target.checked })} />
            Track inventory for this product
          </label>}
        </form>
      </div></div>}
    </div>
  );
};
export default Inventory;