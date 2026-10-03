import React from 'react';
import { Link } from 'react-router-dom';
import Brand from './Brand';

function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="footer-main">
        <div className="footer-brand-column">
          <Brand tone="dark" />
          <p>Retail operations, brought together in one straightforward workspace.</p>
        </div>
        <div className="footer-link-column">
          <b>Product</b>
          <a href="#features">Features</a>
          <a href="#how-it-works">How it works</a>
          <a href="#business-management">Business management</a>
        </div>
        <div className="footer-link-column">
          <b>Workspace</b>
          <Link to="/login">Sign in</Link>
          <Link to="/login">Get started</Link>
        </div>
      </div>
      <div className="footer-bottom">
        <span>© {new Date().getFullYear()} ZenPOS</span>
        <span>Retail, made clearer.</span>
      </div>
    </footer>
  );
}

export default SiteFooter;
