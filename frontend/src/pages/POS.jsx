import React, { useState, useEffect, useRef } from 'react';
import { usePOSStore } from '../store/posStore';
import api from '../services/api';
import toast from 'react-hot-toast';
import {
  ShoppingCart, CreditCard, Smartphone, Trash2,
  Plus, Minus, Search, Barcode, Package, Wallet
} from 'lucide-react';

const POS = () => {
  const { cart, addToCart, updateQuantity, removeFromCart, getTotal, clearCart } = usePOSStore();
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [phone, setPhone] = useState('');
  const [cashAmount, setCashAmount] = useState('');
  const searchInputRef = useRef(null);

  const total = getTotal();

  useEffect(() => {
    fetchProducts();
    if (searchInputRef.current) searchInputRef.current.focus();
  }, [searchTerm]);

  const fetchProducts = async () => {
    try {
      const { data } = await api.get('/products/', { params: { search: searchTerm } });
      const rows = Array.isArray(data) ? data : (data.results || []);
      setProducts(rows);

      if (
        searchTerm &&
        rows.length === 1 &&
        rows[0].sku?.toLowerCase() === searchTerm.toLowerCase()
      ) {
        addToCart(rows[0]);
        setSearchTerm('');
        toast.success(`Added ${rows[0].name}`);
      }
    } catch (err) {
      console.error(err);
      if (err.response?.status === 401 || err.response?.status === 403) {
        toast.error('Your session does not have catalogue access.');
      }
    }
  };

  const handleMpesa = async () => {
    toast.error('M-Pesa checkout is not connected to the Django payments flow yet.');
  };

  const completeCashSale = async () => {
    if (cart.length === 0) return;
    if (Number(cashAmount) < total) return toast.error('Insufficient cash');

    setLoading(true);
    try {
      const saleData = {
        payment_method: 'CASH',
        items: cart.map((item) => ({
          product: item.id,
          quantity: item.quantity,
        })),
      };

      await api.post('/sales/', saleData);

      const change = Number(cashAmount) - total;
      toast.success(
        `Sale Complete! Change: KES ${change.toLocaleString()}`,
        { duration: 5000 }
      );
      clearCart();
      setCashAmount('');
    } catch (err) {
      const detail = err.response?.data?.detail;
      const firstFieldError = err.response?.data && Object.values(err.response.data)[0];
      toast.error(
        typeof detail === 'string'
          ? detail
          : Array.isArray(firstFieldError)
            ? firstFieldError[0]
            : 'Sale failed. Please check stock and permissions.'
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="pos-main">
      <div className="selection-panel">
        <div className="search-bar-container">
          <div className="relative">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-500" />
            <input
              ref={searchInputRef}
              className="search-input"
              placeholder="Scan barcode or search product (SKU/name)..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
            <Barcode className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-700" />
          </div>
        </div>

        <div className="product-grid">
          {products.map((p) => (
            <div key={p.id} className="product-card" onClick={() => addToCart(p)}>
              <div>
                <div className="sku">{p.sku}</div>
                <div className="name uppercase tracking-tight">{p.name}</div>
              </div>
              <div>
                <div className="price">KES {Number(p.price).toLocaleString()}</div>
                <div className={`stock-badge mt-2 ${
                  p.stock_level > 10
                    ? 'stock-green'
                    : p.stock_level > 0
                      ? 'stock-yellow'
                      : 'stock-red'
                }`}>
                  {p.stock_level > 0 ? `${p.stock_level} IN STOCK` : 'OUT OF STOCK'}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="checkout-panel">
        <div className="cart-header">
          <h2 className="text-xl font-black italic flex items-center">
            <ShoppingCart className="mr-2 text-blue-500" size={24} /> CURRENT ORDER
            <span className="ml-3 bg-blue-600/20 text-blue-500 px-2 py-0.5 rounded-md text-xs">
              {cart.length} ITEMS
            </span>
          </h2>
          <button onClick={clearCart} className="text-xs font-bold text-red-500 uppercase hover:underline">Clear</button>
        </div>

        <div className="cart-table">
          {cart.map((item) => (
            <div key={item.id} className="cart-row">
              <div className="item-info">
                <div className="title uppercase text-xs truncate">{item.name}</div>
                <div className="price">KES {item.price}</div>
              </div>
              <div className="flex items-center space-x-2">
                <button onClick={() => updateQuantity(item.id, -1)} className="p-1 bg-slate-800 rounded-md"><Minus size={12} /></button>
                <span className="text-sm font-black w-4 text-center">{item.quantity}</span>
                <button onClick={() => updateQuantity(item.id, 1)} className="p-1 bg-slate-800 rounded-md"><Plus size={12} /></button>
              </div>
              <div className="flex justify-end">
                <button onClick={() => removeFromCart(item.id)} className="text-slate-600 hover:text-red-500"><Trash2 size={16} /></button>
              </div>
            </div>
          ))}
          {cart.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full opacity-10">
              <Package size={80} />
              <p className="font-bold mt-4">ORDER IS EMPTY</p>
            </div>
          )}
        </div>

        <div className="summary-card">
          <div className="total-row grand-total mb-6">
            <span className="text-sm font-bold text-slate-500 uppercase">Total to Pay</span>
            <span>KES {total.toLocaleString()}</span>
          </div>

          <div className="space-y-4">
            <div className="bg-slate-900 p-3 rounded-xl border border-slate-800">
              <label className="block text-[10px] font-black text-slate-500 uppercase mb-2 flex items-center">
                <Smartphone size={12} className="mr-1 text-green-500" /> M-PESA Customer Phone
              </label>
              <input
                className="w-full bg-transparent border-none p-0 text-white font-bold outline-none"
                placeholder="07XX XXX XXX"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
              />
            </div>

            <div className="bg-slate-900 p-3 rounded-xl border border-slate-800">
              <label className="block text-[10px] font-black text-slate-500 uppercase mb-2 flex items-center">
                <Wallet size={12} className="mr-1 text-blue-500" /> Cash Received
              </label>
              <input
                type="number"
                className="w-full bg-transparent border-none p-0 text-white font-bold outline-none"
                placeholder="Enter amount"
                value={cashAmount}
                onChange={(e) => setCashAmount(e.target.value)}
              />
            </div>

            <div className="grid grid-cols-1 gap-3">
              <button
                disabled={loading || cart.length === 0}
                onClick={handleMpesa}
                className="btn-checkout btn-mpesa shadow-lg shadow-green-900/20"
              >
                <Smartphone className="mr-2" size={20} /> M-PESA STK PUSH
              </button>
              <button
                disabled={loading || cart.length === 0 || !cashAmount}
                onClick={completeCashSale}
                className="btn-checkout btn-cash shadow-lg shadow-blue-900/20"
              >
                <CreditCard className="mr-2" size={20} /> COMPLETE CASH SALE
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default POS;
