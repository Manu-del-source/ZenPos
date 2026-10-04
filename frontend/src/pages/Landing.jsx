import React from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowDownRight, ArrowRight, ArrowUpRight, Barcode, Building2, Check,
  ChevronDown, CircleDot, CreditCard, Package, Search, ShoppingCart,
  Smartphone, Users, Wallet,
} from 'lucide-react';
import SiteHeader from '../components/site/SiteHeader';
import SiteFooter from '../components/site/SiteFooter';
import '../styles/site.css';
import '../styles/landing.css';

function WindowFrame({ children, title = 'ZenPOS · Point of Sale', className = '', ariaLabel = 'Illustrative ZenPOS interface preview' }) {
  return (
    <div className={`product-window ${className}`} role="img" aria-label={ariaLabel}>
      <div className="product-window-bar">
        <span className="window-controls" aria-hidden="true"><i /><i /><i /></span>
        <span className="window-title">{title}</span>
        <span className="window-live"><CircleDot size={10} /> Interface preview</span>
      </div>
      {children}
    </div>
  );
}

function CheckoutScreen({ compact = false }) {
  return (
    <WindowFrame
      className={compact ? 'checkout-window checkout-window--compact' : 'checkout-window'}
      ariaLabel="Illustrative ZenPOS point-of-sale preview with product search, an empty cart, totals, and cash or M-Pesa payment options"
    >
      <div className="checkout-screen">
        <aside className="app-rail" aria-label="ZenPOS sections">
          <span className="rail-brand">Z</span>
          <span className="rail-item rail-item--active"><ShoppingCart size={16} /></span>
          <span className="rail-item"><Package size={16} /></span>
          <span className="rail-item"><Users size={16} /></span>
        </aside>
        <div className="checkout-catalog">
          <div className="screen-heading">
            <span><small>POINT OF SALE</small><b>New sale</b></span>
            <span className="screen-location"><Building2 size={13} /> Business</span>
          </div>
          <div className="screen-search"><Search size={15} /><span>Search by product or scan barcode</span><Barcode size={15} /></div>
          <div className="screen-tab-row"><b>Products</b><span>All products</span><span>Categories</span></div>
          {!compact && (
            <div className="screen-product-table">
              <div className="screen-table-head"><span>Product</span><span>SKU</span><span>Price</span><span>Stock</span></div>
              <div className="screen-empty"><Package size={21} /><span>Search your product catalogue to begin</span></div>
            </div>
          )}
          {compact && (
            <div className="screen-product-skeleton" aria-hidden="true">
              <div><i /><span><b /><small /></span><em /></div>
              <div><i /><span><b /><small /></span><em /></div>
              <div><i /><span><b /><small /></span><em /></div>
            </div>
          )}
        </div>
        <aside className="checkout-cart">
          <div className="cart-title"><span><ShoppingCart size={15} /> Cart</span><small>0 items</small></div>
          <div className="cart-empty"><span className="cart-empty-icon"><ShoppingCart size={20} /></span><b>Your cart is empty</b><small>Add products to start a sale</small></div>
          <div className="cart-summary">
            <div><span>Subtotal</span><b>KES 0</b></div>
            <div><span>Total to pay</span><b>KES 0</b></div>
          </div>
          <div className="cart-payments"><span><Wallet size={14} /> Cash</span><span><Smartphone size={14} /> M-Pesa</span></div>
          <button className="screen-checkout" type="button" disabled>Complete sale <ArrowRight size={14} /></button>
        </aside>
      </div>
    </WindowFrame>
  );
}

function InventoryScreen() {
  return (
    <WindowFrame title="ZenPOS · Inventory" className="inventory-window" ariaLabel="Illustrative ZenPOS inventory preview with product, SKU, price and stock fields">
      <div className="inventory-screen">
        <div className="inventory-side-label"><Package size={16} /><span>Inventory</span></div>
        <div className="inventory-main">
          <div className="inventory-heading"><span><small>CATALOGUE</small><b>Inventory</b></span><button type="button" className="inventory-add" disabled>+ Add product</button></div>
          <div className="inventory-search"><Search size={14} /><span>Search products by name or SKU</span></div>
          <div className="inventory-table">
            <div className="inventory-table-head"><span>Product</span><span>SKU</span><span>Price</span><span>Stock</span></div>
            <div className="inventory-empty"><Package size={20} /><span>Your product catalogue</span><small>Product names, prices and stock levels appear here.</small></div>
          </div>
        </div>
      </div>
    </WindowFrame>
  );
}

