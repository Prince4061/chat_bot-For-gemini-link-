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

  // Credit Adjustment State (credits are PER PRODUCT)
  const [products, setProducts] = useState([]);
  const [creditProductId, setCreditProductId] = useState('');
  const [creditAmount, setCreditAmount] = useState(10);
  const [creditReason, setCreditReason] = useState('admin_topup');
  const [creditNote, setCreditNote] = useState('Admin wallet topup');
  const [legacyMode, setLegacyMode] = useState(false); // assigning old unassigned credits

  // Add Reseller State
  const [formData, setFormData] = useState({
    name: '',
    phone: '',
    secret_code: '1234',
    product_id: '',
    credits_balance: 10,
    notes: ''
  });

  const loadResellers = async () => {
    try {
      setLoading(true);
      const [data, prods] = await Promise.all([adminApi.getResellers(), adminApi.getProducts()]);
      setResellers(data);
      setProducts(prods);
      if (prods.length && !creditProductId) setCreditProductId(String(prods[0].id));
      if (prods.length && !formData.product_id) setFormData((f) => ({ ...f, product_id: String(prods[0].id) }));
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
      setFormData((f) => ({
        name: '',
        phone: '',
        secret_code: '1234',
        product_id: f.product_id || (products[0] ? String(products[0].id) : ''),
        credits_balance: 10,
        notes: ''
      }));
      loadResellers();
    } catch (err) {
      alert('Error creating reseller: ' + err.message);
    }
  };

  const handleAdjustCredits = async (e) => {
    e.preventDefault();
    if (!selectedReseller || !creditProductId) return;
    try {
      if (legacyMode) {
        await adminApi.assignLegacyCredits(selectedReseller.id, creditProductId, creditAmount);
      } else {
        await adminApi.adjustCredits(selectedReseller.id, creditProductId, creditAmount, creditReason, creditNote);
      }
      setShowCreditModal(false);
      setLegacyMode(false);
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
          <h2 className="text-lg font-bold text-[#ececec] flex items-center gap-2">
            <Users className="w-5 h-5 text-[#ececec]" />
            Reseller Management & Wallet Credits
          </h2>
          <p className="text-xs text-[#8e8ea0]">
            Manage authorized resellers, set 4-digit secret codes, and top up/deduct credit balances.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={loadResellers}
            className="p-2 bg-[#3a3a3a] hover:bg-[#4a4a4a] text-[#d4d4d4] rounded-xl transition-colors text-xs flex items-center gap-1.5"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Refresh
          </button>
          <button
            onClick={() => setShowAddModal(true)}
            className="px-3.5 py-2 bg-gradient-to-r from-white to-white hover:from-white hover:to-white text-black font-bold rounded-xl text-xs flex items-center gap-1.5 shadow-md active:scale-95 transition-all"
          >
            <Plus className="w-4 h-4" />
            Add Reseller
          </button>
        </div>
      </div>

      {/* Reseller Grid */}
      {loading ? (
        <div className="p-12 text-center text-xs text-[#8e8ea0]">Loading resellers...</div>
      ) : resellers.length === 0 ? (
        <div className="p-12 text-center text-xs text-[#8e8ea0] glass-panel rounded-2xl">
          No registered resellers found. Click "Add Reseller" to create one.
        </div>
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
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#2f2f2f] text-[#ececec] border border-white/15 font-semibold">
                        Active
                      </span>
                    ) : (
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#3a3a3a] text-[#8e8ea0] border border-white/15 font-semibold">
                        Inactive
                      </span>
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
                    <span className="font-mono text-xs font-bold text-[#ececec] tracking-widest">
                      {showCodes[r.id] ? r.secret_code : '••••'}
                    </span>
                    <button
                      onClick={() => handleToggleCode(r.id)}
                      className="p-1 text-[#8e8ea0] hover:text-[#ececec]"
                    >
                      {showCodes[r.id] ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                    </button>
                  </div>
                </div>

                {/* Per-product Credits Card */}
                <div className="p-3 bg-[#2f2f2f] rounded-xl border border-white/15 mb-4">
                  <div className="flex items-center justify-between mb-2">
                    <div>
                      <span className="text-[10px] uppercase font-bold text-[#8e8ea0] block">Credits (per product)</span>
                      <span className="text-lg font-bold text-[#ececec] font-mono">{r.credits_balance}</span>
                      <span className="text-[11px] text-[#8e8ea0] ml-1">total</span>
                    </div>
                    <button
                      onClick={() => { setSelectedReseller(r); setLegacyMode(false); setCreditAmount(10); setShowCreditModal(true); }}
                      className="px-3 py-1.5 bg-white hover:bg-white/90 text-black font-bold text-xs rounded-lg shadow-sm transition-all"
                    >
                      Adjust
                    </button>
                  </div>
                  {r.product_credits && r.product_credits.filter((c) => c.credits > 0).length > 0 ? (
                    <div className="space-y-1">
                      {r.product_credits.filter((c) => c.credits > 0).map((c) => (
                        <div key={c.product_id} className="flex items-center justify-between text-[11px]">
                          <span className="text-[#d4d4d4] truncate max-w-[170px]">{c.product_name.split(' (')[0]}</span>
                          <span className="font-mono font-bold text-[#ececec]">{c.credits}</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-[11px] text-[#8e8ea0]">Kisi product ke credits nahi — Adjust se do.</div>
                  )}
                  {r.legacy_unassigned_credits > 0 && (
                    <button
                      onClick={() => { setSelectedReseller(r); setLegacyMode(true); setCreditAmount(r.legacy_unassigned_credits); setShowCreditModal(true); }}
                      className="mt-2 w-full text-left text-[11px] px-2 py-1.5 rounded-lg bg-amber-950/40 text-amber-300 border border-amber-500/30 hover:bg-amber-950/60"
                      title="Purane generic credits — kisi product ko assign karo tabhi claim honge"
                    >
                      ⚠ {r.legacy_unassigned_credits} unassigned credit(s) → product ko assign karo
                    </button>
                  )}
                </div>
              </div>

              <div className="pt-2 border-t border-white/10 flex items-center justify-between text-xs text-[#8e8ea0]">
                <span className="text-[11px] truncate max-w-[130px]">{r.notes || 'Registered Reseller'}</span>
                <button
                  onClick={() => handleOpenHistory(r)}
                  className="text-[#ececec] hover:text-[#ececec] font-medium flex items-center gap-1 text-[11px]"
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
          <div className="w-full max-w-md bg-[#2f2f2f] border border-white/15 rounded-2xl p-6 text-[#ececec]">
            <h3 className="text-base font-bold text-[#ececec] mb-2 flex items-center gap-2">
              <CreditCard className="w-5 h-5 text-[#ececec]" />
              {legacyMode ? 'Assign unassigned credits' : 'Adjust Credits'}: {selectedReseller.name}
            </h3>
            <p className="text-xs text-[#8e8ea0] mb-4">
              {legacyMode
                ? <>Unassigned: <strong className="text-amber-300">{selectedReseller.legacy_unassigned_credits}</strong> — choose which product these credits are for.</>
                : <>Credits are <strong className="text-[#ececec]">per product</strong>. Total now: <strong className="text-[#ececec]">{selectedReseller.credits_balance}</strong></>}
            </p>

            <form onSubmit={handleAdjustCredits} className="space-y-3.5 text-xs">
              <div>
                <label className="block text-[#8e8ea0] mb-1 font-medium">Product (credits sirf isi ke liye) *</label>
                <select
                  value={creditProductId}
                  onChange={(e) => setCreditProductId(e.target.value)}
                  required
                  className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] focus:outline-none focus:border-white/15"
                >
                  {products.map((p) => {
                    const have = (selectedReseller.product_credits || []).find((c) => c.product_id === p.id)?.credits || 0;
                    return <option key={p.id} value={p.id}>{p.name} — currently {have}</option>;
                  })}
                </select>
              </div>

              <div>
                <label className="block text-[#8e8ea0] mb-1 font-medium">{legacyMode ? 'Credits to assign *' : 'Credit Amount (+ for topup, - for deduction) *'}</label>
                <input
                  type="number"
                  value={creditAmount}
                  onChange={(e) => setCreditAmount(parseInt(e.target.value) || 0)}
                  required
                  className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] text-sm font-bold font-mono focus:outline-none focus:border-white/15"
                />
              </div>

              <div>
                <label className="block text-[#8e8ea0] mb-1 font-medium">Reason</label>
                <select
                  value={creditReason}
                  onChange={(e) => setCreditReason(e.target.value)}
                  className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] focus:outline-none focus:border-white/15"
                >
                  <option value="admin_topup">Admin Manual Topup</option>
                  <option value="purchase">UPI Payment Credit Purchase</option>
                  <option value="admin_deduct">Manual Deduction / Correction</option>
                  <option value="bonus">Promotional Bonus</option>
                </select>
              </div>

              <div>
                <label className="block text-[#8e8ea0] mb-1 font-medium">Audit Reference Note</label>
                <input
                  type="text"
                  placeholder="e.g. Paid Rs 1500 via UPI UTR 98218921"
                  value={creditNote}
                  onChange={(e) => setCreditNote(e.target.value)}
                  className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] focus:outline-none focus:border-white/15"
                />
              </div>

              <div className="p-2.5 bg-[#212121] rounded-xl border border-white/10 flex justify-between items-center text-xs">
                <span className="text-[#8e8ea0]">Is product ke credits after change:</span>
                <span className="font-bold text-[#ececec] font-mono">
                  {Math.max(0, ((selectedReseller.product_credits || []).find((c) => String(c.product_id) === String(creditProductId))?.credits || 0) + creditAmount)} Credits
                </span>
              </div>

              <div className="flex gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCreditModal(false)}
                  className="w-1/2 py-2.5 bg-[#3a3a3a] hover:bg-[#4a4a4a] text-[#d4d4d4] font-semibold rounded-xl"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="w-1/2 py-2.5 bg-white hover:bg-white/90 text-black font-bold rounded-xl shadow-md"
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
          <div className="w-full max-w-md bg-[#2f2f2f] border border-white/15 rounded-2xl p-6 text-[#ececec]">
            <h3 className="text-base font-bold text-[#ececec] mb-4 flex items-center gap-2">
              <Users className="w-5 h-5 text-[#ececec]" />
              Register New Reseller
            </h3>

            <form onSubmit={handleAddReseller} className="space-y-3 text-xs">
              <div>
                <label className="block text-[#8e8ea0] mb-1 font-medium">Reseller Name / Business *</label>
                <input
                  type="text"
                  placeholder="e.g. Vikas Sharma (Tech Solutions)"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  required
                  className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] focus:outline-none focus:border-white/15"
                />
              </div>

              <div>
                <label className="block text-[#8e8ea0] mb-1 font-medium">Registered 10-Digit Phone *</label>
                <input
                  type="text"
                  placeholder="e.g. 9876543210"
                  value={formData.phone}
                  onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                  required
                  className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] focus:outline-none focus:border-white/15 font-mono"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-[#8e8ea0] mb-1 font-medium">4-Digit Secret Code *</label>
                  <input
                    type="text"
                    maxLength={4}
                    placeholder="e.g. 8899"
                    value={formData.secret_code}
                    onChange={(e) => setFormData({ ...formData, secret_code: e.target.value })}
                    required
                    className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] text-center font-mono font-bold tracking-widest text-sm focus:outline-none focus:border-white/15"
                  />
                </div>

                <div>
                  <label className="block text-[#8e8ea0] mb-1 font-medium">Initial Credits</label>
                  <input
                    type="number"
                    min="0"
                    value={formData.credits_balance}
                    onChange={(e) => setFormData({ ...formData, credits_balance: parseInt(e.target.value) || 0 })}
                    className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] focus:outline-none focus:border-white/15"
                  />
                </div>
              </div>

              <div>
                <label className="block text-[#8e8ea0] mb-1 font-medium">Credits kis product ke liye? *</label>
                <select
                  value={formData.product_id}
                  onChange={(e) => setFormData({ ...formData, product_id: e.target.value })}
                  className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] focus:outline-none focus:border-white/15"
                >
                  {products.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
                <span className="text-[10px] text-[#8e8ea0] mt-1 block">Reseller sirf isi product ki link claim kar payega. Aur products baad me "Adjust" se add karo.</span>
              </div>

              <div>
                <label className="block text-[#8e8ea0] mb-1 font-medium">Notes / Location</label>
                <input
                  type="text"
                  placeholder="e.g. Paid starter pack via GPay"
                  value={formData.notes}
                  onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                  className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] focus:outline-none focus:border-white/15"
                />
              </div>

              <div className="flex gap-2 pt-3">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="w-1/2 py-2.5 bg-[#3a3a3a] hover:bg-[#4a4a4a] text-[#d4d4d4] font-semibold rounded-xl"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="w-1/2 py-2.5 bg-white hover:bg-white/90 text-black font-bold rounded-xl shadow-md"
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
          <div className="w-full max-w-xl bg-[#2f2f2f] border border-white/15 rounded-2xl p-6 text-[#ececec]">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-base font-bold text-[#ececec] flex items-center gap-2">
                  <History className="w-4 h-4 text-[#ececec]" />
                  Credit Audit Trail: {selectedReseller.name}
                </h3>
                <p className="text-xs text-[#8e8ea0]">Phone: {selectedReseller.phone}</p>
              </div>
              <button
                onClick={() => setShowHistoryModal(false)}
                className="text-[#8e8ea0] hover:text-[#ececec] text-xs px-2 py-1 bg-[#3a3a3a] rounded-lg"
              >
                Close
              </button>
            </div>

            <div className="max-h-80 overflow-y-auto space-y-2 text-xs">
              {transactions.length === 0 ? (
                <div className="py-8 text-center text-[#8e8ea0] italic">No credit transactions recorded yet.</div>
              ) : (
                transactions.map((t) => (
                  <div key={t.id} className="p-3 bg-[#212121] rounded-xl border border-white/10 flex items-center justify-between">
                    <div className="flex items-center gap-2.5">
                      {t.amount > 0 ? (
                        <div className="w-7 h-7 rounded-lg bg-[#2f2f2f] border border-white/15 flex items-center justify-center text-[#ececec]">
                          <ArrowUpRight className="w-4 h-4" />
                        </div>
                      ) : (
                        <div className="w-7 h-7 rounded-lg bg-amber-950 border border-amber-500/30 flex items-center justify-center text-amber-400">
                          <ArrowDownRight className="w-4 h-4" />
                        </div>
                      )}
                      <div>
                        <div className="font-semibold text-[#ececec]">{t.reference_note || t.reason}</div>
                        <div className="text-[11px] text-[#8e8ea0]">
                          {new Date(t.created_at).toLocaleString()}
                        </div>
                      </div>
                    </div>
                    <div className="text-right">
                      <div className={`font-mono font-bold text-sm ${t.amount > 0 ? 'text-[#ececec]' : 'text-amber-400'}`}>
                        {t.amount > 0 ? `+${t.amount}` : t.amount} Credits
                      </div>
                      <div className="text-[10px] text-[#8e8ea0]">Balance: {t.balance_after}</div>
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
