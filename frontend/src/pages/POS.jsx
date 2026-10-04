import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Barcode, CheckCircle2, CreditCard, Minus, Package, Plus, Search, Smartphone, Trash2, Wallet } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../services/api';
import { usePOSStore } from '../store/posStore';

const money = (value) => Number(value || 0).toLocaleString('en-KE', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export default function POS() {
  const { cart, addToCart, updateQuantity, removeFromCart, getTotal, clearCart } = usePOSStore();
  const [products, setProducts] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [loadingProducts, setLoadingProducts] = useState(true);
  const [checkoutLoading, setCheckoutLoading] = useState(false);
  const [phone, setPhone] = useState('');
  const [cashReceived, setCashReceived] = useState('');
  const searchRef = useRef(null);

  const total = getTotal();
  const cash = Number(cashReceived || 0);
  const change = Math.max(0, cash - total);

  const createSaleNumber = () => {
    const suffix = typeof crypto !== 'undefined' && crypto.randomUUID
      ? crypto.randomUUID().replace(/-/g, '').slice(0, 8).toUpperCase()
      : Math.random().toString(36).slice(2, 10).toUpperCase();
    return `SALE-${Date.now()}-${suffix}`;
  };

  const loadProducts = async (term = '') => {
    setLoadingProducts(true);
    try {
      const { data } = await api.get('/products/', {
        params: { search: term, page_size: 100 },
      });
      setProducts(Array.isArray(data) ? data : (data.results || []));
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not load products.');
    } finally {
      setLoadingProducts(false);
    }
  };

  useEffect(() => {
    const timer = setTimeout(() => loadProducts(searchTerm), 250);
    return () => clearTimeout(timer);
  }, [searchTerm]);

  useEffect(() => {
    searchRef.current?.focus();
  }, []);

  const visibleProducts = useMemo(() => products.filter((product) => product.is_active !== false), [products]);

  const addProduct = (product) => {
    const existing = cart.find((item) => item.id === product.id);
    const currentQty = existing?.quantity || 0;
    if (product.track_inventory && currentQty >= Number(product.stock_level || 0)) {
      toast.error(product.stock_level > 0 ? `Only ${product.stock_level} available.` : 'This product is out of stock.');
      return;
    }
    addToCart(product);
  };

  const changeQuantity = (item, delta) => {
    if (delta > 0 && item.track_inventory && item.quantity >= Number(item.stock_level)) {
      toast.error(`Only ${item.stock_level} available.`);
      return;
    }
    updateQuantity(item.id, delta);
  };

  const completeCashSale = async () => {
    if (!cart.length || cash < total) return;
    setCheckoutLoading(true);
    try {
      await api.post('/sales/', {
        sale_number: createSaleNumber(),
        payment_method: 'CASH',
        items: cart.map((item) => ({ product: item.id, quantity: item.quantity })),
      });
      toast.success(`Cash sale completed. Change: KES ${money(change)}`);
      clearCart();
      setCashReceived('');
      await loadProducts(searchTerm);
    } catch (err) {
      const data = err.response?.data;
      const detail = data?.detail || Object.values(data || {}).flat().find((value) => typeof value === 'string');
      toast.error(detail || 'Cash sale failed. Check stock and permissions.');
    } finally {
      setCheckoutLoading(false);
    }
  };

  const completeMpesaSale = async () => {
    const normalizedPhone = phone.replace(/\s+/g, '');
    if (!cart.length) return;
    if (!/^0(1|7)\d{8}$/.test(normalizedPhone)) {
      toast.error('Enter a valid Kenyan M-Pesa number, e.g. 0712345678.');
      return;
    }

    setCheckoutLoading(true);
    try {
      const { data: sale } = await api.post('/sales/', {
        sale_number: createSaleNumber(),
        payment_method: 'MPESA',
        items: cart.map((item) => ({ product: item.id, quantity: item.quantity })),
      });

      const { data: payment } = await api.post('/payments/', {
        sale: sale.id,
        method: 'MPESA',
        phone: normalizedPhone,
      });

      if (!payment?.id) throw new Error('Payment reference was not returned by the server.');

      toast.success('STK Push sent. Ask the customer to enter their M-Pesa PIN.', { duration: 5000 });

      for (let attempt = 0; attempt < 30; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 2000));
        const { data: current } = await api.get(`/payments/${payment.id}/`);

        if (current.status === 'COMPLETED') {
          toast.success('M-Pesa payment confirmed.');
          clearCart();
          setPhone('');
          await loadProducts(searchTerm);
          return;
        }

        if (current.status === 'FAILED') {
          toast.error('M-Pesa payment failed or was cancelled. The sale remains recorded for reconciliation.');
          return;
        }
      }

      toast.error('M-Pesa is still pending. Check Sales for the transaction status.');
    } catch (err) {
      const data = err.response?.data;
      const detail = data?.detail || Object.values(data || {}).flat().find((value) => typeof value === 'string');
      toast.error(detail || 'M-Pesa checkout failed.');
    } finally {
      setCheckoutLoading(false);
    }
  };

  return (
    <div className="page-shell !max-w-none">
      <div className="mb-5 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="eyebrow">Checkout</div>
          <h1 className="page-title">Point of Sale</h1>
          <p className="page-subtitle">Search products, build an order and collect payment.</p>
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <span className="h-2 w-2 rounded-full bg-emerald-400" />
          Live catalogue
        </div>
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_390px]">
        <section className="panel min-h-[680px] overflow-hidden">
          <div className="border-b border-slate-800 p-4">
            <div className="relative">
              <Search size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-500" />
              <input
                ref={searchRef}
                className="input pl-11 pr-11"
                placeholder="Search product name or SKU…"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
              <Barcode size={18} className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-600" />
            </div>
          </div>

          <div className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-3">
            {loadingProducts ? (
              <div className="col-span-full py-20 text-center text-slate-500">Loading catalogue…</div>
            ) : visibleProducts.length === 0 ? (
              <div className="col-span-full py-20 text-center">
                <Package className="mx-auto mb-3 text-slate-600" size={36} />
                <p className="font-semibold text-slate-300">No products found</p>
                <p className="mt-1 text-sm text-slate-500">Try another search or add products in Inventory.</p>
              </div>
            ) : visibleProducts.map((product) => {
              const stock = Number(product.stock_level || 0);
              const out = product.track_inventory && stock <= 0;
              return (
                <button
                  key={product.id}
                  disabled={out}
                  onClick={() => addProduct(product)}
                  className="rounded-2xl border border-slate-800 bg-slate-950/70 p-4 text-left transition hover:border-blue-500/50 hover:bg-slate-900 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <div className="mb-7 flex items-start justify-between gap-3">
                    <span className="truncate text-xs font-medium text-slate-500">{product.sku}</span>
                    <Plus size={17} className="shrink-0 text-slate-600" />
                  </div>
                  <p className="min-h-10 font-semibold text-slate-100">{product.name}</p>
                  <div className="mt-4 flex items-end justify-between gap-3">
                    <span className="text-lg font-bold text-white">KES {money(product.price)}</span>
                    <span className={`text-xs font-medium ${out ? 'text-red-400' : stock <= product.low_stock_threshold ? 'text-amber-400' : 'text-emerald-400'}`}>
                      {product.track_inventory ? `${stock} in stock` : 'Stock not tracked'}
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        </section>

        <aside className="panel flex min-h-[680px] flex-col overflow-hidden">
          <div className="flex items-center justify-between border-b border-slate-800 px-5 py-4">
            <div>
              <h2 className="font-bold text-white">Current order</h2>
              <p className="text-xs text-slate-500">{cart.length} line{cart.length === 1 ? '' : 's'}</p>
            </div>
            {cart.length > 0 && <button className="text-xs font-semibold text-red-400 hover:text-red-300" onClick={clearCart}>Clear</button>}
          </div>

          <div className="flex-1 overflow-y-auto">
            {cart.length === 0 ? (
              <div className="grid h-full min-h-80 place-items-center p-8 text-center">
                <div>
                  <div className="mx-auto mb-3 grid h-14 w-14 place-items-center rounded-2xl border border-slate-800 bg-slate-950">
                    <Package className="text-slate-600" size={24} />
                  </div>
                  <p className="font-semibold text-slate-300">Order is empty</p>
                  <p className="mt-1 text-sm text-slate-500">Select a product to start the sale.</p>
                </div>
              </div>
            ) : (
              <div className="divide-y divide-slate-800/70">
                {cart.map((item) => (
                  <div key={item.id} className="p-4">
                    <div className="flex gap-3">
                      <div className="min-w-0 flex-1">
                        <p className="truncate font-medium text-slate-200">{item.name}</p>
                        <p className="mt-1 text-xs text-slate-500">KES {money(item.price)} each</p>
                      </div>
                      <button className="text-slate-600 hover:text-red-400" onClick={() => removeFromCart(item.id)}>
                        <Trash2 size={16} />
                      </button>
                    </div>
                    <div className="mt-3 flex items-center justify-between">
                      <div className="flex items-center rounded-lg border border-slate-800 bg-slate-950">
                        <button className="p-2 text-slate-400 hover:text-white" onClick={() => changeQuantity(item, -1)}><Minus size={14} /></button>
                        <span className="w-8 text-center text-sm font-semibold text-white">{item.quantity}</span>
                        <button className="p-2 text-slate-400 hover:text-white" onClick={() => changeQuantity(item, 1)}><Plus size={14} /></button>
                      </div>
                      <span className="font-semibold text-white">KES {money(item.subtotal)}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="border-t border-slate-800 bg-slate-950/50 p-5">
            <div className="mb-5 flex items-end justify-between">
              <span className="text-sm text-slate-500">Total</span>
              <span className="text-2xl font-black text-white">KES {money(total)}</span>
            </div>

            <div className="space-y-3">
              <label className="block">
                <span className="mb-1.5 block text-xs font-semibold text-slate-400">M-Pesa phone</span>
                <div className="relative">
                  <Smartphone size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
                  <input className="input pl-10" placeholder="0712345678" value={phone} onChange={(e) => setPhone(e.target.value)} />
                </div>
              </label>

              <button className="btn-primary w-full !bg-emerald-600 hover:!bg-emerald-500" disabled={checkoutLoading || !cart.length} onClick={completeMpesaSale}>
                <Smartphone size={17} /> {checkoutLoading ? 'Processing…' : 'Pay with M-Pesa'}
              </button>

              <label className="block">
                <span className="mb-1.5 block text-xs font-semibold text-slate-400">Cash received</span>
                <div className="relative">
                  <Wallet size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
                  <input type="number" min="0" className="input pl-10" placeholder="0.00" value={cashReceived} onChange={(e) => setCashReceived(e.target.value)} />
                </div>
              </label>

              {cash > 0 && (
                <div className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-900 px-3 py-2 text-sm">
                  <span className="text-slate-500">Change</span>
                  <span className={cash >= total ? 'font-bold text-emerald-400' : 'font-bold text-red-400'}>
                    KES {money(change)}
                  </span>
                </div>
              )}

              <button className="btn-secondary w-full" disabled={checkoutLoading || !cart.length || cash < total} onClick={completeCashSale}>
                {cash >= total && cart.length ? <CheckCircle2 size={17} /> : <CreditCard size={17} />}
                Complete cash sale
              </button>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
