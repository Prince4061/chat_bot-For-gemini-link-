import React, { useState, useEffect } from 'react';
import { 
  Package, 
  Plus, 
  Trash2, 
  Edit3, 
  TrendingUp, 
  RefreshCw, 
  Check, 
  Sparkles,
  Sliders,
  DollarSign
} from 'lucide-react';
import { adminApi } from '../api/client';

export default function ProductManager() {
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [savingMarginId, setSavingMarginId] = useState(null);
  const [successMsg, setSuccessMsg] = useState('');

  // Form state
  const [formData, setFormData] = useState({
    name: '',
    category: 'AI Models',
    description: '',
    base_price: 300,
    margin_percent: 35,
    reseller_price: ''
  });
  const [resellerPriceDraft, setResellerPriceDraft] = useState({});

  const saveResellerPrice = async (p) => {
    const raw = resellerPriceDraft[p.id];
    if (raw === undefined) return;
    try {
      await adminApi.updateProduct(p.id, { reseller_price: raw === '' ? null : parseFloat(raw) });
      setSuccessMsg(`Reseller price updated for ${p.name}.`);
      setTimeout(() => setSuccessMsg(''), 3000);
      setResellerPriceDraft((d) => { const n = { ...d }; delete n[p.id]; return n; });
      loadProducts();
    } catch (err) {
      alert('Failed to update reseller price: ' + err.message);
    }
  };

  const loadProducts = async () => {
    try {
      setLoading(true);
      const data = await adminApi.getProducts();
      setProducts(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadProducts();
  }, []);

  const handleMarginChange = (id, newMargin) => {
    setProducts(products.map(p => {
      if (p.id === id) {
        const marginVal = parseFloat(newMargin) || 0;
        const newCustomerPrice = p.base_price + (p.base_price * marginVal / 100);
        return {
          ...p,
          margin_percent: marginVal,
          customer_price: Math.round(newCustomerPrice * 100) / 100
        };
      }
      return p;
    }));
  };

  const handleSaveMargin = async (id, marginVal) => {
    try {
      setSavingMarginId(id);
      await adminApi.updateMargin(id, marginVal);
      setSuccessMsg(`Margin updated! Deep Agent is now quoting live price instantly.`);
      setTimeout(() => setSuccessMsg(''), 3500);
    } catch (err) {
      alert('Failed to update margin: ' + err.message);
    } finally {
      setSavingMarginId(null);
    }
  };

  const handleAddProduct = async (e) => {
    e.preventDefault();
    try {
      await adminApi.createProduct(formData);
      setShowAddModal(false);
      setFormData({
        name: '',
        category: 'AI Models',
        description: '',
        base_price: 300,
        margin_percent: 35,
        reseller_price: ''
      });
      loadProducts();
    } catch (err) {
      alert('Error creating product: ' + err.message);
    }
  };

  const handleDelete = async (id) => {
    if (!confirm('Are you sure you want to delete this product and its inventory?')) return;
    try {
      await adminApi.deleteProduct(id);
      loadProducts();
    } catch (err) {
      alert('Error deleting: ' + err.message);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-[#ececec] flex items-center gap-2">
            <Package className="w-5 h-5 text-[#ececec]" />
            Digital Products & Dynamic Live Margin
          </h2>
          <p className="text-xs text-[#8e8ea0]">
            Configure base cost and live profit margins. Chatbot recalculates customer selling price in real-time.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={loadProducts}
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
            Add New Product
          </button>
        </div>
      </div>

      {/* Success Notification */}
      {successMsg && (
        <div className="p-3 bg-[#2f2f2f] border border-white/15 rounded-xl text-xs text-[#ececec] flex items-center gap-2 animate-fadeIn">
          <Check className="w-4 h-4 text-[#ececec] shrink-0" />
          <span>{successMsg}</span>
        </div>
      )}

      {/* Products Grid / Table */}
      {loading ? (
        <div className="p-12 text-center text-xs text-[#8e8ea0]">Loading products catalog...</div>
      ) : products.length === 0 ? (
        <div className="p-12 text-center text-xs text-[#8e8ea0] glass-panel rounded-2xl">
          No digital products added yet. Click "Add New Product" to start.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {products.map((p) => (
            <div key={p.id} className="glass-panel rounded-2xl p-5 border border-white/10 flex flex-col justify-between hover:border-white/15 transition-all shadow-lg">
              <div>
                <div className="flex items-start justify-between gap-2 mb-2">
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#3a3a3a] text-[#d4d4d4] border border-white/15 font-medium">
                    {p.category}
                  </span>
                  <div className="flex items-center gap-1.5">
                    <span className={`text-[10px] px-2 py-0.5 rounded-full font-semibold ${
                      p.in_stock 
                        ? 'bg-[#2f2f2f] text-[#ececec] border border-white/15' 
                        : 'bg-rose-950 text-rose-400 border border-rose-500/30'
                    }`}>
                      {p.in_stock ? `Stock: ${p.stock_count}` : 'Out of Stock'}
                    </span>
                    <button
                      onClick={() => handleDelete(p.id)}
                      className="p-1 text-[#8e8ea0] hover:text-rose-400 transition-colors"
                      title="Delete product"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>

                <h3 className="font-bold text-sm text-[#ececec] mb-1">{p.name}</h3>
                <p className="text-xs text-[#8e8ea0] mb-4 line-clamp-2">{p.description || 'No description provided.'}</p>

                {/* Pricing Metrics Box */}
                <div className="p-3 bg-[#2f2f2f] rounded-xl border border-white/10 mb-3 space-y-2">
                  <div className="flex justify-between items-center text-xs">
                    <span className="text-[#8e8ea0]">Admin Cost (Base):</span>
                    <span className="font-semibold text-[#d4d4d4]">₹{p.base_price.toFixed(2)}</span>
                  </div>

                  {/* Dynamic Margin Slider & Input */}
                  <div className="space-y-1">
                    <div className="flex justify-between items-center text-xs">
                      <span className="text-[#ececec] font-medium flex items-center gap-1">
                        <TrendingUp className="w-3 h-3" />
                        Dynamic Margin:
                      </span>
                      <div className="flex items-center gap-1">
                        <input
                          type="number"
                          min="0"
                          max="300"
                          value={p.margin_percent}
                          onChange={(e) => handleMarginChange(p.id, e.target.value)}
                          className="w-16 py-0.5 px-1.5 bg-[#212121] border border-white/15 rounded text-right text-xs text-[#ececec] font-bold focus:outline-none focus:border-white/15"
                        />
                        <span className="text-xs text-[#8e8ea0]">%</span>
                      </div>
                    </div>

                    <input
                      type="range"
                      min="0"
                      max="150"
                      value={p.margin_percent}
                      onChange={(e) => handleMarginChange(p.id, e.target.value)}
                      className="w-full accent-emerald-500 h-1.5 bg-[#3a3a3a] rounded-lg cursor-pointer"
                    />
                  </div>

                  <div className="pt-2 border-t border-white/10 flex justify-between items-center text-xs">
                    <span className="text-[#ececec] font-bold">Live Customer Price:</span>
                    <span className="text-sm font-bold text-[#ececec]">
                      ₹{p.customer_price.toFixed(2)}
                    </span>
                  </div>
                </div>

                <div className="flex justify-between items-center text-[11px] text-[#8e8ea0] mb-3 px-1 gap-2">
                  <span title="Reseller ke wallet se itna katta hai per link">Reseller Price (₹/link):</span>
                  <div className="flex items-center gap-1">
                    <input
                      type="number" step="0.01" min="0"
                      value={resellerPriceDraft[p.id] ?? (p.reseller_price_set ? p.reseller_price : '')}
                      placeholder={`= base ₹${p.base_price.toFixed(0)}`}
                      onChange={(e) => setResellerPriceDraft((d) => ({ ...d, [p.id]: e.target.value }))}
                      onBlur={() => saveResellerPrice(p)}
                      onKeyDown={(e) => e.key === 'Enter' && e.target.blur()}
                      className="w-24 py-0.5 px-1.5 bg-[#212121] border border-white/15 rounded text-right text-xs text-[#ececec] font-mono font-bold focus:outline-none focus:border-white/25"
                    />
                    {!p.reseller_price_set && resellerPriceDraft[p.id] === undefined && (
                      <span className="text-[10px] text-[#8e8ea0]">(= base)</span>
                    )}
                  </div>
                </div>
              </div>

              {/* Instant Save Button */}
              <button
                onClick={() => handleSaveMargin(p.id, p.margin_percent)}
                disabled={savingMarginId === p.id}
                className="w-full py-2 bg-white hover:bg-white/90 disabled:opacity-50 text-black font-bold text-xs rounded-xl transition-all shadow-md active:scale-98 flex items-center justify-center gap-1.5"
              >
                {savingMarginId === p.id ? 'Updating Live Price...' : 'Apply Live Margin'}
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Add Product Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fadeIn">
          <div className="w-full max-w-lg bg-[#2f2f2f] border border-white/15 rounded-2xl p-6 text-[#ececec]">
            <h3 className="text-base font-bold text-[#ececec] mb-4 flex items-center gap-2">
              <Package className="w-5 h-5 text-[#ececec]" />
              Add New Digital Product
            </h3>

            <form onSubmit={handleAddProduct} className="space-y-3.5 text-xs">
              <div>
                <label className="block text-[#8e8ea0] mb-1 font-medium">Product Name *</label>
                <input
                  type="text"
                  placeholder="e.g. Gemini Advanced (1-Year Private Invite)"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  required
                  className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] focus:outline-none focus:border-white/15"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-[#8e8ea0] mb-1 font-medium">Category</label>
                  <select
                    value={formData.category}
                    onChange={(e) => setFormData({ ...formData, category: e.target.value })}
                    className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] focus:outline-none focus:border-white/15"
                  >
                    <option value="AI Models">AI Models</option>
                    <option value="Design Tools">Design Tools</option>
                    <option value="Productivity">Productivity</option>
                    <option value="Cloud Storage">Cloud Storage</option>
                    <option value="Software Keys">Software Keys</option>
                  </select>
                </div>

                <div>
                  <label className="block text-[#8e8ea0] mb-1 font-medium">Reseller Price (₹/link)</label>
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    placeholder="blank = base price"
                    value={formData.reseller_price}
                    onChange={(e) => setFormData({ ...formData, reseller_price: e.target.value })}
                    className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] focus:outline-none focus:border-white/15"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-[#8e8ea0] mb-1 font-medium">Base Price / Cost (₹) *</label>
                  <input
                    type="number"
                    step="0.01"
                    value={formData.base_price}
                    onChange={(e) => setFormData({ ...formData, base_price: parseFloat(e.target.value) || 0 })}
                    required
                    className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] focus:outline-none focus:border-white/15"
                  />
                </div>

                <div>
                  <label className="block text-[#8e8ea0] mb-1 font-medium">Customer Margin (%) *</label>
                  <input
                    type="number"
                    step="0.01"
                    value={formData.margin_percent}
                    onChange={(e) => setFormData({ ...formData, margin_percent: parseFloat(e.target.value) || 0 })}
                    required
                    className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] focus:outline-none focus:border-white/15"
                  />
                </div>
              </div>

              <div>
                <label className="block text-[#8e8ea0] mb-1 font-medium">Description</label>
                <textarea
                  rows={2}
                  placeholder="Features, access duration, benefits..."
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] focus:outline-none focus:border-white/15"
                />
              </div>

              <div className="p-3 bg-[#2f2f2f] rounded-xl border border-white/15 text-[#ececec]">
                Calculated Initial Customer Selling Price: <strong>₹{(formData.base_price + (formData.base_price * formData.margin_percent / 100)).toFixed(2)}</strong>
              </div>

              <div className="flex gap-2 pt-2">
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
                  Create Product
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
