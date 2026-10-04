import sqlite3
import os
from datetime import datetime
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

DB_PATH = os.path.join(os.path.dirname(__file__), "pos.db")
_password_hasher = PasswordHasher()

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def hash_password(password):
    return _password_hasher.hash(password)

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'cashier'
        );
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        );
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            category_id INTEGER,
            cost_price REAL NOT NULL DEFAULT 0,
            price REAL NOT NULL DEFAULT 0,
            stock INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (category_id) REFERENCES categories(id)
        );
        CREATE INDEX IF NOT EXISTS idx_products_sku ON products(sku);
        CREATE INDEX IF NOT EXISTS idx_products_name ON products(name);
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            email TEXT
        );
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            customer_id INTEGER,
            total REAL NOT NULL DEFAULT 0,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        );
        CREATE TABLE IF NOT EXISTS sale_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            price_per_unit REAL NOT NULL,
            FOREIGN KEY (sale_id) REFERENCES sales(id),
            FOREIGN KEY (product_id) REFERENCES products(id)
        );
        CREATE INDEX IF NOT EXISTS idx_sales_timestamp ON sales(timestamp);
        CREATE INDEX IF NOT EXISTS idx_sale_items_sale_id ON sale_items(sale_id);
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            amount REAL NOT NULL,
            category TEXT,
            description TEXT
        );
    """)
    # Seed default categories
    exist = cursor.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
    if exist == 0:
        cats = [("Hardware",), ("Building Materials",), ("Motorcycle Parts",),
                ("Tools",), ("Electrical",), ("Plumbing",)]
        cursor.executemany("INSERT INTO categories (name) VALUES (?)", cats)
    # Migration: Add cost_price if it doesn't exist
    try:
        cursor.execute("SELECT cost_price FROM products LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE products ADD COLUMN cost_price REAL NOT NULL DEFAULT 0")
        
    conn.commit()
    conn.close()

# ---------- User functions ----------
def check_user(username, password):
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if row is None or not verify_password(row["password_hash"], password):
            return None
        return dict(row)
    finally:
        conn.close()


def _is_legacy_sha256(encoded):
    return len(encoded) == 64 and all(char in "0123456789abcdefABCDEF" for char in encoded)


def verify_password(encoded, password):
    # SHA-256 rows are deliberately rejected: the old seeded credentials were
    # public, and the legacy schema cannot distinguish them from real accounts.
    if _is_legacy_sha256(encoded):
        return False
    try:
        return _password_hasher.verify(encoded, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError, TypeError):
        return False


def get_user_by_id(user_id):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, username, role FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_user_by_username(username):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, username, role FROM users WHERE username = ?", (username,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def get_all_users():
    conn = get_connection()
    rows = conn.execute("SELECT id, username, role FROM users").fetchall()
    conn.close()
    return rows

def add_user(username, password, role):
    conn = get_connection()
    try:
        conn.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                     (username, hash_password(password), role))
        conn.commit()
    finally:
        conn.close()


def reset_user_password(username, password):
    conn = get_connection()
    try:
        result = conn.execute(
            "UPDATE users SET password_hash = ? WHERE username = ?",
            (hash_password(password), username),
        )
        conn.commit()
        return result.rowcount == 1
    finally:
        conn.close()

def delete_user(user_id):
    conn = get_connection()
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

# ---------- Product functions ----------
def add_product(sku, name, category_id, cost_price, price, stock):
    conn = get_connection()
    conn.execute("INSERT INTO products (sku, name, category_id, cost_price, price, stock) VALUES (?,?,?,?,?,?)",
                 (sku, name, category_id, cost_price, price, stock))
    conn.commit()
    conn.close()

def update_product(product_id, sku, name, category_id, cost_price, price, stock):
    conn = get_connection()
    conn.execute("UPDATE products SET sku=?, name=?, category_id=?, cost_price=?, price=?, stock=? WHERE id=?",
                 (sku, name, category_id, cost_price, price, stock, product_id))
    conn.commit()
    conn.close()

def delete_product(product_id):
    conn = get_connection()
    conn.execute("DELETE FROM products WHERE id=?", (product_id,))
    conn.commit()
    conn.close()

def get_all_products():
    conn = get_connection()
    rows = conn.execute("""
        SELECT p.id, p.sku, p.name, c.name as category, p.cost_price, p.price, p.stock
        FROM products p LEFT JOIN categories c ON p.category_id = c.id
        ORDER BY p.name
    """).fetchall()
    conn.close()
    return rows

def get_product_by_sku(sku):
    conn = get_connection()
    row = conn.execute("""
        SELECT p.id, p.sku, p.name, c.name as category, p.cost_price, p.price, p.stock
        FROM products p LEFT JOIN categories c ON p.category_id = c.id
        WHERE p.sku = ?
    """, (sku,)).fetchone()
    conn.close()
    return row

def search_products(search_term):
    conn = get_connection()
    rows = conn.execute("""
        SELECT p.id, p.sku, p.name, c.name as category, p.cost_price, p.price, p.stock
        FROM products p LEFT JOIN categories c ON p.category_id = c.id
        WHERE p.name LIKE ? OR p.sku LIKE ?
        ORDER BY p.name
    """, (f"%{search_term}%", f"%{search_term}%")).fetchall()
    conn.close()
    return rows

def get_low_stock_products(threshold=10):
    conn = get_connection()
    rows = conn.execute("""
        SELECT p.id, p.sku, p.name, p.stock, p.price
        FROM products p
        WHERE p.stock <= ?
        ORDER BY p.stock ASC
    """, (threshold,)).fetchall()
    conn.close()
    return rows

def get_categories():
    conn = get_connection()
    rows = conn.execute("SELECT id, name FROM categories ORDER BY name").fetchall()
    conn.close()
    return rows

# ---------- Customer functions ----------
def add_customer(name, phone, email):
    conn = get_connection()
    conn.execute("INSERT INTO customers (name, phone, email) VALUES (?,?,?)",
                 (name, phone, email))
    conn.commit()
    conn.close()

def update_customer(cust_id, name, phone, email):
    conn = get_connection()
    conn.execute("UPDATE customers SET name=?, phone=?, email=? WHERE id=?",
                 (name, phone, email, cust_id))
    conn.commit()
    conn.close()

def delete_customer(cust_id):
    conn = get_connection()
    conn.execute("DELETE FROM customers WHERE id=?", (cust_id,))
    conn.commit()
    conn.close()

def get_all_customers():
    conn = get_connection()
    rows = conn.execute("SELECT id, name, phone, email FROM customers ORDER BY name").fetchall()
    conn.close()
    return rows

def search_customers(term):
    conn = get_connection()
    rows = conn.execute("SELECT id, name, phone, email FROM customers WHERE name LIKE ? OR phone LIKE ?",
                       (f"%{term}%", f"%{term}%")).fetchall()
    conn.close()
    return rows

# ---------- Sales functions (updated with customer) ----------
def create_sale(items, customer_id=None):
    """
    items: list of dicts {product_id, quantity}
    Prices are fetched from the database at the time of sale for data integrity.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        total = 0
        sale_items_to_insert = []
        
        for item in items:
            # Fetch current product details (price and stock)
            prod = cursor.execute("SELECT price, stock, name FROM products WHERE id = ?", (item["product_id"],)).fetchone()
            if not prod:
                raise ValueError(f"Product ID {item['product_id']} not found.")
            
            if prod["stock"] < item["quantity"]:
                raise ValueError(f"Insufficient stock for {prod['name']}. Available: {prod['stock']}")
            
            price_per_unit = prod["price"]
            subtotal = price_per_unit * item["quantity"]
            total += subtotal
            
            sale_items_to_insert.append((item["product_id"], item["quantity"], price_per_unit))
            
            # Deduct stock
            cursor.execute("UPDATE products SET stock = stock - ? WHERE id = ?", (item["quantity"], item["product_id"]))
        
        # Create sale record
        cursor.execute("INSERT INTO sales (timestamp, customer_id, total) VALUES (?, ?, ?)",
                       (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), customer_id, total))
        sale_id = cursor.lastrowid
        
        # Insert sale items
        for p_id, qty, price in sale_items_to_insert:
            cursor.execute("INSERT INTO sale_items (sale_id, product_id, quantity, price_per_unit) VALUES (?,?,?,?)",
                           (sale_id, p_id, qty, price))
        
        conn.commit()
        return total, sale_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def get_recent_sales(limit=50):
    conn = get_connection()
    rows = conn.execute("""
        SELECT s.id, s.timestamp, s.total, c.name as customer
        FROM sales s LEFT JOIN customers c ON s.customer_id = c.id
        ORDER BY s.timestamp DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return rows

def get_sale_items(sale_id):
    conn = get_connection()
    rows = conn.execute("""
        SELECT pr.name, pr.sku, si.quantity, si.price_per_unit,
               (si.quantity * si.price_per_unit) as subtotal
        FROM sale_items si
        JOIN products pr ON si.product_id = pr.id
        WHERE si.sale_id = ?
    """, (sale_id,)).fetchall()
    conn.close()
    return rows

# ---------- Expense functions ----------
def add_expense(amount, category, description=""):
    conn = get_connection()
    conn.execute("INSERT INTO expenses (timestamp, amount, category, description) VALUES (?,?,?,?)",
                 (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), amount, category, description))
    conn.commit()
    conn.close()

def get_expenses(start_date=None, end_date=None):
    conn = get_connection()
    query = "SELECT id, timestamp, amount, category, description FROM expenses"
    params = []
    if start_date and end_date:
        query += " WHERE date(timestamp) BETWEEN ? AND ?"
        params = [start_date, end_date]
    query += " ORDER BY timestamp DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return rows

# ---------- Report functions ----------
def get_daily_sales(date_str=None):
    """Returns list of sales for a given date (YYYY-MM-DD)."""
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")
    conn = get_connection()
    rows = conn.execute("""
        SELECT id, timestamp, total, customer_id FROM sales
        WHERE date(timestamp) = ?
    """, (date_str,)).fetchall()
    conn.close()
    return rows

def get_sales_summary(date_str):
    conn = get_connection()
    row = conn.execute("""
        SELECT COUNT(*) as count, COALESCE(SUM(total),0) as total FROM sales
        WHERE date(timestamp) = ?
    """, (date_str,)).fetchone()
    conn.close()
    return row

def get_top_products(date_str, limit=5):
    conn = get_connection()
    rows = conn.execute("""
        SELECT pr.name, SUM(si.quantity) as sold, SUM(si.quantity * si.price_per_unit) as revenue
        FROM sale_items si
        JOIN sales s ON si.sale_id = s.id
        JOIN products pr ON si.product_id = pr.id
        WHERE date(s.timestamp) = ?
        GROUP BY si.product_id
        ORDER BY sold DESC
        LIMIT ?
    """, (date_str, limit)).fetchall()
    conn.close()
    return rows

def get_top_selling_products(date_str, limit=5):
    conn = get_connection()
    rows = conn.execute("""
        SELECT p.name, SUM(si.quantity) as total_qty, SUM(si.quantity * si.price_per_unit) as total_revenue
        FROM sale_items si
        JOIN sales s ON si.sale_id = s.id
        JOIN products p ON si.product_id = p.id
        WHERE date(s.timestamp) = ?
        GROUP BY p.id
        ORDER BY total_qty DESC
        LIMIT ?
    """, (date_str, limit)).fetchall()
    conn.close()
def get_total_expenses(date_str):
    conn = get_connection()
    row = conn.execute("""
        SELECT COALESCE(SUM(amount),0) FROM expenses
        WHERE date(timestamp) = ?
    """, (date_str,)).fetchone()
    conn.close()
    return row[0]

def get_cogs(date_str):
    conn = get_connection()
    row = conn.execute("""
        SELECT COALESCE(SUM(si.quantity * p.cost_price), 0)
        FROM sale_items si
        JOIN sales s ON si.sale_id = s.id
        JOIN products p ON si.product_id = p.id
        WHERE date(s.timestamp) = ?
    """, (date_str,)).fetchone()
    conn.close()
    return row[0]
