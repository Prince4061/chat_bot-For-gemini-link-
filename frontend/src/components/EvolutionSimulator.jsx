import React, { useState } from 'react';
import { 
  Smartphone, 
  Send, 
  Bot, 
  User, 
  Code, 
  RefreshCw, 
  ShieldCheck,
  Sparkles,
  Zap
} from 'lucide-react';
import { adminApi } from '../api/client';

export default function EvolutionSimulator() {
  // Default to a NON-registered number so you test the real customer/unregistered flow.
  // To test a reseller, type a registered reseller's number here (e.g. 9876543210).
  const [phone, setPhone] = useState('9000000000');
  const [userName, setUserName] = useState('WhatsApp User');
  const [message, setMessage] = useState('products dikhao');
  const [loading, setLoading] = useState(false);
  const [simulationLog, setSimulationLog] = useState(null);

  const handleSimulate = async (e) => {
    e.preventDefault();
    if (!message.trim() || loading) return;

    try {
      setLoading(true);
      const res = await adminApi.simulateEvolutionWhatsApp(phone, message, userName);
      setSimulationLog(res);
    } catch (err) {
      alert('Simulation error: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      
      {/* Header */}
      <div>
        <h2 className="text-lg font-bold text-[#ececec] flex items-center gap-2">
          <Smartphone className="w-5 h-5 text-[#ececec]" />
          Evolution API (WhatsApp) Webhook Live Simulator
        </h2>
        <p className="text-xs text-[#8e8ea0]">
          Test the exact WhatsApp webhook execution without requiring a live WhatsApp server. 
          The backend runs the identical Deep Agent execution logic.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        
        {/* Simulator Form */}
        <div className="glass-panel rounded-2xl p-5 border border-white/10 space-y-4">
          <h3 className="text-sm font-bold text-[#ececec] flex items-center gap-2">
            <Zap className="w-4 h-4 text-[#ececec]" />
            Simulate Incoming WhatsApp Message
          </h3>

          <form onSubmit={handleSimulate} className="space-y-3.5 text-xs">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-[#8e8ea0] mb-1 font-medium">WhatsApp Sender Phone *</label>
                <input
                  type="text"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  required
                  placeholder="e.g. 9876543210"
                  className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] font-mono focus:outline-none focus:border-white/15"
                />
              </div>

              <div>
                <label className="block text-[#8e8ea0] mb-1 font-medium">Sender WhatsApp Name</label>
                <input
                  type="text"
                  value={userName}
                  onChange={(e) => setUserName(e.target.value)}
                  placeholder="e.g. Rahul Sharma"
                  className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] focus:outline-none focus:border-white/15"
                />
              </div>
            </div>

            <div>
              <label className="block text-[#8e8ea0] mb-1 font-medium">Incoming Message Text *</label>
              <textarea
                rows={3}
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                required
                placeholder="Type customer or reseller query..."
                className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] focus:outline-none focus:border-white/15"
              />
            </div>

            {/* Shortcut Quick Presets */}
            <div className="space-y-1.5 pt-1">
              <span className="text-[10px] text-[#8e8ea0] uppercase font-bold tracking-wider">Quick Presets:</span>
              <div className="flex flex-wrap gap-1.5">
                <button
                  type="button"
                  onClick={() => {
                    setPhone('9876543210');
                    setMessage('gemini ki link do');
                  }}
                  className="px-2 py-1 bg-[#2f2f2f] hover:bg-[#3a3a3a] border border-white/10 rounded-lg text-[11px] text-[#ececec]"
                >
                  Registered reseller (9876543210)
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setPhone('9000000000');
                    setMessage('products dikhao');
                  }}
                  className="px-2 py-1 bg-[#2f2f2f] hover:bg-[#3a3a3a] border border-white/10 rounded-lg text-[11px] text-[#ececec]"
                >
                  New customer
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setPhone('9000000000');
                    setMessage('mujhe reseller credits chahiye');
                  }}
                  className="px-2 py-1 bg-[#2f2f2f] hover:bg-[#3a3a3a] border border-white/10 rounded-lg text-[11px] text-amber-300"
                >
                  Unregistered → reseller ask
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading || !message.trim()}
              className="w-full py-2.5 bg-gradient-to-r from-white to-white hover:from-white hover:to-white disabled:opacity-50 text-black font-bold rounded-xl text-xs transition-all shadow-md active:scale-98 flex items-center justify-center gap-2"
            >
              {loading ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  Running Deep Agent via Webhook...
                </>
              ) : (
                <>
                  <Send className="w-4 h-4" />
                  Dispatch WhatsApp Webhook
                </>
              )}
            </button>
          </form>
        </div>

        {/* Live Simulation WhatsApp View */}
        <div className="glass-panel rounded-2xl p-5 border border-white/10 flex flex-col justify-between">
          <div className="flex items-center justify-between pb-3 border-b border-white/10">
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-white animate-pulse"></div>
              <span className="text-xs font-bold text-[#ececec]">WhatsApp Preview</span>
            </div>
            <span className="text-[10px] text-[#8e8ea0] font-mono">Evolution v2</span>
          </div>

          <div className="flex-1 py-4 space-y-3 overflow-y-auto max-h-[380px]">
            {simulationLog ? (
              <>
                {/* User Message Bubble */}
                <div className="flex justify-end">
                  <div className="max-w-[85%] bg-[#2f2f2f] text-white rounded-2xl rounded-tr-sm p-3 text-xs shadow-md">
                    <div className="text-[10px] font-bold text-[#ececec] mb-0.5">
                      {simulationLog.simulated_whatsapp_sender}
                    </div>
                    <p>{simulationLog.incoming_message}</p>
                  </div>
                </div>

                {/* Bot Response Bubble */}
                <div className="flex justify-start">
                  <div className="max-w-[90%] bg-[#2f2f2f] border border-white/10 text-[#ececec] rounded-2xl rounded-tl-sm p-3.5 text-xs shadow-lg space-y-2">
                    <div className="flex items-center gap-1.5 text-[10px] font-bold text-[#ececec]">
                      <Bot className="w-3 h-3" />
                      <span>Deep Agent (WhatsApp Automated Reply)</span>
                    </div>
                    <div className="whitespace-pre-line text-[#d4d4d4] leading-relaxed font-sans">
                      {simulationLog.deep_agent_whatsapp_reply}
                    </div>
                  </div>
                </div>
              </>
            ) : (
              <div className="h-48 flex items-center justify-center text-center text-xs text-[#8e8ea0] italic">
                Send a simulated message to preview the WhatsApp conversation flow.
              </div>
            )}
          </div>

          {/* Webhook JSON Output Toggle */}
          {simulationLog && (
            <div className="pt-3 border-t border-white/10">
              <details className="text-[11px] text-[#8e8ea0]">
                <summary className="cursor-pointer hover:text-[#ececec] flex items-center gap-1">
                  <Code className="w-3.5 h-3.5 text-[#ececec]" />
                  View Webhook Response JSON
                </summary>
                <pre className="mt-2 p-3 bg-[#212121] rounded-xl border border-white/10 text-[10px] text-[#ececec] overflow-x-auto font-mono max-h-36">
                  {JSON.stringify(simulationLog, null, 2)}
                </pre>
              </details>
            </div>
          )}
        </div>

      </div>

    </div>
  );
}