function RecordsScreen() {
  return (
    <WindowFrame title="ZenPOS · Business records" className="records-window" ariaLabel="Illustrative ZenPOS business records preview showing sales history, customers, revenue and inventory">
      <div className="records-screen">
        <aside className="records-nav"><b>Workspace</b><span className="records-active">Sales</span><span>Inventory</span><span>Customers</span></aside>
        <div className="records-main">
          <div className="records-heading"><span><small>BUSINESS RECORDS</small><b>Sales history</b></span><span className="records-filter">Recent sales <ChevronDown size={13} /></span></div>
          <div className="records-columns"><span>Sale</span><span>Customer</span><span>Payment</span><span>Total</span></div>
          <div className="records-empty">Recorded sales appear here after checkout.</div>
          <div className="records-bottom"><span>Customers</span><span>Revenue</span><span>Inventory</span></div>
        </div>
      </div>
    </WindowFrame>
  );
}

function PaymentScreen() {
  return (
    <div className="payment-ui" aria-label="ZenPOS cash and M-Pesa payment options">
      <div className="payment-ui-top"><span><ShoppingCart size={15} /> Checkout</span><span>Payment</span></div>
      <div className="payment-ui-total"><small>TOTAL TO PAY</small><b>KES —</b></div>
      <div className="payment-option payment-option--selected"><span className="payment-option-icon"><Wallet size={17} /></span><span><b>Cash</b><small>Record a cash sale</small></span><span className="payment-radio" /></div>
      <div className="payment-option"><span className="payment-option-icon payment-option-icon--green"><Smartphone size={17} /></span><span><b>M-Pesa</b><small>Initiate an STK push</small></span><span className="payment-radio" /></div>
      <div className="payment-ui-note"><Check size={14} /> Choose a payment method at the counter</div>
    </div>
  );
}

function Hero() {
  return (
    <section className="hero-section" aria-labelledby="hero-heading">
      <div className="hero-inner">
        <div className="hero-copy">
          <span className="hero-kicker"><i /> RETAIL OPERATIONS · KENYA</span>
          <h1 id="hero-heading">Your shop,<br />running in <em>one place.</em></h1>
          <p className="hero-description">Sales, inventory, customers and payments in one system built for everyday retail.</p>
          <div className="hero-actions">
            <Link className="btn btn--primary" to="/login">Open ZenPOS <ArrowUpRight size={16} /></Link>
            <a className="hero-secondary" href="#how-it-works">See how it works <ArrowDownRight size={16} /></a>
          </div>
          <p className="hero-proof"><span /> Built for everyday retail in Kenya</p>
        </div>
        <div className="hero-product-wrap"><CheckoutScreen compact /></div>
      </div>
      <div className="hero-index"><span>01</span><span>THE DAILY COUNTER</span><span>SCROLL TO EXPLORE ↓</span></div>
    </section>
  );
}

function ProductProof() {
  return (
    <section className="product-proof" id="product" aria-labelledby="product-heading">
      <div className="proof-heading">
        <div><span className="eyebrow">A closer look</span><h2 id="product-heading">The counter, clearly laid out.</h2></div>
        <p>Search the catalogue, see the cart and choose how to take payment in the same checkout.</p>
      </div>
      <CheckoutScreen />
      <div className="product-caption"><span>01 / POINT OF SALE</span><span>Product search · Cart · Cash · M-Pesa</span></div>
    </section>
  );
}

function ProblemSolution() {
  return (
    <section className="problem-section" id="features" aria-labelledby="problem-heading">
      <div className="problem-aside"><span className="eyebrow">The everyday reality</span><span className="section-number">01—04</span></div>
      <div className="problem-copy">
        <h2 id="problem-heading">Retail gets messy when the tools don’t talk to each other.</h2>
        <div className="problem-lines"><p>Sales in one place.</p><p>Stock somewhere else.</p><p>Customer details in a notebook.</p><p>Payments handled separately.</p></div>
        <div className="solution-line"><span className="solution-mark">Z</span><p><b>ZenPOS brings the daily workflow together.</b><small>One workspace for the counter and the business behind it.</small></p></div>
      </div>
    </section>
  );
}

