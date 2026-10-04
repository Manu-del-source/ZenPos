import { useEffect } from 'react';
import api from '../services/api';
import { db } from '../services/db';

// Offline sales are intentionally not pushed until the frontend and Django
// sales contract are aligned. The old Express endpoint (/v1/sales) is gone.
const useOfflineSync = (token) => {
  useEffect(() => {
    if (!navigator.onLine || !token) return undefined;

    // Keep the queue intact while online. A later sales-sync implementation
    // can submit the exact Django SaleSerializer payload atomically.
    // Do not call the removed Express API endpoint here.
    return undefined;
  }, [token]);

  return null;
};

export default useOfflineSync;
