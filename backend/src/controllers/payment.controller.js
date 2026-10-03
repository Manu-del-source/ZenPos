const axios = require('axios');
const db = require('../config/db');
const mpesaService = require('../services/mpesa.service');

exports.initiateStkPush = async (req, res) => {
  try {
    const { phoneNumber, amount, saleId } = req.body;
    const response = await mpesaService.stkPush(phoneNumber, amount, saleId);
    res.json(response);
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
};

exports.mpesaCallback = async (req, res) => {
  const client = await db.pool.connect();
  try {
    await client.query('BEGIN');
    const { Body } = req.body;
    if (!Body || !Body.stkCallback) {
      console.error('❌ Invalid M-Pesa Callback Body:', req.body);
      return res.status(400).json({ ResultCode: 1, ResultDesc: "Invalid body" });
    }

    const stkCallback = Body.stkCallback;
    const checkoutRequestId = stkCallback.CheckoutRequestID;
    const resultCode = stkCallback.ResultCode;
    const resultDesc = stkCallback.ResultDesc;

    console.log(`📱 M-Pesa Callback for ${checkoutRequestId}: ${resultDesc} (${resultCode})`);

    const status = resultCode === 0 ? 'SUCCESS' : 'FAILED';
    
    let mpesaReceipt = null;
    if (resultCode === 0 && stkCallback.CallbackMetadata) {
      const items = stkCallback.CallbackMetadata.Item;
      const receiptItem = items.find(item => item.Name === 'MpesaReceiptNumber');
      mpesaReceipt = receiptItem ? receiptItem.Value : null;
    }

    const result = await client.query(
      'UPDATE "MpesaTransaction" SET status = $1, "resultCode" = $2, "resultDesc" = $3, "mpesaReceipt" = $4, "updatedAt" = NOW() WHERE "checkoutRequestId" = $5 RETURNING "saleId"',
      [status, resultCode, resultDesc, mpesaReceipt, checkoutRequestId]
    );

    if (result.rows.length > 0 && status === 'SUCCESS') {
      const saleId = result.rows[0].saleId;
      await client.query(
        'UPDATE "Sale" SET "paymentStatus" = $1, "updatedAt" = NOW() WHERE id = $2',
        ['PAID', saleId]
      );
      console.log(`✅ Sale ${saleId} marked as PAID`);
    }

    await client.query('COMMIT');
    res.status(200).json({ ResultCode: 0, ResultDesc: "Success" });
  } catch (error) {
    await client.query('ROLLBACK');
    console.error('🔥 M-Pesa Callback Error:', error);
    res.status(200).json({ ResultCode: 1, ResultDesc: "Internal Error" });
  } finally {
    client.release();
  }
};


exports.checkPaymentStatus = async (req, res) => {
  const client = await db.pool.connect();
  try {
    const { checkoutRequestId } = req.params;
    const status = await mpesaService.checkStkStatus(checkoutRequestId);
    
    if (status.ResultCode === '0') {
      await client.query('BEGIN');
      const result = await client.query(
        'SELECT "saleId", status FROM "MpesaTransaction" WHERE "checkoutRequestId" = $1',
        [checkoutRequestId]
      );
      
      if (result.rows.length > 0 && result.rows[0].status !== 'SUCCESS') {
        const saleId = result.rows[0].saleId;
        await client.query(
          'UPDATE "MpesaTransaction" SET status = $1, "updatedAt" = NOW() WHERE "checkoutRequestId" = $2',
          ['SUCCESS', checkoutRequestId]
        );
        await client.query(
          'UPDATE "Sale" SET "paymentStatus" = $1, "updatedAt" = NOW() WHERE id = $2',
          ['PAID', saleId]
        );

        // Notify Real-time Service (REALTIME_URL is injected by the Vercel
        // service binding; read it at request time so it resolves at runtime)
        try {
          const realtimeBaseUrl = (process.env.REALTIME_URL || 'http://localhost:5001').replace(/\/$/, '');
          await axios.post(`${realtimeBaseUrl}/api/realtime/payment-notification`, {
            saleId,
            checkoutRequestId,
            status: 'SUCCESS'
          });
        } catch (err) {
          console.error('⚠️ Failed to notify real-time service:', err.message);
        }
      }
      await client.query('COMMIT');
    }

    res.json(status);
  } catch (error) {
    await client.query('ROLLBACK');
    res.status(500).json({ message: error.message });
  } finally {
    client.release();
  }
};
