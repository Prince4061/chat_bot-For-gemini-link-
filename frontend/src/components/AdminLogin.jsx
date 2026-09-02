import React, { useState } from 'react';
import { ShieldCheck, KeyRound, ArrowRight, Loader2 } from 'lucide-react';
import { adminApi } from '../api/client';

export default function AdminLogin({ onSuccess, onSwitchToChat }) {
  const [token, setToken] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!token.trim()) return;
    setLoading(true);
    setError('');
    try {
      await adminApi.login(token.trim());
      onSuccess();
    } catch (err) {
      setError(err?.response?.status === 429 ? 'Too many attempts. Wait a minute and retry.' : 'Invalid admin token.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex-1 flex items-center justify-center h-screen bg-[#212121] text-[#ececec] p-6">
      <div className="w-full max-w-md glass-panel rounded-3xl border border-white/10 p-8 shadow-2xl shadow-black/40">
        <div className="flex items-center gap-3 mb-6">
          <div className="w-11 h-11 rounded-2xl bg-gradient-to-tr from-white to-white flex items-center justify-center text-black">
            <ShieldCheck className="w-5 h-5" />
          </div>
          <div>
            <h1 className="font-bold text-base">Admin Control Center</h1>
            <p className="text-xs text-[#8e8ea0]">Enter your admin access key to continue</p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs text-[#8e8ea0] mb-1.5 font-medium">Admin API Key</label>
            <div className="relative">
              <KeyRound className="w-4 h-4 text-[#8e8ea0] absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="password"
                autoFocus
                value={token}
                onChange={(e) => setToken(e.target.value)}
                placeholder="ADMIN_API_KEY from .env"
                className="w-full pl-9 pr-3 py-2.5 bg-[#212121] border border-white/10 rounded-xl text-sm font-mono focus:outline-none focus:border-white/15"
              />
            </div>
          </div>

          {error && <p className="text-xs text-rose-400 font-medium">{error}</p>}

          <button
            type="submit"
            disabled={loading || !token.trim()}
            className="w-full py-2.5 bg-gradient-to-r from-white to-white hover:from-white hover:to-white disabled:opacity-50 text-black font-bold rounded-xl text-sm transition-all flex items-center justify-center gap-2"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <ArrowRight className="w-4 h-4" />}
            {loading ? 'Verifying…' : 'Unlock Dashboard'}
          </button>
        </form>

        <button onClick={onSwitchToChat} className="mt-5 w-full text-xs text-[#8e8ea0] hover:text-[#ececec] transition-colors">
          ← Back to chat
        </button>

        <p className="mt-6 text-[11px] text-[#8e8ea0] leading-relaxed">
          The key is set via <code className="text-[#ececec]">ADMIN_API_KEY</code> in the server's <code>.env</code>.
          It is kept only in this tab's session storage.
        </p>
      </div>
    </div>
  );
}
