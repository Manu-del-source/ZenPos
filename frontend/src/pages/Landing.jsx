import React, { useState } from 'react';
import '../styles/landing.css';
import { Link } from 'react-router-dom';
import {
  ArrowDown, ArrowRight, ArrowUpRight, BarChart3, Boxes, Building2, Check,
  ChevronDown, CircleDollarSign, ClipboardList, CreditCard, Menu, Package,
  PackageCheck, Search, ShieldCheck, ShoppingBag, ShoppingCart, Smartphone,
  Users, Warehouse, X,
} from 'lucide-react';

const loginLink = '/login';
const products = [
  { name: 'Everyday notebook', sku: 'ST-204', price: 'KES 180', stock: 'In stock', tone: 'blue' },
  { name: 'Canvas tote bag', sku: 'AC-118', price: 'KES 950', stock: 'In stock', tone: 'sand' },
  { name: 'Desk lamp', sku: 'HM-032', price: 'KES 2,400', stock: 'Low stock', tone: 'green' },
];

function Brand({ footer = false }) {
  return (
    <Link className={'kipchi-brand' + (footer ? ' kipchi-brand-footer' : '')} to="/" aria-label="Kipchi POS home">
      <span className="kipchi-brand-mark" aria-hidden="true"><span>K</span></span>
      <span className="kipchi-brand-name">kipchi<span>POS</span></span>
    </Link>
  );
}

function PosPreview({ compact = false }) {
  return (
    <div className={'pos-preview' + (compact ? ' pos-preview-compact' : '')} role="img" aria-label="Sample Kipchi point of sale screen with product search, a two-item cart, KES total, and cash or M-Pesa payment options">
      <div className="preview-topbar">
        <div className="preview-brand"><span className="preview-brand-mark">K</span><b>Kipchi <span>POS</span></b></div>
        <div className="preview-location"><Building2 size={14} /> Main store <ChevronDown size={13} /></div>
        <div className="preview-avatar">JM</div>
      </div>
      <div className="preview-workspace">
        <div className="preview-catalog">
          <div className="preview-title-row"><div><small>SALES COUNTER</small><h3>New sale</h3></div><span className="preview-time">Today, 10:42 AM</span></div>
          <div className="preview-search"><Search size={15} /><span>Search by product or scan barcode</span><kbd>/</kbd></div>
          <div className="preview-filter-row"><span className="filter-active">All products</span><span>Popular</span><span>Recently added</span></div>
          <div className="preview-products">
            {products.map((product) => (
              <div className="preview-product" key={product.sku}>
                <div className={'preview-product-art ' + product.tone}><Package size={24} strokeWidth={1.6} /></div>
                <span className="preview-product-name">{product.name}</span>
                <span className="preview-product-sku">{product.sku}</span>
                <div className="preview-product-bottom"><b>{product.price}</b><span className={product.stock === 'Low stock' ? 'low-stock' : ''}>{product.stock}</span></div>
              </div>
            ))}
          </div>
          <div className="preview-product-foot"><span><span className="stock-dot" /> Stock updates as sales are recorded</span><span>Showing 3 products</span></div>
        </div>
        <aside className="preview-cart">
          <div className="preview-cart-heading"><div><ShoppingCart size={16} /><b>Current order</b></div><span>2 items</span></div>
          <div className="preview-customer"><Users size={15} /><span>Walk-in customer</span><ChevronDown size={13} /></div>
          <div className="preview-cart-items">
            <div className="preview-cart-item"><span className="cart-item-thumb blue"><Package size={16} /></span><span className="cart-item-copy"><b>Everyday notebook</b><small>KES 180 each</small></span><span className="cart-quantity">× 2</span><b>KES 360</b></div>
            <div className="preview-cart-item"><span className="cart-item-thumb sand"><Package size={16} /></span><span className="cart-item-copy"><b>Canvas tote bag</b><small>KES 950 each</small></span><span className="cart-quantity">× 1</span><b>KES 950</b></div>
          </div>
          <div className="preview-totals"><div><span>Subtotal</span><b>KES 1,310</b></div><div><span>VAT</span><span>Included</span></div><div className="preview-total"><b>Total due</b><b>KES 1,310</b></div></div>
          <div className="preview-payment-label">PAYMENT METHOD</div>
          <div className="preview-payment-options"><span className="selected"><CreditCard size={14} /> Cash</span><span><Smartphone size={14} /> M-Pesa</span></div>
          <button className="preview-checkout" type="button" tabIndex={-1}>Complete sale <ArrowRight size={15} /></button>
          <div className="preview-secure"><ShieldCheck size={12} /> Checkout preview · sample data</div>
        </aside>
      </div>
    </div>
  );
}

