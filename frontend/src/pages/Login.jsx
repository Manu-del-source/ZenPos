import React, { useState } from 'react';
import api from '../services/api';
import { useNavigate } from 'react-router-dom';
import { Lock, User, ShieldCheck } from 'lucide-react';

const Login = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const navigate = useNavigate();

  const handleLogin = async (e) => {
    e.preventDefault();
    try {
      const res = await api.post('/login', { username, password });
      localStorage.setItem('token', res.data.token);
      localStorage.setItem('user', JSON.stringify(res.data.user));
      navigate('/pos');
      window.location.reload();
    } catch (err) {
      setError(err.response?.data?.detail || 'Authentication failed');
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-950">
      <div className="bg-slate-900 p-10 rounded-3xl border border-slate-800 shadow-2xl w-full max-w-md">
        <div className="flex flex-col items-center mb-10">
          <div className="bg-blue-600 p-4 rounded-2xl mb-4 shadow-lg shadow-blue-500/20">
            <ShieldCheck size={40} className="text-white" />
          </div>
          <h2 className="text-3xl font-black text-white tracking-tighter uppercase">KIPCHI <span className="text-blue-500">POS</span></h2>
          <p className="text-slate-500 font-bold text-xs uppercase tracking-[0.2em] mt-2 text-center">Sign in to your workspace</p>
        </div>

        {error && (
          <div className="bg-red-500/10 border border-red-500/20 text-red-400 p-4 mb-6 rounded-xl text-center text-sm font-bold">
            {error}
          </div>
        )}

        <form onSubmit={handleLogin} className="space-y-6">
          <div>
            <label className="block text-slate-400 text-xs font-black uppercase tracking-widest mb-2 ml-1">Username</label>
            <div className="relative">
              <User className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-500" size={18} />
              <input
                type="text"
                className="w-full bg-slate-950 border border-slate-800 text-white pl-12 pr-4 py-4 rounded-xl focus:border-blue-500 outline-none transition-all"
                placeholder="Enter admin ID"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
              />
            </div>
          </div>

          <div>
            <label className="block text-slate-400 text-xs font-black uppercase tracking-widest mb-2 ml-1">Password</label>
            <div className="relative">
              <Lock className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-500" size={18} />
              <input
                type="password"
                className="w-full bg-slate-950 border border-slate-800 text-white pl-12 pr-4 py-4 rounded-xl focus:border-blue-500 outline-none transition-all"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
          </div>

          <button
            type="submit"
            className="w-full bg-blue-600 hover:bg-blue-700 text-white py-5 rounded-2xl font-black text-sm uppercase tracking-widest shadow-lg shadow-blue-600/20 transition-all active:scale-[0.98]"
          >
            Sign in
          </button>
        </form>
      </div>
    </div>
  );
};

export default Login;
