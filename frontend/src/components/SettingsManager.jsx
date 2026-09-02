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
  const [saveError, setSaveError] = useState('');
  // Secrets come back masked ("••••abcd"); we only send them if the admin typed a new value.
  const [newOpenaiKey, setNewOpenaiKey] = useState('');
  const [newEvolutionKey, setNewEvolutionKey] = useState('');
  const [llmTest, setLlmTest] = useState(null);
  const [testing, setTesting] = useState(false);

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
      setSaveError('');
      const payload = { ...settings };
      delete payload.openai_api_key;
      delete payload.evolution_api_key;
      delete payload.has_openai_key;
      if (newOpenaiKey.trim()) payload.openai_api_key = newOpenaiKey.trim();
      if (newEvolutionKey.trim()) payload.evolution_api_key = newEvolutionKey.trim();
      const saved = await adminApi.updateSettings(payload);
      setSettings(saved);
      setNewOpenaiKey('');
      setNewEvolutionKey('');
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err) {
      setSaveError('Failed to save settings: ' + err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleTestLlm = async () => {
    try {
      setTesting(true);
      setLlmTest(null);
      const res = await adminApi.testLlm();
      setLlmTest(res);
    } catch (err) {
      setLlmTest({ ok: false, error: err.message });
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="space-y-6">
      
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-[#ececec] flex items-center gap-2">
            <Settings className="w-5 h-5 text-[#ececec]" />
            System & Gateway Configuration
          </h2>
          <p className="text-xs text-[#8e8ea0]">
            Configure Admin UPI payment details, OpenAI credentials, and Evolution API parameters.
          </p>
        </div>

        {saveSuccess && (
          <span className="text-xs text-[#ececec] font-semibold flex items-center gap-1.5 animate-fadeIn">
            <Check className="w-4 h-4" />
            Saved successfully!
          </span>
        )}
        {saveError && <span className="text-xs text-rose-400 font-semibold">{saveError}</span>}
      </div>

      <form onSubmit={handleSave} className="space-y-5">
        
        {/* UPI & Payment Settings */}
        <div className="glass-panel rounded-2xl p-5 border border-white/10 space-y-4">
          <h3 className="text-sm font-bold text-[#ececec] flex items-center gap-2">
            <QrCode className="w-4 h-4 text-[#ececec]" />
            Admin UPI Payment Gateway
          </h3>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
            <div>
              <label className="block text-[#8e8ea0] mb-1 font-medium">Business / Bot Name</label>
              <input
                type="text"
                value={settings.business_name || ''}
                onChange={(e) => setSettings({ ...settings, business_name: e.target.value })}
                className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] focus:outline-none focus:border-white/15"
              />
            </div>

            <div>
              <label className="block text-[#8e8ea0] mb-1 font-medium">Admin UPI ID (GPay/PhonePe/Paytm)</label>
              <input
                type="text"
                value={settings.admin_upi_id || ''}
                onChange={(e) => setSettings({ ...settings, admin_upi_id: e.target.value })}
                placeholder="e.g. resellerpay@upi"
                className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] font-mono focus:outline-none focus:border-white/15"
              />
            </div>

            <div>
              <label className="block text-[#8e8ea0] mb-1 font-medium">Payee Display Name</label>
              <input
                type="text"
                value={settings.admin_upi_name || ''}
                onChange={(e) => setSettings({ ...settings, admin_upi_name: e.target.value })}
                className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] focus:outline-none focus:border-white/15"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
            <div>
              <label className="block text-[#8e8ea0] mb-1 font-medium">Reseller Credit Unit Price (₹)</label>
              <input
                type="number"
                step="0.01"
                value={settings.reseller_credit_rate_inr || 150}
                onChange={(e) => setSettings({ ...settings, reseller_credit_rate_inr: parseFloat(e.target.value) || 0 })}
                className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] font-mono focus:outline-none focus:border-white/15"
              />
              <span className="text-[11px] text-[#8e8ea0] mt-1 block">Base cost: 1 Credit = ₹{settings.reseller_credit_rate_inr}</span>
            </div>

            <div>
              <label className="block text-[#8e8ea0] mb-1 font-medium">Reseller Terms & Bulk Packs Text</label>
              <textarea
                rows={2}
                value={settings.reseller_terms || ''}
                onChange={(e) => setSettings({ ...settings, reseller_terms: e.target.value })}
                className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] focus:outline-none focus:border-white/15"
              />
            </div>
          </div>
        </div>

        {/* AI Model & OpenAI API Configuration */}
        <div className="glass-panel rounded-2xl p-5 border border-white/10 space-y-4">
          <h3 className="text-sm font-bold text-[#ececec] flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-[#ececec]" />
            OpenAI & Deep Agent LLM Settings
          </h3>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
            <div>
              <label className="block text-[#8e8ea0] mb-1 font-medium">
                OpenAI API Key{' '}
                {settings.openai_api_key && (
                  <span className="text-[#ececec] font-mono">(saved: {settings.openai_api_key})</span>
                )}
              </label>
              <input
                type="password"
                placeholder={settings.openai_api_key ? 'Enter a new key to replace' : 'sk-proj-...'}
                value={newOpenaiKey}
                onChange={(e) => setNewOpenaiKey(e.target.value)}
                autoComplete="new-password"
                className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] font-mono focus:outline-none focus:border-white/15"
              />
              <span className="text-[11px] text-[#8e8ea0] mt-1 block">
                Leave blank to keep the saved key (or the `OPENAI_API_KEY` environment variable).
              </span>
            </div>

            <div>
              <label className="block text-[#8e8ea0] mb-1 font-medium">OpenAI Model Name</label>
              <select
                value={settings.openai_model_name || 'gpt-4o-mini'}
                onChange={(e) => setSettings({ ...settings, openai_model_name: e.target.value })}
                className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] focus:outline-none focus:border-white/15"
              >
                <option value="gpt-4o-mini">gpt-4o-mini (Fast, Efficient & Cost-effective)</option>
                <option value="gpt-4o">gpt-4o (High Reasoning & Multi-step Planning)</option>
                <option value="gpt-4.1-mini">gpt-4.1-mini</option>
                <option value="gpt-4.1">gpt-4.1</option>
                <option value="chatgpt-4o-latest">chatgpt-4o-latest</option>
              </select>
            </div>
          </div>

          <div className="flex items-center gap-3 text-xs">
            <button
              type="button"
              onClick={handleTestLlm}
              disabled={testing}
              className="px-3.5 py-2 bg-[#2f2f2f] hover:bg-[#3a3a3a] border border-white/15 text-[#ececec] font-semibold rounded-xl transition-colors disabled:opacity-50"
            >
              {testing ? 'Testing…' : 'Test LLM connection'}
            </button>
            {llmTest && (
              <span className={llmTest.ok ? 'text-[#ececec]' : 'text-rose-400'}>
                {llmTest.ok ? `✓ Connected to ${llmTest.model}` : `✗ ${llmTest.error}`}
              </span>
            )}
            {!settings.has_openai_key && (
              <span className="text-amber-400">No key saved — the bot runs on the rule-based fallback engine.</span>
            )}
          </div>
        </div>

        {/* Evolution API (WhatsApp) Webhook Parameters */}
        <div className="glass-panel rounded-2xl p-5 border border-white/10 space-y-4">
          <h3 className="text-sm font-bold text-[#ececec] flex items-center gap-2">
            <Smartphone className="w-4 h-4 text-[#ececec]" />
            Evolution API (WhatsApp) Gateway Settings
          </h3>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
            <div>
              <label className="block text-[#8e8ea0] mb-1 font-medium">Evolution API URL</label>
              <input
                type="text"
                placeholder="http://localhost:8080"
                value={settings.evolution_api_url || ''}
                onChange={(e) => setSettings({ ...settings, evolution_api_url: e.target.value })}
                className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] font-mono focus:outline-none focus:border-white/15"
              />
            </div>

            <div>
              <label className="block text-[#8e8ea0] mb-1 font-medium">
                Evolution API Key{' '}
                {settings.evolution_api_key && (
                  <span className="text-[#ececec] font-mono">(saved: {settings.evolution_api_key})</span>
                )}
              </label>
              <input
                type="password"
                placeholder={settings.evolution_api_key ? 'Enter a new key to replace' : 'Evolution API global key'}
                value={newEvolutionKey}
                onChange={(e) => setNewEvolutionKey(e.target.value)}
                autoComplete="new-password"
                className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] font-mono focus:outline-none focus:border-white/15"
              />
            </div>

            <div>
              <label className="block text-[#8e8ea0] mb-1 font-medium">Instance Name</label>
              <input
                type="text"
                placeholder="VendingBot"
                value={settings.evolution_instance_name || ''}
                onChange={(e) => setSettings({ ...settings, evolution_instance_name: e.target.value })}
                className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] font-mono focus:outline-none focus:border-white/15"
              />
            </div>
          </div>

          <div className="p-3 bg-[#212121] rounded-xl border border-white/10 text-[11px] text-[#8e8ea0] space-y-1">
            <p className="font-semibold text-[#d4d4d4]">🔗 Webhook Endpoint URL to paste into Evolution API Manager:</p>
            <code className="text-[#ececec] bg-[#2f2f2f] px-2 py-1 rounded block font-mono">
              https://YOUR_DOMAIN/api/webhook/evolution?token=EVOLUTION_WEBHOOK_SECRET
            </code>
            <p>Events to subscribe: <code>MESSAGES_UPSERT</code>. Set <code>EVOLUTION_WEBHOOK_SECRET</code> in <code>.env</code> so only Evolution can call the webhook.</p>
          </div>
        </div>

        {/* Submit Bar */}
        <div className="flex justify-end">
          <button
            type="submit"
            disabled={saving}
            className="px-6 py-2.5 bg-gradient-to-r from-white to-white hover:from-white hover:to-white text-black font-bold rounded-xl text-xs transition-all shadow-lg active:scale-95 flex items-center gap-2"
          >
            <Save className="w-4 h-4" />
            {saving ? 'Saving...' : 'Save Configuration'}
          </button>
        </div>

      </form>
    </div>
  );
}