const features = [
  { icon: ShoppingCart, tone: 'blue', title: 'Fast point of sale', text: 'Find products, build a cart and complete a sale from one clear checkout.' },
  { icon: Warehouse, tone: 'green', title: 'Inventory visibility', text: 'Search your catalogue and keep stock levels connected to recorded sales.' },
  { icon: Smartphone, tone: 'mint', title: 'M-Pesa payments', text: 'Start an M-Pesa STK push from checkout alongside cash payments.' },
  { icon: BarChart3, tone: 'violet', title: 'Sales and reports', text: 'Review sales history and see business activity in a reporting view.' },
  { icon: Users, tone: 'amber', title: 'Customer records', text: 'Keep customer contact details available alongside day-to-day retail work.' },
  { icon: Building2, tone: 'slate', title: 'Branch-ready platform', text: 'Kipchi includes branch records and staff access foundations. Branch workflows depend on your setup.' },
];
const steps = [
  { icon: ShieldCheck, title: 'Sign in to your workspace', text: 'Use your staff account to open the retail tools available to your role.' },
  { icon: Boxes, title: 'Find products and stock', text: 'Search the catalogue by name, SKU or barcode.' },
  { icon: ShoppingBag, title: 'Build the sale', text: 'Add items, check the total and choose cash or M-Pesa.' },
  { icon: ClipboardList, title: 'Review activity', text: 'Return to sales history and reporting to follow what has been recorded.' },
];

