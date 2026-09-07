import React, { useState, useEffect } from 'react';
import {
  Users,
  Plus,
  KeyRound,
  Wallet,
  History,
  RefreshCw,
  Eye,
  EyeOff,
  ArrowUpRight,
  ArrowDownRight
} from 'lucide-react';
import { adminApi } from '../api/client';

const sym = (cur) => ((cur || 'INR').toUpperCase() === 'USD' ? '$' : '₹');
const fmt = (amt, cur) => `${sym(cur)}${Number(amt || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export default function ResellerManager() {
  const [resellers, setResellers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [showWalletModal, setShowWalletModal] = useState(false);
  const [showHistoryModal, setShowHistoryModal] = useState(false);
  const [selectedReseller, setSelectedReseller] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [showCodes, setShowCodes] = useState({});

  // Wallet adjustment state (money, in the reseller's currency)
  const [amount, setAmount] = useState(500);
  const [reason, setReason] = useState('admin_topup');
  const [note, setNote] = useState('');

  // Add reseller state
  const [formData, setFormData] = useState({
    name: '',
    phone: '',
    secret_code: '1234',
    currency: 'INR',
    wallet_balance: 500,
    notes: ''
  });

  const loadResellers = async () => {
    try {
      setLoading(true);
      setResellers(await adminApi.getResellers());
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadResellers(); }, []);

  const handleToggleCode = (id) => setShowCodes((prev) => ({ ...prev, [id]: !prev[id] }));

  const handleAddReseller = async (e) => {
    e.preventDefault();
    try {
      await adminApi.createReseller(formData);
      setShowAddModal(false);
      setFormData({ name: '', phone: '', secret_code: '1234', currency: 'INR', wallet_balance: 500, notes: '' });
      loadResellers();
    } catch (err) {
      alert('Error creating reseller: ' + err.message);
    }
  };

  const openWallet = (r) => {
    setSelectedReseller(r);
    setAmount(500);
    setReason('admin_topup');
    setNote('');
    setShowWalletModal(true);
  };

  const handleAdjustWallet = async (e) => {
    e.preventDefault();
    if (!selectedReseller || !amount) return;
    try {
      await adminApi.adjustWallet(selectedReseller.id, amount, reason, note);
      setShowWalletModal(false);
      loadResellers();
    } catch (err) {
      alert('Error adjusting wallet: ' + err.message);
    }
  };

  const handleOpenHistory = async (reseller) => {
    setSelectedReseller(reseller);
    try {
      setTransactions(await adminApi.getResellerTransactions(reseller.id));
      setShowHistoryModal(true);
    } catch (err) {
      alert('Error loading history: ' + err.message);
    }
  };

  return (
    <div className="space-y-6">

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-[#ececec] flex items-center gap-2">
            <Users className="w-5 h-5 text-[#ececec]" />
            Resellers & Wallets
          </h2>
          <p className="text-xs text-[#8e8ea0]">
            Har reseller ka money wallet (INR/USD). Link lete hi product ka reseller price wallet se kat jaata hai.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button onClick={loadResellers} className="p-2 bg-[#3a3a3a] hover:bg-[#4a4a4a] text-[#d4d4d4] rounded-xl transition-colors text-xs flex items-center gap-1.5">
            <RefreshCw className="w-3.5 h-3.5" /> Refresh
          </button>
          <button onClick={() => setShowAddModal(true)} className="px-3.5 py-2 bg-white hover:bg-white/90 text-black font-bold rounded-xl text-xs flex items-center gap-1.5 shadow-md active:scale-95 transition-all">
            <Plus className="w-4 h-4" /> Add Reseller
          </button>
        </div>
      </div>

      {/* Reseller Grid */}
      {loading ? (
        <div className="p-12 text-center text-xs text-[#8e8ea0]">Loading resellers...</div>
      ) : resellers.length === 0 ? (
        <div className="p-12 text-center text-xs text-[#8e8ea0] glass-panel rounded-2xl">No registered resellers found. Click "Add Reseller" to create one.</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {resellers.map((r) => (
            <div key={r.id} className="glass-panel rounded-2xl p-5 border border-white/10 flex flex-col justify-between hover:border-white/15 transition-all shadow-lg">
              <div>
                <div className="flex items-start justify-between gap-2 mb-2">
                  <div className="flex items-center gap-1.5">
                    <div className="w-8 h-8 rounded-xl bg-[#2f2f2f] border border-white/15 flex items-center justify-center text-[#ececec] font-bold text-xs">
                      {r.name.charAt(0).toUpperCase()}
                    </div>
                    <div>
                      <h3 className="font-bold text-sm text-[#ececec]">{r.name}</h3>
                      <p className="text-xs text-[#8e8ea0] font-mono">📱 {r.phone}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-1">
                    {r.is_locked ? (
                      <button
                        onClick={async () => { await adminApi.unlockReseller(r.id); loadResellers(); }}
                        title="Too many failed passcode attempts. Click to unlock now."
                        className="text-[10px] px-2 py-0.5 rounded-full bg-rose-950 text-rose-300 border border-rose-500/40 font-semibold hover:bg-rose-900"
                      >
                        🔒 Locked · Unlock
                      </button>
                    ) : r.is_active ? (
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#2f2f2f] text-[#ececec] border border-white/15 font-semibold">Active</span>
                    ) : (
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#3a3a3a] text-[#8e8ea0] border border-white/15 font-semibold">Inactive</span>
                    )}
                  </div>
                </div>

                {/* Secret Passcode Box */}
                <div className="p-2.5 bg-[#2f2f2f] rounded-xl border border-white/10 my-3 flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <KeyRound className="w-3.5 h-3.5 text-[#ececec]" />
                    <span className="text-xs text-[#8e8ea0]">4-Digit Passcode:</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs font-bold text-[#ececec] tracking-widest">{showCodes[r.id] ? r.secret_code : '••••'}</span>
                    <button onClick={() => handleToggleCode(r.id)} className="p-1 text-[#8e8ea0] hover:text-[#ececec]">
                      {showCodes[r.id] ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                    </button>
                  </div>
                </div>

                {/* Wallet Card */}
                <div className="p-3 bg-[#2f2f2f] rounded-xl border border-white/15 mb-4 flex items-center justify-between">
                  <div>
                    <span className="text-[10px] uppercase font-bold text-[#8e8ea0] flex items-center gap-1">
                      <Wallet className="w-3 h-3" /> Wallet ({r.currency})
                    </span>
                    <span className="text-xl font-bold text-[#ececec] font-mono">{fmt(r.wallet_balance, r.currency)}</span>
                  </div>
                  <button onClick={() => openWallet(r)} className="px-3 py-1.5 bg-white hover:bg-white/90 text-black font-bold text-xs rounded-lg shadow-sm transition-all">
                    Add / Deduct
                  </button>
                </div>
              </div>

              <div className="pt-2 border-t border-white/10 flex items-center justify-between text-xs text-[#8e8ea0]">
                <span className="text-[11px] truncate max-w-[130px]">{r.notes || 'Registered Reseller'}</span>
                <button onClick={() => handleOpenHistory(r)} className="text-[#ececec] font-medium flex items-center gap-1 text-[11px]">
                  <History className="w-3 h-3" /> Ledger
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Wallet Add / Deduct Modal */}
      {showWalletModal && selectedReseller && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fadeIn">
          <div className="w-full max-w-md bg-[#2f2f2f] border border-white/15 rounded-2xl p-6 text-[#ececec]">
            <h3 className="text-base font-bold text-[#ececec] mb-2 flex items-center gap-2">
              <Wallet className="w-5 h-5 text-[#ececec]" /> Wallet: {selectedReseller.name}
            </h3>
            <p className="text-xs text-[#8e8ea0] mb-4">
              Current balance: <strong className="text-[#ececec]">{fmt(selectedReseller.wallet_balance, selectedReseller.currency)}</strong> ({selectedReseller.currency})
            </p>

            <form onSubmit={handleAdjustWallet} className="space-y-3.5 text-xs">
              <div>
                <label className="block text-[#8e8ea0] mb-1 font-medium">Amount in {selectedReseller.currency} (+ add, − deduct) *</label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-[#8e8ea0] font-bold">{sym(selectedReseller.currency)}</span>
                  <input
                    type="number" step="0.01" value={amount}
                    onChange={(e) => setAmount(parseFloat(e.target.value) || 0)}
                    required
                    className="w-full p-2.5 pl-7 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] text-sm font-bold font-mono focus:outline-none focus:border-white/15"
                  />
                </div>
                <div className="flex gap-1.5 mt-1.5">
                  {[500, 1000, 2000, 5000].map((v) => (
                    <button key={v} type="button" onClick={() => setAmount(v)} className="px-2 py-1 rounded-lg bg-[#212121] border border-white/10 text-[10px] text-[#d4d4d4] hover:bg-[#3a3a3a]">+{v}</button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-[#8e8ea0] mb-1 font-medium">Reason</label>
                <select value={reason} onChange={(e) => setReason(e.target.value)} className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] focus:outline-none focus:border-white/15">
                  <option value="admin_topup">Top-up (admin)</option>
                  <option value="purchase">Top-up (reseller paid via UPI)</option>
                  <option value="admin_deduct">Deduction / correction</option>
                  <option value="bonus">Promotional bonus</option>
                  <option value="refund">Refund</option>
                </select>
              </div>

              <div>
                <label className="block text-[#8e8ea0] mb-1 font-medium">Note (e.g. UTR)</label>
                <input type="text" placeholder="e.g. Paid ₹2000 via UPI, UTR 98218921" value={note} onChange={(e) => setNote(e.target.value)}
                  className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] focus:outline-none focus:border-white/15" />
              </div>

              <div className="p-2.5 bg-[#212121] rounded-xl border border-white/10 flex justify-between items-center text-xs">
                <span className="text-[#8e8ea0]">Balance after change:</span>
                <span className="font-bold text-[#ececec] font-mono">{fmt(Math.max(0, Number(selectedReseller.wallet_balance) + Number(amount || 0)), selectedReseller.currency)}</span>
              </div>

              <div className="flex gap-2 pt-2">
                <button type="button" onClick={() => setShowWalletModal(false)} className="w-1/2 py-2.5 bg-[#3a3a3a] hover:bg-[#4a4a4a] text-[#d4d4d4] font-semibold rounded-xl">Cancel</button>
                <button type="submit" className="w-1/2 py-2.5 bg-white hover:bg-white/90 text-black font-bold rounded-xl shadow-md">Save</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Add Reseller Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fadeIn">
          <div className="w-full max-w-md bg-[#2f2f2f] border border-white/15 rounded-2xl p-6 text-[#ececec]">
            <h3 className="text-base font-bold text-[#ececec] mb-4 flex items-center gap-2">
              <Users className="w-5 h-5 text-[#ececec]" /> Register New Reseller
            </h3>

            <form onSubmit={handleAddReseller} className="space-y-3 text-xs">
              <div>
                <label className="block text-[#8e8ea0] mb-1 font-medium">Reseller Name / Business *</label>
                <input type="text" placeholder="e.g. Vikas Sharma (Tech Solutions)" value={formData.name} onChange={(e) => setFormData({ ...formData, name: e.target.value })} required
                  className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] focus:outline-none focus:border-white/15" />
              </div>

              <div>
                <label className="block text-[#8e8ea0] mb-1 font-medium">Registered 10-Digit Phone (WhatsApp) *</label>
                <input type="text" placeholder="e.g. 9876543210" value={formData.phone} onChange={(e) => setFormData({ ...formData, phone: e.target.value })} required
                  className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] focus:outline-none focus:border-white/15 font-mono" />
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="block text-[#8e8ea0] mb-1 font-medium">4-Digit Code *</label>
                  <input type="text" maxLength={4} placeholder="8899" value={formData.secret_code} onChange={(e) => setFormData({ ...formData, secret_code: e.target.value })} required
                    className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] text-center font-mono font-bold tracking-widest text-sm focus:outline-none focus:border-white/15" />
                </div>
                <div>
                  <label className="block text-[#8e8ea0] mb-1 font-medium">Currency</label>
                  <select value={formData.currency} onChange={(e) => setFormData({ ...formData, currency: e.target.value })}
                    className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] focus:outline-none focus:border-white/15">
                    <option value="INR">INR ₹</option>
                    <option value="USD">USD $</option>
                  </select>
                </div>
                <div>
                  <label className="block text-[#8e8ea0] mb-1 font-medium">Initial balance</label>
                  <input type="number" min="0" step="0.01" value={formData.wallet_balance} onChange={(e) => setFormData({ ...formData, wallet_balance: parseFloat(e.target.value) || 0 })}
                    className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] focus:outline-none focus:border-white/15 font-mono" />
                </div>
              </div>
              <span className="text-[10px] text-[#8e8ea0] block">USD wallet ke liye product price Settings ke USD→INR rate se convert hoke katega.</span>

              <div>
                <label className="block text-[#8e8ea0] mb-1 font-medium">Notes / Location</label>
                <input type="text" placeholder="e.g. Paid ₹500 via GPay" value={formData.notes} onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                  className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] focus:outline-none focus:border-white/15" />
              </div>

              <div className="flex gap-2 pt-3">
                <button type="button" onClick={() => setShowAddModal(false)} className="w-1/2 py-2.5 bg-[#3a3a3a] hover:bg-[#4a4a4a] text-[#d4d4d4] font-semibold rounded-xl">Cancel</button>
                <button type="submit" className="w-1/2 py-2.5 bg-white hover:bg-white/90 text-black font-bold rounded-xl shadow-md">Register Reseller</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Ledger Modal */}
      {showHistoryModal && selectedReseller && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fadeIn">
          <div className="w-full max-w-xl bg-[#2f2f2f] border border-white/15 rounded-2xl p-6 text-[#ececec]">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-base font-bold text-[#ececec] flex items-center gap-2">
                  <History className="w-4 h-4 text-[#ececec]" /> Wallet Ledger: {selectedReseller.name}
                </h3>
                <p className="text-xs text-[#8e8ea0]">Phone: {selectedReseller.phone} · Balance: {fmt(selectedReseller.wallet_balance, selectedReseller.currency)}</p>
              </div>
              <button onClick={() => setShowHistoryModal(false)} className="text-[#8e8ea0] hover:text-[#ececec] text-xs px-2 py-1 bg-[#3a3a3a] rounded-lg">Close</button>
            </div>

            <div className="max-h-80 overflow-y-auto space-y-2 text-xs">
              {transactions.length === 0 ? (
                <div className="py-8 text-center text-[#8e8ea0] italic">No wallet transactions yet.</div>
              ) : (
                transactions.map((t) => (
                  <div key={t.id} className="p-3 bg-[#212121] rounded-xl border border-white/10 flex items-center justify-between">
                    <div className="flex items-center gap-2.5">
                      {t.amount > 0 ? (
                        <div className="w-7 h-7 rounded-lg bg-[#2f2f2f] border border-white/15 flex items-center justify-center text-[#ececec]"><ArrowUpRight className="w-4 h-4" /></div>
                      ) : (
                        <div className="w-7 h-7 rounded-lg bg-amber-950 border border-amber-500/30 flex items-center justify-center text-amber-400"><ArrowDownRight className="w-4 h-4" /></div>
                      )}
                      <div>
                        <div className="font-semibold text-[#ececec]">{t.reference_note || t.reason}</div>
                        <div className="text-[11px] text-[#8e8ea0]">{new Date(t.created_at).toLocaleString()} · {t.reason}</div>
                      </div>
                    </div>
                    <div className="text-right">
                      <div className={`font-mono font-bold text-sm ${t.amount > 0 ? 'text-[#ececec]' : 'text-amber-400'}`}>{t.amount_display}</div>
                      <div className="text-[10px] text-[#8e8ea0]">Balance: {fmt(t.balance_after, t.currency)}</div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
