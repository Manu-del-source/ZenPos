const { Pool } = require('pg');
const bcrypt = require('bcryptjs');
const { v4: uuidv4 } = require('uuid');
require('dotenv').config();

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
});

async function seed() {
  const cashierPassword = process.env.BOOTSTRAP_CASHIER_PASSWORD;
  if (!cashierPassword || cashierPassword.length < 12) {
    throw new Error('BOOTSTRAP_CASHIER_PASSWORD must be configured with at least 12 characters');
  }
  const client = await pool.connect();
  try {
    await client.query('BEGIN');

    // 1. Create Branch
    const branchId = uuidv4();
    const branchCode = 'BR-001';
    await client.query(
      'INSERT INTO "Branch" (id, name, location, code, "updatedAt") VALUES ($1, $2, $3, $4, NOW()) ON CONFLICT (code) DO NOTHING',
      [branchId, 'Main Branch', 'Nairobi CBD', branchCode]
    );

    // Get branch ID (either new or existing)
    const branchRes = await client.query('SELECT id FROM "Branch" WHERE code = $1', [branchCode]);
    const actualBranchId = branchRes.rows[0].id;

    // 2. Create Cashier User
    const userId = uuidv4();
    const username = 'cashier1';
    const passwordHash = await bcrypt.hash(cashierPassword, 10);
    await client.query(
      'INSERT INTO "User" (id, username, "passwordHash", name, role, "branchId", "updatedAt") VALUES ($1, $2, $3, $4, $5, $6, NOW()) ON CONFLICT (username) DO NOTHING',
      [userId, username, passwordHash, 'John Doe', 'CASHIER', actualBranchId]
    );

    // 3. Create some products
    const products = [
      { id: uuidv4(), name: 'Milk 1L', barcode: '111111', price: 100, costPrice: 80, stockLevel: 50 },
      { id: uuidv4(), name: 'Bread 400g', barcode: '222222', price: 65, costPrice: 50, stockLevel: 100 },
      { id: uuidv4(), name: 'Sugar 1kg', barcode: '333333', price: 210, costPrice: 180, stockLevel: 30 },
    ];

    for (const p of products) {
      await client.query(
        'INSERT INTO "Product" (id, name, barcode, price, "costPrice", "stockLevel", "branchId", "updatedAt") VALUES ($1, $2, $3, $4, $5, $6, $7, NOW()) ON CONFLICT (barcode) DO NOTHING',
        [p.id, p.name, p.barcode, p.price, p.costPrice, p.stockLevel, actualBranchId]
      );
    }

    await client.query('COMMIT');
    console.log('✅ Manual Seed Successful!');
    console.log('Username: cashier1');
  } catch (err) {
    await client.query('ROLLBACK');
    console.error('❌ Seed Failed:', err);
  } finally {
    client.release();
    await pool.end();
  }
}

seed();
