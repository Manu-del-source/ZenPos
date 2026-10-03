import React from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowDown, ArrowRight, ArrowUpRight, BarChart3, Boxes, Building2, Check,
  CircleDollarSign, ClipboardList, PackageCheck, ReceiptText, ShieldCheck,
  ShoppingBag, Smartphone, Users, Warehouse,
} from 'lucide-react';
import SiteHeader from '../components/site/SiteHeader';
import SiteFooter from '../components/site/SiteFooter';
import PosPreview from '../components/site/PosPreview';
import '../styles/site.css';
import '../styles/landing.css';

const features = [
  {
    icon: ShoppingBag,
    tone: 'blue',
    title: 'Fast point of sale',
    text: 'Find products, build a cart and complete a sale from one clear checkout.',
    variant: 'wide',
    chip: 'Built for the counter',
    bullets: ['Search or scan', 'Cart and totals', 'Cash or M-Pesa'],
  },
  { icon: Warehouse, tone: 'green', title: 'Inventory visibility', text: 'Search your catalogue and keep stock levels connected to recorded sales.' },
  { icon: Smartphone, tone: 'mint', title: 'M-Pesa payments', text: 'Start an M-Pesa STK push from checkout alongside cash payments.' },
  { icon: BarChart3, tone: 'violet', title: 'Sales and reports', text: 'Review sales history and see business activity in a reporting view.' },
  { icon: Users, tone: 'amber', title: 'Customer records', text: 'Keep customer contact details available alongside day-to-day retail work.' },
  {
    icon: Building2,
    tone: 'slate',
    title: 'Branch-ready platform',
    text: 'Kipchi includes branch records and staff access foundations. Branch workflows depend on your setup.',
    variant: 'full',
  },
];

const steps = [
  { icon: ShieldCheck, title: 'Sign in to your workspace', text: 'Use your staff account to open the retail tools available to your role.' },
  { icon: Boxes, title: 'Find products and stock', text: 'Search the catalogue by name, SKU or barcode.' },
  { icon: ShoppingBag, title: 'Build the sale', text: 'Add items, check the total and choose cash or M-Pesa.' },
  { icon: ClipboardList, title: 'Review activity', text: 'Return to sales history and reporting to follow what has been recorded.' },
];

const capabilities = [
  { icon: ShoppingBag, label: 'Point of sale' },
  { icon: Warehouse, label: 'Inventory' },
  { icon: Smartphone, label: 'M-Pesa payments' },
  { icon: ReceiptText, label: 'Sales history' },
  { icon: Users, label: 'Customer records' },
  { icon: Building2, label: 'Branch records' },
];

const managementLinks = [
  { icon: Warehouse, title: 'Inventory', text: 'Catalogue and stock visibility' },
  { icon: Users, title: 'Customers', text: 'Contact records and lookup' },
  { icon: ClipboardList, title: 'Sales and reports', text: 'Recorded transactions and activity' },
  { icon: ShieldCheck, title: 'Staff access', text: 'Role-aware access in the platform' },
];

function Hero() {
  return (
    <section className="hero-section" aria-labelledby="hero-heading">
      <div className="hero-inner">
        <div className="hero-copy">
          <div className="hero-kicker">
            <span className="hero-kicker-icon"><CircleDollarSign size={13} /></span>
            Retail, brought together
          </div>
          <h1 id="hero-heading">
            Everything you need to run your <em>retail business.</em>
          </h1>
          <p className="hero-description">
            Bring sales, inventory, payments, customers and business management together in one simple system.
          </p>
          <div className="hero-actions">
            <Link className="btn btn--primary" to="/login">Get started <ArrowRight size={17} /></Link>
            <Link className="btn btn--ghost-light" to="/login">Sign in</Link>
          </div>
          <div className="hero-proof">
            <span><Check size={13} /></span>
            A clearer view of the work happening across your shop
          </div>
        </div>
        <div className="hero-product-wrap">
          <PosPreview variant="compact" />
          <div className="hero-float-note hero-float-note--a">
            <span className="float-note-icon"><PackageCheck size={16} /></span>
            <span><b>Stock-aware checkout</b><small>Items and totals, together</small></span>
          </div>
          <div className="hero-float-note hero-float-note--b">
            <span className="float-note-icon"><Smartphone size={16} /></span>
            <span><b>Cash or M-Pesa</b><small>Choose at the counter</small></span>
          </div>
        </div>
      </div>
      <a className="hero-scroll" href="#features"><span>Explore Kipchi</span><ArrowDown size={14} /></a>
    </section>
  );
}

