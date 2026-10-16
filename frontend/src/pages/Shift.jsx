import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Clock3, Wallet, RefreshCw, CheckCircle2, AlertTriangle, Banknote, Store } from 'lucide-react';
import toast from 'react-hot-toast';
import api, { apiError } from '../services/api';

const money = (value) => Number(value || 0).toLocaleString('en-KE', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export default function Shift({ user = {} }) {
  const [tills, setTills] = useState([]);
  const [selectedTillId, setSelectedTillId] = useState(() => localStorage.getItem('pos.till') || '');
  const [openingCash, setOpeningCash] = useState('0.00');
  const [countedCash, setCountedCash] = useState('');
  const [closeNotes, setCloseNotes] = useState('');
  const [lastClosed, setLastClosed] = useState(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  const selectedTill = useMemo(
    () => tills.find((till) => String(till.id) === String(selectedTillId)) || null,
    [tills, selectedTillId],
  );
  const openSession = selectedTill?.open_session || null;
  const ownOpenSession = openSession && openSession.opened_by === user.username ? openSession : null;
  const occupiedByOther = openSession && openSession.opened_by !== user.username;

  const loadTills = useCallback(async (preferredId) => {
    setLoading(true);
    try {
      const { data } = await api.get('/tills/', { params: { page_size: 100 } });
      const available = (data?.results || (Array.isArray(data) ? data : [])).filter((till) => till.is_active);
      setTills(available);
      const preferred = preferredId || localStorage.getItem('pos.till') || '';
      if (preferred && available.some((till) => String(till.id) === String(preferred))) {
        setSelectedTillId(String(preferred));
      } else if (available.length === 1) {
        setSelectedTillId(String(available[0].id));
      } else if (!available.length) {
        setSelectedTillId('');
      }
    } catch (error) {
      toast.error(apiError(error, 'Could not load tills. Ask an administrator to check your branch access.'));
      setTills([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadTills(); }, [loadTills]);

  const chooseTill = (id) => {
    setSelectedTillId(id);
    setLastClosed(null);
    const till = tills.find((item) => String(item.id) === String(id));
    if (till) {
      localStorage.setItem('pos.till', String(till.id));
      localStorage.setItem('pos.till.branch', String(till.branch));
      localStorage.setItem('pos.branch', String(till.branch));
    } else {
      localStorage.removeItem('pos.till');
      localStorage.removeItem('pos.till.branch');
    }
  };

  const openShift = async (event) => {
    event.preventDefault();
    if (!selectedTill) return toast.error('Select a till first.');
    setSubmitting(true);
    try {
      const { data } = await api.post('/cash-sessions/open/', {
        till: selectedTill.id,
        opening_cash: openingCash,
      });
      localStorage.setItem('pos.till', String(selectedTill.id));
      localStorage.setItem('pos.till.branch', String(selectedTill.branch));
      localStorage.setItem('pos.branch', String(selectedTill.branch));
      setLastClosed(null);
      toast.success('Shift opened. This till is now selected for POS sales.');
      await loadTills(selectedTill.id);
      setOpeningCash('0.00');
      setCountedCash('');
      setCloseNotes('');
      if (data?.id) localStorage.setItem('pos.cashSession', String(data.id));
    } catch (error) {
      toast.error(apiError(error, 'Could not open this shift.'));
      await loadTills(selectedTill.id);
    } finally {
      setSubmitting(false);
    }
  };

  const closeShift = async (event) => {
    event.preventDefault();
    if (!ownOpenSession) return toast.error('You can only close your own open shift.');
    setSubmitting(true);
    try {
      const { data } = await api.post(`/cash-sessions/${ownOpenSession.id}/close/`, {
        counted_cash: countedCash,
        notes: closeNotes.trim(),
      });
      setLastClosed(data);
      localStorage.removeItem('pos.till');
      localStorage.removeItem('pos.till.branch');
      localStorage.removeItem('pos.cashSession');
      toast.success('Shift closed. Review the cash variance below.');
      await loadTills(selectedTill.id);
      setCountedCash('');
      setCloseNotes('');
    } catch (error) {
      toast.error(apiError(error, 'Could not close this shift.'));
      await loadTills(selectedTill.id);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto min-h-screen max-w-5xl space-y-6 p-4 text-[#171715] sm:p-6 lg:p-8">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="mb-2 text-xs font-bold uppercase tracking-[0.2em] text-[#FF5938]">Cash control</p>
          <h1 className="text-3xl font-black tracking-tight text-white">My Shift</h1>
          <p className="mt-2 max-w-2xl text-sm text-slate-400">Open your till with a counted float, work sales through POS, then close with the physical cash count. ZenPOS calculates the expected amount and variance.</p>
        </div>
        <button type="button" onClick={() => loadTills(selectedTillId)} disabled={loading || submitting} className="btn-secondary flex items-center gap-2">
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} /> Refresh
        </button>
      </header>

      <section className="panel space-y-5 p-5 sm:p-6">
        <div className="flex items-center gap-3">
          <div className="grid h-11 w-11 place-items-center rounded-xl bg-slate-800 text-[#FF5938]"><Store size={21} /></div>
          <div>
            <h2 className="font-bold text-white">Register</h2>
            <p className="text-sm text-slate-400">Choose a till you are assigned to.</p>
          </div>
        </div>
        {loading && <p className="text-sm text-slate-400">Loading your tills…</p>}
        {!loading && tills.length === 0 && (
          <div className="flex items-start gap-3 rounded-xl border border-amber-800/60 bg-amber-500/10 p-4 text-sm text-amber-100">
            <AlertTriangle size={18} className="mt-0.5 shrink-0" />
            <p>No active till is available for your account. Ask a manager to create a till for your branch and confirm your branch access.</p>
          </div>
        )}
        {tills.length > 0 && (
          <label className="block max-w-xl">
            <span className="mb-2 block text-xs font-bold uppercase tracking-wider text-slate-400">Till</span>
            <select className="input" value={selectedTillId} onChange={(event) => chooseTill(event.target.value)}>
              <option value="">Select a till…</option>
              {tills.map((till) => (
                <option key={till.id} value={till.id}>
                  {till.branch_name} — {till.name}{till.open_session ? ` (open by ${till.open_session.opened_by})` : ''}
                </option>
              ))}
            </select>
          </label>
        )}
      </section>

      {selectedTill && ownOpenSession && (
        <section className="panel space-y-5 p-5 sm:p-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="mb-2 inline-flex items-center gap-2 rounded-full border border-emerald-800 bg-emerald-500/10 px-3 py-1 text-xs font-bold text-emerald-300">
                <CheckCircle2 size={14} /> Shift open
              </div>
              <h2 className="text-xl font-bold text-white">{selectedTill.branch_name} · {selectedTill.name}</h2>
              <p className="mt-1 text-sm text-slate-400">Opened {ownOpenSession.opened_at ? new Date(ownOpenSession.opened_at).toLocaleString() : ''}</p>
            </div>
            <div className="rounded-xl border border-slate-700 bg-slate-950 px-4 py-3">
              <p className="text-xs text-slate-500">Opening float</p>
              <p className="mt-1 text-xl font-black text-white">KES {money(ownOpenSession.opening_cash)}</p>
            </div>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-4 text-sm text-slate-300">
            Your POS sales will be assigned to this till while it remains selected. Cash sales and refunds are recorded in the drawer ledger automatically; M-Pesa does not increase the cash drawer.
          </div>
          <form onSubmit={closeShift} className="space-y-4 border-t border-slate-800 pt-5">
            <h3 className="font-bold text-white">Close shift</h3>
            <label className="block max-w-sm">
              <span className="mb-2 block text-xs font-bold uppercase tracking-wider text-slate-400">Physical cash counted (KES)</span>
              <input className="input" type="number" min="0" step="0.01" required value={countedCash} onChange={(event) => setCountedCash(event.target.value)} placeholder="e.g. 12500.00" />
            </label>
            <label className="block">
              <span className="mb-2 block text-xs font-bold uppercase tracking-wider text-slate-400">Notes (optional)</span>
              <textarea className="input min-h-24" maxLength={255} value={closeNotes} onChange={(event) => setCloseNotes(event.target.value)} placeholder="Explain any count discrepancy or handover note." />
            </label>
            <button type="submit" disabled={submitting || countedCash === ''} className="btn-primary flex items-center gap-2 !bg-[#FF5938] hover:!bg-[#E94A2B]">
              <Wallet size={17} /> {submitting ? 'Closing shift…' : 'Close shift and reconcile'}
            </button>
          </form>
        </section>
      )}

      {selectedTill && occupiedByOther && (
        <section className="panel flex items-start gap-3 border-amber-800/60 p-5 text-amber-100">
          <AlertTriangle size={20} className="mt-0.5 shrink-0" />
          <div><h2 className="font-bold">Till currently in use</h2><p className="mt-1 text-sm text-amber-100/80">An open shift belongs to {openSession.opened_by}. Select another till or ask a supervisor to handle the handover.</p></div>
        </section>
      )}

      {selectedTill && !openSession && (
        <section className="panel space-y-5 p-5 sm:p-6">
          <div>
            <h2 className="text-xl font-bold text-white">Open a shift</h2>
            <p className="mt-1 text-sm text-slate-400">Count the cash float before taking the first sale.</p>
          </div>
          <form onSubmit={openShift} className="space-y-4">
            <label className="block max-w-sm">
              <span className="mb-2 block text-xs font-bold uppercase tracking-wider text-slate-400">Opening float (KES)</span>
              <input className="input" type="number" min="0" step="0.01" required value={openingCash} onChange={(event) => setOpeningCash(event.target.value)} />
            </label>
            <button type="submit" disabled={submitting || !selectedTillId} className="btn-primary flex items-center gap-2 !bg-[#FF5938] hover:!bg-[#E94A2B]">
              <Clock3 size={17} /> {submitting ? 'Opening shift…' : 'Open shift'}
            </button>
          </form>
        </section>
      )}

      {lastClosed && (
        <section className="panel space-y-4 border-slate-700 p-5 sm:p-6" aria-live="polite">
          <div className="flex items-center gap-3"><CheckCircle2 size={22} className="text-emerald-400" /><h2 className="text-xl font-bold text-white">Shift reconciliation</h2></div>
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-xl bg-slate-950 p-4"><p className="text-xs text-slate-500">Expected cash</p><p className="mt-1 text-lg font-bold text-white">KES {money(lastClosed.expected_cash)}</p></div>
            <div className="rounded-xl bg-slate-950 p-4"><p className="text-xs text-slate-500">Counted cash</p><p className="mt-1 text-lg font-bold text-white">KES {money(lastClosed.counted_cash)}</p></div>
            <div className="rounded-xl bg-slate-950 p-4"><p className="text-xs text-slate-500">Variance</p><p className={`mt-1 text-lg font-black ${Number(lastClosed.cash_variance) < 0 ? 'text-red-400' : Number(lastClosed.cash_variance) > 0 ? 'text-amber-300' : 'text-emerald-400'}`}>KES {money(lastClosed.cash_variance)}</p></div>
          </div>
          <p className="text-sm text-slate-400">{Number(lastClosed.cash_variance) < 0 ? 'The drawer is short. Notify your supervisor and explain the difference.' : Number(lastClosed.cash_variance) > 0 ? 'The drawer is over. Notify your supervisor and explain the difference.' : 'The physical count matches the expected drawer balance.'}</p>
        </section>
      )}
    </div>
  );
}
