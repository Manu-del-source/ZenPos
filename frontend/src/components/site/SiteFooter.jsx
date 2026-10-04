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
          <a href="#product">Product</a>
          <a href="#features">Features</a>
          <a href="#how-it-works">How it works</a>
        </div>
        <div className="footer-link-column">
          <b>ZenPOS</b>
          <a href="#contact">Contact</a>
          <Link to="/login">Sign in</Link>
          <Link to="/login">Open ZenPOS</Link>
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