function CapabilityStrip() {
  return (
    <div className="capability-strip" aria-label="Kipchi POS capabilities">
      {capabilities.map(({ icon: Icon, label }) => (
        <span key={label}><Icon size={14} /> {label}</span>
      ))}
    </div>
  );
}

function Features() {
  return (
    <section className="feature-section" id="features" aria-labelledby="features-heading">
      <div className="feature-section-inner">
        <div className="section-heading-row">
          <div>
            <span className="eyebrow">One system for the daily details</span>
            <h2 className="section-title" id="features-heading">The essentials, all working together.</h2>
          </div>
          <p className="section-lead">Kipchi brings the main parts of retail operations into one connected workspace.</p>
        </div>
        <div className="feature-grid">
          {features.map(({ icon: Icon, tone, title, text, variant, chip, bullets }) => (
            <article
              className={
                'feature-card' +
                (variant === 'wide' ? ' feature-card--wide' : '') +
                (variant === 'full' ? ' feature-card--full' : '')
              }
              key={title}
            >
              {chip && <span className="feature-card-chip"><Check size={12} /> {chip}</span>}
              <span className={'feature-icon ' + tone}><Icon size={20} strokeWidth={1.8} /></span>
              <h3>{title}</h3>
              <p>{text}</p>
              {bullets && (
                <div className="feature-card-pills">
                  {bullets.map((bullet) => <span key={bullet}><Check size={11} /> {bullet}</span>)}
                </div>
              )}
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

function HowItWorks() {
  return (
    <section className="how-section" id="how-it-works" aria-labelledby="how-heading">
      <div className="how-inner">
        <div className="how-head">
          <div>
            <span className="eyebrow">A straightforward daily flow</span>
            <h2 className="section-title" id="how-heading">From product search to paid.</h2>
            <p className="section-lead">Keep the routine clear for the people serving customers and managing the shop.</p>
          </div>
          <Link className="text-link" to="/login">Sign in to Kipchi <ArrowRight size={15} /></Link>
        </div>
        <div className="steps-grid">
          {steps.map(({ icon: Icon, title, text }, index) => (
            <article className="step-card" key={title}>
              <div className="step-top">
                <span className="step-index">0{index + 1}</span>
                <span className="step-icon"><Icon size={17} /></span>
              </div>
              <h3>{title}</h3>
              <p>{text}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

function Showcase() {
  return (
    <section className="showcase-section" aria-labelledby="showcase-heading">
      <div className="showcase-inner">
        <div className="showcase-copy">
          <span className="eyebrow eyebrow--light">A checkout that feels familiar</span>
          <h2 id="showcase-heading">The whole sale,<br />in one view.</h2>
          <p>Pick products, keep an eye on the cart, confirm the total and choose a payment method without losing your place.</p>
          <ul className="showcase-checks">
            <li><Check size={13} /> Search by product name or SKU</li>
            <li><Check size={13} /> See quantities and totals as you build the cart</li>
            <li><Check size={13} /> Choose cash or start an M-Pesa payment</li>
          </ul>
          <Link className="btn btn--light" to="/login">Open the sales desk <ArrowRight size={16} /></Link>
        </div>
        <div className="showcase-visual"><PosPreview /></div>
      </div>
    </section>
  );
}

function Management() {
  return (
    <section className="management-section" id="business-management" aria-labelledby="management-heading">
      <div className="management-inner">
        <div className="management-copy">
          <span className="eyebrow">More than checkout</span>
          <h2 className="section-title" id="management-heading">Keep the business in view.</h2>
          <p className="section-lead">
            Move between the records your team uses to serve customers, manage stock and understand sales activity.
          </p>
          <div className="management-links">
            {managementLinks.map(({ icon: Icon, title, text }) => (
              <div key={title}>
                <span className="management-link-icon"><Icon size={16} /></span>
                <span><b>{title}</b><small>{text}</small></span>
              </div>
            ))}
          </div>
        </div>
        <div className="management-visual" role="img" aria-label="Illustration of a retail management dashboard">
          <div className="management-window">
            <div className="management-window-top">
              <span className="window-dots"><i /><i /><i /></span>
              <span>Business overview</span>
              <span className="sample-tag">SAMPLE VIEW</span>
            </div>
            <div className="management-window-body">
              <div className="management-sidebar">
                <span className="sidebar-logo">K</span>
                <i className="sidebar-selected"><BarChart3 size={14} /></i>
                <i><ShoppingBag size={14} /></i>
                <i><PackageCheck size={14} /></i>
                <i><Users size={14} /></i>
              </div>
              <div className="management-content">
                <div className="management-title">
                  <span><small>YOUR WORKSPACE</small><b>Business overview</b></span>
                  <span className="period-chip">Recent activity</span>
                </div>
                <div className="overview-cards">
                  <div><span>Sales activity</span><b>Reports</b><small>Open sales reports</small></div>
                  <div><span>Transactions</span><b>Sales history</b><small>View recorded sales</small></div>
                  <div><span>Stock</span><b>Catalogue</b><small>View inventory</small></div>
                </div>
                <div className="activity-panel">
                  <div className="activity-heading"><b>Recent sales</b><span>Sample records</span></div>
                  <div className="activity-line"><span className="activity-dot blue-dot" /><span>Sale · Walk-in customer</span><b>KES 2,400</b></div>
                  <div className="activity-line"><span className="activity-dot green-dot" /><span>Sale · Customer record</span><b>KES 1,850</b></div>
                  <div className="activity-line"><span className="activity-dot yellow-dot" /><span>Sale · Walk-in customer</span><b>KES 760</b></div>
                </div>
              </div>
            </div>
          </div>
          <div className="management-caption">
            <span><span className="caption-dot" /> Sample workspace preview</span>
            <span>Sales · stock · customers</span>
          </div>
        </div>
      </div>
    </section>
  );
}

function Branches() {
  return (
    <section className="branches-section" aria-labelledby="branches-heading">
      <div className="branches-inner">
        <div className="branches-head">
          <span className="eyebrow">Built with growing teams in mind</span>
          <h2 className="section-title" id="branches-heading">A platform with branches in its foundations.</h2>
          <p className="section-lead">
            Kipchi includes branch records and branch-scoped staff access. Branch-level sales and stock workflows are still being expanded across the product.
          </p>
        </div>
        <div className="branch-map" role="img" aria-label="An organization connected to three branch locations">
          <div className="branch-root">
            <span><Building2 size={19} /></span>
            <div><b>Your business</b><small>Organization workspace</small></div>
          </div>
          <div className="branch-locations">
            <div className="branch-card">
              <span className="branch-store"><Warehouse size={17} /></span>
              <span><b>Branch A</b><small>Location record</small></span>
              <span className="branch-status">Example</span>
            </div>
            <div className="branch-card">
              <span className="branch-store"><Warehouse size={17} /></span>
              <span><b>Branch B</b><small>Location record</small></span>
              <span className="branch-status">Example</span>
            </div>
            <div className="branch-card branch-add">
              <span className="branch-store"><Building2 size={17} /></span>
              <span><b>More locations</b><small>Managed by authorized staff</small></span>
              <ArrowUpRight size={15} />
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function FinalCta() {
  return (
    <div className="cta-wrap">
      <section className="final-cta" aria-labelledby="cta-heading">
        <div className="final-cta-inner">
          <span className="eyebrow eyebrow--light">Kipchi POS</span>
          <h2 id="cta-heading">Ready to bring the work together?</h2>
          <p>Bring sales, inventory, customers and business management into one retail workspace.</p>
          <div className="cta-actions">
            <Link className="btn btn--light" to="/login">Get started <ArrowRight size={16} /></Link>
            <Link className="cta-signin" to="/login">Sign in to your account <ArrowUpRight size={15} /></Link>
          </div>
        </div>
      </section>
    </div>
  );
}

function Landing() {
  return (
    <div className="kipchi-site">
      <a className="skip-link" href="#main-content">Skip to content</a>
      <SiteHeader />
      <div id="main-content">
        <Hero />
        <CapabilityStrip />
        <Features />
        <HowItWorks />
        <Showcase />
        <Management />
        <Branches />
        <FinalCta />
      </div>
      <SiteFooter />
    </div>
  );
}

export default Landing;
