import React, { useState, useEffect } from 'react';
import { 
  ShoppingCart, 
  CheckCircle2, 
  Clock, 
  RefreshCw, 
  Check, 
  Copy, 
  ExternalLink,
  ShieldCheck,
  Send
} from 'lucide-react';
import { adminApi } from '../api/client';

export default function OrderManager() {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [approvingId, setApprovingId] = useState(null);
  const [copiedId, setCopiedId] = useState(null);

  const loadOrders = async () => {
    try {
      setLoading(true);
      const data = await adminApi.getOrders();
      setOrders(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadOrders();
  }, []);

  const handleApprove = async (orderId) => {
    const utr = prompt('Enter payment UTR / Transaction Reference (or leave default):', 'ADMIN_CONFIRMED');
    if (!utr) return;

    try {
      setApprovingId(orderId);
      await adminApi.approveOrder(orderId, utr);
      loadOrders();
    } catch (err) {
      alert('Failed to approve order: ' + err.message);
    } finally {
      setApprovingId(null);
    }
  };

  const handleCopyLink = (link, id) => {
    navigator.clipboard.writeText(link);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  return (
    <div className="space-y-6">
      
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-[#ececec] flex items-center gap-2">
            <ShoppingCart className="w-5 h-5 text-[#ececec]" />
            Customer Orders & UPI Payments
          </h2>
          <p className="text-xs text-[#8e8ea0]">
            View orders, confirm UPI UTRs, and trigger automated single-use link delivery.
          </p>
        </div>

        <button
          onClick={loadOrders}
          className="p-2 bg-[#3a3a3a] hover:bg-[#4a4a4a] text-[#d4d4d4] rounded-xl transition-colors text-xs flex items-center gap-1.5 self-start"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          Refresh Orders
        </button>
      </div>

      {/* Orders Table */}
      <div className="glass-panel rounded-2xl overflow-hidden border border-white/10">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs text-[#d4d4d4]">
            <thead className="bg-[#2f2f2f] text-[11px] font-bold text-[#8e8ea0] uppercase tracking-wider border-b border-white/10">
              <tr>
                <th className="py-3 px-4">Order ID</th>
                <th className="py-3 px-4">Customer</th>
                <th className="py-3 px-4">Product</th>
                <th className="py-3 px-4">Amount</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4">Payment Ref / UTR</th>
                <th className="py-3 px-4">Delivered Link</th>
                <th className="py-3 px-4 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {loading ? (
                <tr>
                  <td colSpan="8" className="py-8 text-center text-[#8e8ea0]">Loading orders...</td>
                </tr>
              ) : orders.length === 0 ? (
                <tr>
                  <td colSpan="8" className="py-8 text-center text-[#8e8ea0] italic">No customer orders placed yet.</td>
                </tr>
              ) : (
                orders.map((o) => (
                  <tr key={o.id} className="hover:bg-[#2f2f2f] transition-colors">
                    <td className="py-3 px-4 font-mono font-bold text-[#ececec]">{o.id}</td>
                    <td className="py-3 px-4">
                      <div className="font-semibold text-[#ececec]">{o.customer_name}</div>
                      <div className="text-[11px] text-[#8e8ea0] font-mono">{o.customer_phone || 'Web Chat'}</div>
                    </td>
                    <td className="py-3 px-4 font-medium text-[#ececec]">{o.product_name}</td>
                    <td className="py-3 px-4 font-bold text-[#ececec] font-mono">₹{o.total_amount.toFixed(2)}</td>
                    <td className="py-3 px-4">
                      {o.status === 'delivered' ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-[#2f2f2f] text-[#ececec] border border-white/15 text-[10px] font-semibold">
                          <CheckCircle2 className="w-3 h-3" />
                          Delivered
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-950 text-amber-400 border border-amber-500/30 text-[10px] font-semibold">
                          <Clock className="w-3 h-3" />
                          Pending Payment
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-4 font-mono text-[11px] text-[#d4d4d4]">
                      {o.payment_ref || <span className="text-[#8e8ea0] italic">Awaiting UTR</span>}
                    </td>
                    <td className="py-3 px-4 max-w-xs truncate font-mono text-[11px]">
                      {o.delivered_link_content ? (
                        <div className="flex items-center gap-1 text-[#ececec]">
                          <span className="truncate">{o.delivered_link_content}</span>
                          <button
                            onClick={() => handleCopyLink(o.delivered_link_content, o.id)}
                            className="p-1 hover:text-[#ececec]"
                            title="Copy link"
                          >
                            {copiedId === o.id ? <Check className="w-3 h-3 text-[#ececec]" /> : <Copy className="w-3 h-3" />}
                          </button>
                        </div>
                      ) : (
                        <span className="text-[#8e8ea0]">—</span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-right">
                      {o.status !== 'delivered' && (
                        <button
                          onClick={() => handleApprove(o.id)}
                          disabled={approvingId === o.id}
                          className="px-2.5 py-1 bg-white hover:bg-white/90 text-black font-bold text-[11px] rounded-lg shadow-sm transition-all"
                        >
                          {approvingId === o.id ? 'Fulfilling...' : 'Approve & Send'}
                        </button>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

    </div>
  );
}
