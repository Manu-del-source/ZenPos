import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle, Barcode, CheckCircle2, ChevronLeft, CreditCard, Minus, Package,
  Plus, Printer, RefreshCw, Search, Smartphone, Trash2, UserRound, Wallet, X,
} from 'lucide-react';
import toast from 'react-hot-toast';
import api, { apiError } from '../services/api';
import { usePOSStore } from '../store/posStore';

const money = (value) => Number(value || 0).toLocaleString('en-KE', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const PRODUCT_PAGE_SIZE = 100;
const CUSTOMER_PAGE_SIZE = 200;
const MPESA_POLL_INTERVAL_MS = 2000;
const MPESA_POLL_ATTEMPTS = 30;
// The API refuses a second STK push for five minutes after one is issued; the
// till should say so rather than let the cashier discover it as an error.
const STK_PENDING_WINDOW_MS = 5 * 60 * 1000;

const DRAFT_KEY = 'zenpos.pos.draft';

const newClientReference = () => {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID();
  return `ref-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
};

const readDraft = () => {
  try {
    return JSON.parse(sessionStorage.getItem(DRAFT_KEY) || 'null');
  } catch {
    return null;
  }
};

const writeDraft = (draft) => {
  if (draft) sessionStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
  else sessionStorage.removeItem(DRAFT_KEY);
};

const isTypingTarget = (target) =>
  target instanceof HTMLElement &&
  (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT');

/**
 * Print through a hidden iframe.
 *
 * A popup window is blocked by default in most browsers and the cashier has to
 * discover that during a sale. An iframe in the page cannot be blocked, and the
 * receipt endpoint needs the Authorization header, so the HTML is fetched with
 * axios and written in.
 */
const printHtml = (html) => {
  const frame = document.createElement('iframe');
  frame.setAttribute('aria-hidden', 'true');
  frame.style.position = 'fixed';
  frame.style.right = '0';
  frame.style.bottom = '0';
  frame.style.width = '0';
  frame.style.height = '0';
  frame.style.border = '0';
  document.body.appendChild(frame);
  frame.contentWindow.document.open();
  frame.contentWindow.document.write(html);
  frame.contentWindow.document.close();
  frame.onload = () => {
    frame.contentWindow.focus();
    frame.contentWindow.print();
    setTimeout(() => frame.remove(), 1000);
  };
};

const Shortcuts = ({ open, onClose }) => {
  if (!open) return null;
  const rows = [
    ['F1', 'Show this list'],
    ['F2', 'Focus search / barcode box'],
    ['Enter', 'In search: add the scanned product'],
    ['F3', 'Take cash payment'],
    ['F4', 'Send an M-Pesa STK push'],
    ['F8', 'Confirm the payment on screen'],
    ['Esc', 'Go back one step'],
  ];
  return (
    <div className="fixed inset-0 z-[80] grid place-items-center bg-slate-950/80 p-4" role="dialog">
      <div className="panel w-full max-w-md">
        <div className="panel-header">
          <h2 className="panel-title">Keyboard shortcuts</h2>
          <button className="btn-secondary !px-3" onClick={onClose} aria-label="Close"><X size={16} /></button>
        </div>
        <dl className="divide-y divide-slate-800">
          {rows.map(([key, label]) => (
            <div key={key} className="flex items-center justify-between px-5 py-3">
              <dt className="text-sm text-slate-300">{label}</dt>
              <dd><kbd className="kbd">{key}</kbd></dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  );
};

export default function POS() {
  const cart = usePOSStore((state) => state.cart);
  const addToCart = usePOSStore((state) => state.addToCart);
  const setQuantity = usePOSStore((state) => state.setQuantity);
  const updateQuantity = usePOSStore((state) => state.updateQuantity);
  const removeFromCart = usePOSStore((state) => state.removeFromCart);
  const clearCart = usePOSStore((state) => state.clearCart);
  const getTotal = usePOSStore((state) => state.getTotal);
  const getCount = usePOSStore((state) => state.getCount);
  const getQuantityFor = usePOSStore((state) => state.getQuantityFor);

  const [products, setProducts] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [loadingProducts, setLoadingProducts] = useState(true);
  const [customers, setCustomers] = useState([]);
  const [branches, setBranches] = useState([]);
  const [me, setMe] = useState(null);
  const [branchId, setBranchId] = useState(() => localStorage.getItem('pos.branch') || '');
  const [customerId, setCustomerId] = useState('');
  const [step, setStep] = useState('sale');
  const [method, setMethod] = useState('');
  const [phone, setPhone] = useState('');
  const [cashReceived, setCashReceived] = useState('');
  const [busy, setBusy] = useState(false);
  const [statusMessage, setStatusMessage] = useState('');
  const [outcome, setOutcome] = useState(null);
  const [showShortcuts, setShowShortcuts] = useState(false);

  const searchRef = useRef(null);
  const clientRef = useRef(null);
  const saleRef = useRef(null);
  const pollTimer = useRef(null);
  const mounted = useRef(true);

  const total = getTotal();
  const lineCount = getCount();
  const cash = Number(cashReceived || 0);
  const change = Math.max(0, cash - total);
  const cashShort = cash > 0 && cash < total;

  const stopPolling = useCallback(() => {
    if (pollTimer.current) {
      clearTimeout(pollTimer.current);
      pollTimer.current = null;
    }
  }, []);

  const loadProducts = useCallback(async (term = '') => {
    setLoadingProducts(true);
    try {
      const { data } = await api.get('/products/', {
        params: { search: term || undefined, page_size: PRODUCT_PAGE_SIZE },
      });
      setProducts(data?.results || (Array.isArray(data) ? data : []));
    } catch (error) {
      toast.error(apiError(error, 'Could not load the catalogue.'));
    } finally {
      setLoadingProducts(false);
    }
  }, []);

  const resetSale = useCallback(() => {
    stopPolling();
    writeDraft(null);
    clientRef.current = null;
    saleRef.current = null;
    clearCart();
    setCashReceived('');
    setPhone('');
    setMethod('');
    setCustomerId('');
    setOutcome(null);
    setStatusMessage('');
    setStep('sale');
    searchRef.current?.focus();
  }, [clearCart, stopPolling]);

  // --- initial data ------------------------------------------------------
  useEffect(() => {
    mounted.current = true;
    api.get('/auth/me/')
      .then(({ data }) => {
        setMe(data);
        localStorage.setItem('user', JSON.stringify(data));
        const ids = data?.branch_ids || [];
        if (!branchId && data?.default_branch) setBranchId(data.default_branch);
        else if (!branchId && ids.length === 1) setBranchId(ids[0]);
      })
      .catch(() => setMe(null));

    api.get('/branches/', { params: { page_size: 100 } })
      .then(({ data }) => setBranches(data?.results || []))
      .catch(() => setBranches([]));

    api.get('/customers/', { params: { page_size: CUSTOMER_PAGE_SIZE } })
      .then(({ data }) => setCustomers(data?.results || []))
      .catch(() => setCustomers([]));

    return () => {
      mounted.current = false;
      stopPolling();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => loadProducts(searchTerm), 250);
    return () => clearTimeout(timer);
  }, [searchTerm, loadProducts]);

  useEffect(() => {
    if (branchId) localStorage.setItem('pos.branch', branchId);
  }, [branchId]);

  // --- payment status polling -------------------------------------------
  const pollPayment = useCallback(async (paymentId, saleId, attempt = 0) => {
    try {
      const { data } = await api.get(`/payments/${paymentId}/`);
      if (!mounted.current) return;

      if (data.status === 'COMPLETED') {
        writeDraft(null);
        clientRef.current = null;
        saleRef.current = null;
        setOutcome({
          status: 'paid',
          saleId,
          saleNumber: data.sale_number,
          total: Number(data.amount || 0),
          method: 'MPESA',
          reference: data.provider_reference,
        });
        setStep('done');
        clearCart();
        loadProducts(searchTerm);
        return;
      }

      if (data.status === 'FAILED') {
        writeDraft(null);
        setStatusMessage('');
        setOutcome({
          status: 'failed',
          saleId,
          message: 'The M-Pesa payment failed or was cancelled. Nothing was charged; the reserved stock has been returned.',
        });
        return;
      }

      if (attempt + 1 >= MPESA_POLL_ATTEMPTS) {
        setOutcome({
          status: 'stuck',
          saleId,
          paymentId,
          message: 'M-Pesa has not confirmed this payment yet. Check the message on the customer\'s phone, then check again.',
        });
        return;
      }

      pollTimer.current = setTimeout(
        () => pollPayment(paymentId, saleId, attempt + 1),
        MPESA_POLL_INTERVAL_MS,
      );
    } catch (error) {
      if (!mounted.current) return;
      setOutcome({
        status: 'stuck',
        saleId,
        paymentId,
        message: apiError(error, 'Could not read the payment status. Check the connection and try again.'),
      });
    }
  }, [clearCart, loadProducts, searchTerm]);

  // Resume an unfinished sale after a refresh: the sale and its payment exist
  // on the server, so the till must pick the thread back up rather than start
  // a second sale for the same basket.
  useEffect(() => {
    const draft = readDraft();
    if (!draft?.paymentId || !draft?.saleId) return;
    clientRef.current = draft.clientReference || null;
    saleRef.current = draft.saleId;
    setMethod('MPESA');
    setPhone(draft.phone || '');
    setStep('payment');
    setOutcome({ status: 'awaiting', saleId: draft.saleId, paymentId: draft.paymentId, message: 'Resuming the payment this till started before the page reloaded.' });
    pollPayment(draft.paymentId, draft.saleId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // --- cart --------------------------------------------------------------
  const addProduct = useCallback((product, quantity = 1) => {
    const already = getQuantityFor(product.id);
    if (product.track_inventory) {
      const stock = Number(product.stock_level || 0);
      if (stock <= 0) {
        toast.error(`${product.name} is out of stock.`);
        return;
      }
      if (already + quantity > stock) {
        toast.error(`Only ${stock} of ${product.name} in stock.`);
        return;
      }
    }
    addToCart(product, quantity);
  }, [addToCart, getQuantityFor]);

  const changeQuantity = (item, delta) => {
    if (delta > 0 && item.track_inventory && item.quantity + delta > Number(item.stock_level)) {
      toast.error(`Only ${item.stock_level} of ${item.name} in stock.`);
      return;
    }
    updateQuantity(item.id, delta);
  };

  const submitSearch = async () => {
    const term = searchTerm.trim();
    if (!term) return;

    try {
      const { data } = await api.get('/products/search/', { params: { barcode: term } });
      if (data?.id) {
        addProduct(data);
        setSearchTerm('');
        searchRef.current?.focus();
        return;
      }
    } catch (error) {
      if (error.response?.status !== 404) {
        toast.error(apiError(error, 'Barcode lookup failed.'));
        return;
      }
    }

    const exact = products.find(
      (product) => product.sku?.toLowerCase() === term.toLowerCase(),
    );
    if (exact) {
      addProduct(exact);
      setSearchTerm('');
      searchRef.current?.focus();
      return;
    }

    if (products.length === 1) {
      addProduct(products[0]);
      setSearchTerm('');
      searchRef.current?.focus();
      return;
    }

    toast.error(`No product matches “${term}”.`);
  };

  // --- checkout ----------------------------------------------------------
  const openReview = () => {
    if (!cart.length) return;
    if (!clientRef.current) clientRef.current = newClientReference();
    setStep('review');
  };

  const createSale = async (paymentMethod) => {
    if (!clientRef.current) clientRef.current = newClientReference();
    const payload = {
      client_reference: clientRef.current,
      payment_method: paymentMethod,
      customer: customerId || null,
      branch: branchId || null,
      items: cart.map((item) => ({ product: item.id, quantity: item.quantity })),
    };
    const { data } = await api.post('/sales/', payload);
    return data;
  };

  const payCash = async () => {
    if (!cart.length || cash < total || busy) return;
    if (outcome?.paymentId && outcome?.status !== 'paid') {
      toast.error('This basket already has an M-Pesa payment. Void it first, or wait for it to resolve.');
      return;
    }
    setBusy(true);
    setStatusMessage('Recording the sale…');
    try {
      const sale = await createSale('CASH');
      writeDraft(null);
      clientRef.current = null;
      saleRef.current = null;
      setOutcome({
        status: 'paid',
        saleId: sale.id,
        saleNumber: sale.sale_number,
        total: Number(sale.total_amount || total),
        method: 'CASH',
        cashReceived: cash,
        change: Math.max(0, cash - Number(sale.total_amount || total)),
      });
      setStep('done');
      clearCart();
      setStatusMessage('');
      await loadProducts(searchTerm);
    } catch (error) {
      setStatusMessage('');
      toast.error(apiError(error, 'The cash sale could not be recorded.'));
    } finally {
      setBusy(false);
    }
  };

  /**
   * Find a payment this sale already has.
   *
   * Used when a push request fails after the sale was created: the request may
   * have reached the server (and Safaricom) even though the response did not
   * come back. Asking the server beats guessing, and beats starting a second
   * charge for the same basket.
   */
  const recoverPendingPayment = async (saleId) => {
    if (!saleId) return null;
    try {
      const { data } = await api.get('/payments/', {
        params: { sale: saleId, status: 'PENDING' },
      });
      return (data?.results || [])[0] || null;
    } catch {
      return null;
    }
  };

  const sendStkPush = async (saleId) => {
    let sale = saleId;
    if (!sale) {
      const created = await createSale('MPESA');
      sale = created.id;
      // The sale exists on the server from here on. Remember it before the
      // push so a reload, or a retry, resumes this sale instead of creating a
      // second one and reserving the stock twice.
      saleRef.current = sale;
      writeDraft({ saleId: sale, phone, startedAt: Date.now() });
    }

    const { data: payment } = await api.post('/payments/', {
      sale,
      method: 'MPESA',
      phone,
    });
    if (!payment?.id) throw new Error('The server did not return a payment reference.');

    saleRef.current = sale;
    clientRef.current = null;
    writeDraft({ saleId: sale, paymentId: payment.id, phone, startedAt: Date.now() });
    setOutcome({ status: 'awaiting', saleId: sale, paymentId: payment.id });
    setStatusMessage('STK push sent. Ask the customer to enter their M-Pesa PIN.');
    pollPayment(payment.id, sale);
  };

  const payMpesa = async () => {
    const normalized = phone.replace(/\s+/g, '');
    if (!cart.length && !saleRef.current && !outcome?.saleId) return;
    if (!/^0(1|7)\d{8}$/.test(normalized)) {
      toast.error('Enter a valid Kenyan M-Pesa number, e.g. 0712345678.');
      return;
    }
    if (busy || outcome?.status === 'awaiting') return;

    setPhone(normalized);
    setBusy(true);
    setStatusMessage('Creating the sale and requesting the STK push…');
    const saleId = outcome?.saleId || saleRef.current || null;
    try {
      await sendStkPush(saleId);
    } catch (error) {
      setStatusMessage('');
      const message = apiError(error, 'The M-Pesa request could not be started.');
      const existing = await recoverPendingPayment(saleRef.current || saleId);
      if (existing) {
        // The push did reach the server: adopt it and keep watching rather
        // than telling the cashier it failed.
        saleRef.current = existing.sale;
        writeDraft({
          saleId: existing.sale,
          paymentId: existing.id,
          phone: normalized,
          startedAt: Date.now(),
        });
        setOutcome({ status: 'awaiting', saleId: existing.sale, paymentId: existing.id });
        setStatusMessage('A request for this sale is already with M-Pesa. Watching it now.');
        pollPayment(existing.id, existing.sale);
        return;
      }
      // A sale that exists but has no payment is money not taken: the cashier
      // retries the push on the same sale instead of ringing the basket again.
      setOutcome({
        status: 'failed',
        saleId: saleRef.current || saleId || null,
        message,
      });
      toast.error(message);
    } finally {
      setBusy(false);
    }
  };

  const retryPayment = () => {
    if (outcome?.status === 'stuck' && outcome?.paymentId && outcome?.saleId) {
      setOutcome({ status: 'awaiting', saleId: outcome.saleId, paymentId: outcome.paymentId });
      setStatusMessage('Checking the payment status again…');
      pollPayment(outcome.paymentId, outcome.saleId, MPESA_POLL_ATTEMPTS - 1);
      return;
    }
    payMpesa();
  };

  const voidSale = async () => {
    const saleId = outcome?.saleId;
    if (!saleId) {
      resetSale();
      return;
    }
    if (!window.confirm('Cancel this sale? Any reserved stock is returned and the sale is marked voided.')) return;
    try {
      await api.post(`/sales/${saleId}/void/`, { reason: 'Cancelled at the till' });
      toast.success('Sale voided.');
      resetSale();
      await loadProducts(searchTerm);
    } catch (error) {
      toast.error(apiError(error, 'The sale could not be voided. A supervisor may be required.'));
    }
  };

  const printReceipt = async () => {
    if (!outcome?.saleId) return;
    try {
      const { data } = await api.get(`/sales/${outcome.saleId}/receipt/?paper=80mm`, {
        responseType: 'text',
      });
      printHtml(data);
    } catch (error) {
      toast.error(apiError(error, 'The receipt could not be prepared.'));
    }
  };

  const enterCash = () => {
    if (outcome?.paymentId && outcome?.status !== 'paid') {
      toast.error('Finish or void the M-Pesa payment for this basket first.');
      return;
    }
    setMethod('CASH');
    setStatusMessage('');
    setOutcome(null);
    setStep('payment');
    setTimeout(() => document.getElementById('cash-received')?.focus(), 50);
  };

  const enterMpesa = () => {
    setMethod('MPESA');
    setStatusMessage('');
    setOutcome(null);
    setStep('payment');
    setTimeout(() => document.getElementById('mpesa-phone')?.focus(), 50);
  };

  // --- keyboard ----------------------------------------------------------
  useEffect(() => {
    const onKeyDown = (event) => {
      if (event.key === 'F1') {
        event.preventDefault();
        setShowShortcuts((open) => !open);
        return;
      }
      if (event.key === 'F2') {
        event.preventDefault();
        setStep('sale');
        searchRef.current?.focus();
        searchRef.current?.select();
        return;
      }
      if (event.key === 'Escape') {
        if (showShortcuts) { setShowShortcuts(false); return; }
        if (isTypingTarget(event.target) && step === 'sale') { setSearchTerm(''); return; }
        if (step === 'review') { setStep('sale'); return; }
        if (step === 'payment') {
          if (outcome?.status === 'awaiting') {
            toast.error('The M-Pesa request is still live. Wait for it, or cancel and void the sale.');
            return;
          }
          stopPolling();
          setStep('review');
          return;
        }
        return;
      }
      if (isTypingTarget(event.target) && !event.key.startsWith('F')) return;

      if (step === 'sale' || step === 'review') {
        if (event.key === 'F3') { event.preventDefault(); if (cart.length) enterCash(); }
        if (event.key === 'F4') { event.preventDefault(); if (cart.length) enterMpesa(); }
        if (event.key === 'F8' && step === 'sale' && cart.length) { event.preventDefault(); openReview(); }
      } else if (step === 'payment') {
        if (event.key === 'F8') {
          event.preventDefault();
          if (method === 'CASH') payCash();
          else if (outcome?.status !== 'awaiting') payMpesa();
        }
        if (event.key === 'F3' && method !== 'CASH') { event.preventDefault(); enterCash(); }
        if (event.key === 'F4' && method !== 'MPESA') { event.preventDefault(); enterMpesa(); }
      } else if (step === 'done') {
        if (event.key === 'F8') { event.preventDefault(); printReceipt(); }
        if (event.key === 'Enter') { event.preventDefault(); resetSale(); }
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, cart.length, method, outcome, showShortcuts, cash, total, busy, phone]);

  useEffect(() => {
    if (step === 'sale') searchRef.current?.focus();
  }, [step]);

  const visibleProducts = useMemo(
    () => products.filter((product) => product.is_active !== false),
    [products],
  );

  const branchOptions = useMemo(() => {
    const allowed = me?.branch_ids || [];
    const list = branches.filter((branch) => !allowed.length || allowed.includes(branch.id));
    return list;
  }, [branches, me]);

  const busyLabel = outcome?.status === 'awaiting' ? 'Waiting for M-Pesa…' : 'Working…';

  // --- screens -----------------------------------------------------------
  if (step === 'done' && outcome) {
    return (
      <div className="page-shell !max-w-3xl">
        <Shortcuts open={showShortcuts} onClose={() => setShowShortcuts(false)} />
        <section className="panel mt-6 overflow-hidden">
          <div className="border-b border-emerald-900/40 bg-emerald-500/10 px-6 py-5 text-center">
            <CheckCircle2 className="mx-auto mb-2 text-emerald-400" size={34} />
            <h1 className="text-xl font-black text-white">Sale completed</h1>
            <p className="mt-1 text-sm text-emerald-200/80">{outcome.saleNumber}</p>
          </div>
          <dl className="grid gap-4 p-6 sm:grid-cols-2">
            <div className="rounded-xl border border-slate-800 bg-slate-950 p-4">
              <dt className="text-xs uppercase tracking-wider text-slate-500">Total</dt>
              <dd className="mt-1 text-2xl font-black text-white">KES {money(outcome.total)}</dd>
            </div>
            <div className="rounded-xl border border-slate-800 bg-slate-950 p-4">
              <dt className="text-xs uppercase tracking-wider text-slate-500">
                {outcome.method === 'CASH' ? 'Change due' : 'M-Pesa reference'}
              </dt>
              <dd className="mt-1 text-2xl font-black text-white">
                {outcome.method === 'CASH'
                  ? `KES ${money(outcome.change ?? 0)}`
                  : (outcome.reference || 'Confirmed')}
              </dd>
            </div>
          </dl>
          <div className="flex flex-col gap-3 border-t border-slate-800 p-6 sm:flex-row">
            <button className="btn-primary flex-1" onClick={printReceipt}>
              <Printer size={17} /> Print receipt <kbd className="kbd kbd--dark">F8</kbd>
            </button>
            <button className="btn-secondary flex-1" onClick={resetSale}>
              New sale <kbd className="kbd kbd--dark">Enter</kbd>
            </button>
          </div>
        </section>
      </div>
    );
  }

  if (step === 'review') {
    return (
      <div className="page-shell !max-w-5xl">
        <Shortcuts open={showShortcuts} onClose={() => setShowShortcuts(false)} />
        <div className="mb-5 flex items-start justify-between gap-4">
          <div>
            <div className="eyebrow">Step 2 of 4 — Review sale</div>
            <h1 className="page-title">Review sale</h1>
            <p className="page-subtitle">{lineCount} item{lineCount === 1 ? '' : 's'} · confirm before taking payment.</p>
          </div>
          <button className="btn-secondary" onClick={() => setStep('sale')}>
            <ChevronLeft size={16} /> Back <kbd className="kbd kbd--dark">Esc</kbd>
          </button>
        </div>

        <section className="panel overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-950 text-left text-xs uppercase text-slate-500">
                <tr>
                  <th className="p-4">Code</th>
                  <th className="p-4">Product</th>
                  <th className="p-4 text-right">Unit</th>
                  <th className="p-4 text-right">Qty</th>
                  <th className="p-4 text-right">Line total</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {cart.map((item) => (
                  <tr key={item.id}>
                    <td className="p-4 font-mono text-xs text-slate-500">{item.sku || '—'}</td>
                    <td className="p-4 font-medium text-white">{item.name}</td>
                    <td className="p-4 text-right">KES {money(item.price)}</td>
                    <td className="p-4 text-right">{item.quantity}</td>
                    <td className="p-4 text-right font-semibold text-white">
                      KES {money(Number(item.price) * item.quantity)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="border-t border-slate-800 p-6">
            <div className="flex items-end justify-between gap-4">
              <span className="text-sm uppercase tracking-wide text-slate-500">Amount due</span>
              <strong className="text-4xl font-black text-white">KES {money(total)}</strong>
            </div>
            <div className="mt-6 grid gap-3 sm:grid-cols-2">
              <button className="payment-choice" onClick={enterCash}>
                <Wallet size={22} className="text-blue-400" />
                <span>
                  <b>Cash</b>
                  <small>Enter the cash received and see the change.</small>
                </span>
                <kbd className="kbd">F3</kbd>
              </button>
              <button className="payment-choice" onClick={enterMpesa}>
                <Smartphone size={22} className="text-emerald-400" />
                <span>
                  <b>M-Pesa</b>
                  <small>Send an STK push to the customer's phone.</small>
                </span>
                <kbd className="kbd">F4</kbd>
              </button>
            </div>
          </div>
        </section>
      </div>
    );
  }

  if (step === 'payment') {
    const awaiting = outcome?.status === 'awaiting';
    const failed = outcome?.status === 'failed';
    const stuck = outcome?.status === 'stuck';
    return (
      <div className="page-shell !max-w-3xl">
        <Shortcuts open={showShortcuts} onClose={() => setShowShortcuts(false)} />
        <div className="mb-5 flex items-start justify-between gap-4">
          <div>
            <div className="eyebrow">Step 3 of 4 — Payment</div>
            <h1 className="page-title">{method === 'MPESA' ? 'M-Pesa payment' : 'Cash payment'}</h1>
            <p className="page-subtitle">Amount due KES {money(total)}</p>
          </div>
          {awaiting ? (
            <button className="btn-secondary" onClick={voidSale} disabled={busy}>
              <X size={16} /> Cancel &amp; void
            </button>
          ) : (
            <button className="btn-secondary" onClick={() => { stopPolling(); setStep('review'); }} disabled={busy}>
              <ChevronLeft size={16} /> Back
            </button>
          )}
        </div>

        <div className="mb-4 grid grid-cols-2 gap-3">
          <button className={`method-tab ${method === 'CASH' ? 'method-tab--active' : ''}`} onClick={enterCash}>
            <Wallet size={17} /> Cash <kbd className="kbd">F3</kbd>
          </button>
          <button className={`method-tab ${method === 'MPESA' ? 'method-tab--active' : ''}`} onClick={enterMpesa}>
            <Smartphone size={17} /> M-Pesa <kbd className="kbd">F4</kbd>
          </button>
        </div>

        {statusMessage && (
          <div className="mb-4 flex items-start gap-3 rounded-xl border border-blue-900/50 bg-blue-500/10 px-4 py-3 text-sm text-blue-200">
            <RefreshCw size={16} className={awaiting ? 'mt-0.5 animate-spin' : 'mt-0.5'} />
            <span>{statusMessage}</span>
          </div>
        )}

        {(failed || stuck) && (
          <div className="mb-4 flex items-start gap-3 rounded-xl border border-amber-900/50 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
            <AlertTriangle size={16} className="mt-0.5 shrink-0" />
            <div>
              <p>{outcome.message}</p>
              {stuck && <p className="mt-1 text-xs text-amber-200/80">The sale stays on hold; stock remains reserved until it is confirmed or voided.</p>}
            </div>
          </div>
        )}

        <section className="panel p-6">
          {method === 'CASH' ? (
            <>
              <label className="text-xs font-semibold text-slate-400" htmlFor="cash-received">Cash received</label>
              <input
                id="cash-received"
                type="number"
                min="0"
                inputMode="decimal"
                className="input mt-2 h-14 text-xl"
                value={cashReceived}
                disabled={busy}
                onChange={(event) => setCashReceived(event.target.value)}
                onKeyDown={(event) => { if (event.key === 'Enter' && cash >= total) payCash(); }}
                placeholder="0.00"
              />
              <div className="mt-3 flex flex-wrap gap-2">
                {[50, 100, 200, 500, 1000].map((note) => (
                  <button key={note} className="btn-secondary !py-2" onClick={() => setCashReceived(String(note))} disabled={busy}>
                    +{note}
                  </button>
                ))}
                <button className="btn-secondary !py-2" onClick={() => setCashReceived(String(total))} disabled={busy}>
                  Exact
                </button>
              </div>
              <div className="my-6 border-y border-slate-800 py-5 text-center">
                <span className="text-xs uppercase tracking-wider text-slate-500">Change</span>
                <div className={cash >= total ? 'text-4xl font-black text-emerald-400' : 'text-4xl font-black text-red-400'}>
                  KES {money(change)}
                </div>
                {cashShort && <p className="mt-2 text-xs text-red-300">Cash received is less than the amount due.</p>}
              </div>
              <button
                className="btn-primary w-full !py-4"
                disabled={busy || cash < total}
                onClick={payCash}
              >
                {busy ? busyLabel : 'Complete cash sale'} <kbd className="kbd kbd--dark">F8</kbd>
              </button>
            </>
          ) : (
            <>
              <label className="text-xs font-semibold text-slate-400" htmlFor="mpesa-phone">Customer M-Pesa number</label>
              <input
                id="mpesa-phone"
                className="input mt-2 h-14 text-xl"
                value={phone}
                disabled={busy || awaiting}
                onChange={(event) => setPhone(event.target.value)}
                onKeyDown={(event) => { if (event.key === 'Enter') payMpesa(); }}
                placeholder="0712345678"
                inputMode="tel"
              />
              <div className="my-6 rounded-xl border border-slate-800 bg-slate-950 p-5 text-center">
                {awaiting ? (
                  <>
                    <RefreshCw className="mx-auto mb-3 animate-spin text-emerald-400" size={30} />
                    <p className="font-semibold text-white">Waiting for the customer to confirm</p>
                    <p className="mt-1 text-sm text-slate-500">Ask them to enter their M-Pesa PIN. This screen updates by itself.</p>
                  </>
                ) : (
                  <>
                    <Smartphone className="mx-auto mb-3 text-emerald-400" size={30} />
                    <p className="font-semibold text-white">An STK push will be sent to this number</p>
                    <p className="mt-1 text-sm text-slate-500">The sale is only completed once Safaricom confirms the payment.</p>
                  </>
                )}
              </div>
              <div className="flex flex-col gap-3 sm:flex-row">
                <button
                  className="btn-primary flex-1 !bg-emerald-600 hover:!bg-emerald-500 !py-4"
                  disabled={busy && !failed && !stuck}
                  onClick={failed || stuck ? retryPayment : payMpesa}
                >
                  {awaiting ? 'Waiting…' : failed || stuck ? 'Check again' : 'Send STK push'} <kbd className="kbd kbd--dark">F8</kbd>
                </button>
                {(failed || stuck) && (
                  <button className="btn-secondary" onClick={voidSale}>
                    Void sale
                  </button>
                )}
              </div>
              {(failed || stuck) && (
                <p className="mt-3 text-xs text-slate-500">
                  Retrying asks Safaricom again for the same sale. A new push can only be sent once the previous request has expired.
                </p>
              )}
            </>
          )}
        </section>
      </div>
    );
  }

  return (
    <div className="page-shell !max-w-none">
      <Shortcuts open={showShortcuts} onClose={() => setShowShortcuts(false)} />

      <div className="mb-5 flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="eyebrow">Step 1 of 4 — Current sale</div>
          <h1 className="page-title">Point of sale</h1>
          <p className="page-subtitle">Scan or search, then take payment.</p>
        </div>
        <div className="flex items-center gap-3 text-xs text-slate-500">
          <button className="btn-secondary !py-2" onClick={() => setShowShortcuts(true)}>
            Shortcuts <kbd className="kbd kbd--dark">F1</kbd>
          </button>
          {branchOptions.length > 1 && (
            <label className="flex items-center gap-2">
              <span className="uppercase tracking-wider">Branch</span>
              <select className="input !w-auto !py-2" value={branchId} onChange={(event) => setBranchId(event.target.value)}>
                <option value="">Select…</option>
                {branchOptions.map((branch) => (
                  <option key={branch.id} value={branch.id}>{branch.name}</option>
                ))}
              </select>
            </label>
          )}
        </div>
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_420px]">
        <section className="panel flex min-h-[620px] flex-col overflow-hidden">
          <div className="border-b border-slate-800 p-4">
            <div className="relative">
              <Search size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-500" />
              <input
                ref={searchRef}
                className="input !py-4 pl-11 pr-12 text-base"
                placeholder="Scan a barcode or type a product name or SKU…"
                value={searchTerm}
                onChange={(event) => setSearchTerm(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    event.preventDefault();
                    submitSearch();
                  }
                }}
                aria-label="Product search"
              />
              <button
                type="button"
                onClick={submitSearch}
                aria-label="Look up barcode"
                className="absolute right-3 top-1/2 -translate-y-1/2 rounded-md p-1.5 text-slate-500 hover:bg-slate-800 hover:text-white"
              >
                <Barcode size={19} />
              </button>
            </div>
          </div>

          <div className="grid flex-1 content-start gap-3 overflow-y-auto p-4 sm:grid-cols-2 lg:grid-cols-3">
            {loadingProducts ? (
              <div className="col-span-full py-20 text-center text-slate-500">Loading catalogue…</div>
            ) : visibleProducts.length === 0 ? (
              <div className="col-span-full py-16 text-center">
                <Package className="mx-auto mb-3 text-slate-600" size={36} />
                <p className="font-semibold text-slate-300">
                  {searchTerm ? 'No products match that search' : 'The catalogue is empty'}
                </p>
                <p className="mt-1 text-sm text-slate-500">
                  {searchTerm ? 'Check the spelling, or scan the barcode again.' : 'Add products in Inventory to start selling.'}
                </p>
              </div>
            ) : (
              visibleProducts.map((product) => {
                const stock = Number(product.stock_level || 0);
                const tracked = product.track_inventory;
                const out = tracked && stock <= 0;
                const inCart = getQuantityFor(product.id);
                return (
                  <button
                    key={product.id}
                    disabled={out}
                    onClick={() => addProduct(product)}
                    className={`product-tile ${out ? 'product-tile--out' : ''} ${inCart ? 'product-tile--in-cart' : ''}`}
                  >
                    <div className="mb-4 flex items-start justify-between gap-2">
                      <span className="truncate font-mono text-[11px] text-slate-500">{product.sku || '—'}</span>
                      {inCart ? <span className="cart-chip">{inCart}</span> : <Plus size={16} className="shrink-0 text-slate-600" />}
                    </div>
                    <p className="min-h-10 text-left font-semibold text-slate-100">{product.name}</p>
                    <div className="mt-3 flex items-end justify-between gap-2">
                      <span className="text-lg font-bold text-white">KES {money(product.price)}</span>
                      <span className={`text-xs font-medium ${out ? 'text-red-400' : stock <= Number(product.low_stock_threshold ?? 0) ? 'text-amber-400' : 'text-emerald-400'}`}>
                        {tracked ? (out ? 'Out of stock' : `${stock} in stock`) : 'Not stocked'}
                      </span>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </section>

        <aside className="panel flex min-h-[620px] flex-col overflow-hidden">
          <div className="flex items-center justify-between border-b border-slate-800 px-5 py-4">
            <div>
              <h2 className="font-bold text-white">Current sale</h2>
              <p className="text-xs text-slate-500">{lineCount} item{lineCount === 1 ? '' : 's'}</p>
            </div>
            {cart.length > 0 && (
              <button className="text-xs font-semibold text-red-400 hover:text-red-300" onClick={clearCart}>
                Clear
              </button>
            )}
          </div>

          <div className="flex-1 overflow-y-auto">
            {cart.length === 0 ? (
              <div className="grid h-full min-h-72 place-items-center p-8 text-center">
                <div>
                  <div className="mx-auto mb-3 grid h-14 w-14 place-items-center rounded-2xl border border-slate-800 bg-slate-950">
                    <Package className="text-slate-600" size={24} />
                  </div>
                  <p className="font-semibold text-slate-300">No items yet</p>
                  <p className="mt-1 text-sm text-slate-500">Scan a barcode or tap a product to begin.</p>
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
                      <button
                        className="shrink-0 text-slate-600 hover:text-red-400"
                        onClick={() => removeFromCart(item.id)}
                        aria-label={`Remove ${item.name}`}
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                    <div className="mt-3 flex items-center justify-between gap-2">
                      <div className="flex items-center rounded-lg border border-slate-800 bg-slate-950">
                        <button className="p-2 text-slate-400 hover:text-white" onClick={() => changeQuantity(item, -1)} aria-label="Fewer">
                          <Minus size={14} />
                        </button>
                        <input
                          type="number"
                          min="1"
                          className="w-14 border-0 bg-transparent text-center text-sm font-semibold text-white outline-none"
                          value={item.quantity}
                          onChange={(event) => setQuantity(item.id, event.target.value)}
                          aria-label={`Quantity for ${item.name}`}
                        />
                        <button className="p-2 text-slate-400 hover:text-white" onClick={() => changeQuantity(item, 1)} aria-label="More">
                          <Plus size={14} />
                        </button>
                      </div>
                      <span className="font-semibold text-white">KES {money(Number(item.price) * item.quantity)}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="border-t border-slate-800 bg-slate-950/50 p-5">
            <div className="mb-4 flex items-end justify-between">
              <span className="text-sm text-slate-500">Total</span>
              <span className="text-3xl font-black text-white">KES {money(total)}</span>
            </div>
            <label className="mb-4 block">
              <span className="mb-1.5 block text-xs font-semibold text-slate-400">Customer</span>
              <div className="relative">
                <UserRound size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
                <select className="input pl-10" value={customerId} onChange={(event) => setCustomerId(event.target.value)}>
                  <option value="">Walk-in customer</option>
                  {customers.map((customer) => (
                    <option key={customer.id} value={customer.id}>
                      {customer.name} — {customer.phone}
                    </option>
                  ))}
                </select>
              </div>
            </label>
            <button className="btn-primary w-full !py-4 !bg-blue-600 hover:!bg-blue-500" disabled={!cart.length} onClick={openReview}>
              <CreditCard size={18} /> Take payment <kbd className="kbd kbd--dark">F8</kbd>
            </button>
          </div>
        </aside>
      </div>
    </div>
  );
}
