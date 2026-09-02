import React, { useState, useEffect } from 'react';
import { 
  Users, 
  Plus, 
  KeyRound, 
  CreditCard, 
  History, 
  RefreshCw, 
  Check, 
  Eye, 
  EyeOff, 
  ArrowUpRight, 
  ArrowDownRight,
  ShieldCheck
} from 'lucide-react';
import { adminApi } from '../api/client';

export default function ResellerManager() {
  const [resellers, setResellers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [showCreditModal, setShowCreditModal] = useState(false);
  const [showHistoryModal, setShowHistoryModal] = useState(false);
  const [selectedReseller, setSelectedReseller] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [showCodes, setShowCodes] = useState({});

  // Credit Adjustment State
  const [creditAmount, setCreditAmount] = useState(10);
  const [creditReason, setCreditReason] = useState('admin_topup');
  const [creditNote, setCreditNote] = useState('Admin wallet topup');

  // Add Reseller State
  const [formData, setFormData] = useState({
    name: '',
    phone: '',
    secret_code: '1234',
    credits_balance: 10,
    notes: ''
  });

  const loadResellers = async () => {
    try {
      setLoading(true);
      const data = await adminApi.getResellers();
      setResellers(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadResellers();
  }, []);

  const handleToggleCode = (id) => {
    setShowCodes(prev => ({ ...prev, [id]: !prev[id] }));
  };

  const handleAddReseller = async (e) => {
    e.preventDefault();
    try {
      await adminApi.createReseller(formData);
      setShowAddModal(false);
      setFormData({
        name: '',
        phone: '',
        secret_code: '1234',
        credits_balance: 10,
        notes: ''
      });
      loadResellers();
    } catch (err) {
      alert('Error creating reseller: ' + err.message);
    }
  };

  const handleAdjustCredits = async (e) => {
    e.preventDefault();
    if (!selectedReseller) return;
    try {
      await adminApi.adjustCredits(
        selectedReseller.id,
        creditAmount,
        creditReason,
        creditNote
      );
      setShowCreditModal(false);
      loadResellers();
    } catch (err) {
      alert('Error adjusting credits: ' + err.message);
    }
  };

  const handleOpenHistory = async (reseller) => {
    setSelectedReseller(reseller);
    try {
      const txns = await adminApi.getResellerTransactions(reseller.id);
      setTransactions(txns);
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
          <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            <Users className="w-5 h-5 text-emerald-400" />
            Reseller Management & Wallet Credits
          </h2>
          <p className="text-xs text-slate-400">
            Manage authorized resellers, set 4-digit secret codes, and top up/deduct credit balances.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={loadResellers}
            className="p-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl transition-colors text-xs flex items-center gap-1.5"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Refresh
          </button>
          <button
            onClick={() => setShowAddModal(true)}
            className="px-3.5 py-2 bg-gradient-to-r from-emerald-600 to-teal-500 hover:from-emerald-500 hover:to-teal-400 text-slate-950 font-bold rounded-xl text-xs flex items-center gap-1.5 shadow-md active:scale-95 transition-all"
          >
            <Plus className="w-4 h-4" />
            Add Reseller
          </button>
        </div>
      </div>

      {/* Reseller Grid */}
      {loading ? (
        <div className="p-12 text-center text-xs text-slate-400">Loading resellers...</div>
      ) : resellers.length === 0 ? (
        <div className="p-12 text-center text-xs text-slate-400 glass-panel rounded-2xl">
          No registered resellers found. Click "Add Reseller" to create one.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {resellers.map((r) => (
            <div key={r.id} className="glass-panel rounded-2xl p-5 border border-slate-800 flex flex-col justify-between hover:border-slate-700 transition-all shadow-lg">
              <div>
                <div className="flex items-start justify-between gap-2 mb-2">
                  <div className="flex items-center gap-1.5">
                    <div className="w-8 h-8 rounded-xl bg-teal-950 border border-teal-500/30 flex items-center justify-center text-teal-400 font-bold text-xs">
                      {r.name.charAt(0).toUpperCase()}
                    </div>
                    <div>
                      <h3 className="font-bold text-sm text-slate-100">{r.name}</h3>
                      <p className="text-xs text-slate-400 font-mono">📱 {r.phone}</p>
                    </div>
                  </div>
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-400 border border-emerald-500/30 font-semibold">
                    Active
                  </span>
                </div>

                {/* Secret Passcode Box */}
                <div className="p-2.5 bg-slate-900/90 rounded-xl border border-slate-800 my-3 flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <KeyRound className="w-3.5 h-3.5 text-teal-400" />
                    <span className="text-xs text-slate-400">4-Digit Passcode:</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs font-bold text-teal-300 tracking-widest">
                      {showCodes[r.id] ? r.secret_code : '••••'}
                    </span>
                    <button
                      onClick={() => handleToggleCode(r.id)}
                      className="p-1 text-slate-400 hover:text-slate-200"
                    >
                      {showCodes[r.id] ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                    </button>
                  </div>
                </div>

                {/* Credits Wallet Card */}
                <div className="p-3 bg-gradient-to-br from-slate-900 to-teal-950/60 rounded-xl border border-teal-500/30 mb-4 flex items-center justify-between">
                  <div>
                    <span className="text-[10px] uppercase font-bold text-slate-400 block">Wallet Credits</span>
                    <span className="text-xl font-bold text-emerald-400 font-mono">{r.credits_balance}</span>
                    <span className="text-[11px] text-slate-400 ml-1">Credits</span>
                  </div>
                  <button
                    onClick={() => {
                      setSelectedReseller(r);
                      setShowCreditModal(true);
                    }}
                    className="px-3 py-1.5 bg-teal-600 hover:bg-teal-500 text-slate-950 font-bold text-xs rounded-lg shadow-sm transition-all"
                  >
                    Adjust
                  </button>
                </div>
              </div>

              <div className="pt-2 border-t border-slate-800/60 flex items-center justify-between text-xs text-slate-400">
                <span className="text-[11px] truncate max-w-[130px]">{r.notes || 'Registered Reseller'}</span>
                <button
                  onClick={() => handleOpenHistory(r)}
                  className="text-teal-400 hover:text-teal-300 font-medium flex items-center gap-1 text-[11px]"
                >
                  <History className="w-3 h-3" />
                  Audit Log
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Credit Top-Up / Deduct Modal */}
      {showCreditModal && selectedReseller && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fadeIn">
          <div className="w-full max-w-md bg-slate-900 border border-slate-700 rounded-2xl p-6 text-slate-200">
            <h3 className="text-base font-bold text-slate-100 mb-2 flex items-center gap-2">
              <CreditCard className="w-5 h-5 text-teal-400" />
              Adjust Credits: {selectedReseller.name}
            </h3>
            <p className="text-xs text-slate-400 mb-4">
              Current Balance: <strong className="text-emerald-400">{selectedReseller.credits_balance} Credits</strong>
            </p>

            <form onSubmit={handleAdjustCredits} className="space-y-3.5 text-xs">
              <div>
                <label className="block text-slate-400 mb-1 font-medium">Credit Amount (+ for topup, - for deduction) *</label>
                <input
                  type="number"
                  value={creditAmount}
                  onChange={(e) => setCreditAmount(parseInt(e.target.value) || 0)}
                  required
                  className="w-full p-2.5 bg-slate-950 border border-slate-800 rounded-xl text-slate-100 text-sm font-bold font-mono focus:outline-none focus:border-teal-500"
                />
              </div>

              <div>
                <label className="block text-slate-400 mb-1 font-medium">Reason</label>
                <select
                  value={creditReason}
                  onChange={(e) => setCreditReason(e.target.value)}
                  className="w-full p-2.5 bg-slate-950 border border-slate-800 rounded-xl text-slate-100 focus:outline-none focus:border-teal-500"
                >
                  <option value="admin_topup">Admin Manual Topup</option>
                  <option value="purchase">UPI Payment Credit Purchase</option>
                  <option value="admin_deduct">Manual Deduction / Correction</option>
                  <option value="bonus">Promotional Bonus</option>
                </select>
              </div>

              <div>
                <label className="block text-slate-400 mb-1 font-medium">Audit Reference Note</label>
                <input
                  type="text"
                  placeholder="e.g. Paid Rs 1500 via UPI UTR 98218921"
                  value={creditNote}
                  onChange={(e) => setCreditNote(e.target.value)}
                  className="w-full p-2.5 bg-slate-950 border border-slate-800 rounded-xl text-slate-100 focus:outline-none focus:border-teal-500"
                />
              </div>

              <div className="p-2.5 bg-slate-950 rounded-xl border border-slate-800 flex justify-between items-center text-xs">
                <span className="text-slate-400">New Balance after change:</span>
                <span className="font-bold text-emerald-400 font-mono">
                  {Math.max(0, selectedReseller.credits_balance + creditAmount)} Credits
                </span>
              </div>

              <div className="flex gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCreditModal(false)}
                  className="w-1/2 py-2.5 bg-slate-800 hover:bg-slate-700 text-slate-300 font-semibold rounded-xl"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="w-1/2 py-2.5 bg-teal-600 hover:bg-teal-500 text-slate-950 font-bold rounded-xl shadow-md"
                >
                  Save Credit Change
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Add Reseller Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fadeIn">
          <div className="w-full max-w-md bg-slate-900 border border-slate-700 rounded-2xl p-6 text-slate-200">
            <h3 className="text-base font-bold text-slate-100 mb-4 flex items-center gap-2">
              <Users className="w-5 h-5 text-emerald-400" />
              Register New Reseller
            </h3>

            <form onSubmit={handleAddReseller} className="space-y-3 text-xs">
              <div>
                <label className="block text-slate-400 mb-1 font-medium">Reseller Name / Business *</label>
                <input
                  type="text"
                  placeholder="e.g. Vikas Sharma (Tech Solutions)"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  required
                  className="w-full p-2.5 bg-slate-950 border border-slate-800 rounded-xl text-slate-100 focus:outline-none focus:border-emerald-500"
                />
              </div>

              <div>
                <label className="block text-slate-400 mb-1 font-medium">Registered 10-Digit Phone *</label>
                <input
                  type="text"
                  placeholder="e.g. 9876543210"
                  value={formData.phone}
                  onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                  required
                  className="w-full p-2.5 bg-slate-950 border border-slate-800 rounded-xl text-slate-100 focus:outline-none focus:border-emerald-500 font-mono"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-400 mb-1 font-medium">4-Digit Secret Code *</label>
                  <input
                    type="text"
                    maxLength={4}
                    placeholder="e.g. 8899"
                    value={formData.secret_code}
                    onChange={(e) => setFormData({ ...formData, secret_code: e.target.value })}
                    required
                    className="w-full p-2.5 bg-slate-950 border border-slate-800 rounded-xl text-slate-100 text-center font-mono font-bold tracking-widest text-sm focus:outline-none focus:border-emerald-500"
                  />
                </div>

                <div>
                  <label className="block text-slate-400 mb-1 font-medium">Initial Credits</label>
                  <input
                    type="number"
                    min="0"
                    value={formData.credits_balance}
                    onChange={(e) => setFormData({ ...formData, credits_balance: parseInt(e.target.value) || 0 })}
                    className="w-full p-2.5 bg-slate-950 border border-slate-800 rounded-xl text-slate-100 focus:outline-none focus:border-emerald-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-slate-400 mb-1 font-medium">Notes / Location</label>
                <input
                  type="text"
                  placeholder="e.g. Paid starter pack via GPay"
                  value={formData.notes}
                  onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                  className="w-full p-2.5 bg-slate-950 border border-slate-800 rounded-xl text-slate-100 focus:outline-none focus:border-emerald-500"
                />
              </div>

              <div className="flex gap-2 pt-3">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="w-1/2 py-2.5 bg-slate-800 hover:bg-slate-700 text-slate-300 font-semibold rounded-xl"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="w-1/2 py-2.5 bg-emerald-600 hover:bg-emerald-500 text-slate-950 font-bold rounded-xl shadow-md"
                >
                  Register Reseller
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Transaction History Modal */}
      {showHistoryModal && selectedReseller && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fadeIn">
          <div className="w-full max-w-xl bg-slate-900 border border-slate-700 rounded-2xl p-6 text-slate-200">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-base font-bold text-slate-100 flex items-center gap-2">
                  <History className="w-4 h-4 text-teal-400" />
                  Credit Audit Trail: {selectedReseller.name}
                </h3>
                <p className="text-xs text-slate-400">Phone: {selectedReseller.phone}</p>
              </div>
              <button
                onClick={() => setShowHistoryModal(false)}
                className="text-slate-400 hover:text-slate-200 text-xs px-2 py-1 bg-slate-800 rounded-lg"
              >
                Close
              </button>
            </div>

            <div className="max-h-80 overflow-y-auto space-y-2 text-xs">
              {transactions.length === 0 ? (
                <div className="py-8 text-center text-slate-400 italic">No credit transactions recorded yet.</div>
              ) : (
                transactions.map((t) => (
                  <div key={t.id} className="p-3 bg-slate-950 rounded-xl border border-slate-800 flex items-center justify-between">
                    <div className="flex items-center gap-2.5">
                      {t.amount > 0 ? (
                        <div className="w-7 h-7 rounded-lg bg-emerald-950 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
                          <ArrowUpRight className="w-4 h-4" />
                        </div>
                      ) : (
                        <div className="w-7 h-7 rounded-lg bg-amber-950 border border-amber-500/30 flex items-center justify-center text-amber-400">
                          <ArrowDownRight className="w-4 h-4" />
                        </div>
                      )}
                      <div>
                        <div className="font-semibold text-slate-200">{t.reference_note || t.reason}</div>
                        <div className="text-[11px] text-slate-400">
                          {new Date(t.created_at).toLocaleString()}
                        </div>
                      </div>
                    </div>
                    <div className="text-right">
                      <div className={`font-mono font-bold text-sm ${t.amount > 0 ? 'text-emerald-400' : 'text-amber-400'}`}>
                        {t.amount > 0 ? `+${t.amount}` : t.amount} Credits
                      </div>
                      <div className="text-[10px] text-slate-400">Balance: {t.balance_after}</div>
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
