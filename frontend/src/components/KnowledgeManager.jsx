import React, { useState, useEffect } from 'react';
import { GraduationCap, Plus, Trash2, Save, Check, FlaskConical, Power, Pencil, X, Bot, Cpu } from 'lucide-react';
import { adminApi } from '../api/client';

const EMPTY_FORM = { question: '', answer: '', keywords: '', priority: 0 };

export default function KnowledgeManager() {
  const [instructions, setInstructions] = useState('');
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [savingInstr, setSavingInstr] = useState(false);
  const [instrSaved, setInstrSaved] = useState(false);
  const [agent, setAgent] = useState(null);          // engine status: deep_agent | rule_based_fallback

  // Add / edit form
  const [form, setForm] = useState(EMPTY_FORM);
  const [editingId, setEditingId] = useState(null);
  const [saving, setSaving] = useState(false);

  // Test box (runs the SAME decision logic the bot uses)
  const [testQ, setTestQ] = useState('');
  const [testPlatform, setTestPlatform] = useState('web');
  const [testResult, setTestResult] = useState(null);
  const [testing, setTesting] = useState(false);

  const load = async () => {
    try {
      setLoading(true);
      const [kb, settings] = await Promise.all([adminApi.getKnowledge(), adminApi.getSettings()]);
      setEntries(kb);
      setInstructions(settings.agent_instructions || '');
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
    adminApi.agentStatus().then(setAgent).catch(() => setAgent(null));
  };

  useEffect(() => { load(); }, []);

  const saveInstructions = async () => {
    try {
      setSavingInstr(true);
      await adminApi.updateSettings({ agent_instructions: instructions });
      setInstrSaved(true);
      setTimeout(() => setInstrSaved(false), 2500);
    } catch (err) {
      alert('Error: ' + err.message);
    } finally {
      setSavingInstr(false);
    }
  };

  const submitEntry = async (e) => {
    e.preventDefault();
    if (!form.question.trim() || !form.answer.trim()) return;
    try {
      setSaving(true);
      if (editingId) await adminApi.updateKnowledge(editingId, form);
      else await adminApi.createKnowledge(form);
      setForm(EMPTY_FORM); setEditingId(null);
      load();
    } catch (err) {
      alert('Error: ' + err.message);
    } finally {
      setSaving(false);
    }
  };

  const startEdit = (entry) => {
    setEditingId(entry.id);
    setForm({ question: entry.question, answer: entry.answer, keywords: entry.keywords || '', priority: entry.priority || 0 });
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const cancelEdit = () => { setEditingId(null); setForm(EMPTY_FORM); };

  const toggleActive = async (entry) => {
    await adminApi.updateKnowledge(entry.id, { is_active: !entry.is_active });
    load();
  };

  const removeEntry = async (id) => {
    if (!confirm('Is trained answer ko delete karein?')) return;
    await adminApi.deleteKnowledge(id);
    if (editingId === id) cancelEdit();
    load();
  };

  const runTest = async () => {
    if (!testQ.trim()) return;
    try {
      setTesting(true);
      const res = await adminApi.testKnowledge(testQ, testPlatform);
      setTestResult(res);
    } catch (err) {
      setTestResult({ matched: false, decision: 'error', reason: err.message });
    } finally {
      setTesting(false);
    }
  };

  const aiMode = agent?.engine === 'deep_agent';

  const decisionView = (r) => {
    if (!r) return null;
    if (r.decision === 'kb') return { cls: 'bg-emerald-950/40 border-emerald-500/30 text-emerald-200', title: '✅ Bot yahi trained answer dega' };
    if (r.decision === 'kb_fallback') return { cls: 'bg-amber-950/40 border-amber-500/30 text-amber-200', title: '⚠️ Pehle product flow chalega — ye answer tabhi jab wo na lage' };
    if (r.decision === 'builtin') return { cls: 'bg-amber-950/40 border-amber-500/30 text-amber-200', title: '⛔ Transactional message — trained answer nahi lagega' };
    if (r.decision === 'error') return { cls: 'bg-rose-950/40 border-rose-500/30 text-rose-200', title: 'Error' };
    return { cls: 'bg-[#2f2f2f] border-white/10 text-[#8e8ea0]', title: '— Koi trained answer match nahi hua (bot normal reply karega)' };
  };
  const dv = decisionView(testResult);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-bold text-[#ececec] flex items-center gap-2">
          <GraduationCap className="w-5 h-5" />
          AI Training
        </h2>
        <p className="text-xs text-[#8e8ea0]">
          Bot ko sikhao ki kis tarah ke sawaal par kya reply de. Trained Q&amp;A dono engines par same kaam karta hai.
        </p>
      </div>

      {/* Which engine is answering right now — decides what "training" can do */}
      {agent && (
        <div className={`rounded-2xl px-4 py-3 border text-xs flex flex-wrap items-center gap-x-3 gap-y-1 ${aiMode ? 'bg-emerald-950/30 border-emerald-500/30 text-emerald-200' : 'bg-amber-950/30 border-amber-500/30 text-amber-200'}`}>
          {aiMode ? <Bot className="w-4 h-4 shrink-0" /> : <Cpu className="w-4 h-4 shrink-0" />}
          {aiMode ? (
            <span><b>AI mode ({agent.model})</b> — Custom Instructions aur Q&amp;A dono follow honge. Strong-match Q&amp;A exactly waise hi jayega jaisa likha hai.</span>
          ) : (
            <span><b>Rule-engine mode</b> — {agent.llm_configured ? `OpenAI abhi fail ho raha hai (${agent.circuit_reason || agent.last_llm_error?.error?.slice(0, 80) || 'credits/quota'})` : 'OpenAI key set nahi hai'}.
              Trained <b>Q&amp;A 100% kaam karenge</b>; <b>Custom Instructions sirf AI mode me lagte hain</b> (rule engine free-text nahi samajhta).</span>
          )}
        </div>
      )}

      {/* Custom instructions */}
      <div className="glass-panel rounded-2xl p-5 border border-white/10 space-y-3">
        <h3 className="text-sm font-bold text-[#ececec]">Custom Instructions (persona / rules / tone)</h3>
        <p className="text-[11px] text-[#8e8ea0]">Sirf AI (OpenAI) mode me lagta hai. Fixed facts (refund, delivery, timing) ke liye neeche Q&amp;A use karo — wo har mode me pakka chalta hai.</p>
        <textarea
          rows={5}
          value={instructions}
          onChange={(e) => setInstructions(e.target.value)}
          placeholder={"e.g. Hamesha politely 'ji' laga ke baat karo. Kabhi discount promise mat karo. Sirf UPI accept karte hain."}
          className="w-full p-3 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] text-xs focus:outline-none focus:border-white/20"
        />
        <div className="flex items-center gap-3">
          <button
            onClick={saveInstructions}
            disabled={savingInstr}
            className="px-4 py-2 bg-white hover:bg-white/90 text-black font-bold rounded-xl text-xs flex items-center gap-1.5 disabled:opacity-50"
          >
            <Save className="w-4 h-4" />
            {savingInstr ? 'Saving…' : 'Save instructions'}
          </button>
          {instrSaved && <span className="text-xs text-emerald-400 flex items-center gap-1"><Check className="w-4 h-4" /> Saved</span>}
        </div>
      </div>

      {/* Add / edit FAQ */}
      <div className={`glass-panel rounded-2xl p-5 border ${editingId ? 'border-sky-500/40' : 'border-white/10'}`}>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-bold text-[#ececec]">{editingId ? `Edit trained answer #${editingId}` : 'Add a trained Q&A'}</h3>
          {editingId && (
            <button type="button" onClick={cancelEdit} className="text-xs text-[#8e8ea0] hover:text-[#ececec] flex items-center gap-1"><X className="w-3.5 h-3.5" /> Cancel</button>
          )}
        </div>
        <form onSubmit={submitEntry} className="space-y-3 text-xs">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-[#8e8ea0] mb-1">Example question(s) *</label>
              <textarea
                rows={2}
                value={form.question}
                onChange={(e) => setForm({ ...form, question: e.target.value })}
                placeholder={"Delivery kitni der me hoti hai?\nLink kab milega?"}
                className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] focus:outline-none focus:border-white/20"
              />
              <p className="text-[10px] text-[#8e8ea0] mt-1">Ek se zyada tarike se poocha ja sakta hai? Har line me ek likho.</p>
            </div>
            <div>
              <label className="block text-[#8e8ea0] mb-1">Trigger keywords (comma separated)</label>
              <input
                value={form.keywords}
                onChange={(e) => setForm({ ...form, keywords: e.target.value })}
                placeholder="delivery, kitni der, kab milega"
                className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] font-mono focus:outline-none focus:border-white/20"
              />
              <p className="text-[10px] text-[#8e8ea0] mt-1"><b>2-shabd ka phrase</b> (jaise <code>kaise activate</code>) = strong match — product ka naam ho tab bhi ye answer jayega. Single word = weak (typo/plural bhi pakadta hai).</p>
            </div>
          </div>
          <div>
            <label className="block text-[#8e8ea0] mb-1">Bot ka reply (answer) *</label>
            <textarea
              rows={3}
              value={form.answer}
              onChange={(e) => setForm({ ...form, answer: e.target.value })}
              placeholder="Payment confirm hote hi link turant milta hai — 1 minute ke andar. UPI: {upi_id}"
              className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] focus:outline-none focus:border-white/20"
            />
            <p className="text-[10px] text-[#8e8ea0] mt-1">Placeholders (Settings se live bharte hain): <code>{'{upi_id}'}</code> <code>{'{upi_name}'}</code> <code>{'{business_name}'}</code> <code>{'{admin_contact}'}</code> <code>{'{min_topup}'}</code></p>
          </div>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <label className="text-[#8e8ea0]">Priority</label>
              <input
                type="number"
                value={form.priority}
                onChange={(e) => setForm({ ...form, priority: parseInt(e.target.value) || 0 })}
                className="w-16 p-1.5 bg-[#212121] border border-white/10 rounded-lg text-[#ececec] text-center"
              />
              <span className="text-[10px] text-[#8e8ea0]">(barabar match par zyada priority jeetegi)</span>
            </div>
            <button
              type="submit"
              disabled={saving || !form.question.trim() || !form.answer.trim()}
              className="px-4 py-2 bg-white hover:bg-white/90 text-black font-bold rounded-xl flex items-center gap-1.5 disabled:opacity-50"
            >
              {editingId ? <Save className="w-4 h-4" /> : <Plus className="w-4 h-4" />}
              {saving ? 'Saving…' : editingId ? 'Update' : 'Add'}
            </button>
          </div>
        </form>
      </div>

      {/* Test box */}
      <div className="glass-panel rounded-2xl p-4 border border-white/10">
        <h3 className="text-sm font-bold text-[#ececec] mb-2 flex items-center gap-2">
          <FlaskConical className="w-4 h-4" /> Test — bot is sawaal par kya karega?
        </h3>
        <div className="flex items-center gap-2 text-xs">
          <input
            value={testQ}
            onChange={(e) => setTestQ(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && runTest()}
            placeholder="ek sawaal type karo… (jaise: gemini kaise activate kare)"
            className="flex-1 p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] focus:outline-none focus:border-white/20"
          />
          <select value={testPlatform} onChange={(e) => setTestPlatform(e.target.value)}
            className="p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] focus:outline-none">
            <option value="web">Web</option>
            <option value="whatsapp">WhatsApp</option>
          </select>
          <button onClick={runTest} disabled={testing} className="px-3 py-2 bg-[#3a3a3a] hover:bg-[#4a4a4a] text-[#d4d4d4] rounded-xl disabled:opacity-50">{testing ? '…' : 'Test'}</button>
        </div>
        {testResult && dv && (
          <div className={`mt-3 rounded-xl border p-3 text-xs space-y-1.5 ${dv.cls}`}>
            <div className="font-semibold">{dv.title}</div>
            {testResult.reason && <div className="opacity-80">Reason: {testResult.reason}</div>}
            {testResult.matched && (
              <>
                <div className="text-[#ececec]">Matched: <span className="font-medium">{testResult.entry.question.split('\n')[0]}</span>
                  <span className="opacity-70"> · score {testResult.score}{testResult.strong ? ' (strong)' : ' (weak)'}</span></div>
                {testResult.matched_keywords?.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {testResult.matched_keywords.map((k, i) => <span key={i} className="px-1.5 py-0.5 rounded bg-black/30 font-mono text-[10px]">{k}</span>)}
                  </div>
                )}
                <div className="mt-1 p-2 rounded-lg bg-black/25 text-[#ececec] whitespace-pre-wrap">{testResult.rendered_answer}</div>
                {testResult.empty_placeholders?.length > 0 && (
                  <div className="text-amber-300">⚠ Settings me khaali hai: {testResult.empty_placeholders.map((k) => `{${k}}`).join(', ')} — Settings &amp; UPI tab me bhar do, tab tak neutral word ("admin") lagega.</div>
                )}
                {testResult.decision === 'kb_fallback' && (
                  <div className="opacity-80">Tip: keywords me 2-shabd ka phrase add karo (jaise <code>kaise activate</code>) to ye answer product flow se pehle jayega.</div>
                )}
              </>
            )}
            <div className="opacity-60 text-[10px]">Engine abhi: {testResult.engine}{testResult.model ? ` · ${testResult.model}` : ''}</div>
          </div>
        )}
      </div>

      {/* Entries list */}
      <div className="glass-panel rounded-2xl border border-white/10 overflow-hidden">
        <div className="p-4 text-sm font-bold text-[#ececec] border-b border-white/5">
          Trained answers ({entries.length})
        </div>
        {loading ? (
          <div className="p-8 text-center text-xs text-[#8e8ea0]">Loading…</div>
        ) : entries.length === 0 ? (
          <div className="p-8 text-center text-xs text-[#8e8ea0]">Abhi koi trained answer nahi. Upar se add karo.</div>
        ) : (
          <div className="divide-y divide-white/5">
            {entries.map((e) => (
              <div key={e.id} className={`p-4 flex items-start justify-between gap-3 ${editingId === e.id ? 'bg-sky-950/20' : ''}`}>
                <div className="min-w-0">
                  <div className="text-sm text-[#ececec] font-medium whitespace-pre-line">{e.question}</div>
                  <div className="text-xs text-[#8e8ea0] mt-0.5 whitespace-pre-line">{e.answer}</div>
                  {e.keywords ? (
                    <div className="text-[11px] text-[#8e8ea0] mt-1 font-mono">🔑 {e.keywords}</div>
                  ) : (
                    <div className="text-[11px] text-amber-300/80 mt-1">🔑 koi keywords nahi — question ke shabdon se match hoga (keywords dena behtar hai)</div>
                  )}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#2f2f2f] text-[#8e8ea0]">P{e.priority}</span>
                  <button onClick={() => startEdit(e)} title="Edit" className="p-1.5 text-[#8e8ea0] hover:text-[#ececec] rounded-lg bg-[#2f2f2f]">
                    <Pencil className="w-3.5 h-3.5" />
                  </button>
                  <button
                    onClick={() => toggleActive(e)}
                    title={e.is_active ? 'Active — click to disable' : 'Disabled — click to enable'}
                    className={`p-1.5 rounded-lg ${e.is_active ? 'text-emerald-300 bg-emerald-950/40' : 'text-[#8e8ea0] bg-[#2f2f2f]'}`}
                  >
                    <Power className="w-3.5 h-3.5" />
                  </button>
                  <button onClick={() => removeEntry(e.id)} className="p-1.5 text-[#8e8ea0] hover:text-rose-400">
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
