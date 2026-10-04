import React from 'react';
import { Bell, Building2, LogOut, ShieldCheck, UserRound } from 'lucide-react';
import toast from 'react-hot-toast';

export default function Settings() {
  let user = {};
  try { user = JSON.parse(localStorage.getItem('user') || '{}'); } catch {}
  const organization = user?.organization_name || user?.organization?.name || 'ZenPOS Store';
  const signOut = () => {
    localStorage.removeItem('token'); localStorage.removeItem('refreshToken'); localStorage.removeItem('user');
    window.location.href = '/login';
  };
  return <div className="page-shell">
    <div><div className="eyebrow">Workspace configuration</div><h1 className="page-title">Settings</h1><p className="page-subtitle">Review the workspace and account connected to this terminal.</p></div>
    <div className="mt-6 grid gap-5 lg:grid-cols-2">
      <section className="panel"><div className="panel-header"><div><h2 className="panel-title">Workspace</h2><p className="panel-subtitle">Current organization context</p></div><Building2 size={18} className="text-blue-400"/></div><div className="space-y-4 p-5">
        <div className="rounded-xl border border-slate-800 bg-slate-950 p-4"><p className="text-xs uppercase tracking-wider text-slate-500">Organization</p><p className="mt-1 font-semibold text-white">{organization}</p></div>
        <div className="rounded-xl border border-slate-800 bg-slate-950 p-4"><p className="text-xs uppercase tracking-wider text-slate-500">Currency</p><p className="mt-1 font-semibold text-white">KES — Kenyan Shilling</p></div>
        <div className="rounded-xl border border-slate-800 bg-slate-950 p-4"><p className="text-xs uppercase tracking-wider text-slate-500">Timezone</p><p className="mt-1 font-semibold text-white">Africa/Nairobi</p></div>
      </div></section>
      <section className="panel"><div className="panel-header"><div><h2 className="panel-title">Your account</h2><p className="panel-subtitle">Signed-in staff identity</p></div><UserRound size={18} className="text-violet-400"/></div><div className="space-y-4 p-5">
        <div className="flex items-center gap-3 rounded-xl border border-slate-800 bg-slate-950 p-4"><div className="grid h-10 w-10 place-items-center rounded-full bg-slate-800 font-bold text-blue-400">{(user?.username || 'U').slice(0,1).toUpperCase()}</div><div><p className="font-semibold text-white">{user?.username || 'User'}</p><p className="text-xs text-slate-500">{user?.is_superuser ? 'Administrator' : 'Staff account'}</p></div></div>
        <div className="flex items-center gap-3 rounded-xl border border-slate-800 bg-slate-950 p-4"><ShieldCheck size={18} className="text-emerald-400"/><div><p className="font-semibold text-slate-200">Authenticated</p><p className="text-xs text-slate-500">JWT session is active on this device.</p></div></div>
        <button className="btn-secondary w-full !border-red-500/20 !text-red-400 hover:!bg-red-500/10" onClick={signOut}><LogOut size={17}/> Sign out</button>
      </div></section>
    </div>
    <section className="panel mt-5"><div className="panel-header"><div><h2 className="panel-title">Configuration modules</h2><p className="panel-subtitle">Modules not yet connected to editable settings.</p></div><Bell size={18} className="text-slate-500"/></div>
      <div className="grid gap-3 p-5 sm:grid-cols-3">{['Branch configuration','Tax & eTIMS','Payment provider'].map(item=><button key={item} className="rounded-xl border border-slate-800 bg-slate-950 p-4 text-left transition hover:border-slate-700" onClick={()=>toast('This module is not enabled yet.') }><p className="font-semibold text-slate-200">{item}</p><p className="mt-1 text-xs text-slate-500">Not enabled yet</p></button>)}</div>
    </section>
  </div>;
}