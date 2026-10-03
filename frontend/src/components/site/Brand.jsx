import React from 'react';
import { Link } from 'react-router-dom';

/**
 * ZenPOS logo lockup. `tone="dark"` renders for dark backgrounds.
 */
function Brand({ tone = 'light', to = '/', label = 'ZenPOS home' }) {
  return (
    <Link
      className={'zenpos-brand' + (tone === 'dark' ? ' zenpos-brand--on-dark' : '')}
      to={to}
      aria-label={label}
    >
      <span className="zenpos-brand-mark" aria-hidden="true"><span>Z</span></span>
      <span className="zenpos-brand-name">zen<span>POS</span></span>
    </Link>
  );
}

export default Brand;
