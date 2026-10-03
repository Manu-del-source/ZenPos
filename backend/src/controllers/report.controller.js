const db = require('../config/db');

exports.getDashboardStats = async (req, res) => {
  try {
    const { branchId } = req.user;

    // 1. Total Revenue (Today)
    const revenueToday = await db.query(
      'SELECT SUM(total) as revenue FROM "Sale" WHERE "branchId" = $1 AND "createdAt" >= CURRENT_DATE',
      [branchId]
    );

    // 2. Sales Count (Today)
    const salesToday = await db.query(
      'SELECT COUNT(*) as count FROM "Sale" WHERE "branchId" = $1 AND "createdAt" >= CURRENT_DATE',
      [branchId]
    );

    // 3. Low Stock Count
    const lowStockCount = await db.query(
      'SELECT COUNT(*) as count FROM "Product" WHERE "branchId" = $1 AND "stockLevel" <= "lowStockThreshold"',
      [branchId]
    );

    // 4. Net Profit (Today): sum of (unitPrice - costPrice) * quantity sold
    const profitToday = await db.query(
      `SELECT COALESCE(SUM((si."unitPrice" - p."costPrice") * si.quantity), 0) as profit
       FROM "SaleItem" si
       JOIN "Sale" s ON si."saleId" = s.id
       JOIN "Product" p ON si."productId" = p.id
       WHERE s."branchId" = $1 AND s."createdAt" >= CURRENT_DATE`,
      [branchId]
    );

    // 5. Top Selling Products (all time)
    const topSelling = await db.query(
      `SELECT p.name, SUM(si.quantity) as "totalSold", SUM(si.subtotal) as revenue
       FROM "SaleItem" si
       JOIN "Product" p ON si."productId" = p.id
       JOIN "Sale" s ON si."saleId" = s.id
       WHERE s."branchId" = $1
       GROUP BY p.id, p.name
       ORDER BY "totalSold" DESC LIMIT 5`,
      [branchId]
    );

    // 6. Low Stock Items
    const lowStock = await db.query(
      'SELECT id, name, "stockLevel", "lowStockThreshold" FROM "Product" WHERE "branchId" = $1 AND "stockLevel" <= "lowStockThreshold" ORDER BY "stockLevel" ASC LIMIT 10',
      [branchId]
    );

    res.json({
      revenueToday: revenueToday.rows[0].revenue || 0,
      salesToday: salesToday.rows[0].count,
      lowStockCount: lowStockCount.rows[0].count,
      profitToday: profitToday.rows[0].profit || 0,
      topSelling: topSelling.rows,
      lowStock: lowStock.rows
    });
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
};

exports.getSalesReport = async (req, res) => {
  try {
    const { branchId } = req.user;
    const { startDate, endDate } = req.query;

    const result = await db.query(
      'SELECT COUNT(*) as "totalSales", SUM(total) as "totalRevenue", SUM(tax) as "totalTax" FROM "Sale" WHERE "branchId" = $1 AND "createdAt" BETWEEN $2 AND $3',
      [branchId, startDate || '1970-01-01', endDate || '9999-12-31']
    );

    res.json(result.rows[0]);
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
};

exports.getTopProducts = async (req, res) => {
  try {
    const { branchId } = req.user;
    const result = await db.query(
      `SELECT p.name, SUM(si.quantity) as "totalSold", SUM(si.subtotal) as revenue 
       FROM "SaleItem" si 
       JOIN "Product" p ON si."productId" = p.id 
       JOIN "Sale" s ON si."saleId" = s.id 
       WHERE s."branchId" = $1 
       GROUP BY p.id, p.name 
       ORDER BY "totalSold" DESC LIMIT 10`,
      [branchId]
    );
    res.json(result.rows);
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
};

exports.getInventoryAlerts = async (req, res) => {
  try {
    const { branchId } = req.user;
    const result = await db.query(
      'SELECT * FROM "Product" WHERE "branchId" = $1 AND "stockLevel" <= "lowStockThreshold"',
      [branchId]
    );
    res.json(result.rows);
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
};
