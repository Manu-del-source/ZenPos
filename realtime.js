const express = require('express');
const http = require('http');
const { Server } = require('socket.io');
const cors = require('cors');
const mpesaService = require('./backend/src/services/mpesa.service'); // Reuse existing logic

const app = express();
app.use(cors());
app.use(express.json());

const server = http.createServer(app);
const io = new Server(server, {
  cors: { origin: "*", methods: ["GET", "POST"] }
});

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

app.post('/api/realtime/mpesa/stkpush', async (req, res) => {
  try {
    const { phoneNumber, amount, saleId } = req.body;
    console.log(`📱 Triggering M-Pesa STK Push for ${phoneNumber} - ${amount} KES`);
    const response = await mpesaService.stkPush(phoneNumber, amount, saleId);
    res.json(response);
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
});

const PORT = process.env.PORT || 5001; // Separate port from Django
server.listen(PORT, () => {
  console.log(`🚀 Real-time & M-Pesa Service running on port ${PORT}`);
});