function PosSection() {
  return (
    <section className="feature-section feature-section--pos" aria-labelledby="pos-heading">
      <div className="feature-copy">
        <span className="eyebrow">01 · Point of sale</span>
        <h2 id="pos-heading">Sell clearly at the counter.</h2>
        <p>Find a product, build the cart and complete the sale from one checkout screen.</p>
        <ul className="feature-list"><li><Check size={15} /> Search by name, SKU or barcode</li><li><Check size={15} /> Keep the cart and total in view</li><li><Check size={15} /> Take cash or initiate an M-Pesa STK push</li><li><Check size={15} /> Record completed cash sales</li></ul>
        <Link className="text-link" to="/login">Open ZenPOS <ArrowRight size={15} /></Link>
      </div>
      <div className="feature-visual feature-visual--pos"><CheckoutScreen /></div>
    </section>
  );
}

function InventorySection() {
  return (
    <section className="inventory-feature" aria-labelledby="inventory-heading">
      <div className="inventory-feature-visual"><InventoryScreen /><div className="visual-index"><span>02</span><span>PRODUCT CATALOGUE</span></div></div>
      <div className="inventory-feature-copy">
        <span className="eyebrow">02 · Inventory</span>
        <h2 id="inventory-heading">Know what you have before you sell it.</h2>
        <p>Keep product details and stock levels close to the work at the counter.</p>
        <div className="inventory-facts"><div><b>Products</b><span>One searchable catalogue</span></div><div><b>Prices</b><span>Product prices at a glance</span></div><div><b>Stock</b><span>Recorded quantities and low-stock visibility</span></div></div>
        <Link className="text-link" to="/login">View inventory in ZenPOS <ArrowRight size={15} /></Link>
      </div>
    </section>
  );
}

function ManagementSection() {
  return (
    <section className="management-section" id="business-management" aria-labelledby="management-heading">
      <div className="management-heading"><span className="eyebrow">03 · Business management</span><h2 id="management-heading">Run the business,<br />not just the till.</h2><p>Follow recorded sales, keep customer records and review business activity across your workspace.</p></div>
      <div className="management-screen-wrap"><RecordsScreen /><div className="management-label"><span>SALES HISTORY</span><span>Customers · Revenue · Inventory</span></div></div>
      <div className="management-bottom"><span><Users size={16} /> Customer records</span><span><Building2 size={16} /> Business and staff access</span><span><Package size={16} /> Inventory visibility</span></div>
    </section>
  );
}

function PaymentsSection() {
  return (
    <section className="payments-section" aria-labelledby="payments-heading">
      <div className="payments-copy">
        <span className="eyebrow eyebrow--light">04 · Payments</span>
        <h2 id="payments-heading">Cash when you need it. M-Pesa when your customer prefers it.</h2>
        <p>Choose cash at checkout to record the sale, or initiate an M-Pesa STK push from the counter. M-Pesa availability depends on your payment configuration.</p>
        <div className="roadmap-note"><span className="roadmap-rule" /><span><b>On the roadmap</b><small>eTIMS integration</small></span></div>
      </div>
      <div className="payments-visual"><PaymentScreen /><div className="payment-caption"><span><CreditCard size={14} /> CASH SALE</span><span><Smartphone size={14} /> M-PESA STK PUSH</span></div></div>
    </section>
  );
}

function HowItWorks() {
  return (
    <section className="how-section" id="how-it-works" aria-labelledby="how-heading">
      <div className="how-intro"><span className="eyebrow">A straightforward daily flow</span><h2 id="how-heading">From product search to paid.</h2></div>
      <div className="how-steps"><div><span>01</span><b>Find the product</b><small>Search by name, SKU or barcode.</small></div><div><span>02</span><b>Build the cart</b><small>Review items and the amount due.</small></div><div><span>03</span><b>Take payment</b><small>Record cash or initiate M-Pesa.</small></div><div><span>04</span><b>Review activity</b><small>Return to sales and business records.</small></div></div>
    </section>
  );
}

function FinalCta() {
  return (
    <section className="final-cta" id="contact" aria-labelledby="cta-heading">
      <div><span className="eyebrow">ZENPOS · RETAIL OPERATIONS</span><h2 id="cta-heading">Ready to run your shop better?</h2><p>Bring the everyday work of your shop into one place.</p></div>
      <Link className="btn btn--primary" to="/login">Open ZenPOS <ArrowUpRight size={16} /></Link>
    </section>
  );
}

function Landing() {
  return (
    <div className="zenpos-site landing-page">
      <a className="skip-link" href="#main-content">Skip to content</a>
      <SiteHeader />
      <main id="main-content">
        <Hero />
        <ProductProof />
        <ProblemSolution />
        <PosSection />
        <InventorySection />
        <ManagementSection />
        <PaymentsSection />
        <HowItWorks />
        <FinalCta />
      </main>
      <SiteFooter />
    </div>
  );
}

export default Landing;
