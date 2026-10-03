import React, { useState } from 'react';
import api from '../services/api';
import { Link, useNavigate } from 'react-router-dom';
import {
  ArrowLeft, ArrowUpRight, Check, CircleDollarSign, Lock, ShieldCheck,
  Smartphone, User, Warehouse,
} from 'lucide-react';
import Brand from '../components/site/Brand';
import '../styles/site.css';
import '../styles/login.css';

const benefits = [
  {
    icon: CircleDollarSign,
    title: 'Fast point of sale',
    text: 'Products, cart and totals in one clear checkout.',
  },
  {
    icon: Warehouse,
    title: 'Stock-aware selling',
    text: 'Catalogue and stock levels connected to sales.',
  },
  {
    icon: Smartphone,
    title: 'Cash or M-Pesa',
    text: 'Start an M-Pesa STK push or take cash at the counter.',
  },
];

const Login = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const navigate = useNavigate();

  const handleLogin = async (e) => {
    e.preventDefault();
    try {
      const res = await api.post('/v1/auth/login', { username, password });
      localStorage.setItem('token', res.data.token);
      localStorage.setItem('user', JSON.stringify(res.data.user));
      navigate('/pos');
      window.location.reload();
    } catch (err) {
      setError(err.response?.data?.message || 'Authentication failed');
    }
  };

  return (
    <div className="login-page">
      <aside className="login-brand-panel" aria-label="About ZenPOS">
        <div className="login-brand-top">
          <Brand tone="dark" />
        </div>

        <div className="login-brand-body">
          <span className="eyebrow eyebrow--light">Retail, brought together</span>
          <h1>Everything you need to run your <em>retail business.</em></h1>
          <p>
            Bring sales, inventory, payments, customers and business management together in one simple system.
          </p>
          <ul className="login-benefits">
            {benefits.map(({ icon: Icon, title, text }) => (
              <li key={title}>
                <Icon size={19} strokeWidth={1.9} />
                <span><b>{title}</b><small>{text}</small></span>
              </li>
            ))}
          </ul>
        </div>

        <div className="login-float-note login-float-note--a">
          <span className="float-note-icon"><Check size={16} /></span>
          <span><b>Stock-aware checkout</b><small>Items and totals, together</small></span>
        </div>
        <div className="login-float-note login-float-note--b">
          <span className="float-note-icon"><ShieldCheck size={16} /></span>
          <span><b>Role-aware workspace</b><small>Tools for your staff account</small></span>
        </div>

        <div className="login-brand-foot">
          <span>© {new Date().getFullYear()} ZenPOS</span>
          <Link to="/"><ArrowLeft size={14} /> Back to home</Link>
        </div>
      </aside>

      <main className="login-form-panel">
        <div className="login-form-top">
          <span>New to ZenPOS?</span>
          <Link to="/">Get started <ArrowUpRight size={14} /></Link>
        </div>

        <div className="login-form-wrap">
          <div className="login-form-card">
            <div className="login-mobile-brand"><Brand /></div>
            <h2>Welcome back</h2>
            <p>Sign in to your workspace to reach the retail tools available to your role.</p>

            {error && (
              <div className="login-error" role="alert">
                <ShieldCheck size={17} />
                {error}
              </div>
            )}

            <form onSubmit={handleLogin} className="login-form">
              <div className="login-field">
                <label htmlFor="login-username">Username</label>
                <div className="login-input-wrap">
                  <User size={17} />
                  <input
                    id="login-username"
                    type="text"
                    placeholder="Enter your username"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    required
                    autoComplete="username"
                  />
                </div>
              </div>

              <div className="login-field">
                <label htmlFor="login-password">Password</label>
                <div className="login-input-wrap">
                  <Lock size={17} />
                  <input
                    id="login-password"
                    type="password"
                    placeholder="••••••••"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    autoComplete="current-password"
                  />
                </div>
              </div>

              <button type="submit" className="login-submit">Sign in</button>
            </form>

            <div className="login-hint">
              <ShieldCheck size={16} />
              Use the staff account provided by your administrator. Ask them if you need access.
            </div>

            <Link className="login-back-link" to="/"><ArrowLeft size={14} /> Back to ZenPOS home</Link>
          </div>
        </div>
      </main>
    </div>
  );
};

export default Login;
