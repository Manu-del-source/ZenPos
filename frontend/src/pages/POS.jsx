import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Barcode, CheckCircle2, CreditCard, Minus, Package, Plus, Search, Smartphone, Trash2, UserRound, Wallet } from 'lucide-react';
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
  const [customers, setCustomers] = useState([]);
  const [customerId, setCustomerId] = useState('');
  const [screen, setScreen] = useState('sale');
  const [paymentMethod, setPaymentMethod] = useState('');
  const searchRef = useRef(null);

  const total = getTotal();
  const cash = Number(cashReceived || 0);
  const change = Math.max(0, cash - total);

  const loadProducts = async (term = '') => {
    setLoadingProducts(true);
    try {
      const { data } = await api.get('/products/', { params: { search: term, page_size: 100 } });
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
    api.get('/customers/', { params: { page_size: 100 } })
      .then(({ data }) => setCustomers(Array.isArray(data) ? data : (data.results || [])))
      .catch(() => {});
  }, []);

  const scanBarcode = async () => {
    const barcode = searchTerm.trim();
    if (!barcode) return;
    try {
      const { data } = await api.get('/products/search/', { params: { barcode } });
      if (data?.id) {
        addProduct(data);
        setSearchTerm('');
        searchRef.current?.focus();
      }
    } catch {
      toast.error('No product found for that barcode.');
    }
  };

  const printReceipt = async (saleId) => {
    try {
      const { data } = await api.get(`/sales/${saleId}/receipt/?paper=80mm`, { responseType: 'text' });
      const printWindow = window.open('', '_blank', 'width=480,height=760');
      if (!printWindow) {
        toast.error('Allow pop-ups to print the receipt.');
        return;
      }
      printWindow.document.open();
      printWindow.document.write(data);
      printWindow.document.close();
      printWindow.focus();
      printWindow.onload = () => printWindow.print();
    } catch {
      toast.error('Could not prepare the receipt.');
    }
  };

  const visibleProducts = useMemo(
    () => products.filter((product) => product.is_active !== false),
    [products]
  );

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

  const createSaleNumber = () => {
    const suffix = typeof crypto !== 'undefined' && crypto.randomUUID
      ? crypto.randomUUID().replace(/-/g, '').slice(0, 8).toUpperCase()
      : Math.random().toString(36).slice(2, 10).toUpperCase();
    return `SALE-${Date.now()}-${suffix}`;
  };

  const completeCashSale = async () => {
    if (!cart.length || cash < total) return;
    setCheckoutLoading(true);
    try {
      const { data: sale } = await api.post('/sales/', {
        sale_number: createSaleNumber(),
        payment_method: 'CASH',
        customer: customerId || null,
        items: cart.map((item) => ({ product: item.id, quantity: item.quantity })),
      });
      toast.success(`Cash sale completed. Change: KES ${money(change)}`);
      await printReceipt(sale.id);
      clearCart();
      setCashReceived('');
      setPaymentMethod('');
      setScreen('sale');
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
        customer: customerId || null,
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
          await printReceipt(sale.id);
          clearCart();
          setPhone('');
          setPaymentMethod('');
          setScreen('sale');
          await loadProducts(searchTerm);
          return;
        }
        if (current.status === 'FAILED') {
          toast.error('M-Pesa payment failed or was cancelled. The reserved stock has been released.');
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

  const openCheckout = () => {
    if (cart.length) setScreen('checkout');
  };

  return (
    <div className="page-shell !max-w-none">
      {screen === 'checkout' && (
        <section className="fixed inset-0 z-50 overflow-y-auto bg-slate-950 p-4 sm:p-8">
          <div className="mx-auto max-w-5xl">
            <div className="mb-5 flex items-center justify-between gap-4">
              <div>
                <div className="eyebrow">Front Office / Checkout</div>
                <h1 className="page-title">Review Sale</h1>
                <p className="page-subtitle">Confirm the order before taking payment.</p>
              </div>
              <button className="btn-secondary" onClick={() => setScreen('sale')}>← Back to sale</button>
            </div>
            <div className="panel overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-slate-950 text-left text-xs uppercase text-slate-500">
                    <tr><th className="p-4">Code</th><th className="p-4">Product</th><th className="p-4">Unit</th><th className="p-4">Qty</th><th className="p-4 text-right">Total</th></tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800">
                    {cart.map((item) => (
                      <tr key={item.id}>
                        <td className="p-4 text-slate-500">{item.sku}</td>
                        <td className="p-4 font-medium text-white">{item.name}</td>
                        <td className="p-4">KES {money(item.price)}</td>
                        <td className="p-4">{item.quantity}</td>
                        <td className="p-4 text-right font-semibold">KES {money(item.subtotal)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="border-t border-slate-800 p-6">
                <div className="flex items-end justify-between gap-4">
                  <span className="text-sm uppercase text-slate-500">Amount Due</span>
                  <strong className="text-4xl font-black text-white">KES {money(total)}</strong>
                </div>
                <div className="mt-6 grid gap-3 sm:grid-cols-2">
                  <button className="border border-slate-700 bg-slate-900 p-6 text-left hover:border-blue-500" onClick={() => { setPaymentMethod('CASH'); setScreen('payment'); }}>
                    <Wallet className="mb-3 text-blue-400" /><b className="block text-lg text-white">Cash</b><span className="text-sm text-slate-500">Enter cash received and calculate change.</span>
                  </button>
                  <button className="border border-slate-700 bg-slate-900 p-6 text-left hover:border-emerald-500" onClick={() => { setPaymentMethod('MPESA'); setScreen('payment'); }}>
                    <Smartphone className="mb-3 text-emerald-400" /><b className="block text-lg text-white">M-Pesa</b><span className="text-sm text-slate-500">Send STK Push and wait for confirmation.</span>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </section>
      )}

      {screen === 'payment' && (
        <section className="fixed inset-0 z-50 overflow-y-auto bg-slate-950 p-4 sm:p-8">
          <div className="mx-auto max-w-xl">
            <div className="mb-5 flex items-center justify-between gap-4">
              <div><div className="eyebrow">Front Office / Payment</div><h1 className="page-title">{paymentMethod === 'CASH' ? 'Cash Payment' : 'M-Pesa Payment'}</h1></div>
              <button className="btn-secondary" disabled={checkoutLoading} onClick={() => setScreen('checkout')}>← Back</button>
            </div>
            <div className="panel p-6">
              <div className="mb-6 text-center"><span className="text-xs uppercase text-slate-500">Amount Due</span><div className="text-4xl font-black text-white">KES {money(total)}</div></div>
              {paymentMethod === 'CASH' ? (
                <>
                  <label className="text-xs font-semibold text-slate-400">Cash received</label>
                  <input autoFocus type="number" min="0" className="input mt-2 h-14 text-xl" value={cashReceived} onChange={(e) => setCashReceived(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && cash >= total) completeCashSale(); }} placeholder="0.00" />
                  <div className="my-7 border-y border-slate-800 py-6 text-center"><span className="text-xs uppercase text-slate-500">Change</span><div className={cash >= total ? 'text-4xl font-black text-emerald-400' : 'text-4xl font-black text-red-400'}>KES {money(change)}</div></div>
                  <button className="w-full bg-blue-600 p-4 font-bold text-white disabled:opacity-40" disabled={checkoutLoading || cash < total} onClick={completeCashSale}>{checkoutLoading ? 'Completing…' : 'COMPLETE CASH SALE'}</button>
                </>
              ) : (
                <>
                  <label className="text-xs font-semibold text-slate-400">Customer M-Pesa phone</label>
                  <input autoFocus className="input mt-2 h-14 text-xl" value={phone} onChange={(e) => setPhone(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') completeMpesaSale(); }} placeholder="0712345678" />
                  <div className="my-7 border border-slate-800 bg-slate-950 p-6 text-center"><Smartphone className="mx-auto mb-3 text-emerald-400" size={32} /><p className="font-semibold text-white">Customer confirmation required</p><p className="mt-1 text-sm text-slate-500">An STK Push will be sent to this number.</p></div>
                  <button className="w-full bg-emerald-600 p-4 font-bold text-white disabled:opacity-40" disabled={checkoutLoading} onClick={completeMpesaSale}>{checkoutLoading ? 'Waiting for M-Pesa…' : 'SEND STK PUSH'}</button>
                </>
              )}
            </div>
          </div>
        </section>
      )}

      <div className="mb-5 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div><div className="eyebrow">Checkout</div><h1 className="page-title">Point of Sale</h1><p className="page-subtitle">Search products, build an order and collect payment.</p></div>
        <div className="flex items-center gap-2 text-xs text-slate-500"><span className="h-2 w-2 rounded-full bg-emerald-400" />Live catalogue</div>
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_390px]">
        <section className="panel min-h-[680px] overflow-hidden">
          <div className="border-b border-slate-800 p-4">
            <div className="relative">
              <Search size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-500" />
              <input ref={searchRef} className="input pl-11 pr-11" placeholder="Search product name or scan barcode…" value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); scanBarcode(); } }} />
              <button type="button" onClick={scanBarcode} aria-label="Scan barcode" className="absolute right-3 top-1/2 -translate-y-1/2 rounded-md p-1 text-slate-500 hover:bg-slate-800 hover:text-white"><Barcode size={18} /></button>
            </div>
          </div>
          <div className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-3">
            {loadingProducts ? <div className="col-span-full py-20 text-center text-slate-500">Loading catalogue…</div> : visibleProducts.length === 0 ? <div className="col-span-full py-20 text-center"><Package className="mx-auto mb-3 text-slate-600" size={36} /><p className="font-semibold text-slate-300">No products found</p><p className="mt-1 text-sm text-slate-500">Try another search or add products in Inventory.</p></div> : visibleProducts.map((product) => {
              const stock = Number(product.stock_level || 0);
              const out = product.track_inventory && stock <= 0;
              return <button key={product.id} disabled={out} onClick={() => addProduct(product)} className="rounded-2xl border border-slate-800 bg-slate-950/70 p-4 text-left transition hover:border-blue-500/50 hover:bg-slate-900 disabled:cursor-not-allowed disabled:opacity-50"><div className="mb-7 flex items-start justify-between gap-3"><span className="truncate text-xs font-medium text-slate-500">{product.sku}</span><Plus size={17} className="shrink-0 text-slate-600" /></div><p className="min-h-10 font-semibold text-slate-100">{product.name}</p><div className="mt-4 flex items-end justify-between gap-3"><span className="text-lg font-bold text-white">KES {money(product.price)}</span><span className={`text-xs font-medium ${out ? 'text-red-400' : stock <= product.low_stock_threshold ? 'text-amber-400' : 'text-emerald-400'}`}>{product.track_inventory ? `${stock} in stock` : 'Stock not tracked'}</span></div></button>;
            })}
          </div>
        </section>

        <aside className="panel flex min-h-[680px] flex-col overflow-hidden">
          <div className="flex items-center justify-between border-b border-slate-800 px-5 py-4"><div><h2 className="font-bold text-white">Current order</h2><p className="text-xs text-slate-500">{cart.length} line{cart.length === 1 ? '' : 's'}</p></div>{cart.length > 0 && <button className="text-xs font-semibold text-red-400 hover:text-red-300" onClick={clearCart}>Clear</button>}</div>
          <div className="flex-1 overflow-y-auto">
            {cart.length === 0 ? <div className="grid h-full min-h-80 place-items-center p-8 text-center"><div><div className="mx-auto mb-3 grid h-14 w-14 place-items-center rounded-2xl border border-slate-800 bg-slate-950"><Package className="text-slate-600" size={24} /></div><p className="font-semibold text-slate-300">Order is empty</p><p className="mt-1 text-sm text-slate-500">Select a product to start the sale.</p></div></div> : <div className="divide-y divide-slate-800/70">{cart.map((item) => <div key={item.id} className="p-4"><div className="flex gap-3"><div className="min-w-0 flex-1"><p className="truncate font-medium text-slate-200">{item.name}</p><p className="mt-1 text-xs text-slate-500">KES {money(item.price)} each</p></div><button className="text-slate-600 hover:text-red-400" onClick={() => removeFromCart(item.id)}><Trash2 size={16} /></button></div><div className="mt-3 flex items-center justify-between"><div className="flex items-center rounded-lg border border-slate-800 bg-slate-950"><button className="p-2 text-slate-400 hover:text-white" onClick={() => changeQuantity(item, -1)}><Minus size={14} /></button><span className="w-8 text-center text-sm font-semibold text-white">{item.quantity}</span><button className="p-2 text-slate-400 hover:text-white" onClick={() => changeQuantity(item, 1)}><Plus size={14} /></button></div><span className="font-semibold text-white">KES {money(item.subtotal)}</span></div></div>)}</div>}
          </div>
          <div className="border-t border-slate-800 bg-slate-950/50 p-5">
            <div className="mb-5 flex items-end justify-between"><span className="text-sm text-slate-500">Total</span><span className="text-2xl font-black text-white">KES {money(total)}</span></div>
            <div className="space-y-3">
              <label className="block"><span className="mb-1.5 block text-xs font-semibold text-slate-400">Customer</span><div className="relative"><UserRound size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" /><select className="input pl-10" value={customerId} onChange={(e) => setCustomerId(e.target.value)}><option value="">Walk-in customer</option>{customers.map((customer) => <option key={customer.id} value={customer.id}>{customer.name} — {customer.phone}</option>)}</select></div></label>
              <button className="btn-primary w-full !bg-blue-600 hover:!bg-blue-500" disabled={checkoutLoading || !cart.length} onClick={openCheckout}>Proceed to Checkout</button>
              <div className="grid grid-cols-2 gap-3"><button className="btn-secondary" disabled={checkoutLoading || !cart.length || cash < total} onClick={completeCashSale}>{cash >= total && cart.length ? <CheckCircle2 size={17} /> : <CreditCard size={17} />}Cash</button><button className="btn-primary !bg-emerald-600 hover:!bg-emerald-500" disabled={checkoutLoading || !cart.length} onClick={() => { setPaymentMethod('MPESA'); setScreen('payment'); }}><Smartphone size={17} />M-Pesa</button></div>
              <label className="block"><span className="mb-1.5 block text-xs font-semibold text-slate-400">Cash received</span><div className="relative"><Wallet size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" /><input type="number" min="0" className="input pl-10" placeholder="0.00" value={cashReceived} onChange={(e) => setCashReceived(e.target.value)} /></div></label>
              {cash > 0 && <div className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-900 px-3 py-2 text-sm"><span className="text-slate-500">Change</span><span className={cash >= total ? 'font-bold text-emerald-400' : 'font-bold text-red-400'}>KES {money(change)}</span></div>}
              <label className="block"><span className="mb-1.5 block text-xs font-semibold text-slate-400">M-Pesa phone</span><div className="relative"><Smartphone size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" /><input className="input pl-10" placeholder="0712345678" value={phone} onChange={(e) => setPhone(e.target.value)} /></div></label>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
