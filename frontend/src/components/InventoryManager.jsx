import React, { useState, useEffect } from 'react';
import { 
  Layers, 
  Upload, 
  Filter, 
  Trash2, 
  RefreshCw, 
  CheckCircle, 
  Flame, 
  ShieldCheck,
  Search,
  Key
} from 'lucide-react';
import { adminApi } from '../api/client';

export default function InventoryManager() {
  const [inventory, setInventory] = useState([]);
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('');
  const [productFilter, setProductFilter] = useState('');
  const [searchTerm, setSearchTerm] = useState('');

  // Bulk Upload State
  const [selectedProductId, setSelectedProductId] = useState('');
  const [bulkLinksText, setBulkLinksText] = useState('');
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState('');
  const [uploadErr, setUploadErr] = useState('');
  const [rechecking, setRechecking] = useState(false);
  const [checker, setChecker] = useState(null);   // Google link checker status (verifies Gemini links)

  const loadData = async () => {
    adminApi.googleCheckerStatus().then(setChecker).catch(() => setChecker(null));
    try {
      setLoading(true);
      const [invData, prodData] = await Promise.all([
        adminApi.getInventory(statusFilter, productFilter),
        adminApi.getProducts()
      ]);
      setInventory(invData);
      setProducts(prodData);
      if (prodData.length > 0 && !selectedProductId) {
        setSelectedProductId(prodData[0].id.toString());
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [statusFilter, productFilter]);

  const handleBulkUpload = async (e) => {
    e.preventDefault();
    if (!bulkLinksText.trim() || !selectedProductId) return;

    try {
      setUploading(true);
      setUploadMsg('');
      setUploadErr('');
      const res = await adminApi.bulkUploadInventory(selectedProductId, bulkLinksText);
      const added = res.added_count || 0;
      const skipped = res.skipped_duplicates || 0;
      if (added > 0) {
        setUploadMsg(`✅ ${added} link(s) added to ${res.product_name}. Total available: ${res.new_available_stock}.${skipped ? ` (${skipped} duplicate skipped)` : ''}`);
        setBulkLinksText('');
      } else if (skipped > 0) {
        // Nothing new — every link was already in stock.
        setUploadErr(`⚠️ Ye link(s) pehle se stock me hain (duplicate) — kuch naya add nahi hua.`);
      } else {
        setUploadErr('Kuch add nahi hua. Link aur product sahi hai?');
      }
      loadData();
      setTimeout(() => { setUploadMsg(''); setUploadErr(''); }, 6000);
    } catch (err) {
      const status = err?.response?.status;
      if (status === 401) setUploadErr('Unauthorized — admin token expired. Refresh karke dobara login karo.');
      else setUploadErr('Error: ' + (err.message || 'upload failed'));
    } finally {
      setUploading(false);
    }
  };

  const handleRecheck = async () => {
    try {
      setRechecking(true);
      const res = await adminApi.recheckInventory(productFilter);
      alert(`Freshness check done.\nChecked: ${res.checked}\nFresh: ${res.fresh}\nMarked used: ${res.marked_used}\nRestored: ${res.restored || 0}`);
      loadData();
    } catch (err) {
      alert('Error rechecking: ' + err.message);
    } finally {
      setRechecking(false);
    }
  };

  const handleRestore = async (id) => {
    try {
      await adminApi.restoreInventoryItem(id);
      loadData();
    } catch (err) {
      alert('Error restoring: ' + err.message);
    }
  };

  const handleDelete = async (id) => {
    if (!confirm('Is link ko inventory se delete karein? Ye action wapas nahi hoga.')) return;
    try {
      await adminApi.deleteInventoryItem(id);
      loadData();
    } catch (err) {
      alert('Error deleting: ' + err.message);
    }
  };

  const filteredLinks = inventory.filter(item => {
    if (!searchTerm) return true;
    const term = searchTerm.toLowerCase();
    return (
      item.link_or_key?.toLowerCase().includes(term) ||
      item.product_name?.toLowerCase().includes(term) ||
      item.claimed_by_id?.toLowerCase().includes(term)
    );
  });

  return (
    <div className="space-y-6">
      
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-[#ececec] flex items-center gap-2">
            <Layers className="w-5 h-5 text-[#ececec]" />
            Single-Use Invite Links Inventory & Burning Audit
          </h2>
          <p className="text-xs text-[#8e8ea0]">
            Bulk stock upload and live audit logs of claimed single-use invite links.
          </p>
        </div>

        <div className="flex items-center gap-2 self-start">
          <button
            onClick={handleRecheck}
            disabled={rechecking}
            title="Gemini/Google links ko abhi verify karo — used links ko 'Used' mark kar dega"
            className="px-3 py-2 bg-[#3a3a3a] hover:bg-[#4a4a4a] text-[#d4d4d4] rounded-xl transition-colors text-xs flex items-center gap-1.5 disabled:opacity-50"
          >
            <ShieldCheck className="w-3.5 h-3.5" />
            {rechecking ? 'Checking…' : 'Recheck freshness'}
          </button>
          <button
            onClick={loadData}
            className="p-2 bg-[#3a3a3a] hover:bg-[#4a4a4a] text-[#d4d4d4] rounded-xl transition-colors text-xs flex items-center gap-1.5"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Refresh
          </button>
        </div>
      </div>

      {/* Google Link Checker state: are Gemini links actually verified before delivery? */}
      {checker && (
        <div className={`rounded-2xl px-4 py-3 border text-xs flex flex-wrap items-center gap-x-3 gap-y-1 ${checker.ready && checker.logged_in !== false ? 'bg-emerald-950/30 border-emerald-500/30 text-emerald-200' : 'bg-amber-950/30 border-amber-500/30 text-amber-200'}`}>
          <ShieldCheck className="w-4 h-4 shrink-0" />
          {checker.ready && checker.logged_in !== false ? (
            <span><b>Google Link Checker: ON</b> — har Gemini link dene se pehle Google par live verify hoti hai
              {checker.logged_in ? ' (session connected ✓)' : ' (session saved — pehli check par confirm hoga)'}.
              Checks this hour: {checker.checks_this_hour}/{checker.max_per_hour}</span>
          ) : (
            <span><b>Google Link Checker: OFF</b> — Gemini links abhi <b>verify NAHI</b> ho rahi.
              Reason: {checker.not_ready_reason || 'unknown'}. Fix: <b>Settings → Google Link Checker</b>
              {!checker.session_present && ' (throwaway Gmail se `python google_checker.py login` → JSON paste → Connect)'}
              {checker.installed && !checker.browser_ok && ' (VPS: python3 -m playwright install --with-deps chromium)'}.
            </span>
          )}
        </div>
      )}

      {/* Bulk Upload Section */}
      <div className="glass-panel rounded-2xl p-5 border border-white/10">
        <h3 className="text-sm font-bold text-[#ececec] mb-2 flex items-center gap-2">
          <Upload className="w-4 h-4 text-[#ececec]" />
          Bulk Stock Ingestion (Paste Links / Product Keys)
        </h3>
        
        <form onSubmit={handleBulkUpload} className="space-y-3 text-xs">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <label className="block text-[#8e8ea0] mb-1 font-medium">Select Target Product *</label>
              <select
                value={selectedProductId}
                onChange={(e) => setSelectedProductId(e.target.value)}
                required
                className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] focus:outline-none focus:border-white/15"
              >
                {products.map(p => (
                  <option key={p.id} value={p.id}>
                    {p.name} (Stock: {p.stock_count})
                  </option>
                ))}
              </select>
            </div>

            <div className="sm:col-span-2">
              <label className="block text-[#8e8ea0] mb-1 font-medium">
                Paste Invite Links / Keys (1 link per line) *
              </label>
              <textarea
                rows={3}
                placeholder="https://families.google.com/join/invite?token=XXXX1&#10;https://families.google.com/join/invite?token=XXXX2&#10;KEY-8921-VIP-ACCESS"
                value={bulkLinksText}
                onChange={(e) => setBulkLinksText(e.target.value)}
                required
                className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] font-mono text-[11px] focus:outline-none focus:border-white/15"
              />
            </div>
          </div>

          <div className="flex items-center justify-between pt-1">
            <span className="text-[11px] text-[#8e8ea0]">
              {bulkLinksText.split('\n').filter(l => l.trim()).length} link(s) ready to upload
            </span>
            <button
              type="submit"
              disabled={uploading || !bulkLinksText.trim()}
              className="px-4 py-2 bg-gradient-to-r from-white to-white hover:from-white hover:to-white disabled:opacity-50 text-black font-bold rounded-xl text-xs transition-all shadow-md active:scale-95"
            >
              {uploading ? 'Ingesting Links...' : 'Add Links to Stock'}
            </button>
          </div>
        </form>

        {uploadMsg && (
          <div className="mt-3 p-2.5 bg-[#2f2f2f] border border-emerald-500/30 rounded-xl text-xs text-[#ececec] flex items-center gap-2 animate-fadeIn">
            <CheckCircle className="w-4 h-4 text-emerald-400" />
            <span>{uploadMsg}</span>
          </div>
        )}
        {uploadErr && (
          <div className="mt-3 p-2.5 bg-rose-950/40 border border-rose-500/40 rounded-xl text-xs text-rose-300 flex items-center gap-2 animate-fadeIn">
            <span>{uploadErr}</span>
          </div>
        )}
      </div>

      {/* Filter & Search Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-3 bg-[#2f2f2f] rounded-xl border border-white/10">
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-[#8e8ea0]" />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="p-1.5 bg-[#212121] border border-white/10 rounded-lg text-xs text-[#d4d4d4] focus:outline-none"
          >
            <option value="">All Statuses</option>
            <option value="available">Available in Stock</option>
            <option value="claimed">Claimed / Burned</option>
            <option value="used">Used (dead)</option>
          </select>

          <select
            value={productFilter}
            onChange={(e) => setProductFilter(e.target.value)}
            className="p-1.5 bg-[#212121] border border-white/10 rounded-lg text-xs text-[#d4d4d4] focus:outline-none"
          >
            <option value="">All Products</option>
            {products.map(p => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </div>

        <div className="relative">
          <Search className="w-3.5 h-3.5 text-[#8e8ea0] absolute left-2.5 top-2.5" />
          <input
            type="text"
            placeholder="Search link, phone, product..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="pl-8 pr-3 py-1.5 bg-[#212121] border border-white/10 rounded-lg text-xs text-[#ececec] focus:outline-none focus:border-white/15 w-56"
          />
        </div>
      </div>

      {/* Links Inventory Table */}
      <div className="glass-panel rounded-2xl overflow-hidden border border-white/10">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs text-[#d4d4d4]">
            <thead className="bg-[#2f2f2f] text-[11px] font-bold text-[#8e8ea0] uppercase tracking-wider border-b border-white/10">
              <tr>
                <th className="py-3 px-4">ID</th>
                <th className="py-3 px-4">Product</th>
                <th className="py-3 px-4">Single-Use Link / Key</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4">Claimed By</th>
                <th className="py-3 px-4">Claimed At</th>
                <th className="py-3 px-4 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {loading ? (
                <tr>
                  <td colSpan="7" className="py-8 text-center text-[#8e8ea0]">Loading inventory records...</td>
                </tr>
              ) : filteredLinks.length === 0 ? (
                <tr>
                  <td colSpan="7" className="py-8 text-center text-[#8e8ea0] italic">No matching inventory links found.</td>
                </tr>
              ) : (
                filteredLinks.map((item) => (
                  <tr key={item.id} className="hover:bg-[#2f2f2f] transition-colors">
                    <td className="py-3 px-4 font-mono text-[#8e8ea0]">#{item.id}</td>
                    <td className="py-3 px-4 font-semibold text-[#ececec]">{item.product_name}</td>
                    <td className="py-3 px-4 font-mono text-xs max-w-xs truncate text-[#ececec] select-all">
                      {item.link_or_key}
                    </td>
                    <td className="py-3 px-4">
                      {item.status === 'available' ? (
                        <div className="flex items-center gap-1.5">
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-[#2f2f2f] text-[#ececec] border border-white/15 text-[10px] font-semibold">
                            <CheckCircle className="w-3 h-3" />
                            Available
                          </span>
                          {item.health === 'fresh' && (
                            <span className="px-1.5 py-0.5 rounded-full bg-emerald-950 text-emerald-300 border border-emerald-500/30 text-[9px] font-semibold" title="Verified fresh">✓ Fresh</span>
                          )}
                          {item.health === 'unknown' && (
                            <span className="px-1.5 py-0.5 rounded-full bg-[#3a3a3a] text-[#8e8ea0] border border-white/10 text-[9px] font-semibold" title="Could not verify">? </span>
                          )}
                        </div>
                      ) : item.status === 'used' ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-rose-950 text-rose-300 border border-rose-500/40 text-[10px] font-semibold" title="Detected as already used — not handed out">
                          ⚠ Used (dead)
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-950 text-amber-400 border border-amber-500/30 text-[10px] font-semibold">
                          <Flame className="w-3 h-3 text-amber-400" />
                          Burned / Claimed
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-[#d4d4d4]">
                      {item.claimed_by_id ? (
                        <div>
                          <span className="capitalize font-medium text-[#ececec]">
                            {item.claimed_by_type || 'User'}:
                          </span>{' '}
                          <span className="font-mono text-[#ececec]">{item.claimed_by_id}</span>
                        </div>
                      ) : (
                        <span className="text-[#8e8ea0]">—</span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-[#8e8ea0] text-[11px]">
                      {item.claimed_at ? new Date(item.claimed_at).toLocaleString() : '—'}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        {item.status === 'used' && (
                          <button
                            onClick={() => handleRestore(item.id)}
                            className="px-2 py-1 rounded-lg bg-[#3a3a3a] hover:bg-[#4a4a4a] text-emerald-300 text-[10px] font-semibold transition-colors"
                            title="Wapas available stock me daalo"
                          >
                            Restore
                          </button>
                        )}
                        <button
                          onClick={() => handleDelete(item.id)}
                          className="p-1 hover:text-rose-400 text-[#8e8ea0] transition-colors"
                          title="Delete from stock"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
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
