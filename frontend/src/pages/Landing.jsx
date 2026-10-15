import React from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight, ArrowUpRight, BarChart3, Barcode, Building2, Check,
  ClipboardList, CreditCard, Package, ReceiptText, ScanBarcode,
  ShieldCheck, ShoppingCart, Smartphone, Store, Users, Wallet
} from 'lucide-react';
import SiteHeader from '../components/site/SiteHeader';
import SiteFooter from '../components/site/SiteFooter';
import '../styles/site.css';
import '../styles/landing.css';

const capabilities = [
  {
    icon: ShoppingCart,
    title: 'Point of sale',
    text: 'Record sales, add products to a cart and keep checkout organized from one workspace.',
  },
  {
    icon: Package,
    title: 'Inventory management',
    text: 'Maintain your product catalogue, track stock levels and identify items that need attention.',
  },
  {
    icon: Smartphone,
    title: 'Cash and M-Pesa',
    text: 'Support your checkout workflow with cash sales and M-Pesa payment requests where enabled.',
  },
  {
    icon: Users,
    title: 'Customer records',
    text: 'Keep customer information connected to your day-to-day retail operations.',
  },
  {
    icon: BarChart3,
    title: 'Business reporting',
    text: 'Review recorded sales and inventory information to understand how your business is operating.',
  },
  {
    icon: Building2,
    title: 'Staff and branches',
    text: 'Organize access for your team and support multi-location workflows as your setup allows.',
  },
];

const steps = [
  {
    number: '01',
    title: 'Set up your catalogue',
    text: 'Add the products you sell, with the names, prices and stock information your team needs.',
    icon: Barcode,
  },
  {
    number: '02',
    title: 'Record each sale',
    text: 'Use the point-of-sale workflow to select products and record the payment method.',
    icon: ReceiptText,
  },
  {
    number: '03',
    title: 'Keep track of operations',
    text: 'Use your recorded sales and inventory information to review activity and decide what needs attention.',
    icon: ClipboardList,
  },
];

function CapabilityCard({ icon: Icon, title, text }) {
  return (
    <article className="lp-capability-card">
      <span className="lp-capability-icon"><Icon size={21} strokeWidth={1.8} /></span>
      <h3>{title}</h3>
      <p>{text}</p>
    </article>
  );
}

function Landing() {
  return (
    <div className="zenpos-site landing-page">
      <a className="skip-link" href="#main-content">Skip to content</a>
      <SiteHeader isDark={false} onToggleTheme={() => {}} />
      <main id="main-content">
        <section className="lp-hero">
          <div className="lp-hero-glow lp-hero-glow-one" aria-hidden="true" />
          <div className="lp-hero-glow lp-hero-glow-two" aria-hidden="true" />
          <div className="lp-hero-inner">
            <div className="lp-hero-copy">
              <span className="lp-eyebrow"><span /> Retail operations, brought together</span>
              <h1>Run your shop with <em>more clarity.</em></h1>
              <p className="lp-hero-description">
                ZenPOS brings point of sale, inventory, customer records and business reporting into one workspace for Kenyan retailers.
              </p>
              <div className="lp-hero-actions">
                <Link className="btn btn--primary" to="/login">Sign in to ZenPOS <ArrowUpRight size={16} /></Link>
                <a className="lp-secondary-link" href="#product">Explore the platform <ArrowRight size={15} /></a>
              </div>
              <ul className="lp-proof-list">
                <li><Check size={15} /> Sales and inventory in one place</li>
                <li><Check size={15} /> Cash and M-Pesa workflows</li>
                <li><Check size={15} /> Tools for everyday retail operations</li>
              </ul>
            </div>
            <div className="lp-hero-art" aria-hidden="true">
              <div className="lp-hero-panel">
                <div className="lp-hero-panel-top"><span className="lp-panel-mark">Z</span><span>ZENPOS / RETAIL SYSTEM</span><span className="lp-panel-index">01—03</span></div>
                <div className="lp-hero-panel-main">
                  <span className="lp-panel-overline">THE DAILY BUSINESS,</span>
                  <strong>IN<br /><em>GOOD</em><br />ORDER.</strong>
                </div>
                <div className="lp-hero-panel-bottom"><span>SELL WITH CLARITY</span><span className="lp-panel-rule" /><span>KENYA</span></div>
                <div className="lp-panel-side-label">POINT OF SALE · STOCK · REPORTS</div>
              </div>
            </div>
          </div>
          <div className="lp-hero-bottom"><span>MADE FOR RETAIL OPERATIONS</span><span className="lp-hero-bottom-line" /><span>KENYA</span></div>
        </section>

        <section className="lp-audience-strip" aria-label="Retail business types">
          <div><Store size={18} /><span>Retail shops</span></div>
          <div><Package size={18} /><span>Hardware and spare parts</span></div>
          <div><ShoppingCart size={18} /><span>Convenience stores</span></div>
          <div><Barcode size={18} /><span>Product-led businesses</span></div>
        </section>

        <section className="lp-product-section" id="product">
          <div className="lp-section-heading">
            <div>
              <span className="lp-section-kicker">THE PLATFORM</span>
              <h2>Less switching.<br /><em>More control.</em></h2>
            </div>
            <p>Bring essential retail workflows together. Keep daily sales, stock information and business records organized without relying on disconnected processes.</p>
          </div>
          <div className="lp-capability-grid" id="features">
            {capabilities.map((item) => <CapabilityCard key={item.title} {...item} />)}
          </div>
        </section>

        <section className="lp-workflow-section" id="how-it-works">
          <div className="lp-workflow-heading">
            <span className="lp-section-kicker">A CLEARER WORKFLOW</span>
            <h2>From product to recorded sale.</h2>
            <p>A straightforward way to organize the work that happens at the counter and behind it.</p>
          </div>
          <div className="lp-workflow-list">
            {steps.map(({ number, title, text, icon: Icon }) => (
              <article className="lp-workflow-step" key={number}>
                <span className="lp-step-number">{number}</span>
                <span className="lp-step-icon"><Icon size={22} strokeWidth={1.7} /></span>
                <div><h3>{title}</h3><p>{text}</p></div>
                <ArrowRight className="lp-step-arrow" size={19} />
              </article>
            ))}
          </div>
        </section>

        <section className="lp-principles-section">
          <div className="lp-principles-copy">
            <span className="lp-section-kicker">BUILT AROUND YOUR OPERATIONS</span>
            <h2>Know what was recorded. Know what needs attention.</h2>
            <p>Use your actual business records to follow sales activity, monitor inventory and keep your team working from a shared system.</p>
            <Link className="lp-inline-link" to="/login">Access your workspace <ArrowRight size={16} /></Link>
          </div>
          <div className="lp-principles-list">
            <div><span><ScanBarcode size={19} /></span><div><b>Product-level visibility</b><p>Keep catalogue and stock information organized.</p></div></div>
            <div><span><Wallet size={19} /></span><div><b>Payment workflow support</b><p>Record supported payment methods as part of sales.</p></div></div>
            <div><span><BarChart3 size={19} /></span><div><b>Reporting from business records</b><p>Review the data your team records in ZenPOS.</p></div></div>
          </div>
        </section>

        <section className="lp-cta-section" id="contact">
          <div>
            <span className="lp-section-kicker lp-section-kicker-light">ZENPOS</span>
            <h2>Bring your retail work<br /><em>into one place.</em></h2>
            <p>Sign in to access your ZenPOS workspace.</p>
          </div>
          <Link className="btn btn--light" to="/login">Sign in to ZenPOS <ArrowUpRight size={16} /></Link>
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}

export default Landing;