function Landing() {
  const [menuOpen, setMenuOpen] = useState(false);
  const closeMenu = () => setMenuOpen(false);
  return (
    <div className="kipchi-site">
      <a className="skip-link" href="#main-content">Skip to content</a>
      <header className="site-header">
        <div className="site-header-inner">
          <Brand />
          <button className="mobile-menu-toggle" type="button" aria-expanded={menuOpen} aria-controls="site-navigation" aria-label={menuOpen ? 'Close navigation menu' : 'Open navigation menu'} onClick={() => setMenuOpen((open) => !open)}>
            {menuOpen ? <X size={21} /> : <Menu size={21} />}
          </button>
          <nav id="site-navigation" className={'site-navigation' + (menuOpen ? ' is-open' : '')} aria-label="Main navigation">
            <div className="site-nav-links">
              <a href="#features" onClick={closeMenu}>Features</a>
              <a href="#how-it-works" onClick={closeMenu}>How it works</a>
              <a href="#business-management" onClick={closeMenu}>Business management</a>
            </div>
            <div className="site-nav-actions">
              <Link className="nav-signin" to={loginLink} onClick={closeMenu}>Sign in</Link>
              <Link className="button button-small button-primary" to={loginLink} onClick={closeMenu}>Get started <ArrowUpRight size={15} /></Link>
            </div>
          </nav>
        </div>
      </header>
      <main id="main-content">
        <section className="hero-section" aria-labelledby="hero-heading">
          <div className="hero-inner">
            <div className="hero-copy">
              <div className="hero-kicker"><span className="hero-kicker-icon"><CircleDollarSign size={14} /></span> Retail, brought together</div>
              <h1 id="hero-heading">Everything you need to run your <span>retail business.</span></h1>
              <p className="hero-description">Bring sales, inventory, payments, customers and business management together in one simple system.</p>
              <div className="hero-actions"><Link className="button button-primary" to={loginLink}>Get started <ArrowRight size={17} /></Link><Link className="button button-secondary" to={loginLink}>Sign in</Link></div>
              <div className="hero-proof"><span><Check size={14} /></span> A clearer view of the work happening across your shop</div>
            </div>
            <div className="hero-product-wrap">
              <div className="product-orbit orbit-one" /><div className="product-orbit orbit-two" />
              <PosPreview compact />
              <div className="hero-float-note"><span className="float-note-icon"><PackageCheck size={16} /></span><span><b>Stock-aware checkout</b><small>Items and totals, together</small></span></div>
            </div>
          </div>
          <a className="hero-scroll" href="#features"><span>Explore Kipchi</span><ArrowDown size={14} /></a>
        </section>

        <section className="feature-section section-pad" id="features" aria-labelledby="features-heading">
          <div className="section-heading"><div><span className="eyebrow">One system for the daily details</span><h2 id="features-heading">The essentials, all working together.</h2></div><p>Kipchi brings the main parts of retail operations into one connected workspace.</p></div>
          <div className="feature-grid">
            {features.map(({ icon: Icon, tone, title, text }) => <article className="feature-card" key={title}><span className={'feature-icon ' + tone}><Icon size={20} strokeWidth={1.8} /></span><h3>{title}</h3><p>{text}</p><span className="feature-card-rule" /></article>)}
          </div>
        </section>

        <section className="how-section section-pad" id="how-it-works" aria-labelledby="how-heading">
          <div className="how-intro"><span className="eyebrow">A straightforward daily flow</span><h2 id="how-heading">From product search to paid.</h2><p>Keep the routine clear for the people serving customers and managing the shop.</p><Link className="text-link" to={loginLink}>Sign in to Kipchi <ArrowRight size={15} /></Link></div>
          <div className="steps-list">{steps.map(({ icon: Icon, title, text }, index) => <article className="step-row" key={title}><span className="step-index">0{index + 1}</span><span className="step-icon"><Icon size={18} /></span><div><h3>{title}</h3><p>{text}</p></div>{index < steps.length - 1 && <span className="step-connector" aria-hidden="true" />}</article>)}</div>
        </section>

        <section className="showcase-section" aria-labelledby="showcase-heading">
          <div className="showcase-copy"><span className="eyebrow eyebrow-light">A checkout that feels familiar</span><h2 id="showcase-heading">The whole sale,<br />in one view.</h2><p>Pick products, keep an eye on the cart, confirm the total and choose a payment method without losing your place.</p>
            <ul className="showcase-checks"><li><Check size={15} /> Search by product name or SKU</li><li><Check size={15} /> See quantities and totals as you build the cart</li><li><Check size={15} /> Choose cash or start an M-Pesa payment</li></ul>
            <Link className="button button-light" to={loginLink}>Open the sales desk <ArrowRight size={16} /></Link>
          </div>
          <div className="showcase-visual"><PosPreview /></div>
        </section>

        <section className="management-section section-pad" id="business-management" aria-labelledby="management-heading">
          <div className="management-copy"><span className="eyebrow">More than checkout</span><h2 id="management-heading">Keep the business in view.</h2><p>Move between the records your team uses to serve customers, manage stock and understand sales activity.</p>
            <div className="management-links">
              <div><span className="management-link-icon"><Warehouse size={17} /></span><span><b>Inventory</b><small>Catalogue and stock visibility</small></span></div>
              <div><span className="management-link-icon"><Users size={17} /></span><span><b>Customers</b><small>Contact records and lookup</small></span></div>
              <div><span className="management-link-icon"><ClipboardList size={17} /></span><span><b>Sales and reports</b><small>Recorded transactions and activity</small></span></div>
              <div><span className="management-link-icon"><ShieldCheck size={17} /></span><span><b>Staff access</b><small>Role-aware access in the platform</small></span></div>
            </div>
          </div>
          <div className="management-visual" role="img" aria-label="Illustration of a retail management dashboard">
            <div className="management-window">
              <div className="management-window-top"><span className="window-dots"><i /><i /><i /></span><span>Business overview</span><span className="sample-tag">SAMPLE VIEW</span></div>
              <div className="management-window-body">
                <div className="management-sidebar"><span className="sidebar-logo">K</span><i className="sidebar-selected"><BarChart3 size={15} /></i><i><ShoppingCart size={15} /></i><i><Package size={15} /></i><i><Users size={15} /></i></div>
                <div className="management-content"><div className="management-title"><span><small>YOUR WORKSPACE</small><b>Business overview</b></span><span className="period-chip">Recent activity <ChevronDown size={12} /></span></div>
                  <div className="overview-cards"><div><span>Sales activity</span><b>Reports</b><small>Open sales reports</small></div><div><span>Transactions</span><b>Sales history</b><small>View recorded sales</small></div><div><span>Stock</span><b>Catalogue</b><small>View inventory</small></div></div>
                  <div className="activity-panel"><div className="activity-heading"><b>Recent sales</b><span>Sample records</span></div><div className="activity-line"><span className="activity-dot blue-dot" /><span>Sale · Walk-in customer</span><b>KES 2,400</b></div><div className="activity-line"><span className="activity-dot green-dot" /><span>Sale · Customer record</span><b>KES 1,850</b></div><div className="activity-line"><span className="activity-dot yellow-dot" /><span>Sale · Walk-in customer</span><b>KES 760</b></div></div>
                </div>
              </div>
            </div>
            <div className="management-caption"><span><span className="caption-dot" /> Sample workspace preview</span><span>Sales · stock · customers</span></div>
          </div>
        </section>

        <section className="branches-section section-pad" aria-labelledby="branches-heading">
          <div className="branches-heading"><span className="eyebrow">Built with growing teams in mind</span><h2 id="branches-heading">A platform with branches in its foundations.</h2><p>Kipchi includes branch records and branch-scoped staff access. Branch-level sales and stock workflows are still being expanded across the product.</p></div>
          <div className="branch-map" role="img" aria-label="An organization connected to three branch locations">
            <div className="branch-root"><span><Building2 size={20} /></span><div><b>Your business</b><small>Organization workspace</small></div></div>
            <div className="branch-tree-lines" aria-hidden="true"><i /><i /><i /><i /></div>
            <div className="branch-locations">
              <div className="branch-card"><span className="branch-store"><Warehouse size={18} /></span><span><b>Branch A</b><small>Location record</small></span><span className="branch-status">Example</span></div>
              <div className="branch-card"><span className="branch-store"><Warehouse size={18} /></span><span><b>Branch B</b><small>Location record</small></span><span className="branch-status">Example</span></div>
              <div className="branch-card branch-add"><span className="branch-store"><Building2 size={18} /></span><span><b>More locations</b><small>Managed by authorized staff</small></span><ArrowUpRight size={15} /></div>
            </div>
          </div>
        </section>

        <section className="final-cta" aria-labelledby="cta-heading">
          <div className="cta-pattern" aria-hidden="true" />
          <div className="final-cta-inner"><span className="eyebrow eyebrow-light">Kipchi POS</span><h2 id="cta-heading">Ready to bring the work together?</h2><p>Bring sales, inventory, customers and business management into one retail workspace.</p><div className="cta-actions"><Link className="button button-light" to={loginLink}>Get started <ArrowRight size={16} /></Link><Link className="cta-signin" to={loginLink}>Sign in to your account <ArrowUpRight size={15} /></Link></div></div>
        </section>
      </main>
      <footer className="site-footer">
        <div className="footer-main"><div className="footer-brand-column"><Brand footer /><p>Retail operations, brought together in one straightforward workspace.</p></div>
          <div className="footer-link-column"><b>Product</b><a href="#features">Features</a><a href="#how-it-works">How it works</a><a href="#business-management">Business management</a></div>
          <div className="footer-link-column"><b>Workspace</b><Link to={loginLink}>Sign in</Link><Link to={loginLink}>Get started</Link></div>
        </div>
        <div className="footer-bottom"><span>© {new Date().getFullYear()} Kipchi POS</span><span>Retail, made clearer.</span></div>
      </footer>
    </div>
  );
}

export default Landing;
