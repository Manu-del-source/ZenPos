import React from 'react';
import { Link } from 'react-router-dom';

/**
 * Kipchi POS logo lockup. `tone="dark"` renders for dark backgrounds.
 */
function Brand({ tone = 'light', to = '/', label = 'Kipchi POS home' }) {
  return (
    <Link
      className={'kipchi-brand' + (tone === 'dark' ? ' kipchi-brand--on-dark' : '')}
      to={to}
      aria-label={label}
    >
      <span className="kipchi-brand-mark" aria-hidden="true"><span>K</span></span>
      <span className="kipchi-brand-name">kipchi<span>POS</span></span>
    </Link>
  );
}

export default Brand;
