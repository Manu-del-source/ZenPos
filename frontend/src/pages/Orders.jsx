import React, { useState, useEffect } from 'react';
import api from '../services/api';
import toast from 'react-hot-toast';
import { History, Search, Eye, X } from 'lucide-react';

const Orders = () => {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [orderDetails, setOrderDetails] = useState([]);

  const fetchOrders = async () => {
    setLoading(true);
    try {
      const res = await api.get('/sales/');
      setOrders(res.data);
    } catch (err) {
      toast.error('Failed to load transaction history');
    } finally {
      setLoading(false);
    }
  };

  const fetchOrderDetails = async (saleId) => {
    try {
      const res = await api.get(`/sales/${saleId}`);
      setOrderDetails(res.data.items || []);
    } catch (err) {
      toast.error('Failed to load details');
    }
  };

  useEffect(() => {
    fetchOrders();
  }, []);

  const handleViewDetails = (order) => {
    setSelectedOrder(order);
    fetchOrderDetails(order.id);
  };

  return (
    <div className="p-8 max-w-7xl mx-auto bg-slate-950 min-h-screen text-white">
      <div className="flex justify-between items-center mb-8">
        <div>
          <h1 className="text-3xl font-black tracking-tight uppercase italic">SALES <span className="text-blue-500">HISTORY</span></h1>
          <p className="text-slate-500 text-sm font-bold uppercase tracking-widest">Hardware & Motorcycle Spare Parts</p>
        </div>
        <button 
          onClick={fetchOrders}
          className="bg-slate-800 text-slate-300 px-6 py-2 rounded-xl font-bold hover:bg-slate-700 transition flex items-center border border-slate-700"
        >
          REFRESH
        </button>
      </div>

      <div className="bg-slate-900 rounded-3xl border border-slate-800 overflow-hidden shadow-2xl">
        <table className="w-full text-left">
          <thead className="bg-slate-800/50">
            <tr className="text-slate-400 text-[10px] font-black uppercase tracking-[0.2em]">
              <th className="p-5">Transaction ID</th>
              <th className="p-5">Timestamp</th>
              <th className="p-5">Customer</th>
              <th className="p-5 text-right">Total Amount</th>
              <th className="p-5 text-center">Details</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {orders.map((order) => (
              <tr key={order.id} className="hover:bg-slate-800/30 transition group">
                <td className="p-5">
                  <div className="font-mono text-blue-500 font-bold">#{order.saleNumber || order.id}</div>
                </td>
                <td className="p-5 text-slate-300 text-sm">
                  {new Date(order.createdAt).toLocaleString()}
                </td>
                <td className="p-5 text-slate-400 text-sm italic">
                  {order.customerName || 'Walk-in Customer'}
                </td>
                <td className="p-5 text-right font-black text-white">
                  KES {Number(order.total).toLocaleString()}
                </td>
                <td className="p-5 text-center">
                   <button 
                    onClick={() => handleViewDetails(order)}
                    className="p-2 bg-slate-800 hover:bg-blue-600 rounded-lg text-slate-400 hover:text-white transition"
                   >
                     <Eye size={18} />
                   </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {orders.length === 0 && !loading && (
          <div className="p-20 text-center flex flex-col items-center">
            <History size={64} className="text-slate-800 mb-4" />
            <p className="text-slate-500 font-bold uppercase tracking-widest text-sm">No transactions archived</p>
          </div>
        )}
      </div>

      {/* Modern Receipt Modal */}
      {selectedOrder && (
        <div className="fixed inset-0 bg-slate-950/90 backdrop-blur-md flex items-center justify-center z-[100] p-4">
          <div className="bg-white text-slate-900 rounded-2xl p-8 w-full max-w-md shadow-2xl relative font-mono">
            <button 
              onClick={() => setSelectedOrder(null)}
              className="absolute -top-12 right-0 text-white hover:text-red-500 transition"
            >
              <X size={32} />
            </button>
            
            <div className="text-center border-b-2 border-dashed border-slate-300 pb-4 mb-4">
              <h3 className="text-xl font-black uppercase tracking-tighter">HARDWARE & MOTO</h3>
              <p className="text-xs text-slate-500">Official Sales Receipt</p>
            </div>

            <div className="space-y-1 text-[10px] mb-6 uppercase font-bold">
               <div className="flex justify-between"><span>RECEIPT NO:</span> <span>{selectedOrder.saleNumber || selectedOrder.id}</span></div>
               <div className="flex justify-between"><span>DATE:</span> <span>{new Date(selectedOrder.createdAt).toLocaleString()}</span></div>
               <div className="flex justify-between"><span>CUSTOMER:</span> <span>{selectedOrder.customerName || 'CASH SALE'}</span></div>
            </div>

            <div className="border-b border-slate-200 mb-4"></div>

            <div className="space-y-3 mb-8">
               {orderDetails.map((item, i) => (
                 <div key={i} className="flex justify-between text-xs">
                   <div className="flex flex-col">
                     <span className="font-bold">{item.productName}</span>
                     <span className="text-[10px] text-slate-500">{item.quantity} x {item.unitPrice}</span>
                   </div>
                   <span className="font-bold">KES {item.subtotal}</span>
                 </div>
               ))}
            </div>

            <div className="border-t-2 border-dashed border-slate-300 pt-4 mt-auto">
               <div className="flex justify-between text-lg font-black italic">
                 <span>TOTAL:</span>
                 <span className="text-blue-600 underline">KES {Number(selectedOrder.total).toLocaleString()}</span>
               </div>
            </div>

            <div className="text-center mt-8 text-[10px] text-slate-400 uppercase font-black tracking-widest">
              *** Thank you for your business ***
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Orders;
