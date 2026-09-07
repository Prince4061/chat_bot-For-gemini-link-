import React, { useState, useRef, useEffect } from 'react';
import { Send, RotateCcw, Bot, Smartphone, Globe, Zap, Wrench, BookOpen, Clock, User, AlertTriangle } from 'lucide-react';
import { adminApi } from '../api/client';

const PRESETS = [
  { label: 'hi', text: 'hi' },
  { label: 'Products', text: 'products dikhao' },
  { label: 'Price', text: 'gemini ka price kya hai' },
  { label: 'Buy', text: 'mujhe canva pro chahiye' },
  { label: 'Pay (UTR)', text: 'paid 123456789012' },
  { label: 'Reseller (web)', text: '9876543210 1234' },
  { label: 'Claim link', text: 'gemini ki link do' },
  { label: 'Balance', text: 'balance batao' },
  { label: 'Refund?', text: 'refund milega kya?' },
];

function formatInline(str) {
  return (str || '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/\*\*(.*?)\*\*/g, '<strong class="text-white">$1</strong>')
    .replace(/`([^`]+)`/g, '<code class="px-1 rounded bg-black/30 font-mono text-[12px]">$1</code>');
}

export default function BotTester() {
  const [mode, setMode] = useState('web');          // 'web' | 'whatsapp'
  const [phone, setPhone] = useState('9876543210');
  const [sessionId, setSessionId] = useState('');
  const [messages, setMessages] = useState([]);       // {role, text, debug?}
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [agent, setAgent] = useState(null);
  const endRef = useRef(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, loading]);
  useEffect(() => { adminApi.getAgentStatus().then(setAgent).catch(() => {}); }, []);

  const reset = async () => {
    if (sessionId) { try { await adminApi.botTestReset(sessionId); } catch {} }
    setSessionId('');
    setMessages([]);
  };

  const switchMode = (m) => { setMode(m); reset(); };

  const send = async (text) => {
    const msg = (text ?? input).trim();
    if (!msg || loading) return;
    setInput('');
    setMessages((prev) => [...prev, { role: 'user', text: msg }]);
    setLoading(true);
    try {
      const res = await adminApi.botTest({ message: msg, mode, phone, session_id: sessionId });
      setSessionId(res.session_id);
      setAgent(res.agent);
      setMessages((prev) => [...prev, { role: 'bot', text: res.reply, debug: res }]);
    } catch (err) {
      setMessages((prev) => [...prev, { role: 'bot', text: '⚠️ ' + (err.message || 'request failed'), debug: null }]);
    } finally {
      setLoading(false);
    }
  };

  const engineBadge = (engine) => {
    const isAI = engine === 'deep_agent';
    const partial = engine === 'deep_agent_partial';
    return (
      <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold ${
        isAI ? 'bg-emerald-950/60 text-emerald-300' : partial ? 'bg-amber-950/60 text-amber-300' : 'bg-[#3a3a3a] text-[#d4d4d4]'
      }`}>
        <Zap className="w-3 h-3" />
        {isAI ? 'AI (LLM)' : partial ? 'AI partial' : 'Rule engine'}
      </span>
    );
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-[#ececec] flex items-center gap-2">
            <Bot className="w-5 h-5" /> Bot Tester
          </h2>
          <p className="text-xs text-[#8e8ea0]">Live chat karke check karo ki bot sahi jawab de raha hai — har reply ke neeche debug info.</p>
        </div>
        {agent && (
          <div className={`text-[11px] px-2.5 py-1.5 rounded-lg border ${
            agent.engine === 'deep_agent' ? 'bg-emerald-950/40 border-emerald-500/30 text-emerald-300' : 'bg-amber-950/40 border-amber-500/30 text-amber-300'
          }`}>
            {agent.engine === 'deep_agent' ? `AI active: ${agent.model}` : `Fallback engine (no LLM${agent.circuit_open ? ' — ' + agent.circuit_reason : ''})`}
            {agent.last_llm_error?.error && <span className="block text-[10px] text-[#8e8ea0] max-w-xs truncate" title={agent.last_llm_error.error}>last error: {agent.last_llm_error.error}</span>}
          </div>
        )}
      </div>

      {/* Controls */}
      <div className="glass-panel rounded-2xl p-3 border border-white/10 flex flex-wrap items-center gap-2 text-xs">
        <div className="flex items-center bg-[#212121] rounded-lg p-0.5 border border-white/10">
          <button onClick={() => switchMode('web')} className={`px-2.5 py-1.5 rounded-md flex items-center gap-1 ${mode === 'web' ? 'bg-white text-black font-semibold' : 'text-[#b4b4b4]'}`}>
            <Globe className="w-3.5 h-3.5" /> Web
          </button>
          <button onClick={() => switchMode('whatsapp')} className={`px-2.5 py-1.5 rounded-md flex items-center gap-1 ${mode === 'whatsapp' ? 'bg-white text-black font-semibold' : 'text-[#b4b4b4]'}`}>
            <Smartphone className="w-3.5 h-3.5" /> WhatsApp
          </button>
        </div>
        {mode === 'whatsapp' && (
          <div className="flex items-center gap-1.5">
            <span className="text-[#8e8ea0]">From number:</span>
            <input
              value={phone}
              onChange={(e) => setPhone(e.target.value.replace(/\D/g, '').slice(0, 10))}
              onBlur={reset}
              className="w-32 p-1.5 bg-[#212121] border border-white/10 rounded-lg text-[#ececec] font-mono focus:outline-none focus:border-white/20"
              placeholder="10-digit"
            />
            <span className="text-[10px] text-[#8e8ea0]">(registered reseller no. = auto-verify)</span>
          </div>
        )}
        <div className="flex-1" />
        <button onClick={reset} className="px-2.5 py-1.5 bg-[#3a3a3a] hover:bg-[#4a4a4a] text-[#d4d4d4] rounded-lg flex items-center gap-1">
          <RotateCcw className="w-3.5 h-3.5" /> New session
        </button>
      </div>

      {/* Presets */}
      <div className="flex flex-wrap gap-1.5">
        {PRESETS.map((p) => (
          <button key={p.label} onClick={() => send(p.text)} disabled={loading}
            className="px-2.5 py-1 rounded-full bg-[#2f2f2f] hover:bg-[#3a3a3a] border border-white/10 text-[11px] text-[#d4d4d4] disabled:opacity-50">
            {p.label}
          </button>
        ))}
      </div>

      {/* Chat */}
      <div className="glass-panel rounded-2xl border border-white/10 flex flex-col" style={{ height: '58vh' }}>
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {messages.length === 0 && (
            <div className="h-full flex items-center justify-center text-xs text-[#8e8ea0] text-center px-6">
              Preset dabao ya neeche message likho. {mode === 'whatsapp' ? `Bot number ${phone || '…'} ko sender maanega.` : 'Web customer/reseller ki tarah test hoga.'}
            </div>
          )}
          {messages.map((m, i) => (
            m.role === 'user' ? (
              <div key={i} className="flex justify-end">
                <div className="max-w-[80%] rounded-2xl px-3.5 py-2 bg-[#2f2f2f] text-[#ececec] text-sm whitespace-pre-wrap">{m.text}</div>
              </div>
            ) : (
              <div key={i} className="flex gap-2.5">
                <div className="w-6 h-6 rounded-full bg-white flex items-center justify-center shrink-0 mt-0.5"><Bot className="w-3.5 h-3.5 text-black" /></div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-[#ececec] leading-6 whitespace-pre-wrap" dangerouslySetInnerHTML={{ __html: formatInline(m.text) }} />
                  {m.debug && (
                    <div className="mt-2 p-2.5 rounded-xl bg-[#212121] border border-white/10 text-[11px] space-y-1.5">
                      <div className="flex flex-wrap items-center gap-2">
                        {engineBadge(m.debug.engine)}
                        <span className="inline-flex items-center gap-1 text-[#8e8ea0]"><Clock className="w-3 h-3" /> {m.debug.elapsed_ms} ms</span>
                        {m.debug.tool_calls?.length > 0 ? (
                          <span className="inline-flex items-center gap-1 text-[#d4d4d4]">
                            <Wrench className="w-3 h-3" />
                            {m.debug.tool_calls.map((t, k) => (
                              <span key={k} className={`px-1.5 rounded ${t.ok ? 'bg-[#2f2f2f]' : 'bg-rose-950/50 text-rose-300'}`} title={t.detail}>{t.tool}</span>
                            ))}
                          </span>
                        ) : (
                          <span className="text-[#8e8ea0]">no tools</span>
                        )}
                      </div>
                      {m.debug.kb_match && (
                        <div className="flex items-start gap-1 text-[#d4d4d4]">
                          <BookOpen className="w-3 h-3 mt-0.5 shrink-0" />
                          <span>Trained FAQ match: <span className="text-[#ececec]">“{m.debug.kb_match.question}”</span>
                            {!m.debug.tool_calls?.some((t) => t.tool === 'knowledge_base') && m.debug.engine !== 'deep_agent' && (
                              <span className="text-amber-300"> (matched but a commerce flow answered first)</span>
                            )}
                          </span>
                        </div>
                      )}
                      {m.debug.session && (
                        <div className="flex flex-wrap items-center gap-2 text-[#8e8ea0]">
                          <User className="w-3 h-3" />
                          {m.debug.session.reseller
                            ? <span className="text-emerald-300">Reseller: {m.debug.session.reseller.name} · wallet: {m.debug.session.reseller.balance}</span>
                            : <span>Not a verified reseller</span>}
                          {m.debug.session.pending_order && (
                            <span className="text-amber-300">· Pending order {m.debug.session.pending_order.id} ({m.debug.session.pending_order.product}, ₹{m.debug.session.pending_order.amount})</span>
                          )}
                          {m.debug.session.last_order_id && !m.debug.session.pending_order && <span>· last order {m.debug.session.last_order_id}</span>}
                        </div>
                      )}
                      {m.debug.todos?.length > 0 && (
                        <div className="text-[#8e8ea0]">Plan: {m.debug.todos.map((t) => `${t.status === 'completed' ? '✓' : '○'} ${t.task}`).join(' · ')}</div>
                      )}
                      {!m.debug.success && <div className="text-rose-300 flex items-center gap-1"><AlertTriangle className="w-3 h-3" /> request reported failure</div>}
                    </div>
                  )}
                </div>
              </div>
            )
          ))}
          {loading && (
            <div className="flex gap-2.5 items-center text-xs text-[#8e8ea0]">
              <div className="w-6 h-6 rounded-full bg-white flex items-center justify-center"><Bot className="w-3.5 h-3.5 text-black" /></div>
              <span className="animate-pulse">thinking…</span>
            </div>
          )}
          <div ref={endRef} />
        </div>
        <form onSubmit={(e) => { e.preventDefault(); send(); }} className="p-3 border-t border-white/5 flex items-center gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={mode === 'whatsapp' ? `Message as ${phone || 'number'}…` : 'Message as a web user…'}
            disabled={loading}
            className="flex-1 py-2.5 px-4 bg-[#2f2f2f] rounded-full text-sm text-[#ececec] placeholder-[#8e8ea0] focus:outline-none"
          />
          <button type="submit" disabled={!input.trim() || loading} className="p-2.5 bg-white text-black rounded-full disabled:bg-[#676767] disabled:cursor-not-allowed">
            <Send className="w-4 h-4" />
          </button>
        </form>
      </div>
    </div>
  );
}
