const db = require('../config/db');
const { v4: uuidv4 } = require('uuid');

exports.getCustomers = async (req, res) => {
  try {
    const { search } = req.query;
    const result = search
      ? await db.query(
          'SELECT * FROM "Customer" WHERE name ILIKE $1 OR phone ILIKE $1 ORDER BY name ASC',
          [`%${search}%`]
        )
      : await db.query('SELECT * FROM "Customer" ORDER BY name ASC');
    res.json(result.rows);
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
};

exports.getCustomerByPhone = async (req, res) => {
  try {
    const { phone } = req.params;
    const result = await db.query('SELECT * FROM "Customer" WHERE phone = $1', [phone]);
    if (result.rows.length === 0) return res.status(404).json({ message: 'Customer not found' });
    res.json(result.rows[0]);
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
};

exports.createCustomer = async (req, res) => {
  try {
    const { name, phone } = req.body;
    const id = uuidv4();
    const result = await db.query(
      'INSERT INTO "Customer" (id, name, phone, "loyaltyPoints", "updatedAt") VALUES ($1, $2, $3, 0, NOW()) RETURNING *',
      [id, name, phone]
    );
    res.json(result.rows[0]);
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
};

exports.updateCustomer = async (req, res) => {
  try {
    const { id } = req.params;
    const { name, phone } = req.body;
    const result = await db.query(
      'UPDATE "Customer" SET name = COALESCE($1, name), phone = COALESCE($2, phone), "updatedAt" = NOW() WHERE id = $3 RETURNING *',
      [name, phone, id]
    );
    if (result.rows.length === 0) return res.status(404).json({ message: 'Customer not found' });
    res.json(result.rows[0]);
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
};

exports.deleteCustomer = async (req, res) => {
  try {
    const { id } = req.params;
    await db.query('DELETE FROM "Customer" WHERE id = $1', [id]);
    res.json({ message: 'Customer deleted' });
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
};

exports.redeemPoints = async (req, res) => {
  try {
    const { id } = req.params;
    const { points } = req.body;
    
    const result = await db.query('SELECT * FROM "Customer" WHERE id = $1', [id]);
    const customer = result.rows[0];
    
    if (!customer) return res.status(404).json({ message: 'Customer not found' });
    if (customer.loyaltyPoints < points) {
      return res.status(400).json({ message: 'Insufficient loyalty points' });
    }

    const updateResult = await db.query(
      'UPDATE "Customer" SET "loyaltyPoints" = "loyaltyPoints" - $1, "updatedAt" = NOW() WHERE id = $2 RETURNING *',
      [points, id]
    );

    res.json(updateResult.rows[0]);
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
};
