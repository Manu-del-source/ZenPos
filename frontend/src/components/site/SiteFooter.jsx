import React from 'react';
import { Link } from 'react-router-dom';
import Brand from './Brand';

function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="footer-main">
        <div className="footer-brand-column">
          <Brand tone="dark" />
          <p>Retail operations, in one place.</p>
        </div>
        <div className="footer-link-column">
          <b>Product</b>
          <Link to="/#product">Product</Link>
          <Link to="/#features">Features</Link>
          <Link to="/#how-it-works">How it works</Link>
        </div>
        <div className="footer-link-column">
          <b>ZenPOS</b>
          <Link to="/#contact">Contact</Link>
          <Link to="/login">Sign in</Link>
          <Link to="/login">Open ZenPOS</Link>
          <Link to="/privacy">Privacy policy</Link>
          <Link to="/terms">Terms and conditions</Link>
        </div>
      </div>
      <div className="footer-bottom">
        <span>© {new Date().getFullYear()} ZenPOS</span>
        <span>Retail operations, in one place.</span>
      </div>
    </footer>
  );
}

export default SiteFooter;
