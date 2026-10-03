import Dexie from 'dexie';

export const db = new Dexie('ZenPOS_DB');

db.version(1).stores({
  products: '++id, name, barcode, price, stockLevel',
  salesQueue: '++id, total, items, status, createdAt',
  settings: 'key, value'
});

export const saveProductToLocal = async (products) => {
  await db.products.bulkPut(products);
};

export const queueSaleOffline = async (sale) => {
  return await db.salesQueue.add({
    ...sale,
    status: 'pending_sync',
    createdAt: new Date().toISOString()
  });
};
