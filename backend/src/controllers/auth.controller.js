const db = require('../config/db');
const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');
const { v4: uuidv4 } = require('uuid');

exports.register = async (req, res) => {
  try {
    const { username, password, name, branchId } = req.body;

    const existingUser = await db.query('SELECT * FROM "User" WHERE username = $1', [username]);
    if (existingUser.rows.length > 0) {
      return res.status(400).json({ message: 'Username already exists' });
    }

    const passwordHash = await bcrypt.hash(password, 10);
    const id = uuidv4();

    const result = await db.query(
      'INSERT INTO "User" (id, username, "passwordHash", name, role, "branchId", "updatedAt") VALUES ($1, $2, $3, $4, $5, $6, NOW()) RETURNING id',
      [id, username, passwordHash, name, 'CASHIER', branchId]
    );

    res.status(201).json({ message: 'User created successfully', userId: result.rows[0].id });
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
};

exports.login = async (req, res) => {
  try {
    const { username, password } = req.body;

    const result = await db.query(
      'SELECT u.*, b.name as "branchName" FROM "User" u JOIN "Branch" b ON u."branchId" = b.id WHERE u.username = $1',
      [username]
    );
    const user = result.rows[0];

    if (!user || !(await bcrypt.compare(password, user.passwordHash))) {
      return res.status(401).json({ message: 'Invalid credentials' });
    }

    const token = jwt.sign(
      { userId: user.id, role: user.role, branchId: user.branchId },
      process.env.JWT_SECRET,
      { expiresIn: '12h' }
    );

    res.json({
      token,
      user: {
        id: user.id,
        name: user.name,
        role: user.role,
        branch: { id: user.branchId, name: user.branchName },
      },
    });
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
};
