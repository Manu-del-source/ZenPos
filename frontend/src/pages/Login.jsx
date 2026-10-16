import React, { useState } from 'react';
import api, { apiError } from '../services/api';
import { Link, useNavigate } from 'react-router-dom';
import {
  ArrowLeft, ArrowUpRight, Check, CircleDollarSign, Lock, ShieldCheck,
  Smartphone, User, Warehouse,
} from 'lucide-react';
import Brand from '../components/site/Brand';
import '../styles/site.css';
import '../styles/login.css';

const benefits = [
  { icon: CircleDollarSign, title: 'Checkout, made clear', text: 'Find products, build the sale and keep totals in view.' },
  { icon: Warehouse, title: 'Stock in view', text: 'Keep product and stock records connected to daily sales.' },
  { icon: Smartphone, title: 'Payment options', text: 'Record supported cash and M-Pesa workflows at checkout.' },
];

const Login = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const navigate = useNavigate();

  const handleLogin = async (e) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);

    try {
      // Django REST Framework Simple JWT returns access and refresh tokens.
      const { data } = await api.post('/auth/login/', { username: username.trim(), password });
      if (!data?.access || !data?.refresh) {
        throw new Error('The server response did not include valid access and refresh tokens.');
      }

      // Keep the existing storage keys so the rest of the app's auth guards
      // and request interceptor continue to use the same session contract.
      localStorage.setItem('token', data.access);
      localStorage.setItem('refreshToken', data.refresh);

      // Django exposes the authoritative roles, permissions and branch data
      // separately; do not invent a user object from the token response.
      const profile = await api.get('/auth/me/');
      localStorage.setItem('user', JSON.stringify(profile.data));

      window.dispatchEvent(new Event('zenpos:auth'));
      const roles = Array.isArray(profile.data?.roles) ? profile.data.roles : [];
      navigate(roles.includes('HR_MANAGER') || roles.includes('MANAGER') ? '/dashboard' : '/pos');
    } catch (err) {
      setError(apiError(err, err?.message || 'Authentication failed'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="login-page">
      <aside className="login-brand-panel" aria-label="About ZenPOS">
        <div className="login-brand-top"><Brand tone="dark" /></div>
        <div className="login-brand-body">
          <span className="eyebrow eyebrow--light">YOUR SHOP, IN GOOD ORDER</span>
          <h1>Your shop.<br /><em>Under control.</em></h1>
          <p>A clearer way to handle sales, stock and the everyday work behind your counter.</p>
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
            <p>Enter your details to open your ZenPOS workspace.</p>
            {error && (
              <div className="login-error" role="alert">
                <ShieldCheck size={17} /> {error}
              </div>
            )}
            <form onSubmit={handleLogin} className="login-form">
              <div className="login-field">
                <label htmlFor="login-username">Username</label>
                <div className="login-input-wrap">
                  <User size={17} />
                  <input id="login-username" type="text" placeholder="Enter your username"
                    value={username} onChange={(e) => setUsername(e.target.value)} required autoComplete="username" />
                </div>
              </div>
              <div className="login-field">
                <label htmlFor="login-password">Password</label>
                <div className="login-input-wrap">
                  <Lock size={17} />
                  <input id="login-password" type="password" placeholder="••••••••"
                    value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="current-password" />
                </div>
              </div>
              <button type="submit" className="login-submit" disabled={submitting}>
                {submitting ? 'Signing in…' : 'Sign in'}
              </button>
            </form>
            <div className="login-hint">
              <ShieldCheck size={16} /> Use the staff account provided by your administrator. Ask them if you need access.
            </div>
            <Link className="login-back-link" to="/"><ArrowLeft size={14} /> Back to ZenPOS home</Link>
          </div>
        </div>
      </main>
    </div>
  );
};

export default Login;
