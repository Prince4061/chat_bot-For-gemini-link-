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
    admin_contact_number: '',
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

  // --- Google Link Checker (logged-in headless browser) ---
  const [gc, setGc] = useState(null);            // status object
  const [gcSession, setGcSession] = useState(''); // pasted google_session.json / cookie export
  const [gcBusy, setGcBusy] = useState('');
  const [gcMsg, setGcMsg] = useState(null);      // {ok, text}
  const [gcTestUrl, setGcTestUrl] = useState('');
  const [gcTest, setGcTest] = useState(null);
  const [gcShot, setGcShot] = useState(null);      // object URL of the last screenshot

  const loadChecker = async () => {
    try { setGc(await adminApi.googleCheckerStatus()); } catch (err) { console.error(err); }
  };
  useEffect(() => { loadChecker(); }, []);

  const gcConnect = async () => {
    if (!gcSession.trim()) return;
    let parsed;
    try { parsed = JSON.parse(gcSession); } catch { setGcMsg({ ok: false, text: 'Ye valid JSON nahi hai — google_session.json ka poora content paste karo.' }); return; }
    try {
      setGcBusy('connect'); setGcMsg(null);
      const res = await adminApi.googleCheckerConnect(parsed);
      const v = res.verification;
      setGcMsg({ ok: !v || v.status === 'logged_in', text: v ? (v.status === 'logged_in' ? `✅ Connected — Google session kaam kar raha hai (${res.saved.cookies} cookies).` : `Saved, par verify: ${v.status} — ${v.reason}`) : `Saved (${res.saved.cookies} cookies). Server par playwright install nahi hai, verify baad me hoga.` });
      setGcSession('');
      setGc(res.status);
    } catch (err) { setGcMsg({ ok: false, text: 'Error: ' + err.message }); }
    finally { setGcBusy(''); }
  };

  const gcVerify = async () => {
    try { setGcBusy('verify'); setGcMsg(null); const res = await adminApi.googleCheckerVerify(); setGc(res.status);
      setGcMsg({ ok: res.result.status === 'logged_in', text: `${res.result.status}: ${res.result.reason}` }); }
    catch (err) { setGcMsg({ ok: false, text: 'Error: ' + err.message }); }
    finally { setGcBusy(''); }
  };

  const gcDisconnect = async () => {
    if (!confirm('Google checker session disconnect karein? (Gemini links phir verify nahi hongi)')) return;
    try { const res = await adminApi.googleCheckerDisconnect(); setGc(res.status); setGcMsg({ ok: true, text: 'Disconnected.' }); }
    catch (err) { setGcMsg({ ok: false, text: 'Error: ' + err.message }); }
  };

  const gcRunTest = async () => {
    if (!gcTestUrl.trim()) return;
    try {
      setGcBusy('test'); setGcTest(null);
      if (gcShot) { URL.revokeObjectURL(gcShot); setGcShot(null); }
      const res = await adminApi.googleCheckerTest(gcTestUrl.trim());
      setGcTest(res.result); setGc(res.status);
      if (res.result?.screenshot) {
        try { setGcShot(await adminApi.googleCheckerScreenshot()); } catch { /* no screenshot */ }
      }
    }
    catch (err) { setGcTest({ status: 'error', reason: err.response?.data?.error || err.message }); }
    finally { setGcBusy(''); }
  };

  const gcToggle = async (val) => {
    try { const saved = await adminApi.updateSettings({ google_checker_enabled: val }); setSettings(saved); loadChecker(); }
    catch (err) { alert('Error: ' + err.message); }
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
              <label className="block text-[#8e8ea0] mb-1 font-medium">Admin Contact Number (for new resellers)</label>
              <input
                type="text"
                value={settings.admin_contact_number || ''}
                onChange={(e) => setSettings({ ...settings, admin_contact_number: e.target.value })}
                placeholder="e.g. +91 98765 43210"
                className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] font-mono focus:outline-none focus:border-white/15"
              />
              <span className="text-[11px] text-[#8e8ea0] mt-1 block">
                Unregistered WhatsApp users ko bot yahi number deta hai — "yahan baat karke pay karke credits lo".
              </span>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
            <div>
              <label className="block text-[#8e8ea0] mb-1 font-medium">Minimum Wallet Top-up (₹)</label>
              <input
                type="number"
                step="0.01"
                value={settings.reseller_credit_rate_inr || 150}
                onChange={(e) => setSettings({ ...settings, reseller_credit_rate_inr: parseFloat(e.target.value) || 0 })}
                className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] font-mono focus:outline-none focus:border-white/15"
              />
              <span className="text-[11px] text-[#8e8ea0] mt-1 block">Bot naye resellers ko yahi minimum top-up batata hai.</span>

              <label className="block text-[#8e8ea0] mb-1 mt-3 font-medium">USD → INR rate (USD wallets ke liye)</label>
              <input
                type="number"
                step="0.01"
                value={settings.usd_to_inr_rate || 83}
                onChange={(e) => setSettings({ ...settings, usd_to_inr_rate: parseFloat(e.target.value) || 0 })}
                className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] font-mono focus:outline-none focus:border-white/15"
              />
              <span className="text-[11px] text-[#8e8ea0] mt-1 block">1 USD = ₹{settings.usd_to_inr_rate || 83}. USD-wallet reseller se INR product price isi rate se convert hoke katega.</span>
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

        {/* Google Link Checker — logged-in headless browser reads Google's used/fresh page */}
        <div className="glass-panel rounded-2xl p-5 border border-white/10 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-sm font-bold text-[#ececec] flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-[#ececec]" />
              Google Link Checker (Gemini links fresh/used)
            </h3>
            {gc && (
              <div className="flex items-center gap-2 text-[11px]">
                <span className={`px-2 py-0.5 rounded-full border ${gc.installed && gc.browser_ok ? 'bg-[#2f2f2f] text-[#ececec] border-white/15' : 'bg-rose-950/40 text-rose-300 border-rose-500/30'}`}
                  title={gc.installed && !gc.browser_ok ? 'Server par chalao: python3 -m playwright install --with-deps chromium' : ''}>
                  {gc.installed ? (gc.browser_ok ? 'Chromium ✓' : 'Chromium missing') : 'Playwright missing'}
                </span>
                <span className={`px-2 py-0.5 rounded-full border ${gc.session_present ? (gc.logged_in === false ? 'bg-amber-950/40 text-amber-300 border-amber-500/30' : 'bg-emerald-950/40 text-emerald-300 border-emerald-500/30') : 'bg-[#3a3a3a] text-[#8e8ea0] border-white/10'}`}>
                  {gc.session_present ? (gc.logged_in === false ? 'Session expired' : gc.logged_in ? 'Connected' : 'Session saved') : 'Not connected'}
                </span>
                <label className="flex items-center gap-1 text-[#8e8ea0] cursor-pointer">
                  <input type="checkbox" checked={settings.google_checker_enabled !== false} onChange={(e) => gcToggle(e.target.checked)} />
                  enabled
                </label>
              </div>
            )}
          </div>

          <p className="text-[11px] text-[#8e8ea0] leading-relaxed">
            Google bina login ke fresh/used nahi batata. Ye checker ek <strong className="text-[#ececec]">alag (throwaway) Google account</strong> ke logged-in
            session se link kholta hai, sirf page <em>padhta</em> hai (Activate kabhi click nahi karta — isliye link consume nahi hoti), aur
            "already used / expired" mile to us link ko skip karke agli fresh link deta hai.
          </p>

          <div className="p-3 bg-[#212121] rounded-xl border border-white/10 text-[11px] text-[#d4d4d4] space-y-1">
            <div className="font-semibold text-[#ececec]">Connect karne ke 3 steps</div>
            <div>1. Ek naya Gmail banao jisme <strong>Google One / Gemini plan na ho</strong> (main business Gmail mat use karo).</div>
            <div>2. Apne PC par project folder me chalao: <code className="text-[#ececec] bg-black/30 px-1 rounded">pip install playwright</code>, <code className="text-[#ececec] bg-black/30 px-1 rounded">playwright install chromium</code>, phir <code className="text-[#ececec] bg-black/30 px-1 rounded">python google_checker.py login</code> → Chrome khulega, us account se sign in karo, Enter dabao → <code className="text-[#ececec] bg-black/30 px-1 rounded">google_session.json</code> banega.</div>
            <div>3. Us file ka poora content neeche paste karke <strong>Connect</strong> dabao. (Cookie-Editor extension ka cookie export bhi chalta hai.)</div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 text-xs">
            <div>
              <label className="block text-[#8e8ea0] mb-1 font-medium">google_session.json ka content</label>
              <textarea
                rows={5}
                value={gcSession}
                onChange={(e) => setGcSession(e.target.value)}
                placeholder='{"cookies":[{"name":"SID","value":"…","domain":".google.com",…}], "origins":[]}'
                className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] font-mono text-[11px] focus:outline-none focus:border-white/20"
              />
              <div className="flex flex-wrap items-center gap-2 mt-2">
                <button type="button" onClick={gcConnect} disabled={gcBusy !== '' || !gcSession.trim()}
                  className="px-4 py-2 bg-white hover:bg-white/90 text-black font-bold rounded-xl disabled:opacity-50">
                  {gcBusy === 'connect' ? 'Connecting…' : 'Connect'}
                </button>
                <button type="button" onClick={gcVerify} disabled={gcBusy !== '' || !gc?.session_present}
                  className="px-3 py-2 bg-[#3a3a3a] hover:bg-[#4a4a4a] text-[#d4d4d4] rounded-xl disabled:opacity-50">
                  {gcBusy === 'verify' ? 'Checking…' : 'Verify session'}
                </button>
                {gc?.session_present && (
                  <button type="button" onClick={gcDisconnect} className="px-3 py-2 text-rose-300 hover:bg-rose-950/40 rounded-xl">Disconnect</button>
                )}
              </div>
              {gcMsg && <div className={`mt-2 text-[11px] ${gcMsg.ok ? 'text-emerald-300' : 'text-rose-300'}`}>{gcMsg.text}</div>}
              {gc && (
                <div className="mt-2 text-[10px] text-[#8e8ea0]">
                  Last check: {gc.last_check_at || '—'} · result: {gc.last_status || '—'} · this hour: {gc.checks_this_hour}/{gc.max_per_hour}
                  {gc.last_error && <span className="text-amber-300"> · {gc.last_error}</span>}
                </div>
              )}
            </div>

            <div>
              <label className="block text-[#8e8ea0] mb-1 font-medium">Test — ek Gemini link paste karo (sirf padhega, activate nahi karega)</label>
              <div className="flex items-center gap-2">
                <input value={gcTestUrl} onChange={(e) => setGcTestUrl(e.target.value)} placeholder="https://one.google.com/activate-plan/subscription/new/…"
                  className="flex-1 p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] font-mono text-[11px] focus:outline-none focus:border-white/20" />
                <button type="button" onClick={gcRunTest} disabled={gcBusy !== '' || !gcTestUrl.trim() || !gc?.installed}
                  className="px-3 py-2 bg-[#3a3a3a] hover:bg-[#4a4a4a] text-[#d4d4d4] rounded-xl disabled:opacity-50">
                  {gcBusy === 'test' ? 'Checking…' : 'Check'}
                </button>
              </div>
              {gcTest && (
                <div className="mt-2 p-2.5 rounded-xl bg-[#212121] border border-white/10 text-[11px] space-y-1">
                  <div>
                    Result: <span className={`font-bold ${gcTest.status === 'fresh' ? 'text-emerald-300' : (gcTest.status === 'used' || gcTest.status === 'expired') ? 'text-rose-300' : 'text-amber-300'}`}>{gcTest.status?.toUpperCase()}</span>
                    <span className="text-[#8e8ea0]"> — {gcTest.reason}</span>
                  </div>
                  {gcTest.snippet && <div className="text-[#8e8ea0] break-words">“{gcTest.snippet.slice(0, 220)}”</div>}
                  {gcShot && <img alt="page" src={gcShot} className="mt-1 rounded-lg border border-white/10 max-h-56" />}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Auto-buy suppliers — bot buys from the CHEAPEST mapped supplier on demand */}
        <SupplierCard
          label="m00nshots Auto-Buy Supplier" keyField="moonshots_api_key" enabledField="moonshots_enabled"
          statusFn={adminApi.moonshotsStatus} productsFn={adminApi.moonshotsProducts}
          settings={settings} setSettings={setSettings} keyPlaceholder="mk_..." idLabel="ID"
          desc="Telegram bot ka /api command se key milti hai. Prices USD me hain (Settings ke USD→INR rate se ₹ me compare hota hai)."
        />
        <SupplierCard
          label="Loot Paglu Auto-Buy Supplier" keyField="lootpaglu_api_key" enabledField="lootpaglu_enabled"
          statusFn={adminApi.lootpagluStatus} productsFn={adminApi.lootpagluProducts}
          settings={settings} setSettings={setSettings} keyPlaceholder="LootPaglu_..." idLabel="service id"
          desc="lootpaglu.in ka X-API-Key. Prices seedha ₹ me. Ek hi product dono suppliers pe ho to bot jo sasta hai wahi se kharidta hai (Products tab me dono IDs map karo)."
        />

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


// One card per auto-buy supplier: API key, enable toggle, live balance, catalogue browser.
function SupplierCard({ label, keyField, enabledField, statusFn, productsFn, settings, setSettings, keyPlaceholder, idLabel, desc }) {
  const [st, setSt] = useState(null);
  const [key, setKey] = useState('');
  const [busy, setBusy] = useState('');
  const [msg, setMsg] = useState(null);
  const [search, setSearch] = useState('');
  const [items, setItems] = useState(null);

  const load = async () => { try { setSt(await statusFn()); } catch (err) { console.error(err); } };
  useEffect(() => { load(); }, []);   // eslint-disable-line react-hooks/exhaustive-deps

  const saveKey = async () => {
    if (!key.trim()) return;
    try {
      setBusy('key'); setMsg(null);
      const saved = await adminApi.updateSettings({ [keyField]: key.trim() });
      setSettings(saved); setKey('');
      await load();
      setMsg({ ok: true, text: 'API key saved.' });
    } catch (err) { setMsg({ ok: false, text: 'Error: ' + err.message }); }
    finally { setBusy(''); }
  };
  const toggle = async (val) => {
    try { const saved = await adminApi.updateSettings({ [enabledField]: val }); setSettings(saved); load(); }
    catch (err) { alert('Error: ' + err.message); }
  };
  const browse = async () => {
    try { setBusy('browse'); setMsg(null); setItems(null); const res = await productsFn(search.trim()); setItems(res.data || []); }
    catch (err) { setMsg({ ok: false, text: 'Error: ' + (err.response?.data?.error || err.message) }); }
    finally { setBusy(''); }
  };
  const cur = st?.currency || '';
  const sym = cur === 'INR' ? '₹' : (cur === 'USD' ? '$' : '');

  return (
    <div className="glass-panel rounded-2xl p-5 border border-white/10 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-bold text-[#ececec] flex items-center gap-2">
          <DollarSign className="w-4 h-4 text-[#ececec]" />
          {label}
        </h3>
        {st && (
          <div className="flex items-center gap-2 text-[11px]">
            <span className={`px-2 py-0.5 rounded-full border ${st.has_key ? 'bg-[#2f2f2f] text-[#ececec] border-white/15' : 'bg-rose-950/40 text-rose-300 border-rose-500/30'}`}>
              {st.has_key ? `Key ${st.key_mask || 'set'}` : 'No API key'}
            </span>
            {st.has_key && (
              <span className={`px-2 py-0.5 rounded-full border ${st.error ? 'bg-rose-950/40 text-rose-300 border-rose-500/30' : 'bg-emerald-950/40 text-emerald-300 border-emerald-500/30'}`}>
                {st.error ? 'Error' : `Balance: ${sym}${st.balance} ${sym ? '' : cur}`}
              </span>
            )}
            <label className="flex items-center gap-1 text-[#8e8ea0] cursor-pointer">
              <input type="checkbox" checked={settings[enabledField] === true} onChange={(e) => toggle(e.target.checked)} />
              enabled
            </label>
          </div>
        )}
      </div>

      <p className="text-[11px] text-[#8e8ea0] leading-relaxed">
        {desc}{st?.error && <span className="text-rose-300"> · {st.error}</span>}
      </p>

      <div className="flex items-center gap-2">
        <input type="password" value={key} onChange={(e) => setKey(e.target.value)}
          placeholder={st?.has_key ? 'Nayi key daalo (purani replace hogi)' : keyPlaceholder}
          className="flex-1 p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] font-mono text-[11px] focus:outline-none focus:border-white/20" />
        <button type="button" onClick={saveKey} disabled={busy !== '' || !key.trim()}
          className="px-3 py-2 bg-[#2f2f2f] hover:bg-[#3a3a3a] border border-white/15 text-[#ececec] rounded-xl disabled:opacity-50">
          {busy === 'key' ? 'Saving…' : 'Save key'}
        </button>
        <button type="button" onClick={load} disabled={busy !== ''}
          className="px-3 py-2 bg-[#3a3a3a] hover:bg-[#4a4a4a] text-[#d4d4d4] rounded-xl disabled:opacity-50">Refresh</button>
      </div>
      {msg && <div className={`text-[11px] ${msg.ok ? 'text-emerald-300' : 'text-rose-300'}`}>{msg.text}</div>}

      <div>
        <label className="block text-[#8e8ea0] mb-1 font-medium text-[11px]">Supplier catalogue — product ki {idLabel} dhoondo (Products tab me map karne ke liye)</label>
        <div className="flex items-center gap-2">
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="e.g. gemini"
            className="flex-1 p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] text-[11px] focus:outline-none focus:border-white/20" />
          <button type="button" onClick={browse} disabled={busy !== '' || !st?.has_key}
            className="px-3 py-2 bg-[#3a3a3a] hover:bg-[#4a4a4a] text-[#d4d4d4] rounded-xl disabled:opacity-50">
            {busy === 'browse' ? 'Loading…' : 'Browse'}
          </button>
        </div>
        {items && (
          <div className="mt-2 max-h-56 overflow-auto rounded-xl border border-white/10 divide-y divide-white/5">
            {items.length === 0 && <div className="p-2.5 text-[11px] text-[#8e8ea0]">Koi product nahi mila.</div>}
            {items.map((it) => (
              <div key={it.id} className="p-2.5 text-[11px] flex items-center justify-between gap-2">
                <span className="text-[#d4d4d4]">{it.icon ? `${it.icon} ` : ''}{it.name}{it.category ? <span className="text-[#8e8ea0]"> · {it.category}</span> : null}</span>
                <span className="text-[#8e8ea0] whitespace-nowrap">{idLabel} <b className="text-[#ececec] font-mono">{it.id}</b> · {it.currency === 'INR' ? '₹' : '$'}{it.price} · stock {it.stock}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
