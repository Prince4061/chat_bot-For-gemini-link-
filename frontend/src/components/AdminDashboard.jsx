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
  ShieldCheck,
  LogOut,
  AlertTriangle,
  Bot,
  Menu
} from 'lucide-react';
import { adminApi } from '../api/client';
import AdminLogin from './AdminLogin';
import ProductManager from './ProductManager';
import InventoryManager from './InventoryManager';
import ResellerManager from './ResellerManager';
import OrderManager from './OrderManager';
import SettingsManager from './SettingsManager';
import EvolutionSimulator from './EvolutionSimulator';
import KnowledgeManager from './KnowledgeManager';

export default function AdminDashboard({ onSwitchToChat, onOpenSidebar }) {
  const [activeTab, setActiveTab] = useState('overview');
  const [metrics, setMetrics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [authed, setAuthed] = useState(adminApi.isLoggedIn());
  const [authRequired, setAuthRequired] = useState(null); // null = still checking

  // On mount, ask the server whether an admin key is even required.
  // If not (no ADMIN_API_KEY set), the dashboard opens straight away - no login.
  useEffect(() => {
    let cancelled = false;
    adminApi.isAuthRequired().then((required) => {
      if (cancelled) return;
      setAuthRequired(required);
      if (!required) setAuthed(true);
    });
    return () => { cancelled = true; };
  }, []);

  // Server rejected the token (expired / rotated) -> back to the login screen.
  useEffect(() => {
    const onUnauthorized = () => { if (authRequired) setAuthed(false); };
    window.addEventListener('admin-unauthorized', onUnauthorized);
    return () => window.removeEventListener('admin-unauthorized', onUnauthorized);
  }, [authRequired]);

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
    if (authed && activeTab === 'overview') {
      loadMetrics();
    }
  }, [activeTab, authed]);

  const handleLogout = () => {
    adminApi.logout();
    setAuthed(false);
  };

  // Still figuring out whether a key is needed - brief neutral screen (usually a flash).
  if (!authed && authRequired === null) {
    return <div className="flex-1 h-screen bg-[#212121]" />;
  }
  if (!authed && authRequired) {
    return <AdminLogin onSuccess={() => setAuthed(true)} onSwitchToChat={onSwitchToChat} />;
  }

  const tabs = [
    { id: 'overview', label: 'Overview', icon: LayoutDashboard },
    { id: 'products', label: 'Products & Margin %', icon: Package },
    { id: 'inventory', label: 'Single-Use Links Stock', icon: Layers },
    { id: 'resellers', label: 'Resellers & Passcodes', icon: Users },
    { id: 'orders', label: 'Customer Orders', icon: ShoppingCart },
    { id: 'training', label: 'AI Training', icon: Sparkles },
    { id: 'evolution', label: 'WhatsApp Simulator', icon: Smartphone },
    { id: 'settings', label: 'Settings & UPI', icon: Settings },
  ];

  return (
    <div className="flex-1 flex flex-col h-[100dvh] bg-[#212121] text-[#ececec] overflow-y-auto">

      {/* Top Admin Header */}
      <header className="h-16 border-b border-white/5 px-3 sm:px-6 flex items-center justify-between bg-[#212121] backdrop-blur-md sticky top-0 z-20 shrink-0">
        <div className="flex items-center gap-2">
          <button
            onClick={onOpenSidebar}
            className="md:hidden p-2 -ml-1 text-[#d4d4d4] hover:text-[#ececec] rounded-lg hover:bg-white/5"
            aria-label="Open menu"
          >
            <Menu className="w-5 h-5" />
          </button>
          <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-white to-white flex items-center justify-center text-black font-bold">
            <LayoutDashboard className="w-4 h-4" />
          </div>
          <div>
            <h1 className="font-bold text-sm text-[#ececec]">Admin</h1>
            <p className="hidden sm:block text-[11px] text-[#8e8ea0]">Inventory, margin & reseller management</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {metrics?.agent && (
            <span
              title={metrics.agent.engine === 'deep_agent' ? `Deep Agent active (${metrics.agent.model})` : 'No OpenAI key - rule-based fallback engine'}
              className={`hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-semibold border ${
                metrics.agent.engine === 'deep_agent'
                  ? 'bg-[#2f2f2f]/70 text-[#ececec] border-white/15'
                  : 'bg-amber-950/70 text-amber-300 border-amber-500/30'
              }`}
            >
              <Bot className="w-3.5 h-3.5" />
              {metrics.agent.engine === 'deep_agent' ? `AI: ${metrics.agent.model}` : 'Fallback engine'}
            </span>
          )}
          <button
            onClick={onSwitchToChat}
            className="px-3.5 py-1.5 bg-[#2f2f2f] hover:bg-[#3a3a3a] border border-white/15 text-[#ececec] text-xs font-semibold rounded-xl transition-colors hidden sm:flex items-center gap-1.5"
          >
            Live Chat
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
          {authRequired && (
            <button
              onClick={handleLogout}
              title="Log out of admin"
              className="p-2 bg-[#2f2f2f] hover:bg-[#3a3a3a] border border-white/15 text-[#8e8ea0] hover:text-rose-400 rounded-xl transition-colors"
            >
              <LogOut className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </header>

      {/* Tabs Navigation */}
      <div className="border-b border-white/5 px-3 sm:px-6 bg-[#212121] sticky top-16 z-10">
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
                    ? 'bg-[#2f2f2f] text-[#ececec] border border-white/15 shadow-sm'
                    : 'text-[#8e8ea0] hover:text-[#ececec] hover:bg-[#2f2f2f]'
                }`}
              >
                <Icon className={`w-3.5 h-3.5 ${isActive ? 'text-[#ececec]' : 'text-[#8e8ea0]'}`} />
                {tab.label}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Tab Content Container */}
      <main className="flex-1 p-4 sm:p-6 max-w-7xl w-full mx-auto">
        
        {/* Tab 1: Overview */}
        {activeTab === 'overview' && (
          <div className="space-y-6">

            {/* Operational alerts */}
            {((metrics?.orders_needing_fulfilment ?? 0) > 0 || (metrics?.low_stock_products?.length ?? 0) > 0) && (
              <div className="glass-panel rounded-2xl p-4 border border-amber-500/30 bg-amber-950/20 text-xs space-y-1.5">
                <div className="flex items-center gap-2 text-amber-300 font-bold uppercase tracking-wider text-[11px]">
                  <AlertTriangle className="w-4 h-4" /> Needs attention
                </div>
                {metrics.orders_needing_fulfilment > 0 && (
                  <button onClick={() => setActiveTab('orders')} className="block text-[#ececec] hover:text-amber-200">
                    • {metrics.orders_needing_fulfilment} paid order(s) waiting for stock — approve after restocking →
                  </button>
                )}
                {metrics.low_stock_products?.map((p) => (
                  <button key={p.id} onClick={() => setActiveTab('inventory')} className="block text-[#ececec] hover:text-amber-200">
                    • Low stock: <span className="font-semibold">{p.name}</span> ({p.stock} left) →
                  </button>
                ))}
              </div>
            )}

            {/* Quick Metrics Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              
              <div className="glass-panel rounded-2xl p-5 border border-white/10 flex items-center justify-between">
                <div>
                  <span className="text-[11px] uppercase font-bold text-[#8e8ea0] tracking-wider block">
                    Available Stock
                  </span>
                  <span className="text-2xl font-bold text-[#ececec] font-mono mt-1 block">
                    {metrics?.available_links ?? 0}
                  </span>
                  <span className="text-[11px] text-[#8e8ea0]">Fresh Single-Use Links</span>
                </div>
                <div className="w-10 h-10 rounded-xl bg-[#2f2f2f] border border-white/15 flex items-center justify-center text-[#ececec]">
                  <CheckCircle2 className="w-5 h-5" />
                </div>
              </div>

              <div className="glass-panel rounded-2xl p-5 border border-white/10 flex items-center justify-between">
                <div>
                  <span className="text-[11px] uppercase font-bold text-[#8e8ea0] tracking-wider block">
                    Burned / Claimed
                  </span>
                  <span className="text-2xl font-bold text-amber-400 font-mono mt-1 block">
                    {metrics?.claimed_links ?? 0}
                  </span>
                  <span className="text-[11px] text-[#8e8ea0]">Locked & Redeemed Links</span>
                </div>
                <div className="w-10 h-10 rounded-xl bg-amber-950/80 border border-amber-500/30 flex items-center justify-center text-amber-400">
                  <Flame className="w-5 h-5" />
                </div>
              </div>

              <div className="glass-panel rounded-2xl p-5 border border-white/10 flex items-center justify-between">
                <div>
                  <span className="text-[11px] uppercase font-bold text-[#8e8ea0] tracking-wider block">
                    Reseller Credits
                  </span>
                  <span className="text-2xl font-bold text-[#ececec] font-mono mt-1 block">
                    {metrics?.total_credits_in_wallets ?? 0}
                  </span>
                  <span className="text-[11px] text-[#8e8ea0]">Across {metrics?.total_resellers ?? 0} Resellers</span>
                </div>
                <div className="w-10 h-10 rounded-xl bg-[#2f2f2f] border border-white/15 flex items-center justify-center text-[#ececec]">
                  <Users className="w-5 h-5" />
                </div>
              </div>

              <div className="glass-panel rounded-2xl p-5 border border-white/10 flex items-center justify-between">
                <div>
                  <span className="text-[11px] uppercase font-bold text-[#8e8ea0] tracking-wider block">
                    Customer Revenue
                  </span>
                  <span className="text-2xl font-bold text-[#ececec] font-mono mt-1 block">
                    ₹{metrics?.total_customer_revenue?.toFixed(2) ?? '0.00'}
                  </span>
                  <span className="text-[11px] text-[#8e8ea0]">From Direct UPI Orders</span>
                </div>
                <div className="w-10 h-10 rounded-xl bg-[#2f2f2f] border border-white/15 flex items-center justify-center text-[#ececec]">
                  <DollarSign className="w-5 h-5" />
                </div>
              </div>

            </div>

            {/* Quick Action Cards & Live Claim Log */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              
              {/* Quick Navigation Cards */}
              <div className="glass-panel rounded-2xl p-5 border border-white/10 space-y-3">
                <h3 className="font-bold text-xs uppercase text-[#8e8ea0] tracking-wider mb-2">Quick Controls</h3>
                
                <div
                  onClick={() => setActiveTab('products')}
                  className="p-3 bg-[#2f2f2f] hover:bg-[#3a3a3a] rounded-xl border border-white/10 cursor-pointer transition-all flex items-center justify-between"
                >
                  <div className="flex items-center gap-2.5">
                    <TrendingUp className="w-4 h-4 text-[#ececec]" />
                    <div>
                      <div className="font-bold text-xs text-[#ececec]">Adjust Live Margin %</div>
                      <div className="text-[11px] text-[#8e8ea0]">Change profit % instantly</div>
                    </div>
                  </div>
                  <ArrowRight className="w-3.5 h-3.5 text-[#8e8ea0]" />
                </div>

                <div
                  onClick={() => setActiveTab('inventory')}
                  className="p-3 bg-[#2f2f2f] hover:bg-[#3a3a3a] rounded-xl border border-white/10 cursor-pointer transition-all flex items-center justify-between"
                >
                  <div className="flex items-center gap-2.5">
                    <Layers className="w-4 h-4 text-[#ececec]" />
                    <div>
                      <div className="font-bold text-xs text-[#ececec]">Bulk Ingest Stock</div>
                      <div className="text-[11px] text-[#8e8ea0]">Paste 50+ invite links</div>
                    </div>
                  </div>
                  <ArrowRight className="w-3.5 h-3.5 text-[#8e8ea0]" />
                </div>

                <div
                  onClick={() => setActiveTab('resellers')}
                  className="p-3 bg-[#2f2f2f] hover:bg-[#3a3a3a] rounded-xl border border-white/10 cursor-pointer transition-all flex items-center justify-between"
                >
                  <div className="flex items-center gap-2.5">
                    <Users className="w-4 h-4 text-[#ececec]" />
                    <div>
                      <div className="font-bold text-xs text-[#ececec]">Top-up Reseller Wallet</div>
                      <div className="text-[11px] text-[#8e8ea0]">Add or deduct credits</div>
                    </div>
                  </div>
                  <ArrowRight className="w-3.5 h-3.5 text-[#8e8ea0]" />
                </div>

                <div
                  onClick={() => setActiveTab('evolution')}
                  className="p-3 bg-[#2f2f2f] hover:bg-[#3a3a3a] rounded-xl border border-white/10 cursor-pointer transition-all flex items-center justify-between"
                >
                  <div className="flex items-center gap-2.5">
                    <Smartphone className="w-4 h-4 text-[#ececec]" />
                    <div>
                      <div className="font-bold text-xs text-[#ececec]">WhatsApp Webhook Test</div>
                      <div className="text-[11px] text-[#8e8ea0]">Simulate incoming WhatsApp</div>
                    </div>
                  </div>
                  <ArrowRight className="w-3.5 h-3.5 text-[#8e8ea0]" />
                </div>
              </div>

              {/* Recent Claim Audit Trail */}
              <div className="lg:col-span-2 glass-panel rounded-2xl p-5 border border-white/10 flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="font-bold text-xs uppercase text-[#8e8ea0] tracking-wider flex items-center gap-1.5">
                      <Flame className="w-3.5 h-3.5 text-amber-400" />
                      Recent Single-Use Link Redemptions & Burns
                    </h3>
                    <button onClick={loadMetrics} className="text-[#8e8ea0] hover:text-[#ececec] p-1">
                      <RefreshCw className="w-3 h-3" />
                    </button>
                  </div>

                  <div className="space-y-2 text-xs">
                    {metrics?.recent_claims?.length === 0 ? (
                      <div className="py-8 text-center text-[#8e8ea0] italic">No links claimed yet.</div>
                    ) : (
                      metrics?.recent_claims?.map((claim) => (
                        <div key={claim.id} className="p-2.5 bg-[#2f2f2f] rounded-xl border border-white/10 flex items-center justify-between">
                          <div>
                            <div className="font-semibold text-[#ececec]">{claim.product_name}</div>
                            <div className="text-[11px] text-[#8e8ea0] font-mono">
                              Claimed by {claim.claimed_by_type}: <span className="text-[#ececec]">{claim.claimed_by_id}</span>
                            </div>
                          </div>
                          <div className="text-right">
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-950 text-amber-400 border border-amber-500/30 text-[10px] font-bold">
                              Burned
                            </span>
                            <div className="text-[10px] text-[#8e8ea0] mt-0.5">
                              {claim.claimed_at ? new Date(claim.claimed_at).toLocaleTimeString() : ''}
                            </div>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>

                <div className="pt-3 border-t border-white/10 text-[11px] text-[#8e8ea0] flex items-center gap-1">
                  <ShieldCheck className="w-3.5 h-3.5 text-[#ececec]" />
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

        {activeTab === 'training' && <KnowledgeManager />}

        {/* Tab 6: Evolution WhatsApp Simulator */}
        {activeTab === 'evolution' && <EvolutionSimulator />}

        {/* Tab 7: Settings */}
        {activeTab === 'settings' && <SettingsManager />}

      </main>

    </div>
  );
}
