import React, { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import api, { apiError } from '../services/api';

/** Public page where an invited organization owner sets their own password. */
export default function AcceptInvite() {
  const [params] = useSearchParams();
  const uid = params.get('uid');
  const token = params.get('token');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    if (password !== confirm) { setError('The two passwords do not match.'); return; }
    setBusy(true);
    try {
      await api.post('/platform/invites/accept/', { uid, token, password });
      setDone(true);
    } catch (err) {
      setError(apiError(err, 'Could not set the password.'));
    } finally {
      setBusy(false);
    }
  };

  const invalid = !uid || !token;
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 p-4">
      <div className="w-full max-w-sm rounded-2xl border border-slate-800 bg-slate-900 p-6">
        <h1 className="mb-1 text-xl font-black text-white">Set your password</h1>
        <p className="mb-5 text-sm text-slate-500">Choose a password to activate your ZenPOS account.</p>
        {invalid && <p className="text-sm text-red-400">This invite link is incomplete. Ask your administrator for a new one.</p>}
        {done && (
          <div>
            <p className="mb-4 text-sm text-green-400">Password set. You can now sign in.</p>
            <Link to="/login" className="btn-primary w-full">Go to sign in</Link>
          </div>
        )}
        {!invalid && !done && (
          <form onSubmit={submit} className="space-y-3">
            <input className="input" type="password" autoComplete="new-password" placeholder="New password (10+ characters)" value={password} onChange={(e) => setPassword(e.target.value)} required />
            <input className="input" type="password" autoComplete="new-password" placeholder="Confirm password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required />
            {error && <p className="text-sm text-red-400">{error}</p>}
            <button className="btn-primary w-full" disabled={busy}>{busy ? 'Saving…' : 'Set password'}</button>
          </form>
        )}
      </div>
    </div>
  );
}
