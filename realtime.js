const express = require('express');
const http = require('http');
const { Server } = require('socket.io');
const cors = require('cors');
const jwt = require('jsonwebtoken');
const mpesaService = require('./backend/src/services/mpesa.service'); // Reuse existing logic

const app = express();
const corsOrigins = (process.env.CORS_ORIGINS || 'http://localhost:5173,https://kipchi-pos.vercel.app')
  .split(',')
  .map((origin) => origin.trim())
  .filter(Boolean);
if (corsOrigins.includes('*')) {
  throw new Error('CORS_ORIGINS must be an explicit origin allowlist');
}
app.use(cors({ origin: corsOrigins, methods: ['GET', 'POST', 'OPTIONS'] }));
app.use(express.json());

const server = http.createServer(app);
const io = new Server(server, {
  cors: { origin: corsOrigins, methods: ['GET', 'POST'] }
});

function requireSignedBearerToken(req, res, next) {
  const authorization = req.headers.authorization || '';
  const match = authorization.match(/^Bearer\s+(.+)$/i);
  const secret = process.env.JWT_SECRET_KEY;
  if (!match || !secret || Buffer.byteLength(secret, 'utf8') < 32) {
    return res.status(401).json({ message: 'Authentication required' });
  }
  try {
    const claims = jwt.verify(match[1], secret, { algorithms: ['HS256'] });
    if (!claims.sub) return res.status(401).json({ message: 'Invalid or expired token' });
    req.authenticatedUserId = claims.sub;
    return next();
  } catch (_error) {
    return res.status(401).json({ message: 'Invalid or expired token' });
  }
}

// Real-time Event Handling
io.on('connection', (socket) => {
  console.log('⚡ Terminal connected:', socket.id);

  socket.on('sale_completed', (data) => {
    // Broadcast to all other terminals to sync inventory levels
    socket.broadcast.emit('inventory_sync', data);
  });

  socket.on('disconnect', () => {
    console.log('❌ Terminal disconnected');
  });
});

// M-Pesa Integration Endpoints
app.post('/api/realtime/payment-notification', (req, res) => {
  const { saleId, checkoutRequestId, status } = req.body;
  console.log(`🔔 Payment Notification: ${saleId} - ${status}`);
  
  // Emit to all connected clients (or specifically to the one that initiated the sale if tracked)
  io.emit('payment_completed', { saleId, checkoutRequestId, status });
  
  res.json({ message: 'Notification received' });
});

app.post('/api/realtime/mpesa/stkpush', requireSignedBearerToken, async (req, res) => {
  try {
    const { phoneNumber, amount, saleId } = req.body;
    if (!/^(?:\+?254|0)(?:7|1)\d{8}$/.test(String(phoneNumber || '')) ||
        !Number.isFinite(Number(amount)) || Number(amount) <= 0 || !saleId) {
      return res.status(422).json({ message: 'Invalid payment request' });
    }
    const response = await mpesaService.stkPush(phoneNumber, amount, saleId);
    res.json(response);
  } catch (_error) {
    res.status(502).json({ message: 'Payment request failed' });
  }
});

const PORT = process.env.PORT || 5001; // Separate port from Django
server.listen(PORT, () => {
  console.log(`🚀 Real-time & M-Pesa Service running on port ${PORT}`);
});
