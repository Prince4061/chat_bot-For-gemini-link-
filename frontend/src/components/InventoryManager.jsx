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

  const loadData = async () => {
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
      const res = await adminApi.bulkUploadInventory(selectedProductId, bulkLinksText);
      setUploadMsg(`Successfully added ${res.added_count} single-use link(s) to ${res.product_name}!`);
      setBulkLinksText('');
      loadData();
      setTimeout(() => setUploadMsg(''), 4000);
    } catch (err) {
      alert('Error uploading inventory: ' + err.message);
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (id) => {
    if (!confirm('Are you sure you want to delete this link from inventory?')) return;
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
          <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            <Layers className="w-5 h-5 text-emerald-400" />
            Single-Use Invite Links Inventory & Burning Audit
          </h2>
          <p className="text-xs text-slate-400">
            Bulk stock upload and live audit logs of claimed single-use invite links.
          </p>
        </div>

        <button
          onClick={loadData}
          className="p-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl transition-colors text-xs flex items-center gap-1.5 self-start"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          Refresh Stock
        </button>
      </div>

      {/* Bulk Upload Section */}
      <div className="glass-panel rounded-2xl p-5 border border-slate-800">
        <h3 className="text-sm font-bold text-slate-200 mb-2 flex items-center gap-2">
          <Upload className="w-4 h-4 text-teal-400" />
          Bulk Stock Ingestion (Paste Links / Product Keys)
        </h3>
        
        <form onSubmit={handleBulkUpload} className="space-y-3 text-xs">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <label className="block text-slate-400 mb-1 font-medium">Select Target Product *</label>
              <select
                value={selectedProductId}
                onChange={(e) => setSelectedProductId(e.target.value)}
                required
                className="w-full p-2.5 bg-slate-950 border border-slate-800 rounded-xl text-slate-100 focus:outline-none focus:border-teal-500"
              >
                {products.map(p => (
                  <option key={p.id} value={p.id}>
                    {p.name} (Stock: {p.stock_count})
                  </option>
                ))}
              </select>
            </div>

            <div className="sm:col-span-2">
              <label className="block text-slate-400 mb-1 font-medium">
                Paste Invite Links / Keys (1 link per line) *
              </label>
              <textarea
                rows={3}
                placeholder="https://families.google.com/join/invite?token=XXXX1&#10;https://families.google.com/join/invite?token=XXXX2&#10;KEY-8921-VIP-ACCESS"
                value={bulkLinksText}
                onChange={(e) => setBulkLinksText(e.target.value)}
                required
                className="w-full p-2.5 bg-slate-950 border border-slate-800 rounded-xl text-slate-100 font-mono text-[11px] focus:outline-none focus:border-teal-500"
              />
            </div>
          </div>

          <div className="flex items-center justify-between pt-1">
            <span className="text-[11px] text-slate-400">
              {bulkLinksText.split('\n').filter(l => l.trim()).length} link(s) ready to upload
            </span>
            <button
              type="submit"
              disabled={uploading || !bulkLinksText.trim()}
              className="px-4 py-2 bg-gradient-to-r from-teal-600 to-emerald-600 hover:from-teal-500 hover:to-emerald-500 disabled:opacity-50 text-slate-950 font-bold rounded-xl text-xs transition-all shadow-md active:scale-95"
            >
              {uploading ? 'Ingesting Links...' : 'Add Links to Stock'}
            </button>
          </div>
        </form>

        {uploadMsg && (
          <div className="mt-3 p-2.5 bg-emerald-950/80 border border-emerald-500/40 rounded-xl text-xs text-emerald-300 flex items-center gap-2 animate-fadeIn">
            <CheckCircle className="w-4 h-4 text-emerald-400" />
            <span>{uploadMsg}</span>
          </div>
        )}
      </div>

      {/* Filter & Search Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-3 bg-slate-900/60 rounded-xl border border-slate-800/80">
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-slate-400" />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="p-1.5 bg-slate-950 border border-slate-800 rounded-lg text-xs text-slate-300 focus:outline-none"
          >
            <option value="">All Statuses</option>
            <option value="available">Available in Stock</option>
            <option value="claimed">Claimed / Burned</option>
          </select>

          <select
            value={productFilter}
            onChange={(e) => setProductFilter(e.target.value)}
            className="p-1.5 bg-slate-950 border border-slate-800 rounded-lg text-xs text-slate-300 focus:outline-none"
          >
            <option value="">All Products</option>
            {products.map(p => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </div>

        <div className="relative">
          <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2.5" />
          <input
            type="text"
            placeholder="Search link, phone, product..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="pl-8 pr-3 py-1.5 bg-slate-950 border border-slate-800 rounded-lg text-xs text-slate-200 focus:outline-none focus:border-emerald-500 w-56"
          />
        </div>
      </div>

      {/* Links Inventory Table */}
      <div className="glass-panel rounded-2xl overflow-hidden border border-slate-800">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs text-slate-300">
            <thead className="bg-slate-900/90 text-[11px] font-bold text-slate-400 uppercase tracking-wider border-b border-slate-800">
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
                  <td colSpan="7" className="py-8 text-center text-slate-400">Loading inventory records...</td>
                </tr>
              ) : filteredLinks.length === 0 ? (
                <tr>
                  <td colSpan="7" className="py-8 text-center text-slate-400 italic">No matching inventory links found.</td>
                </tr>
              ) : (
                filteredLinks.map((item) => (
                  <tr key={item.id} className="hover:bg-slate-900/40 transition-colors">
                    <td className="py-3 px-4 font-mono text-slate-400">#{item.id}</td>
                    <td className="py-3 px-4 font-semibold text-slate-200">{item.product_name}</td>
                    <td className="py-3 px-4 font-mono text-xs max-w-xs truncate text-emerald-300 select-all">
                      {item.link_or_key}
                    </td>
                    <td className="py-3 px-4">
                      {item.status === 'available' ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-400 border border-emerald-500/30 text-[10px] font-semibold">
                          <CheckCircle className="w-3 h-3" />
                          Available
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-950 text-amber-400 border border-amber-500/30 text-[10px] font-semibold">
                          <Flame className="w-3 h-3 text-amber-400" />
                          Burned / Claimed
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-slate-300">
                      {item.claimed_by_id ? (
                        <div>
                          <span className="capitalize font-medium text-slate-200">
                            {item.claimed_by_type || 'User'}:
                          </span>{' '}
                          <span className="font-mono text-teal-400">{item.claimed_by_id}</span>
                        </div>
                      ) : (
                        <span className="text-slate-400">—</span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-slate-400 text-[11px]">
                      {item.claimed_at ? new Date(item.claimed_at).toLocaleString() : '—'}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <button
                        onClick={() => handleDelete(item.id)}
                        className="p-1 hover:text-rose-400 text-slate-400 transition-colors"
                        title="Delete from stock"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
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
