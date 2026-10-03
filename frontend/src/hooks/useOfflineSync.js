import { useEffect } from 'react';
import api from '../services/api';
import { db } from '../services/db';

const useOfflineSync = (token) => {
  useEffect(() => {
    const syncSales = async () => {
      if (!navigator.onLine || !token) return;

      const offlineSales = await db.salesQueue
        .where('status')
        .equals('pending_sync')
        .toArray();

      if (offlineSales.length === 0) return;

      console.log(`Syncing ${offlineSales.length} offline sales...`);

      for (const sale of offlineSales) {
        try {
          await api.post('/v1/sales', sale);
          // Update status in local DB to synced
          await db.salesQueue.update(sale.id, { status: 'synced' });
        } catch (error) {
          console.error('Sync failed for sale:', sale.id, error);
        }
      }
    };


    window.addEventListener('online', syncSales);
    // Initial sync check
    syncSales();

    return () => window.removeEventListener('online', syncSales);
  }, [token]);
};

export default useOfflineSync;
