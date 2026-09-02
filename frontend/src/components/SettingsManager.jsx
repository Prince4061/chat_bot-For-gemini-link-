import React, { useState, useEffect } from 'react';
import { 
  Settings, 
  Save, 
  Check, 
  QrCode, 
  Smartphone, 
  Key, 
  ShieldCheck, 
  DollarSign, 
  MessageSquare,
  Sparkles
} from 'lucide-react';
import { adminApi } from '../api/client';

export default function SettingsManager() {
  const [settings, setSettings] = useState({
    business_name: '',
    admin_upi_id: '',
    admin_upi_name: '',
    reseller_credit_rate_inr: 150,
    reseller_terms: '',
    evolution_api_url: '',
    evolution_api_key: '',
    evolution_instance_name: '',
    openai_api_key: '',
    openai_model_name: 'gpt-4o-mini'
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  const loadSettings = async () => {
    try {
      setLoading(true);
      const data = await adminApi.getSettings();
      setSettings(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSettings();
  }, []);

  const handleSave = async (e) => {
    e.preventDefault();
    try {
      setSaving(true);
      await adminApi.updateSettings(settings);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err) {
      alert('Failed to save settings: ' + err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            <Settings className="w-5 h-5 text-emerald-400" />
            System & Gateway Configuration
          </h2>
          <p className="text-xs text-slate-400">
            Configure Admin UPI payment details, OpenAI credentials, and Evolution API parameters.
          </p>
        </div>

        {saveSuccess && (
          <span className="text-xs text-emerald-400 font-semibold flex items-center gap-1.5 animate-fadeIn">
            <Check className="w-4 h-4" />
            Saved successfully!
          </span>
        )}
      </div>

      <form onSubmit={handleSave} className="space-y-5">
        
        {/* UPI & Payment Settings */}
        <div className="glass-panel rounded-2xl p-5 border border-slate-800 space-y-4">
          <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2">
            <QrCode className="w-4 h-4 text-emerald-400" />
            Admin UPI Payment Gateway
          </h3>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
            <div>
              <label className="block text-slate-400 mb-1 font-medium">Business / Bot Name</label>
              <input
                type="text"
                value={settings.business_name || ''}
                onChange={(e) => setSettings({ ...settings, business_name: e.target.value })}
                className="w-full p-2.5 bg-slate-950 border border-slate-800 rounded-xl text-slate-100 focus:outline-none focus:border-emerald-500"
              />
            </div>

            <div>
              <label className="block text-slate-400 mb-1 font-medium">Admin UPI ID (GPay/PhonePe/Paytm)</label>
              <input
                type="text"
                value={settings.admin_upi_id || ''}
                onChange={(e) => setSettings({ ...settings, admin_upi_id: e.target.value })}
                placeholder="e.g. resellerpay@upi"
                className="w-full p-2.5 bg-slate-950 border border-slate-800 rounded-xl text-slate-100 font-mono focus:outline-none focus:border-emerald-500"
              />
            </div>

            <div>
              <label className="block text-slate-400 mb-1 font-medium">Payee Display Name</label>
              <input
                type="text"
                value={settings.admin_upi_name || ''}
                onChange={(e) => setSettings({ ...settings, admin_upi_name: e.target.value })}
                className="w-full p-2.5 bg-slate-950 border border-slate-800 rounded-xl text-slate-100 focus:outline-none focus:border-emerald-500"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
            <div>
              <label className="block text-slate-400 mb-1 font-medium">Reseller Credit Unit Price (₹)</label>
              <input
                type="number"
                step="0.01"
                value={settings.reseller_credit_rate_inr || 150}
                onChange={(e) => setSettings({ ...settings, reseller_credit_rate_inr: parseFloat(e.target.value) || 0 })}
                className="w-full p-2.5 bg-slate-950 border border-slate-800 rounded-xl text-slate-100 font-mono focus:outline-none focus:border-emerald-500"
              />
              <span className="text-[11px] text-slate-400 mt-1 block">Base cost: 1 Credit = ₹{settings.reseller_credit_rate_inr}</span>
            </div>

            <div>
              <label className="block text-slate-400 mb-1 font-medium">Reseller Terms & Bulk Packs Text</label>
              <textarea
                rows={2}
                value={settings.reseller_terms || ''}
                onChange={(e) => setSettings({ ...settings, reseller_terms: e.target.value })}
                className="w-full p-2.5 bg-slate-950 border border-slate-800 rounded-xl text-slate-100 focus:outline-none focus:border-emerald-500"
              />
            </div>
          </div>
        </div>

        {/* AI Model & OpenAI API Configuration */}
        <div className="glass-panel rounded-2xl p-5 border border-slate-800 space-y-4">
          <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-emerald-400" />
            OpenAI & Deep Agent LLM Settings
          </h3>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
            <div>
              <label className="block text-slate-400 mb-1 font-medium">OpenAI API Key</label>
              <input
                type="password"
                placeholder="sk-proj-..."
                value={settings.openai_api_key || ''}
                onChange={(e) => setSettings({ ...settings, openai_api_key: e.target.value })}
                className="w-full p-2.5 bg-slate-950 border border-slate-800 rounded-xl text-slate-100 font-mono focus:outline-none focus:border-emerald-500"
              />
              <span className="text-[11px] text-slate-400 mt-1 block">
                Leave blank to use environment variable `OPENAI_API_KEY`.
              </span>
            </div>

            <div>
              <label className="block text-slate-400 mb-1 font-medium">OpenAI Model Name</label>
              <select
                value={settings.openai_model_name || 'gpt-4o-mini'}
                onChange={(e) => setSettings({ ...settings, openai_model_name: e.target.value })}
                className="w-full p-2.5 bg-slate-950 border border-slate-800 rounded-xl text-slate-100 focus:outline-none focus:border-emerald-500"
              >
                <option value="gpt-4o-mini">gpt-4o-mini (Fast, Efficient & Cost-effective)</option>
                <option value="gpt-4o">gpt-4o (High Reasoning & Multi-step Planning)</option>
                <option value="chatgpt-4o-latest">chatgpt-4o-latest</option>
              </select>
            </div>
          </div>
        </div>

        {/* Evolution API (WhatsApp) Webhook Parameters */}
        <div className="glass-panel rounded-2xl p-5 border border-slate-800 space-y-4">
          <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2">
            <Smartphone className="w-4 h-4 text-teal-400" />
            Evolution API (WhatsApp) Gateway Settings
          </h3>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
            <div>
              <label className="block text-slate-400 mb-1 font-medium">Evolution API URL</label>
              <input
                type="text"
                placeholder="http://localhost:8080"
                value={settings.evolution_api_url || ''}
                onChange={(e) => setSettings({ ...settings, evolution_api_url: e.target.value })}
                className="w-full p-2.5 bg-slate-950 border border-slate-800 rounded-xl text-slate-100 font-mono focus:outline-none focus:border-teal-500"
              />
            </div>

            <div>
              <label className="block text-slate-400 mb-1 font-medium">Evolution API Key</label>
              <input
                type="password"
                value={settings.evolution_api_key || ''}
                onChange={(e) => setSettings({ ...settings, evolution_api_key: e.target.value })}
                className="w-full p-2.5 bg-slate-950 border border-slate-800 rounded-xl text-slate-100 font-mono focus:outline-none focus:border-teal-500"
              />
            </div>

            <div>
              <label className="block text-slate-400 mb-1 font-medium">Instance Name</label>
              <input
                type="text"
                placeholder="VendingBot"
                value={settings.evolution_instance_name || ''}
                onChange={(e) => setSettings({ ...settings, evolution_instance_name: e.target.value })}
                className="w-full p-2.5 bg-slate-950 border border-slate-800 rounded-xl text-slate-100 font-mono focus:outline-none focus:border-teal-500"
              />
            </div>
          </div>

          <div className="p-3 bg-slate-950/80 rounded-xl border border-slate-800 text-[11px] text-slate-400 space-y-1">
            <p className="font-semibold text-slate-300">🔗 Webhook Endpoint URL to paste into Evolution API Manager:</p>
            <code className="text-emerald-400 bg-slate-900 px-2 py-1 rounded block font-mono">
              http://YOUR_SERVER_IP:5000/api/webhook/evolution
            </code>
            <p>Events to subscribe: <code>MESSAGES_UPSERT</code></p>
          </div>
        </div>

        {/* Submit Bar */}
        <div className="flex justify-end">
          <button
            type="submit"
            disabled={saving}
            className="px-6 py-2.5 bg-gradient-to-r from-emerald-600 to-teal-500 hover:from-emerald-500 hover:to-teal-400 text-slate-950 font-bold rounded-xl text-xs transition-all shadow-lg active:scale-95 flex items-center gap-2"
          >
            <Save className="w-4 h-4" />
            {saving ? 'Saving...' : 'Save Configuration'}
          </button>
        </div>

      </form>
    </div>
  );
}
