import React from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight, ArrowUpRight, BarChart3, Boxes, Check, ChevronRight,
  ClipboardList, CreditCard, Package, ReceiptText, Smartphone, Users,
} from 'lucide-react';
import SiteHeader from '../components/site/SiteHeader';
import SiteFooter from '../components/site/SiteFooter';
import PosPreview from '../components/site/PosPreview';
import '../styles/site.css';
import '../styles/landing.css';

const features = [
  {
    icon: CreditCard,
    number: '01',
    title: 'Sell without friction',
    text: 'A focused checkout for busy counters. Search products, manage the cart and take payment without unnecessary screens.',
  },
  {
    icon: Boxes,
    number: '02',
    title: 'Know what is in stock',
    text: 'Keep your catalogue and stock movements connected to every recorded sale so the team works from the same numbers.',
  },
  {
    icon: BarChart3,
    number: '03',
    title: 'See the business clearly',
    text: 'Sales history, customers and reporting give owners a practical view of what happened in the shop.',
  },
];

const workflow = [
  { icon: Package, title: 'Catalogue', text: 'Products, prices and stock in one place.' },
  { icon: ReceiptText, title: 'Checkout', text: 'Build the order and confirm the total.' },
  { icon: Smartphone, title: 'Payment', text: 'Cash today, M-Pesa when you need it.' },
  { icon: ClipboardList, title: 'Records', text: 'Every completed sale stays in the system.' },
];

function Hero() {
  return (
    <section className="lp-hero">
      <div className="lp-hero-inner">
        <div className="lp-hero-copy">
          <p className="lp-overline">POINT OF SALE · INVENTORY · PAYMENTS</p>
          <h1>Run the shop.<br /><span>Not the paperwork.</span></h1>
          <p className="lp-hero-text">
            ZenPOS is a straightforward retail system for businesses that need sales,
            stock and payments to stay in sync.
          </p>
          <div className="lp-hero-actions">
            <Link className="lp-button lp-button--dark" to="/login">
              Open ZenPOS <ArrowRight size={16} />
            </Link>
            <a className="lp-text-button" href="#features">
              See how it works <ChevronRight size={15} />
            </a>
          </div>
          <div className="lp-local-note">
            <span className="lp-check"><Check size={12} /></span>
            Designed around everyday retail in Kenya
          </div>
        </div>

        <div className="lp-hero-product">
          <div className="lp-browser-bar">
            <span className="lp-browser-dots"><i /><i /><i /></span>
            <span>ZenPOS · Point of Sale</span>
            <span className="lp-browser-live">LIVE</span>
          </div>
          <PosPreview variant="compact" />
        </div>
      </div>
    </section>
  );
}

function Intro() {
  return (
    <section className="lp-intro">
      <div className="lp-container lp-intro-grid">
        <p className="lp-intro-label">A retail workspace, kept simple.</p>
        <div>
          <h2>Everything at the counter should be easy to find.</h2>
          <p>
            ZenPOS brings the work that usually gets scattered across notebooks,
            spreadsheets and separate payment steps into one calm workspace.
          </p>
        </div>
      </div>
    </section>
  );
}

function Features() {
  return (
    <section className="lp-section lp-features" id="features">
      <div className="lp-container">
        <div className="lp-section-head">
          <div>
            <p className="lp-overline">THE CORE</p>
            <h2>Built around the work that matters.</h2>
          </div>
          <p>Less dashboard theatre. More useful tools for the person actually running the counter.</p>
        </div>
        <div className="lp-feature-grid">
          {features.map(({ icon: Icon, number, title, text }) => (
            <article className="lp-feature" key={title}>
              <div className="lp-feature-top">
                <span>{number}</span>
                <Icon size={20} />
              </div>
              <h3>{title}</h3>
              <p>{text}</p>
              <span className="lp-feature-line" />
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

function Workflow() {
  return (
    <section className="lp-workflow" id="how-it-works">
      <div className="lp-container">
        <div className="lp-workflow-head">
          <div>
            <p className="lp-overline">ONE DAILY FLOW</p>
            <h2>From shelf to sale.</h2>
          </div>
          <p>Keep the routine familiar for staff while keeping the records useful for the owner.</p>
        </div>
        <div className="lp-workflow-grid">
          {workflow.map(({ icon: Icon, title, text }, index) => (
            <div className="lp-workflow-item" key={title}>
              <div className="lp-workflow-number">0{index + 1}</div>
              <Icon size={19} />
              <h3>{title}</h3>
              <p>{text}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function Management() {
  return (
    <section className="lp-management" id="business-management">
      <div className="lp-container lp-management-grid">
        <div className="lp-management-copy">
          <p className="lp-overline">BEYOND THE TILL</p>
          <h2>The owner sees what the cashier sees.</h2>
          <p>
            Sales, stock and customer records live in the same workspace. That means
            fewer handovers, fewer guesses and a clearer picture at the end of the day.
          </p>
          <div className="lp-list">
            <div><Check size={15} /><span>Sales history with recorded transaction details</span></div>
            <div><Check size={15} /><span>Inventory visibility linked to sales</span></div>
            <div><Check size={15} /><span>Customer records for repeat business</span></div>
          </div>
          <Link className="lp-inline-link" to="/login">Go to the workspace <ArrowUpRight size={15} /></Link>
        </div>

        <div className="lp-management-card">
          <div className="lp-management-card-head">
            <div>
              <span>ZENPOS WORKSPACE</span>
              <strong>Today at a glance</strong>
            </div>
            <span className="lp-date">LIVE DATA</span>
          </div>
          <div className="lp-metrics">
            <div><span>Sales</span><strong>Recorded</strong><small>Every completed order</small></div>
            <div><span>Inventory</span><strong>Connected</strong><small>Stock-aware checkout</small></div>
            <div><span>Customers</span><strong>Organised</strong><small>One customer record</small></div>
          </div>
          <div className="lp-activity">
            <div className="lp-activity-head"><strong>Recent activity</strong><span>Sales desk</span></div>
            <div><span className="lp-activity-dot" />Sale recorded <b>CASH</b></div>
            <div><span className="lp-activity-dot lp-activity-dot--green" />Payment workflow <b>M-PESA</b></div>
            <div><span className="lp-activity-dot lp-activity-dot--muted" />Stock updated <b>INVENTORY</b></div>
          </div>
        </div>
      </div>
    </section>
  );
}

function FinalCta() {
  return (
    <section className="lp-final">
      <div className="lp-container lp-final-inner">
        <div>
          <p className="lp-overline">ZENPOS</p>
          <h2>Make the next sale<br />the easy part.</h2>
        </div>
        <div className="lp-final-side">
          <p>Start with the tools your shop needs today. Add more as the business grows.</p>
          <Link className="lp-button lp-button--light" to="/login">Open ZenPOS <ArrowRight size={16} /></Link>
        </div>
      </div>
    </section>
  );
}

function Landing() {
  return (
    <div className="zenpos-site lp-site">
      <a className="skip-link" href="#main-content">Skip to content</a>
      <SiteHeader />
      <main id="main-content">
        <Hero />
        <Intro />
        <Features />
        <Workflow />
        <Management />
        <FinalCta />
      </main>
      <SiteFooter />
    </div>
  );
}

export default Landing;
