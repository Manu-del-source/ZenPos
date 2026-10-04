require('dotenv').config();
const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const morgan = require('morgan');
const rateLimit = require('express-rate-limit');
const db = require('./src/config/db');
const app = express();
const PORT = process.env.PORT || 5000;
const corsOrigins = (process.env.CORS_ORIGINS || 'http://localhost:5173,https://kipchi-pos.vercel.app')
  .split(',')
  .map((origin) => origin.trim())
  .filter(Boolean);
if (corsOrigins.includes('*')) {
  throw new Error('CORS_ORIGINS must be an explicit origin allowlist');
}

// Behind Vercel's proxy (or any reverse proxy) so express-rate-limit and
// req.ip see the real client address.
app.set('trust proxy', 1);

// Rate limiting
const generalLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 100,
  message: { message: 'Too many requests, please try again later' }
});

const authLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 10, // Only 10 login attempts per 15 mins
  message: { message: 'Too many login attempts' }
});

const paymentLimiter = rateLimit({
  windowMs: 60 * 1000,
  max: 3, // Only 3 STK pushes per minute
  message: { message: 'Please wait before requesting another payment' }
});

// Middleware
app.use(helmet());
app.use(generalLimiter);
app.use('/api/v1/auth/login', authLimiter);
app.use('/api/v1/payments/mpesa/stkpush', paymentLimiter);
app.use(cors({ origin: corsOrigins }));
app.use(express.json());
app.use(morgan('dev'));

// Routes (to be implemented)
app.use('/api/v1/auth', require('./src/routes/auth.routes'));
app.use('/api/v1/inventory', require('./src/routes/inventory.routes'));
app.use('/api/v1/sales', require('./src/routes/sales.routes'));
app.use('/api/v1/payments', require('./src/routes/payment.routes'));
app.use('/api/v1/reports', require('./src/routes/report.routes'));
app.use('/api/v1/branches', require('./src/routes/branch.routes'));
app.use('/api/v1/customers', require('./src/routes/customer.routes'));

// Health check
app.get('/health', (req, res) => {
  res.status(200).json({ status: 'OK', timestamp: new Date() });
});

// Error handling middleware
app.use((err, req, res, next) => {
  console.error(err.stack);
  res.status(500).json({
    message: 'Something went wrong!',
    error: process.env.NODE_ENV === 'development' ? err.message : {}
  });
});

app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});

process.on('SIGINT', async () => {
  await db.pool.end();
  process.exit(0);
});
