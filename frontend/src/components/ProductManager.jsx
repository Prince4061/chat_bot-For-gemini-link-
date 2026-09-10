import React, { useState, useEffect, useRef } from 'react';
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

  // Form state — two margins over the same base cost: one for customers, one for resellers.
  const [formData, setFormData] = useState({
    name: '',
    category: 'AI Models',
    description: '',
    base_price: 300,
    margin_percent: 35,
    reseller_margin_percent: 10
  });

  const priceWithMargin = (base, pct) => Math.round((base + (base * (parseFloat(pct) || 0) / 100)) * 100) / 100;

  // Live m00nshots info (name / $ price / ≈₹ / stock) per LOCAL product id, so the admin never has
  // to open Browse to see what the supplier currently charges.
  const [supInfo, setSupInfo] = useState({});
  const [supLoading, setSupLoading] = useState(false);
  const supTimers = useRef({});

  const loadSupplierInfo = async (fresh = false) => {
    try {
      setSupLoading(true);
      const res = await adminApi.moonshotsMapped(fresh);
      setSupInfo(prev => ({ ...prev, ...(res.items || {}) }));
    } catch (err) {
      console.error(err);
    } finally {
      setSupLoading(false);
    }
  };

  // Called (debounced) while the admin types a supplier id, so the card shows that id's live price
  // before they even press "Save source".
  const fetchSupplierInfoFor = (localId, supplierId, fresh = false) => {
    clearTimeout(supTimers.current[localId]);
    const sid = parseInt(supplierId, 10);
    if (!sid) { setSupInfo(prev => ({ ...prev, [localId]: null })); return; }
    supTimers.current[localId] = setTimeout(async () => {
      setSupInfo(prev => ({ ...prev, [localId]: { loading: true } }));
      try {
        const res = await adminApi.moonshotsProduct(sid, fresh);
        setSupInfo(prev => ({ ...prev, [localId]: res.data }));
      } catch (err) {
        setSupInfo(prev => ({ ...prev, [localId]: { error: err.response?.data?.error || err.message } }));
      }
    }, fresh ? 0 : 600);
  };

  const loadProducts = async () => {
    try {
      setLoading(true);
      const data = await adminApi.getProducts();
      setProducts(data);
      if (data.some(p => p.source === 'moonshots' && p.supplier_product_id)) loadSupplierInfo();
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadProducts();
  }, []);

  // Live-preview either slider; prices are recomputed locally until "Apply" saves them.
  const handleMarginChange = (id, field, value) => {
    setProducts(products.map(p => {
      if (p.id !== id) return p;
      const v = parseFloat(value) || 0;
      const next = { ...p, [field]: v };
      next.customer_price = priceWithMargin(p.base_price, next.margin_percent);
      next.reseller_price = priceWithMargin(p.base_price, next.reseller_margin_percent);
      return next;
    }));
  };

  const handleSupplierChange = (id, field, value) => {
    setProducts(products.map(p => (p.id === id ? { ...p, [field]: value } : p)));
    if (field === 'supplier_product_id') fetchSupplierInfoFor(id, value);
    if (field === 'source' && value === 'moonshots') {
      const cur = products.find(p => p.id === id);
      if (cur?.supplier_product_id) fetchSupplierInfoFor(id, cur.supplier_product_id);
    }
  };

  const handleSaveSupplier = async (p) => {
    try {
      setSavingMarginId(p.id);
      await adminApi.updateProduct(p.id, {
        source: p.source || 'stock',
        supplier_product_id: p.supplier_product_id === '' ? null : p.supplier_product_id,
        supplier_max_price: p.supplier_max_price === '' ? null : p.supplier_max_price,
      });
      setSuccessMsg((p.source === 'moonshots')
        ? `Auto-buy ON: stock khatam hone par bot m00nshots product #${p.supplier_product_id} khud khareed ke dega.`
        : 'Source set to local stock.');
      setTimeout(() => setSuccessMsg(''), 4000);
      loadProducts();
    } catch (err) {
      alert('Failed to save supplier settings: ' + (err.response?.data?.error || err.message));
    } finally {
      setSavingMarginId(null);
    }
  };

  const handleSaveMargin = async (p) => {
    try {
      setSavingMarginId(p.id);
      await adminApi.updateMargin(p.id, p.margin_percent, p.reseller_margin_percent);
      setSuccessMsg(`Saved! Bot ab customer ko ₹${priceWithMargin(p.base_price, p.margin_percent).toFixed(2)} aur reseller ko ₹${priceWithMargin(p.base_price, p.reseller_margin_percent).toFixed(2)} quote karega.`);
      setTimeout(() => setSuccessMsg(''), 4000);
      loadProducts();
    } catch (err) {
      alert('Failed to update margins: ' + err.message);
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
        reseller_margin_percent: 10
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

                  {/* Slider 1: CUSTOMER margin */}
                  <div className="space-y-1">
                    <div className="flex justify-between items-center text-xs">
                      <span className="text-[#ececec] font-medium flex items-center gap-1">
                        <TrendingUp className="w-3 h-3" />
                        Customer Margin:
                      </span>
                      <div className="flex items-center gap-1">
                        <input
                          type="number" min="0" max="300"
                          value={p.margin_percent}
                          onChange={(e) => handleMarginChange(p.id, 'margin_percent', e.target.value)}
                          className="w-16 py-0.5 px-1.5 bg-[#212121] border border-white/15 rounded text-right text-xs text-[#ececec] font-bold focus:outline-none focus:border-white/15"
                        />
                        <span className="text-xs text-[#8e8ea0]">%</span>
                      </div>
                    </div>
                    <input
                      type="range" min="0" max="150"
                      value={p.margin_percent}
                      onChange={(e) => handleMarginChange(p.id, 'margin_percent', e.target.value)}
                      className="w-full accent-emerald-500 h-1.5 bg-[#3a3a3a] rounded-lg cursor-pointer"
                    />
                    <div className="flex justify-between items-center text-xs">
                      <span className="text-[#ececec] font-bold">Live Customer Price:</span>
                      <span className="text-sm font-bold text-emerald-300">₹{p.customer_price.toFixed(2)}</span>
                    </div>
                  </div>

                  {/* Slider 2: RESELLER margin */}
                  <div className="space-y-1 pt-2 border-t border-white/10">
                    <div className="flex justify-between items-center text-xs">
                      <span className="text-[#ececec] font-medium flex items-center gap-1">
                        <TrendingUp className="w-3 h-3" />
                        Reseller Margin:
                      </span>
                      <div className="flex items-center gap-1">
                        <input
                          type="number" min="0" max="300"
                          value={p.reseller_margin_percent ?? 0}
                          onChange={(e) => handleMarginChange(p.id, 'reseller_margin_percent', e.target.value)}
                          className="w-16 py-0.5 px-1.5 bg-[#212121] border border-white/15 rounded text-right text-xs text-[#ececec] font-bold focus:outline-none focus:border-white/15"
                        />
                        <span className="text-xs text-[#8e8ea0]">%</span>
                      </div>
                    </div>
                    <input
                      type="range" min="0" max="150"
                      value={p.reseller_margin_percent ?? 0}
                      onChange={(e) => handleMarginChange(p.id, 'reseller_margin_percent', e.target.value)}
                      className="w-full accent-sky-400 h-1.5 bg-[#3a3a3a] rounded-lg cursor-pointer"
                    />
                    <div className="flex justify-between items-center text-xs">
                      <span className="text-[#ececec] font-bold" title="Reseller ke wallet se itna katta hai per link">Live Reseller Price:</span>
                      <span className="text-sm font-bold text-sky-300">₹{Number(p.reseller_price).toFixed(2)}</span>
                    </div>
                  </div>
                </div>
                {/* Auto-buy supplier source */}
                <div className="p-3 bg-[#2f2f2f] rounded-xl border border-white/10 mt-3 space-y-2">
                  <div className="flex justify-between items-center text-xs">
                    <span className="text-[#ececec] font-medium">Stock source</span>
                    <select
                      value={p.source || 'stock'}
                      onChange={(e) => handleSupplierChange(p.id, 'source', e.target.value)}
                      className="py-0.5 px-1.5 bg-[#212121] border border-white/15 rounded text-xs text-[#ececec] focus:outline-none"
                    >
                      <option value="stock">Local stock</option>
                      <option value="moonshots">m00nshots auto-buy</option>
                    </select>
                  </div>
                  {(p.source || 'stock') === 'moonshots' && (
                    <div className="space-y-2">
                      <div className="flex justify-between items-center text-xs gap-2">
                        <span className="text-[#8e8ea0] whitespace-nowrap" title="Supplier catalogue me product ki ID (Settings → m00nshots → Browse)">Supplier product ID</span>
                        <input
                          type="number" min="1" placeholder="e.g. 42"
                          value={p.supplier_product_id ?? ''}
                          onChange={(e) => handleSupplierChange(p.id, 'supplier_product_id', e.target.value)}
                          className="w-24 py-0.5 px-1.5 bg-[#212121] border border-white/15 rounded text-right text-xs text-[#ececec] focus:outline-none"
                        />
                      </div>
                      <div className="flex justify-between items-center text-xs gap-2">
                        <span className="text-[#8e8ea0] whitespace-nowrap" title="Is price se upar supplier ho to auto-buy nahi hoga (USD). Khaali = no cap">Max buy price ($)</span>
                        <input
                          type="number" min="0" step="0.01" placeholder="optional"
                          value={p.supplier_max_price ?? ''}
                          onChange={(e) => handleSupplierChange(p.id, 'supplier_max_price', e.target.value)}
                          className="w-24 py-0.5 px-1.5 bg-[#212121] border border-white/15 rounded text-right text-xs text-[#ececec] focus:outline-none"
                        />
                      </div>
                      {/* Live supplier info for the mapped id — no need to open Browse */}
                      {p.supplier_product_id && (() => {
                        const info = supInfo[p.id];
                        const rupee = info && !info.error && !info.loading ? Number(info.price_inr || 0) : null;
                        const losing = rupee !== null && rupee > Number(p.base_price || 0);
                        return (
                          <div className="rounded-lg bg-[#212121] border border-white/10 p-2 text-[11px] space-y-1">
                            <div className="flex items-center justify-between gap-2">
                              <span className="text-[#8e8ea0]">m00nshots live</span>
                              <button type="button" title="Abhi refresh karo"
                                onClick={() => fetchSupplierInfoFor(p.id, p.supplier_product_id, true)}
                                className="text-[#8e8ea0] hover:text-[#ececec] px-1 rounded">
                                <RefreshCw className={`w-3 h-3 ${info?.loading ? 'animate-spin' : ''}`} />
                              </button>
                            </div>
                            {!info || info.loading ? (
                              <div className="text-[#8e8ea0]">Price load ho raha hai…</div>
                            ) : info.error ? (
                              <div className="text-rose-300 break-words">{info.error}</div>
                            ) : (
                              <>
                                <div className="text-[#ececec] font-semibold truncate" title={info.name}>{info.icon} {info.name}</div>
                                <div className="flex justify-between items-center">
                                  <span className="text-[#8e8ea0]">Supplier price</span>
                                  <span className="font-bold text-emerald-300">${Number(info.price).toFixed(2)}
                                    <span className="text-[#8e8ea0] font-normal"> ≈ ₹{rupee.toFixed(0)}</span>
                                  </span>
                                </div>
                                <div className="flex justify-between items-center">
                                  <span className="text-[#8e8ea0]">Supplier stock</span>
                                  <span className={info.in_stock ? 'text-[#d4d4d4]' : 'text-rose-300'}>{info.in_stock ? info.stock : 'out of stock'}</span>
                                </div>
                                {losing && (
                                  <div className="text-amber-300 leading-snug">⚠ Supplier price (₹{rupee.toFixed(0)}) aapke base price (₹{Number(p.base_price).toFixed(0)}) se zyada — base price badhao warna nuksan.</div>
                                )}
                              </>
                            )}
                          </div>
                        );
                      })()}
                      <p className="text-[10px] text-[#8e8ea0] leading-snug">Stock khatam hone par bot supplier se khud khareed ke user ko dega. Settings me API key + enable zaroori hai.</p>
                    </div>
                  )}
                  <button
                    onClick={() => handleSaveSupplier(p)}
                    disabled={savingMarginId === p.id}
                    className="w-full py-1.5 bg-[#3a3a3a] hover:bg-[#4a4a4a] disabled:opacity-50 text-[#d4d4d4] font-semibold text-[11px] rounded-lg transition-all"
                  >
                    Save source
                  </button>
                </div>
              </div>

              {/* Saves both margins */}
              <button
                onClick={() => handleSaveMargin(p)}
                disabled={savingMarginId === p.id}
                className="w-full py-2 bg-white hover:bg-white/90 disabled:opacity-50 text-black font-bold text-xs rounded-xl transition-all shadow-md active:scale-98 flex items-center justify-center gap-1.5"
              >
                {savingMarginId === p.id ? 'Updating Live Prices...' : 'Apply Live Margins'}
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
                  <label className="block text-[#8e8ea0] mb-1 font-medium">Reseller Margin (%)</label>
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    value={formData.reseller_margin_percent}
                    onChange={(e) => setFormData({ ...formData, reseller_margin_percent: parseFloat(e.target.value) || 0 })}
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

              <div className="p-3 bg-[#2f2f2f] rounded-xl border border-white/15 text-[#ececec] space-y-1">
                <div>Customer price: <strong className="text-emerald-300">₹{priceWithMargin(formData.base_price, formData.margin_percent).toFixed(2)}</strong> <span className="text-[#8e8ea0]">(base + {formData.margin_percent || 0}%)</span></div>
                <div>Reseller price: <strong className="text-sky-300">₹{priceWithMargin(formData.base_price, formData.reseller_margin_percent).toFixed(2)}</strong> <span className="text-[#8e8ea0]">(base + {formData.reseller_margin_percent || 0}%, wallet se katega)</span></div>
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
