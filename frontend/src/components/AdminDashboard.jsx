import React, { useState, useEffect } from 'react';
import { 
  LayoutDashboard, 
  Package, 
  Layers, 
  Users, 
  ShoppingCart, 
  Settings, 
  Smartphone, 
  TrendingUp, 
  CheckCircle2, 
  Flame, 
  CreditCard, 
  DollarSign,
  RefreshCw,
  Sparkles,
  ArrowRight,
  ShieldCheck
} from 'lucide-react';
import { adminApi } from '../api/client';
import ProductManager from './ProductManager';
import InventoryManager from './InventoryManager';
import ResellerManager from './ResellerManager';
import OrderManager from './OrderManager';
import SettingsManager from './SettingsManager';
import EvolutionSimulator from './EvolutionSimulator';

export default function AdminDashboard({ onSwitchToChat }) {
  const [activeTab, setActiveTab] = useState('overview');
  const [metrics, setMetrics] = useState(null);
  const [loading, setLoading] = useState(true);

  const loadMetrics = async () => {
    try {
      setLoading(true);
      const data = await adminApi.getMetrics();
      setMetrics(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'overview') {
      loadMetrics();
    }
  }, [activeTab]);

  const tabs = [
    { id: 'overview', label: 'Overview', icon: LayoutDashboard },
    { id: 'products', label: 'Products & Margin %', icon: Package },
    { id: 'inventory', label: 'Single-Use Links Stock', icon: Layers },
    { id: 'resellers', label: 'Resellers & Passcodes', icon: Users },
    { id: 'orders', label: 'Customer Orders', icon: ShoppingCart },
    { id: 'evolution', label: 'WhatsApp Simulator', icon: Smartphone },
    { id: 'settings', label: 'Settings & UPI', icon: Settings },
  ];

  return (
    <div className="flex-1 flex flex-col h-screen bg-slate-950 text-slate-100 overflow-y-auto">
      
      {/* Top Admin Header */}
      <header className="h-16 border-b border-slate-800/80 px-8 flex items-center justify-between bg-slate-950/90 backdrop-blur-md sticky top-0 z-20 shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-teal-500 to-emerald-400 flex items-center justify-center text-slate-950 font-bold">
            <LayoutDashboard className="w-4 h-4" />
          </div>
          <div>
            <h1 className="font-bold text-sm text-slate-100">Admin Control Center</h1>
            <p className="text-[11px] text-slate-400">Real-Time Inventory, Margin & Reseller Management</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={onSwitchToChat}
            className="px-3.5 py-1.5 bg-slate-900 hover:bg-slate-800 border border-slate-700 text-emerald-400 text-xs font-semibold rounded-xl transition-colors flex items-center gap-1.5"
          >
            Open Live AI Chat
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </header>

      {/* Tabs Navigation */}
      <div className="border-b border-slate-800/80 px-8 bg-slate-950/40 sticky top-16 z-10">
        <nav className="flex space-x-2 overflow-x-auto py-2.5">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold whitespace-nowrap transition-all ${
                  isActive
                    ? 'bg-emerald-950/80 text-emerald-300 border border-emerald-500/40 shadow-sm'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60'
                }`}
              >
                <Icon className={`w-3.5 h-3.5 ${isActive ? 'text-emerald-400' : 'text-slate-400'}`} />
                {tab.label}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Tab Content Container */}
      <main className="flex-1 p-8 max-w-7xl w-full mx-auto">
        
        {/* Tab 1: Overview */}
        {activeTab === 'overview' && (
          <div className="space-y-6">
            
            {/* Quick Metrics Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              
              <div className="glass-panel rounded-2xl p-5 border border-slate-800 flex items-center justify-between">
                <div>
                  <span className="text-[11px] uppercase font-bold text-slate-400 tracking-wider block">
                    Available Stock
                  </span>
                  <span className="text-2xl font-bold text-emerald-400 font-mono mt-1 block">
                    {metrics?.available_links ?? 0}
                  </span>
                  <span className="text-[11px] text-slate-400">Fresh Single-Use Links</span>
                </div>
                <div className="w-10 h-10 rounded-xl bg-emerald-950/80 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
                  <CheckCircle2 className="w-5 h-5" />
                </div>
              </div>

              <div className="glass-panel rounded-2xl p-5 border border-slate-800 flex items-center justify-between">
                <div>
                  <span className="text-[11px] uppercase font-bold text-slate-400 tracking-wider block">
                    Burned / Claimed
                  </span>
                  <span className="text-2xl font-bold text-amber-400 font-mono mt-1 block">
                    {metrics?.claimed_links ?? 0}
                  </span>
                  <span className="text-[11px] text-slate-400">Locked & Redeemed Links</span>
                </div>
                <div className="w-10 h-10 rounded-xl bg-amber-950/80 border border-amber-500/30 flex items-center justify-center text-amber-400">
                  <Flame className="w-5 h-5" />
                </div>
              </div>

              <div className="glass-panel rounded-2xl p-5 border border-slate-800 flex items-center justify-between">
                <div>
                  <span className="text-[11px] uppercase font-bold text-slate-400 tracking-wider block">
                    Reseller Credits
                  </span>
                  <span className="text-2xl font-bold text-teal-400 font-mono mt-1 block">
                    {metrics?.total_credits_in_wallets ?? 0}
                  </span>
                  <span className="text-[11px] text-slate-400">Across {metrics?.total_resellers ?? 0} Resellers</span>
                </div>
                <div className="w-10 h-10 rounded-xl bg-teal-950/80 border border-teal-500/30 flex items-center justify-center text-teal-400">
                  <Users className="w-5 h-5" />
                </div>
              </div>

              <div className="glass-panel rounded-2xl p-5 border border-slate-800 flex items-center justify-between">
                <div>
                  <span className="text-[11px] uppercase font-bold text-slate-400 tracking-wider block">
                    Customer Revenue
                  </span>
                  <span className="text-2xl font-bold text-emerald-400 font-mono mt-1 block">
                    ₹{metrics?.total_customer_revenue?.toFixed(2) ?? '0.00'}
                  </span>
                  <span className="text-[11px] text-slate-400">From Direct UPI Orders</span>
                </div>
                <div className="w-10 h-10 rounded-xl bg-emerald-950/80 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
                  <DollarSign className="w-5 h-5" />
                </div>
              </div>

            </div>

            {/* Quick Action Cards & Live Claim Log */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              
              {/* Quick Navigation Cards */}
              <div className="glass-panel rounded-2xl p-5 border border-slate-800 space-y-3">
                <h3 className="font-bold text-xs uppercase text-slate-400 tracking-wider mb-2">Quick Controls</h3>
                
                <div
                  onClick={() => setActiveTab('products')}
                  className="p-3 bg-slate-900/80 hover:bg-slate-800 rounded-xl border border-slate-800 cursor-pointer transition-all flex items-center justify-between"
                >
                  <div className="flex items-center gap-2.5">
                    <TrendingUp className="w-4 h-4 text-emerald-400" />
                    <div>
                      <div className="font-bold text-xs text-slate-200">Adjust Live Margin %</div>
                      <div className="text-[11px] text-slate-400">Change profit % instantly</div>
                    </div>
                  </div>
                  <ArrowRight className="w-3.5 h-3.5 text-slate-400" />
                </div>

                <div
                  onClick={() => setActiveTab('inventory')}
                  className="p-3 bg-slate-900/80 hover:bg-slate-800 rounded-xl border border-slate-800 cursor-pointer transition-all flex items-center justify-between"
                >
                  <div className="flex items-center gap-2.5">
                    <Layers className="w-4 h-4 text-teal-400" />
                    <div>
                      <div className="font-bold text-xs text-slate-200">Bulk Ingest Stock</div>
                      <div className="text-[11px] text-slate-400">Paste 50+ invite links</div>
                    </div>
                  </div>
                  <ArrowRight className="w-3.5 h-3.5 text-slate-400" />
                </div>

                <div
                  onClick={() => setActiveTab('resellers')}
                  className="p-3 bg-slate-900/80 hover:bg-slate-800 rounded-xl border border-slate-800 cursor-pointer transition-all flex items-center justify-between"
                >
                  <div className="flex items-center gap-2.5">
                    <Users className="w-4 h-4 text-emerald-400" />
                    <div>
                      <div className="font-bold text-xs text-slate-200">Top-up Reseller Wallet</div>
                      <div className="text-[11px] text-slate-400">Add or deduct credits</div>
                    </div>
                  </div>
                  <ArrowRight className="w-3.5 h-3.5 text-slate-400" />
                </div>

                <div
                  onClick={() => setActiveTab('evolution')}
                  className="p-3 bg-slate-900/80 hover:bg-slate-800 rounded-xl border border-slate-800 cursor-pointer transition-all flex items-center justify-between"
                >
                  <div className="flex items-center gap-2.5">
                    <Smartphone className="w-4 h-4 text-teal-400" />
                    <div>
                      <div className="font-bold text-xs text-slate-200">WhatsApp Webhook Test</div>
                      <div className="text-[11px] text-slate-400">Simulate incoming WhatsApp</div>
                    </div>
                  </div>
                  <ArrowRight className="w-3.5 h-3.5 text-slate-400" />
                </div>
              </div>

              {/* Recent Claim Audit Trail */}
              <div className="lg:col-span-2 glass-panel rounded-2xl p-5 border border-slate-800 flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="font-bold text-xs uppercase text-slate-400 tracking-wider flex items-center gap-1.5">
                      <Flame className="w-3.5 h-3.5 text-amber-400" />
                      Recent Single-Use Link Redemptions & Burns
                    </h3>
                    <button onClick={loadMetrics} className="text-slate-400 hover:text-slate-200 p-1">
                      <RefreshCw className="w-3 h-3" />
                    </button>
                  </div>

                  <div className="space-y-2 text-xs">
                    {metrics?.recent_claims?.length === 0 ? (
                      <div className="py-8 text-center text-slate-400 italic">No links claimed yet.</div>
                    ) : (
                      metrics?.recent_claims?.map((claim) => (
                        <div key={claim.id} className="p-2.5 bg-slate-900/80 rounded-xl border border-slate-800/80 flex items-center justify-between">
                          <div>
                            <div className="font-semibold text-slate-200">{claim.product_name}</div>
                            <div className="text-[11px] text-slate-400 font-mono">
                              Claimed by {claim.claimed_by_type}: <span className="text-teal-400">{claim.claimed_by_id}</span>
                            </div>
                          </div>
                          <div className="text-right">
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-950 text-amber-400 border border-amber-500/30 text-[10px] font-bold">
                              Burned
                            </span>
                            <div className="text-[10px] text-slate-400 mt-0.5">
                              {claim.claimed_at ? new Date(claim.claimed_at).toLocaleTimeString() : ''}
                            </div>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>

                <div className="pt-3 border-t border-slate-800 text-[11px] text-slate-400 flex items-center gap-1">
                  <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                  Each invite link is guaranteed single-use and permanently removed from stock upon claim.
                </div>
              </div>

            </div>

          </div>
        )}

        {/* Tab 2: Products */}
        {activeTab === 'products' && <ProductManager />}

        {/* Tab 3: Inventory */}
        {activeTab === 'inventory' && <InventoryManager />}

        {/* Tab 4: Resellers */}
        {activeTab === 'resellers' && <ResellerManager />}

        {/* Tab 5: Orders */}
        {activeTab === 'orders' && <OrderManager />}

        {/* Tab 6: Evolution WhatsApp Simulator */}
        {activeTab === 'evolution' && <EvolutionSimulator />}

        {/* Tab 7: Settings */}
        {activeTab === 'settings' && <SettingsManager />}

      </main>

    </div>
  );
}
