import Dexie from 'dexie';
import api from './api';
import toast from 'react-hot-toast';

// 1. Setup Local Database
export const db = new Dexie('KipchiOfflineDB');
db.version(1).stores({
  offlineSales: '++id, sale_number, sync_status',
  cachedProducts: 'id, barcode, name'
});

// 2. Sync Manager
export const syncOfflineSales = async () => {
  const pendingSales = await db.offlineSales.where('sync_status').equals('pending').toArray();
  
  if (pendingSales.length === 0) return;

  console.log(`🔄 Syncing ${pendingSales.length} offline sales...`);
  
  for (const sale of pendingSales) {
    try {
      // Remove local ID before sending to Django
      const { id, sync_status, ...saleData } = sale;
      await api.post('/v1/sales', saleData);
      
      // Update local status
      await db.offlineSales.update(id, { sync_status: 'synced' });
      toast.success(`Synced sale: ${sale.sale_number}`);
    } catch (err) {
      console.error('❌ Sync failed for sale:', sale.sale_number);
    }
  }
};

// 3. Auto-sync heartbeat
setInterval(() => {
  if (navigator.onLine) syncOfflineSales();
}, 30000); // Try every 30 seconds
