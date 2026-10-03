const db = require('../config/db');
const { v4: uuidv4 } = require('uuid');

exports.getProducts = async (req, res) => {
  try {
    const { branchId } = req.user;
    const { search } = req.query;
    const result = search
      ? await db.query(
          'SELECT * FROM "Product" WHERE "branchId" = $1 AND (name ILIKE $2 OR barcode ILIKE $2 OR COALESCE(sku, \'\') ILIKE $2) ORDER BY name ASC',
          [branchId, `%${search}%`]
        )
      : await db.query(
          'SELECT * FROM "Product" WHERE "branchId" = $1 ORDER BY name ASC',
          [branchId]
        );
    res.json(result.rows);
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
};

exports.getProductByBarcode = async (req, res) => {
  try {
    const { barcode } = req.params;
    const { branchId } = req.user;
    const result = await db.query(
      'SELECT * FROM "Product" WHERE barcode = $1 AND "branchId" = $2',
      [barcode, branchId]
    );
    if (result.rows.length === 0) return res.status(404).json({ message: 'Product not found' });
    res.json(result.rows[0]);
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
};

exports.upsertProduct = async (req, res) => {
  try {
    const { name, barcode, price, costPrice, stockLevel, lowStockThreshold, sku, category } = req.body;
    const { branchId } = req.user;

    const existing = await db.query(
      'SELECT id FROM "Product" WHERE barcode = $1 AND "branchId" = $2',
      [barcode, branchId]
    );

    let result;
    if (existing.rows.length > 0) {
      result = await db.query(
        'UPDATE "Product" SET name = $1, price = $2, "costPrice" = $3, "stockLevel" = $4, "lowStockThreshold" = $5, sku = $6, category = $7, "updatedAt" = NOW() WHERE id = $8 RETURNING *',
        [name, price, costPrice, stockLevel, lowStockThreshold, sku, category, existing.rows[0].id]
      );
    } else {
      const id = uuidv4();
      result = await db.query(
        'INSERT INTO "Product" (id, name, barcode, price, "costPrice", "stockLevel", "lowStockThreshold", sku, category, "branchId", "updatedAt") VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW()) RETURNING *',
        [id, name, barcode, price, costPrice, stockLevel, lowStockThreshold, sku, category, branchId]
      );
    }
    res.json(result.rows[0]);
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
};

exports.updateProduct = async (req, res) => {
  try {
    const { id } = req.params;
    const { name, price, stockLevel } = req.body;
    const result = await db.query(
      'UPDATE "Product" SET name = COALESCE($1, name), price = COALESCE($2, price), "stockLevel" = COALESCE($3, "stockLevel"), "updatedAt" = NOW() WHERE id = $4 RETURNING *',
      [name, price, stockLevel, id]
    );
    if (result.rows.length === 0) return res.status(404).json({ message: 'Product not found' });
    res.json(result.rows[0]);
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
};

exports.deleteProduct = async (req, res) => {
  try {
    const { id } = req.params;
    await db.query('DELETE FROM "Product" WHERE id = $1', [id]);
    res.json({ message: 'Product deleted' });
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
};

exports.updateStock = async (req, res) => {
  try {
    const { id } = req.params;
    const { quantity } = req.body; // positive to add, negative to subtract
    const result = await db.query(
      'UPDATE "Product" SET "stockLevel" = "stockLevel" + $1, "updatedAt" = NOW() WHERE id = $2 RETURNING *',
      [quantity, id]
    );
    if (result.rows.length === 0) return res.status(404).json({ message: 'Product not found' });
    res.json(result.rows[0]);
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
};
