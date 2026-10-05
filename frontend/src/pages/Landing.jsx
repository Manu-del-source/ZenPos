import React from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight, ArrowUpRight, BarChart3, Barcode, Building2, Check,
  ChevronRight, CreditCard, Package, ReceiptText, ScanBarcode,
  ShoppingCart, Smartphone, Store, Users, Wallet
} from 'lucide-react';
import SiteHeader from '../components/site/SiteHeader';
import SiteFooter from '../components/site/SiteFooter';
import '../styles/site.css';
import '../styles/landing.css';

function Metric({ label, value, detail, positive = true }) {
  return (
    <div className="dash-metric">
      <span>{label}</span>
      <strong>{value}</strong>
      <small className={positive ? 'is-positive' : ''}>{detail}</small>
    </div>
  );
}

function DashboardPreview() {
  return (
    <div className="dashboard-shell">
      <div className="dash-topbar">
        <div className="dash-brand"><span>Z</span><b>ZenPOS</b></div>
        <div className="dash-search">Search anything...</div>
        <div className="dash-user"><span>MK</span><div><b>Manager</b><small>ZenPOS Demo Store</small></div></div>
      </div>
      <div className="dash-body">
        <aside className="dash-sidebar">
          <b>WORKSPACE</b>
          <span className="active"><ShoppingCart size={13} /> Dashboard</span>
          <span><ReceiptText size={13} /> Sales</span>
          <span><Package size={13} /> Inventory</span>
          <span><Users size={13} /> Customers</span>
          <span><Building2 size={13} /> Branches</span>
          <b className="dash-sidebar-label">MANAGEMENT</b>
          <span><BarChart3 size={13} /> Reports</span>
        </aside>
        <main className="dash-main">
          <div className="dash-heading"><div><small>MONDAY, 5 OCTOBER</small><h3>Good afternoon, Manager</h3></div><button>+ New sale</button></div>
          <div className="dash-metrics">
            <Metric label="Today's sales" value="KES 84,250" detail="+18.4% vs yesterday" />
            <Metric label="Transactions" value="126" detail="+12 today" />
            <Metric label="Items in stock" value="4,832" detail="42 low stock" positive={false} />
            <Metric label="Customers" value="1,284" detail="+26 this week" />
          </div>
          <div className="dash-grid">
            <div className="dash-card sales-chart">
              <div className="dash-card-head"><span><b>Sales overview</b><small>Last 7 days</small></span><em>KES 421,680</em></div>
              <div className="chart-area">
                <div className="chart-lines"><i/><i/><i/><i/></div>
                <svg viewBox="0 0 520 150" preserveAspectRatio="none" aria-hidden="true"><polyline points="0,125 70,106 140,116 210,73 280,92 350,48 420,65 520,22" fill="none" stroke="currentColor" strokeWidth="3"/><polyline points="0,125 70,106 140,116 210,73 280,92 350,48 420,65 520,22 520,150 0,150" fill="currentColor" opacity=".08"/></svg>
                <div className="chart-days"><span>Mon</span><span>Tue</span><span>Wed</span><span>Thu</span><span>Fri</span><span>Sat</span><span>Sun</span></div>
              </div>
            </div>
            <div className="dash-card recent-sales">
              <div className="dash-card-head"><span><b>Recent sales</b><small>Live activity</small></span><ChevronRight size={15}/></div>
              <div className="sale-row"><span className="sale-icon"><ShoppingCart size={13}/></span><div><b>SALE-10284</b><small>Cash · 4 items</small></div><strong>KES 8,450</strong></div>
              <div className="sale-row"><span className="sale-icon mpesa"><Smartphone size={13}/></span><div><b>SALE-10283</b><small>M-Pesa · 7 items</small></div><strong>KES 12,700</strong></div>
              <div className="sale-row"><span className="sale-icon"><ShoppingCart size={13}/></span><div><b>SALE-10282</b><small>Cash · 2 items</small></div><strong>KES 3,250</strong></div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

function POSPreview() {
  return (
    <div className="pos-preview">
      <div className="pos-head"><span><ShoppingCart size={15}/> New sale</span><small>Branch: Main Store</small></div>
      <div className="pos-content">
        <div className="pos-products">
          <div className="pos-search"><ScanBarcode size={14}/><span>Search product or scan barcode</span><kbd>⌘ K</kbd></div>
          <div className="pos-categories"><b>All products</b><span>Electronics</span><span>Household</span><span>Motorcycle</span></div>
          <div className="product-grid">
            <div><span className="product-thumb">HP</span><b>HP Wireless Mouse</b><small>SKU HP-MOUSE-01</small><strong>KES 1,250</strong></div>
            <div><span className="product-thumb">KB</span><b>Keyboard USB</b><small>SKU KB-USB-04</small><strong>KES 1,800</strong></div>
            <div><span className="product-thumb">USB</span><b>USB-C Cable 1m</b><small>SKU USB-C-1M</small><strong>KES 650</strong></div>
            <div><span className="product-thumb">AD</span><b>65W Laptop Adapter</b><small>SKU AD-65W-02</small><strong>KES 3,500</strong></div>
          </div>
        </div>
        <aside className="pos-cart">
          <div className="pos-cart-title"><b>Current sale</b><span>3 items</span></div>
          <div className="cart-line"><span>HP Wireless Mouse × 1</span><strong>KES 1,250</strong></div>
          <div className="cart-line"><span>USB-C Cable 1m × 2</span><strong>KES 1,300</strong></div>
          <div className="cart-total"><span>Total</span><strong>KES 2,550</strong></div>
          <div className="pay-options"><button><Wallet size={14}/> Cash</button><button className="selected"><Smartphone size={14}/> M-Pesa</button></div>
          <button className="complete-sale">Complete sale <ArrowRight size={14}/></button>
        </aside>
      </div>
    </div>
  );
}

function InventoryPreview() {
  return (
    <div className="inventory-preview">
      <div className="inventory-preview-head"><div><small>PRODUCT CATALOGUE</small><h3>Inventory</h3></div><button>+ Add product</button></div>
      <div className="inventory-toolbar"><span><Barcode size={13}/> Search by product, SKU or barcode</span><span>All branches ▾</span></div>
      <div className="inventory-rows">
        <div className="inventory-row header"><span>Product</span><span>SKU</span><span>Price</span><span>Stock</span><span>Status</span></div>
        <div className="inventory-row"><span><b>HP Wireless Mouse</b><small>Computer accessories</small></span><span>HP-MOUSE-01</span><span>KES 1,250</span><strong>42</strong><em>In stock</em></div>
        <div className="inventory-row"><span><b>USB-C Cable 1m</b><small>Cables & adapters</small></span><span>USB-C-1M</span><span>KES 650</span><strong>8</strong><em className="low">Low stock</em></div>
        <div className="inventory-row"><span><b>65W Laptop Adapter</b><small>Power accessories</small></span><span>AD-65W-02</span><span>KES 3,500</span><strong>24</strong><em>In stock</em></div>
      </div>
    </div>
  );
}

function Feature({ icon: Icon, number, title, text }) {
  return <div className="feature-card"><span className="feature-icon"><Icon size={19}/></span><small>{number}</small><h3>{title}</h3><p>{text}</p><Link to="/login">Explore <ArrowRight size={14}/></Link></div>;
}

function Landing() {
  return (
    <div className="zenpos-site landing-page">
      <a className="skip-link" href="#main-content">Skip to content</a>
      <SiteHeader isDark={false} onToggleTheme={() => {}} />
      <main id="main-content">
        <section className="hero">
          <div className="hero-bg-orb orb-one"/><div className="hero-bg-orb orb-two"/>
          <div className="hero-inner">
            <div className="hero-copy">
              <div className="hero-badge"><span/> Built for Kenyan businesses</div>
              <h1>Run your business.<br/><em>Know your numbers.</em></h1>
              <p>ZenPOS puts sales, inventory, customers, payments and business reporting in one simple system.</p>
              <div className="hero-actions"><Link className="btn btn--primary" to="/login">Get started with ZenPOS <ArrowUpRight size={16}/></Link><a className="hero-watch" href="#product">See how it works <ArrowRight size={15}/></a></div>
              <div className="hero-trust"><span><Check size={13}/> Cash sales</span><span><Check size={13}/> M-Pesa</span><span><Check size={13}/> Inventory</span></div>
            </div>
            <div className="hero-product"><div className="browser-chrome"><span/><span/><span/><b>app.zenpos.co.ke</b><i>● LIVE</i></div><DashboardPreview/></div>
          </div>
        </section>

        <section className="trust-strip"><div><Store size={17}/><span>Retail shops</span></div><div><Package size={17}/><span>Hardware & spare parts</span></div><div><ShoppingCart size={17}/><span>Supermarkets</span></div><div><ReceiptText size={17}/><span>Everyday sales</span></div></section>

        <section className="product-section" id="product">
          <div className="section-intro"><div><span className="eyebrow">The point of sale</span><h2>Fast at the counter.<br/>Clear behind the counter.</h2></div><p>Everything your cashier needs is on one screen. Search products, scan barcodes, build the cart and take payment without jumping between systems.</p></div>
          <POSPreview/>
        </section>

        <section className="feature-section">
          <div className="feature-heading"><span className="eyebrow">One system for the whole shop</span><h2>More than a till.</h2><p>ZenPOS connects the daily work that keeps a retail business moving.</p></div>
          <div className="feature-grid">
            <Feature icon={ShoppingCart} number="01" title="Point of sale" text="Process cash and M-Pesa sales quickly, with stock updated as you sell."/>
            <Feature icon={Package} number="02" title="Inventory control" text="Track products, SKUs, prices and stock levels across your catalogue."/>
            <Feature icon={Users} number="03" title="Customers" text="Keep customer records connected to the sales they make."/>
            <Feature icon={BarChart3} number="04" title="Business reports" text="See sales activity, inventory value and the numbers that matter."/>
          </div>
        </section>

        <section className="inventory-section">
          <div className="inventory-copy"><span className="eyebrow">Inventory that stays current</span><h2>Sell with confidence, not guesswork.</h2><p>Every completed sale updates tracked stock. Low-stock visibility helps you know what needs attention before it becomes a problem.</p><div className="check-list"><span><Check size={14}/> Product catalogue & SKUs</span><span><Check size={14}/> Barcode lookup</span><span><Check size={14}/> Stock adjustments</span><span><Check size={14}/> Low-stock visibility</span></div><Link className="text-link" to="/login">Manage inventory <ArrowRight size={15}/></Link></div>
          <InventoryPreview/>
        </section>

        <section className="payments-section">
          <div><span className="eyebrow eyebrow--light">Kenyan payments</span><h2>Cash or M-Pesa.<br/><em>Your counter is ready.</em></h2><p>Record cash sales or initiate an M-Pesa STK push directly from checkout. Payment status stays connected to the sale.</p><div className="payment-pills"><span><Wallet size={15}/> Cash</span><span><Smartphone size={15}/> M-Pesa STK</span></div></div>
          <div className="payment-card"><div><span className="payment-brand"><Smartphone size={18}/> M-Pesa</span><small>PAYMENT REQUEST</small></div><strong>KES 2,550</strong><span className="payment-phone">+254 7•• ••• 482</span><div className="payment-status"><span/> Waiting for customer confirmation</div><div className="payment-progress"><i/></div></div>
        </section>

        <section className="business-section">
          <div className="business-copy"><span className="eyebrow">Built to grow with you</span><h2>One business today.<br/><em>Multiple branches tomorrow.</em></h2><p>Start with one shop and keep your operations organized as you add staff, products and locations.</p><div className="business-points"><span><Building2 size={17}/><b>Branches</b><small>Organize locations and operations</small></span><span><Users size={17}/><b>Staff access</b><small>Keep business access under control</small></span><span><ReceiptText size={17}/><b>Audit trail</b><small>Know what happened and when</small></span></div></div>
          <div className="branch-card"><div className="branch-card-top"><span>YOUR BUSINESS</span><b>3 branches</b></div><div className="branch"><span className="branch-dot active"/> <div><b>Main Store</b><small>Nairobi · 4 staff</small></div><strong>KES 84,250</strong></div><div className="branch"><span className="branch-dot"/> <div><b>Westlands Branch</b><small>Nairobi · 2 staff</small></div><strong>KES 51,800</strong></div><div className="branch"><span className="branch-dot"/> <div><b>Industrial Area</b><small>Nairobi · 3 staff</small></div><strong>KES 37,420</strong></div><div className="branch-total"><span>Total today</span><b>KES 173,470</b></div></div>
        </section>

        <section className="cta-section">
          <div><span className="eyebrow eyebrow--light">ZENPOS</span><h2>Your business deserves<br/><em>better numbers.</em></h2><p>Bring your sales, stock and payments into one place.</p></div>
          <Link className="btn btn--light" to="/login">Open ZenPOS <ArrowUpRight size={16}/></Link>
        </section>
      </main>
      <SiteFooter/>
    </div>
  );
}

export default Landing;
