import React from 'react';
import {
  ArrowRight, Building2, ChevronDown, CreditCard, Package,
  Search, ShieldCheck, ShoppingCart, Smartphone, Users,
} from 'lucide-react';

const products = [
  { name: 'Everyday notebook', sku: 'ST-204', price: 'KES 180', stock: 'In stock', tone: 'blue' },
  { name: 'Canvas tote bag', sku: 'AC-118', price: 'KES 950', stock: 'In stock', tone: 'sand' },
  { name: 'Desk lamp', sku: 'HM-032', price: 'KES 2,400', stock: 'Low stock', tone: 'green' },
];

/**
 * Sample ZenPOS checkout window used as marketing artwork.
 * `variant="compact"` (hero) is slightly rotated and floated; `variant="showcase"`
 * is the full-size copy on the dark band. Content is illustrative sample data.
 */
function PosPreview({ variant = 'showcase' }) {
  return (
    <div
      className={'pos-preview' + (variant === 'compact' ? ' pos-preview-compact' : '')}
      role="img"
      aria-label="Sample ZenPOS point of sale screen with product search, a two-item cart, KES total, and cash or M-Pesa payment options"
    >
      <div className="preview-topbar">
        <div className="preview-brand"><span className="preview-brand-mark">Z</span><b>Zen<span>POS</span></b></div>
        <div className="preview-location"><Building2 size={13} /> Main store <ChevronDown size={12} /></div>
        <div className="preview-avatar">JM</div>
      </div>
      <div className="preview-workspace">
        <div className="preview-catalog">
          <div className="preview-title-row">
            <div><small>SALES COUNTER</small><h3>New sale</h3></div>
            <span className="preview-time">Today, 10:42 AM</span>
          </div>
          <div className="preview-search"><Search size={14} /><span>Search by product or scan barcode</span><kbd>/</kbd></div>
          <div className="preview-filter-row"><span className="filter-active">All products</span><span>Popular</span><span>Recently added</span></div>
          <div className="preview-products">
            {products.map((product) => (
              <div className="preview-product" key={product.sku}>
                <div className={'preview-product-art ' + product.tone}><Package size={22} strokeWidth={1.6} /></div>
                <span className="preview-product-name">{product.name}</span>
                <span className="preview-product-sku">{product.sku}</span>
                <div className="preview-product-bottom">
                  <b>{product.price}</b>
                  <span className={product.stock === 'Low stock' ? 'low-stock' : ''}>{product.stock}</span>
                </div>
              </div>
            ))}
          </div>
          <div className="preview-product-foot">
            <span><span className="stock-dot" /> Stock updates as sales are recorded</span>
            <span>Showing 3 products</span>
          </div>
        </div>
        <aside className="preview-cart">
          <div className="preview-cart-heading">
            <div><ShoppingCart size={15} /><b>Current order</b></div>
            <span>2 items</span>
          </div>
          <div className="preview-customer"><Users size={13} /><span>Walk-in customer</span><ChevronDown size={12} /></div>
          <div className="preview-cart-items">
            <div className="preview-cart-item">
              <span className="cart-item-thumb blue"><Package size={15} /></span>
              <span className="cart-item-copy"><b>Everyday notebook</b><small>KES 180 each</small></span>
              <span className="cart-quantity">× 2</span>
              <b>KES 360</b>
            </div>
            <div className="preview-cart-item">
              <span className="cart-item-thumb sand"><Package size={15} /></span>
              <span className="cart-item-copy"><b>Canvas tote bag</b><small>KES 950 each</small></span>
              <span className="cart-quantity">× 1</span>
              <b>KES 950</b>
            </div>
          </div>
          <div className="preview-totals">
            <div><span>Subtotal</span><b>KES 1,310</b></div>
            <div><span>VAT</span><span>Included</span></div>
            <div className="preview-total"><b>Total due</b><b>KES 1,310</b></div>
          </div>
          <div className="preview-payment-label">PAYMENT METHOD</div>
          <div className="preview-payment-options">
            <span className="selected"><CreditCard size={13} /> Cash</span>
            <span><Smartphone size={13} /> M-Pesa</span>
          </div>
          <button className="preview-checkout" type="button" tabIndex={-1}>
            Complete sale <ArrowRight size={14} />
          </button>
          <div className="preview-secure"><ShieldCheck size={11} /> Checkout preview · sample data</div>
        </aside>
      </div>
    </div>
  );
}

export default PosPreview;
