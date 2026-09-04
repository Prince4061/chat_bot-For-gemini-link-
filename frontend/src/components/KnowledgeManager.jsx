import React, { useState, useEffect } from 'react';
import { GraduationCap, Plus, Trash2, Save, Check, FlaskConical, Power } from 'lucide-react';
import { adminApi } from '../api/client';

export default function KnowledgeManager() {
  const [instructions, setInstructions] = useState('');
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [savingInstr, setSavingInstr] = useState(false);
  const [instrSaved, setInstrSaved] = useState(false);

  // New entry form
  const [form, setForm] = useState({ question: '', answer: '', keywords: '', priority: 0 });
  const [adding, setAdding] = useState(false);

  // Test box
  const [testQ, setTestQ] = useState('');
  const [testResult, setTestResult] = useState(null);

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

  const addEntry = async (e) => {
    e.preventDefault();
    if (!form.question.trim() || !form.answer.trim()) return;
    try {
      setAdding(true);
      await adminApi.createKnowledge(form);
      setForm({ question: '', answer: '', keywords: '', priority: 0 });
      load();
    } catch (err) {
      alert('Error: ' + err.message);
    } finally {
      setAdding(false);
    }
  };

  const toggleActive = async (entry) => {
    await adminApi.updateKnowledge(entry.id, { is_active: !entry.is_active });
    load();
  };

  const removeEntry = async (id) => {
    if (!confirm('Is trained answer ko delete karein?')) return;
    await adminApi.deleteKnowledge(id);
    load();
  };

  const runTest = async () => {
    if (!testQ.trim()) return;
    try {
      const res = await adminApi.testKnowledge(testQ);
      setTestResult(res);
    } catch (err) {
      setTestResult({ matched: false, error: err.message });
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-bold text-[#ececec] flex items-center gap-2">
          <GraduationCap className="w-5 h-5" />
          AI Training
        </h2>
        <p className="text-xs text-[#8e8ea0]">
          Bot ko sikhao ki kis tarah ke sawaal par kya reply de. Ye LLM aur fallback dono me lagta hai.
        </p>
      </div>

      {/* Custom instructions */}
      <div className="glass-panel rounded-2xl p-5 border border-white/10 space-y-3">
        <h3 className="text-sm font-bold text-[#ececec]">Custom Instructions (persona / rules / tone)</h3>
        <textarea
          rows={5}
          value={instructions}
          onChange={(e) => setInstructions(e.target.value)}
          placeholder={"e.g. Hamesha politely reply karo. Refund 24 ghante me milta hai. Sirf UPI accept karte hain. Delivery instant hoti hai."}
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

      {/* Add FAQ */}
      <div className="glass-panel rounded-2xl p-5 border border-white/10">
        <h3 className="text-sm font-bold text-[#ececec] mb-3">Add a trained Q&amp;A</h3>
        <form onSubmit={addEntry} className="space-y-3 text-xs">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-[#8e8ea0] mb-1">Example question / topic *</label>
              <input
                value={form.question}
                onChange={(e) => setForm({ ...form, question: e.target.value })}
                placeholder="e.g. Delivery kitni der me hoti hai?"
                className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] focus:outline-none focus:border-white/20"
              />
            </div>
            <div>
              <label className="block text-[#8e8ea0] mb-1">Trigger keywords (comma separated)</label>
              <input
                value={form.keywords}
                onChange={(e) => setForm({ ...form, keywords: e.target.value })}
                placeholder="delivery, kitni der, time, kab milega"
                className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] font-mono focus:outline-none focus:border-white/20"
              />
            </div>
          </div>
          <div>
            <label className="block text-[#8e8ea0] mb-1">Bot ka reply (answer) *</label>
            <textarea
              rows={3}
              value={form.answer}
              onChange={(e) => setForm({ ...form, answer: e.target.value })}
              placeholder="Payment confirm hote hi link turant milta hai — 1 minute ke andar."
              className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] focus:outline-none focus:border-white/20"
            />
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
              <span className="text-[10px] text-[#8e8ea0]">(zyada = pehle match)</span>
            </div>
            <button
              type="submit"
              disabled={adding || !form.question.trim() || !form.answer.trim()}
              className="px-4 py-2 bg-white hover:bg-white/90 text-black font-bold rounded-xl flex items-center gap-1.5 disabled:opacity-50"
            >
              <Plus className="w-4 h-4" />
              Add
            </button>
          </div>
        </form>
      </div>

      {/* Test box */}
      <div className="glass-panel rounded-2xl p-4 border border-white/10">
        <h3 className="text-sm font-bold text-[#ececec] mb-2 flex items-center gap-2">
          <FlaskConical className="w-4 h-4" /> Test — kaunsa answer match hota hai?
        </h3>
        <div className="flex items-center gap-2 text-xs">
          <input
            value={testQ}
            onChange={(e) => setTestQ(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && runTest()}
            placeholder="ek sawaal type karo..."
            className="flex-1 p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] focus:outline-none focus:border-white/20"
          />
          <button onClick={runTest} className="px-3 py-2 bg-[#3a3a3a] hover:bg-[#4a4a4a] text-[#d4d4d4] rounded-xl">Test</button>
        </div>
        {testResult && (
          <div className={`mt-2 text-xs ${testResult.matched ? 'text-emerald-300' : 'text-[#8e8ea0]'}`}>
            {testResult.matched
              ? <>✅ Match: <span className="text-[#ececec]">{testResult.entry.question}</span> → “{testResult.entry.answer}”</>
              : '— Koi trained answer match nahi hua (bot normal reply karega).'}
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
              <div key={e.id} className="p-4 flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-sm text-[#ececec] font-medium">{e.question}</div>
                  <div className="text-xs text-[#8e8ea0] mt-0.5">{e.answer}</div>
                  {e.keywords && (
                    <div className="text-[11px] text-[#8e8ea0] mt-1 font-mono">🔑 {e.keywords}</div>
                  )}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#2f2f2f] text-[#8e8ea0]">P{e.priority}</span>
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
